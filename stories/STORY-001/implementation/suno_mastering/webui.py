"""Local-only web UI for customising MasteringConfig and running a master.

Auto-generates an HTML form from the MasteringConfig dataclass tree (via
introspection, so it stays in sync with config.py automatically), runs the
pipeline in a background thread, and streams progress to the browser via
polling. Binds to 127.0.0.1 only -- this is a single-user local tool, not a
service meant to be exposed on a network.

    python -m suno_mastering.webui
"""
from __future__ import annotations

import dataclasses
import json
import os
import threading
import types
import typing
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from .analysis import measure_all
from .analysis.artifact_detection import CONFIDENCE_THRESHOLD_TO_WARN
from .config import MasteringConfig
from .errors import MasteringError
from ._paths import user_data_dir
from .io.ingest import ingest as ingest_audio
from .pipeline import master
from .report.render import render_json, render_markdown

HOST = "127.0.0.1"
PORT = 8765

# Repo root's .env in a normal checkout (shared with master_track.bat);
# %LOCALAPPDATA%\SunoMastering\.env when frozen, since the install location
# may not be writable. See _paths.py.
_ENV_PATH = user_data_dir() / ".env"
_HF_TOKEN_URL = "https://huggingface.co/settings/tokens"

# Fields whose values are constrained to a fixed set, keyed by "section.field"
# (or bare "field" for top-level MasteringConfig fields). Not derivable from
# the dataclass type alone -- StemConfig.__post_init__ enforces this set.
_SELECT_OPTIONS: dict[str, list[str]] = {
    "stem_config.model_name": ["htdemucs", "htdemucs_ft", "mdx_extra", "htdemucs_6s"],
}

# (min, max, step) for fields rendered as a slider + linked number box instead
# of a bare text input. Only fields _FIELD_HELP frames as "Higher/Lower ->"
# tunable-by-ear controls belong here -- fixed spec constants (BS.1770 gates,
# oversample factor, sample rates, dither seed, solver iteration/tolerance
# knobs the help text itself says to leave alone, etc.) are deliberately
# left as plain text inputs in the Advanced section, so nothing invites
# fiddling with a value that isn't meant to be tuned by ear.
_SLIDER_RANGES: dict[str, tuple[float, float, float]] = {
    # --- Loudness & true peak ---
    "lufs_target_low": (-20.0, -8.0, 0.1),
    "lufs_ceiling": (-18.0, -6.0, 0.1),
    "lufs_floor": (-20.0, -10.0, 0.1),
    "true_peak_ceiling_dbtp": (-3.0, -0.1, 0.1),
    # --- Dynamic range ---
    "dr_floor": (4.0, 14.0, 0.5),
    "dr_max_reduction_db": (0.0, 10.0, 0.5),
    # --- Frequency balance ---
    "thin_low_end_threshold_db": (1.0, 10.0, 0.5),
    "muddiness_threshold_db": (1.0, 8.0, 0.5),
    "harshness_threshold_db": (1.0, 8.0, 0.5),
    "eq_max_gain_db": (0.5, 6.0, 0.5),
    # --- Stereo ---
    "phase_correlation_widened_target": (0.0, 1.0, 0.05),
    "stereo_side_mid_ratio_threshold": (0.1, 1.5, 0.05),
    "stereo_debounce_windows": (1, 10, 1),
    "stereo_crossfade_ms": (5.0, 200.0, 5.0),
    # --- Solver / limiter ---
    "limiter_lookahead_ms": (1.0, 20.0, 0.5),
    "limiter_release_ms": (10.0, 300.0, 5.0),
    # --- Stem separation ---
    "stem_config.shifts": (1, 5, 1),
    "stem_config.overlap": (0.0, 0.9, 0.05),
    "stem_config.bass_mono_cutoff_hz": (40.0, 200.0, 5.0),
    "stem_config.vocal_lpf_hz": (8000.0, 18000.0, 500.0),
    "stem_config.vocal_hpf_hz": (20.0, 200.0, 5.0),
    # --- Adaptive harshness ---
    "adaptive_harshness.broad_threshold_db": (0.5, 8.0, 0.5),
    "adaptive_harshness.narrow_threshold_db": (0.5, 8.0, 0.5),
    "adaptive_harshness.broad_gain_db": (-6.0, 0.0, 0.5),
    "adaptive_harshness.narrow_gain_db": (-6.0, 0.0, 0.5),
    "adaptive_harshness.max_gain_db": (0.0, 10.0, 0.5),
    # --- Whistle repair (experimental) ---
    "repair_whistles.confidence_threshold": (0.0, 1.0, 0.05),
    "repair_whistles.prominence_floor_db": (0.0, 20.0, 0.5),
    "repair_whistles.crossfade_ms": (5.0, 200.0, 5.0),
    # --- Transient shaping (experimental) ---
    "shape_transients.attack_boost_db": (0.0, 10.0, 0.5),
    "shape_transients.sustain_cut_db": (-10.0, 0.0, 0.5),
    # --- Swish collapse (experimental) ---
    "collapse_swish.cutoff_freq_hz": (500.0, 10000.0, 100.0),
}

# Section title + one-line description shown above each nested-dataclass
# fieldset, purely cosmetic.
_SECTION_INFO: dict[str, tuple[str, str]] = {
    "stem_config": ("Stem separation", "AI stem split (Demucs) pre-processing."),
    "adaptive_harshness": ("Adaptive harshness correction", "Automatic 2-5 kHz correction."),
    "repair_whistles": ("Whistle repair (experimental)", "Requires the suno_dsp C++ extension."),
    "shape_transients": ("Transient shaping (experimental)", "Requires the suno_dsp C++ extension."),
    "collapse_swish": ("Swish collapse (experimental)", "Requires the suno_dsp C++ extension."),
}

# Top-level scalar fields grouped into named, always-open sections; anything
# not listed here falls into the collapsed "Advanced" section automatically,
# so a new config.py field is never silently dropped from the form.
_TOP_LEVEL_GROUPS: list[tuple[str, list[str]]] = [
    ("Loudness & true peak", [
        "lufs_target_low", "lufs_ceiling", "lufs_floor",
        "true_peak_ceiling_dbtp",
    ]),
    ("Dynamic range", [
        "dr_floor", "dr_max_reduction_db",
    ]),
    ("Frequency balance", [
        "thin_low_end_threshold_db", "muddiness_threshold_db",
        "harshness_threshold_db", "eq_max_gain_db",
    ]),
]

# Tooltip text shown behind an (i) icon next to every field label. Keyed by
# the same "field" / "section.field" name used for the form input, so it
# stays attached to the right widget regardless of which group it's rendered
# in. Fields with no entry render without a tooltip icon rather than raising
# -- writing one for every field in config.py is intentional (STORY: guided
# settings UI) but shouldn't be a hard requirement for a field to appear.
#
# Style: one sentence on what it is, then "Higher/Lower ->" on what moving
# it does, then a typical/safe value where one exists. Fields that are fixed
# spec constants (BS.1770 gates, standard sample rates) skip the
# higher/lower framing since they're not meant to be tuned by ear.
_FIELD_HELP: dict[str, str] = {
    # --- Loudness ---
    "lufs_target_low": "The quiet edge of the loudness band the solver aims for (LUFS integrated, BS.1770-4). Higher = louder, less headroom before the true-peak ceiling. Lower = quieter, more headroom. -14.5 matches Spotify/YouTube's own normalization target, so a track landing here won't get turned down on playback.",
    "lufs_ceiling": "The loudest the solver will ever push the master, no matter what. Higher = louder master, more risk of sounding squashed. Lower = safer but quieter. -13.5 leaves the DR floor below reachable; going much above -12 usually means fighting the DR floor.",
    "lufs_floor": "The quietest the solver is allowed to land at when the true-peak ceiling or DR floor force it to back off. Lower = the solver has more room to back off before giving up and erroring. Rarely needs changing -- it's a safety backstop, not a target.",
    "bs1770_absolute_gate_lufs": "Fixed spec constant (BS.1770-4): blocks quieter than this are excluded from the loudness measurement outright, so long silences don't drag the reading down. -70 LUFS is the spec value -- leave as is.",
    "bs1770_relative_gate_lu": "Fixed spec constant (BS.1770-4): after the absolute gate, blocks more than this many LU below the running average are also excluded. -10 LU is the spec value -- leave as is.",
    # --- True peak ---
    "true_peak_ceiling_dbtp": "The hardest limit in the whole pipeline: the loudest any true (inter-sample) peak in the output is allowed to be. Higher (closer to 0) = louder potential master but more risk of clipping on lossy re-encodes (MP3/AAC). -1.0 dBTP is the standard streaming-safe ceiling; don't go above -1.0 for anything meant for streaming platforms.",
    "true_peak_oversample_factor": "How finely the true-peak detector interpolates between samples to catch peaks a plain sample-peak reading would miss. Higher = more accurate peak detection, slower to compute. 8x is already generous (spec floor is 4x) -- no reason to raise it.",
    "true_peak_monotonicity_tolerance_db": "Internal test tolerance only -- used by the test suite to check the true-peak measurement agrees with itself across oversampling factors. Never relaxes the actual true-peak ceiling. Leave alone.",
    # --- Dynamic range ---
    "dr_floor": "The least dynamic (most squashed) the master is allowed to become, on the TT DR-meter scale. Higher = preserves more punch/dynamics but the solver may not be able to hit the loudness target and can error out (\"Cannot satisfy DR floor\"). Lower = the solver has more freedom to squash the track for loudness. DR8 is a reasonable floor for dense electronic material; DR10+ preserves noticeably more punch.",
    "dr_max_reduction_db": "A second, independent brake on top of the floor above: caps how many dB of DR the solver can remove versus what the source already had, even if the floor would allow more. Higher = allows more squashing of an already-dynamic source. Lower = preserves more of the source's original dynamics regardless of the target.",
    "dr_block_seconds": "Block length the DR measurement itself is computed over (TT DR-meter method). Standard value (3s), rarely changed -- changing it changes what DR number gets reported, not what the track sounds like.",
    "dr_exclude_fraction": "Fraction of the loudest blocks excluded before computing DR (TT DR-meter method excludes the top 20% so a few hot moments don't dominate the reading). Standard value, rarely changed.",
    # --- Frequency balance ---
    "freq_low_band_hz": "Frequency range (Hz) treated as the 'low end' band for the thin-low-end check. Matches the sub/bass region for this genre -- only change if you're adapting the tool to a different genre curve.",
    "freq_mud_band_hz": "Frequency range (Hz) treated as the 'mud' band for the muddiness check -- the low-mid region where excess energy reads as boxy/muddy.",
    "freq_presence_band_hz": "Frequency range (Hz) treated as the 'presence/harsh' band -- where excess energy reads as harsh/fatiguing, and what adaptive harshness correction targets.",
    "freq_reference_band_hz": "The 500 Hz-2 kHz band used as the 0 dB baseline every other band's deviation is measured against.",
    "thin_low_end_threshold_db": "How far below the genre reference (dB) the low band has to fall before it's flagged thin. Lower threshold = flags smaller deviations (more sensitive, more false positives). Higher = only flags obviously thin tracks. 4 dB is a moderate bar.",
    "muddiness_threshold_db": "How far above the genre reference (dB) the mud band has to rise before it's flagged muddy. Lower = more sensitive. Higher = only flags obviously muddy tracks.",
    "harshness_threshold_db": "How far above the genre reference (dB) the presence band has to rise before it's flagged harsh -- this is also the trigger diagnose uses to suggest turning on adaptive harshness correction. Lower = triggers correction more readily. Higher = only corrects clearly harsh tracks.",
    "reference_curve_path": "Path to the genre reference curve JSON (the target spectral shape for melodic prog house/techno at 124bpm) that every frequency-balance deviation above is measured against. Only change this if you're targeting a different genre.",
    "silence_gate_threshold_db": "Level (dBFS) below which audio is treated as silence and excluded from the frequency-balance analysis, so quiet intros/outros don't skew the reading.",
    "silence_block_ms": "Block size (ms) used by the silence gate above.",
    "eq_max_gain_db": "Hard ceiling on how much gain (dB) the automatic genre-curve EQ can apply to any one band, win or lose. Higher = EQ can correct larger deviations in one pass but risks sounding more processed. Lower = gentler, more conservative correction, deviations may not fully close.",
    # --- Stereo ---
    "phase_correlation_floor": "The minimum whole-track stereo correlation still considered mono-compatible. Below this, the track is flagged as having phase/mono issues (bass and other content may partially cancel when summed to mono, e.g. on a phone speaker or club system). 0.0 is the standard floor (fully decorrelated = 0, out-of-phase = negative).",
    "phase_correlation_widened_target": "When a stereo-widened region is corrected/narrowed, this is the correlation the correction aims to land at. Higher (closer to 1) = narrower, safer result. Lower = leaves more width but less mono-safety margin.",
    "stereo_window_ms": "Window length (ms) the stereo correlation/width measurement slides across the track in.",
    "stereo_hop_ms": "Hop size (ms) between consecutive stereo-analysis windows (0 overlap by design, so hop == window).",
    "stereo_side_mid_ratio_threshold": "Side-to-mid energy ratio above which a region is considered over-widened. Lower = flags moderate width as a problem too (more sensitive). Higher = only flags very wide regions.",
    "stereo_debounce_windows": "How many consecutive flagged windows are required before a stereo-widened region is actually corrected -- avoids reacting to one stray window. Higher = more conservative, may miss short-lived width issues.",
    "stereo_crossfade_ms": "Crossfade length (ms) used when a stereo correction fades in/out, so the transition isn't an audible seam.",
    # --- Clipping ---
    "clip_sample_threshold": "Sample amplitude (0-1 scale) at or above which a sample counts as clipped. 0.999 is effectively full-scale, catching true digital clipping without flagging normal hot peaks.",
    "clip_minor_fraction": "Below this fraction of samples clipped, severity reads as 'minor'. Purely a reporting threshold -- doesn't change what the pipeline does, only how it's labelled.",
    "clip_moderate_fraction": "Below this fraction, severity reads as 'moderate'; at or above it, 'severe'. Reporting threshold only.",
    # --- Output ---
    "output_bit_depth": "Bit depth of the exported WAV. 24-bit is the standard mastering delivery depth -- more than enough headroom for dither, no reason to go lower.",
    "supported_sample_rates": "Sample rates this tool will accept as input. 44100 and 48000 Hz cover essentially everything Suno and streaming platforms use.",
    "default_sample_rate": "Sample rate used if the input's own rate somehow can't be honoured.",
    # --- Dither ---
    "dither_seed": "Fixed random seed for the dither noise added on export. Keeping it fixed means re-running the exact same input/config always produces a byte-identical output -- useful for verifying nothing else changed.",
    # --- Targets ---
    "targets_json_path": "Path to targets.json, the file the solver's DR floor / de-mud caps / other derived targets come from. Required -- the pipeline refuses to run at all if this file is missing.",
    # --- Solver ---
    "solver_max_iterations": "Cap on how many bisection steps the loudness/true-peak/DR solver takes before giving up and reporting it couldn't converge. Higher = more attempts at a precise result, marginally slower. Rarely needs raising -- 32 already converges almost every real track.",
    "solver_lufs_tolerance": "How close (LU) the solver has to land to the loudness target before it calls the search converged. Lower = more precise loudness matching, may need more iterations. Higher = looser matching, converges faster.",
    "limiter_lookahead_ms": "How far ahead (ms) the true-peak limiter looks to catch an upcoming peak before it happens. Higher = catches peaks more reliably but reacts slightly later. Lower = tighter, more transparent, slightly more risk of missing a very fast peak.",
    "limiter_release_ms": "How long (ms) the limiter takes to let go after catching a peak. Higher = smoother, less audible pumping, slower to recover level. Lower = snappier recovery, more risk of audible pumping on dense material.",
    "tool_version": "Version tag written into the report for traceability. Doesn't change processing.",
    # --- Stem separation (StemConfig) ---
    "stem_config.enabled": "Turns on AI stem separation (Demucs) before mastering: splits the track into vocals/drums/bass/other, applies targeted per-stem cleanup (mono-summed sub-bass, de-sizzled vocals), then re-sums. Slower (needs torch/demucs, can take minutes on CPU) and won't help every track -- some material comes out worse. If diagnose flags a mono-compatibility issue, this is the fix; otherwise try it and compare, and turn it off if it introduces artifacts.",
    "stem_config.model_name": "Which Demucs model performs the split. htdemucs is the standard 4-stem model and the documented default -- fastest and lightest. htdemucs_ft (fine-tuned) runs an ensemble of 4 sub-models for slightly better separation at roughly 4x the time/memory -- can be heavy enough to strain a machine with 16 GB RAM or less. htdemucs_6s adds piano/guitar stems.",
    "stem_config.shifts": "Number of equivariant-shift passes Demucs runs and averages together. Higher = marginally better separation quality, proportionally slower (shifts=2 roughly doubles separation time). 1 is the default and usually sufficient.",
    "stem_config.overlap": "Overlap fraction between Demucs analysis chunks (0.0-1.0). Higher = fewer audible chunk-boundary artifacts, slower. 0.25 is a reasonable default; rarely worth pushing much higher.",
    "stem_config.segment_seconds": "Optional fixed chunk length (seconds) Demucs processes at a time, mainly to cap memory use on long tracks. Leave blank to use the model's own default chunking.",
    "stem_config.profile_version": "Label recorded in the report identifying this separation profile. Purely for traceability -- required to be non-empty whenever shifts/overlap/segment_seconds are changed from default, so a changed profile is always distinguishable in reports.",
    "stem_config.allow_device_fallback": "If a GPU/accelerator run fails, allow one automatic retry on CPU instead of failing the whole run. Leave on unless you specifically want a GPU failure to stop the run immediately.",
    "stem_config.stem_cache_dir": "Folder where separated stems are cached, keyed by audio hash + model + profile, so re-running the same file with the same settings skips Demucs entirely. Leave blank to force a fresh separation every time (e.g. while comparing models).",
    "stem_config.bass_mono_cutoff_hz": "Frequency below which the bass stem is summed to mono. Higher = more of the low end forced mono (safer on club systems, less perceived width). Lower = less forced mono, more low-end width preserved. 90 Hz is a common mastering convention for sub-bass mono-compatibility.",
    "stem_config.vocal_lpf_hz": "Low-pass filter applied to the vocal stem, to tame AI-generated high-frequency sizzle. Lower = more aggressive de-sizzling but risks dulling the vocal. Higher = more transparent but leaves more sizzle.",
    "stem_config.vocal_hpf_hz": "High-pass filter applied to the vocal stem to remove sub-audible rumble/DC offset. Higher = removes more low-end mud from the vocal but risks thinning it. 80 Hz is conservative.",
    # --- Adaptive harshness ---
    "adaptive_harshness.enabled": "Automatically tames the 2-5 kHz presence band when it measures too hot against the genre reference (broad shelf for a moderate excess, narrower cut for a more severe one). On by default -- this is what diagnose suggests turning on when it flags a harsh reading.",
    "adaptive_harshness.broad_threshold_db": "Deviation (dB) above reference that triggers the gentler broad-shelf correction. Lower = corrects smaller excesses. Higher = only corrects clearly harsh material.",
    "adaptive_harshness.narrow_threshold_db": "Deviation (dB) above reference that triggers the more targeted narrow cut (used when the excess is small and localized rather than broad). Usually set lower than the broad threshold.",
    "adaptive_harshness.broad_gain_db": "Gain (dB, negative = cut) applied by the broad-shelf correction when it fires. More negative = stronger correction, more audible change.",
    "adaptive_harshness.narrow_gain_db": "Gain (dB, negative = cut) applied by the narrow correction when it fires.",
    "adaptive_harshness.max_gain_db": "Hard ceiling on total harshness-correction gain, regardless of how far out of range the measurement is -- a safety cap against over-correcting a severely harsh source.",
    # --- Whistle repair (experimental) ---
    "repair_whistles.enabled": "Notches out a detected stationary whistle (a narrow, sustained tone -- a known Suno artifact). Experimental: requires the suno_dsp C++ extension to be built, and only ever acts on frequencies the detector actually flagged -- it can't introduce a notch anywhere the detector didn't confirm.",
    "repair_whistles.confidence_threshold": "Minimum detector confidence (0-1) required before a detected whistle is treated as real and repaired. Higher = only repairs very confident detections (fewer false fixes, may miss subtler whistles). Lower = repairs more aggressively, more risk of acting on a false positive.",
    "repair_whistles.prominence_floor_db": "Minimum prominence (dB above the surrounding spectrum) a whistle needs before the auto-notch fires. Must be set (non-blank) whenever this stage is enabled. Higher = only notches clearly prominent whistles.",
    "repair_whistles.crossfade_ms": "Crossfade length (ms) around each repair, so the notch doesn't create an audible edit seam.",
    "repair_whistles.detect_stationary_whistles": "Runs the whistle detector at all -- turning this off suppresses whistle flags everywhere (both the diagnose readout and the repair stage), not just the repair.",
    # --- Transient shaping (experimental) ---
    "shape_transients.enabled": "Boosts attacks and cuts sustain on detected transients (drum hits etc), aimed at smeared-transient artifacts. Experimental: requires the suno_dsp C++ extension to be built.",
    "shape_transients.attack_boost_db": "Gain (dB) added to a detected transient's attack. Higher = punchier, more aggressive transient.",
    "shape_transients.sustain_cut_db": "Gain (dB, negative = cut) applied to the sustain following a detected transient. More negative = tighter, snappier decay.",
    # --- Swish collapse (experimental) ---
    "collapse_swish.enabled": "Collapses a detected stereo 'phase swish' artifact (an audible sweeping stereo-phase effect) toward mono. Experimental: requires the suno_dsp C++ extension to be built.",
    "collapse_swish.cutoff_freq_hz": "Frequency below which the swish-collapse filter operates. Higher = affects more of the spectrum. Lower = more surgical, narrower effect.",
}


def _read_env_token() -> str:
    """Current HF_TOKEN, preferring the live process environment (already
    loaded by master_track_ui.bat) and falling back to reading .env directly
    so the form reflects a token saved via /token without a server restart."""
    token = os.environ.get("HF_TOKEN", "")
    if token:
        return token
    if not _ENV_PATH.exists():
        return ""
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip().upper() == "HF_TOKEN":
            return value.strip()
    return ""


def _write_env_token(token: str) -> None:
    """Persist HF_TOKEN to the repo-root .env (creating it if needed,
    preserving every other line untouched) and set it in this process's
    environment so a stem-separation run started right after saving picks it
    up without restarting the server."""
    lines: list[str] = []
    replaced = False
    if _ENV_PATH.exists():
        for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
            key = line.split("=", 1)[0].strip().upper() if "=" in line else ""
            if key == "HF_TOKEN":
                lines.append(f"HF_TOKEN={token}")
                replaced = True
            else:
                lines.append(line)
    if not replaced:
        lines.append(f"HF_TOKEN={token}")
    _ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    os.environ["HF_TOKEN"] = token
    os.environ["HUGGING_FACE_HUB_TOKEN"] = token


def _hints(cls) -> dict:
    return typing.get_type_hints(cls)


def _unwrap_optional(tp):
    """Optional[X] -> (X, True); X -> (X, False). Handles both
    typing.Optional/Union and PEP 604 `X | None` (types.UnionType)."""
    origin = typing.get_origin(tp)
    if origin is typing.Union or origin is types.UnionType:
        args = [a for a in typing.get_args(tp) if a is not type(None)]
        if len(args) == 1:
            return args[0], True
    return tp, False


def _is_tuple_type(tp) -> bool:
    # config.py uses both bare `tuple` and (implicitly, via defaults) plain
    # tuples -- no field currently uses a subscripted tuple[float, float],
    # but handle both forms.
    return tp is tuple or typing.get_origin(tp) is tuple


def _tuple_elem_type(tp):
    args = typing.get_args(tp)
    if not args:
        return float
    first = args[0]
    return float if first is Ellipsis else first


def _fmt_value(value) -> str:
    if isinstance(value, tuple):
        return ", ".join(str(v) for v in value)
    if value is None:
        return ""
    return str(value)


def _coerce(raw: str, tp) -> object:
    tp, optional = _unwrap_optional(tp)
    raw = raw.strip() if isinstance(raw, str) else raw
    if optional and raw == "":
        return None
    if tp is bool:
        return str(raw).strip().lower() in ("true", "1", "on", "yes")
    if _is_tuple_type(tp):
        elem_type = _tuple_elem_type(tp)
        parts = [p.strip() for p in str(raw).split(",") if p.strip() != ""]
        return tuple(elem_type(p) for p in parts)
    if tp is int:
        return int(float(raw))
    if tp is float:
        return float(raw)
    return str(raw)  # str, or unrecognised -- pass through as text


def _widget_html(name: str, tp, value, *, help_text: str | None = None) -> str:
    tp, optional = _unwrap_optional(tp)
    label = name.rsplit(".", 1)[-1].replace("_", " ")
    if help_text is None:
        help_text = _FIELD_HELP.get(name, "")
    desc = f'<p class="field-desc">{help_text}</p>' if help_text else ""

    if name in _SELECT_OPTIONS:
        opts = "".join(
            f'<option value="{o}"{" selected" if o == value else ""}>{o}</option>'
            for o in _SELECT_OPTIONS[name]
        )
        control = f'<select name="{name}">{opts}</select>'
    elif tp is bool:
        checked = "checked" if value else ""
        control = (
            f'<input type="hidden" name="{name}" value="false">'
            f'<input type="checkbox" name="{name}" value="true" {checked}>'
        )
    elif name in _SLIDER_RANGES and tp in (int, float):
        lo, hi, step = _SLIDER_RANGES[name]
        val = value if value is not None else lo
        # The number box carries no `name` of its own -- only the range
        # input submits with the form. The two stay in sync purely via
        # sibling references in oninput, so the markup order here
        # (range, then number, then reset) must not change.
        control = (
            f'<div class="slider-row">'
            f'<input type="range" class="slider" name="{name}" min="{lo}" max="{hi}" '
            f'step="{step}" value="{val}" '
            f'oninput="this.nextElementSibling.value=this.value">'
            f'<input type="number" class="slider-num" min="{lo}" max="{hi}" step="{step}" '
            f'value="{val}" '
            f'oninput="this.previousElementSibling.value=this.value">'
            f'<button type="button" class="reset-btn" title="Reset to default ({val})" '
            f'onclick="const r=this.previousElementSibling.previousElementSibling; '
            f'r.value={val}; r.nextElementSibling.value={val};">&#8635;</button>'
            f'</div>'
        )
    elif tp in (int, float) or _is_tuple_type(tp):
        step = "1" if tp is int else "any"
        step_attr = f'step="{step}"' if tp in (int, float) else ""
        control = (
            f'<input type="text" {step_attr} name="{name}" '
            f'value="{_fmt_value(value)}">'
        )
    else:
        control = f'<input type="text" name="{name}" value="{_fmt_value(value)}">'

    return (
        f'<div class="field"><label for="{name}">{label}</label>'
        f'{control}</div>{desc}'
    )


def _render_fieldset(title: str, description: str, body_html: str, *, collapsed: bool = False) -> str:
    if collapsed:
        return (
            f"<details class='section'><summary>{title}</summary>"
            f"<p class='desc'>{description}</p>{body_html}</details>"
        )
    return (
        f"<fieldset class='section'><legend>{title}</legend>"
        f"<p class='desc'>{description}</p>{body_html}</fieldset>"
    )


def build_form_html(config: MasteringConfig, *, error: str | None = None, hf_token: str = "") -> str:
    hints = _hints(MasteringConfig)
    fields = {f.name: f for f in dataclasses.fields(MasteringConfig)}

    grouped_names: set[str] = set()
    top_sections = []
    for title, names in _TOP_LEVEL_GROUPS:
        body = "".join(
            _widget_html(n, hints[n], getattr(config, n)) for n in names if n in fields
        )
        grouped_names.update(names)
        top_sections.append(_render_fieldset(title, "", body))

    nested_sections = []
    advanced_scalar_body = []
    for f in dataclasses.fields(MasteringConfig):
        tp = hints[f.name]
        if dataclasses.is_dataclass(tp):
            nested = getattr(config, f.name)
            nested_hints = _hints(tp)
            body = "".join(
                _widget_html(f"{f.name}.{nf.name}", nested_hints[nf.name], getattr(nested, nf.name))
                for nf in dataclasses.fields(tp)
            )
            title, desc = _SECTION_INFO.get(f.name, (f.name.replace("_", " "), ""))
            nested_sections.append(_render_fieldset(title, desc, body))
        elif f.name not in grouped_names:
            advanced_scalar_body.append(_widget_html(f.name, tp, getattr(config, f.name)))

    advanced_section = _render_fieldset(
        "Advanced / rarely-tuned constants",
        "Everything else in MasteringConfig: solver, stereo, clipping, output format.",
        "".join(advanced_scalar_body),
        collapsed=True,
    )

    error_html = f'<div class="error">{error}</div>' if error else ""
    token_status_html = (
        f'<span class="token-status token-set">A token is already saved &mdash; leave blank to keep it.</span>'
        if hf_token else
        '<span class="token-status token-unset">No token saved yet.</span>'
    )

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Suno Mastering</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }}
h1 {{ font-size: 1.4rem; }}
fieldset.section, details.section {{ margin-bottom: 1rem; border: 1px solid #ccc; border-radius: 6px; padding: 0.75rem 1rem; }}
legend, summary {{ font-weight: 600; cursor: pointer; }}
.desc {{ color: #666; font-size: 0.85rem; margin: 0.2rem 0 0.6rem; }}
.field {{ display: flex; align-items: center; gap: 0.5rem; margin: 0.35rem 0 0.1rem; }}
.field label {{ flex: 0 0 200px; font-size: 0.9rem; }}
.field input[type=text], .field input[type=password], .field select {{ flex: 1; padding: 0.2rem 0.4rem; }}
.field-desc {{
  margin: 0 0 0.7rem 208px; color: #666; font-size: 0.78rem; line-height: 1.4; max-width: 46rem;
}}
.slider-row {{ display: flex; align-items: center; gap: 0.5rem; flex: 1; }}
.slider-row .slider {{ flex: 1; accent-color: #2a7; }}
.slider-row .slider-num {{ flex: none; width: 5.5rem; padding: 0.2rem 0.35rem; }}
.slider-row .reset-btn {{
  flex: none; border: 1px solid #ccc; background: #fff; border-radius: 4px;
  padding: 0.1rem 0.45rem; font-size: 0.9rem; line-height: 1.4; cursor: pointer; color: #667;
}}
.slider-row .reset-btn:hover {{ background: #eef2f6; border-color: #99a; }}
.run-bar {{ position: sticky; top: 0; background: #fff; padding: 0.75rem 0; border-bottom: 2px solid #333; z-index: 10; }}
.run-bar input[type=text] {{ width: 60%; padding: 0.4rem; }}
button {{ padding: 0.5rem 1.2rem; font-size: 1rem; cursor: pointer; }}
button:disabled {{ opacity: 0.5; cursor: default; }}
.error {{ background: #fde; border: 1px solid #c33; padding: 0.5rem 1rem; border-radius: 4px; margin-bottom: 1rem; }}
.diagnose-bar {{ margin-top: 0.5rem; display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }}
.diagnose-status {{ font-size: 0.85rem; color: #666; margin-left: 0.5rem; }}
.diag {{ display: flex; flex-direction: column; gap: 1rem; background: #f6f8fa; border: 1px solid #ccc; border-radius: 6px; padding: 0.75rem 1rem; margin-top: 0.5rem; }}
.diaggroup {{ }}
.diaggroup h4 {{ font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.04em; color: #777; margin: 0 0 0.35rem; }}
.diagrow {{ display: flex; align-items: baseline; gap: 0.5rem; font-size: 0.85rem; padding: 0.15rem 0; }}
.diagrow .badge {{ flex: none; font-size: 0.68rem; font-weight: 700; padding: 0.05rem 0.4rem; border-radius: 3px; text-transform: uppercase; }}
.diagrow.ok .badge {{ background: #e3f3e9; color: #1a7a1a; }}
.diagrow.flag .badge {{ background: #fdecd2; color: #a05a00; }}
.diagrow.info .badge {{ background: #e8ebef; color: #556; }}
.suggestion {{ background: #fff; border: 1px solid #ddd; border-left: 3px solid #2a7; border-radius: 4px; padding: 0.5rem 0.7rem; margin-bottom: 0.5rem; }}
.suggestion .sugtitle {{ font-weight: 600; font-size: 0.85rem; }}
.diagwhat, .diagwhy {{ display: block; color: #555; margin-top: 0.15rem; font-size: 0.8rem; }}
.diagwhy {{ color: #888; font-style: italic; }}
.diag-applied {{ outline: 2px solid #2a7; outline-offset: 2px; border-radius: 3px; }}
.token-box {{ background: #f6f8fa; border: 1px solid #ccc; border-radius: 6px; padding: 0.75rem 1rem; margin-bottom: 1rem; }}
.token-box .field label {{ flex-basis: 200px; }}
.token-status {{ font-size: 0.8rem; margin-left: 0.5rem; }}
.token-set {{ color: #1a7a1a; }}
.token-unset {{ color: #a60; }}
.token-msg {{ font-size: 0.8rem; margin-left: 0.5rem; }}
.hidden {{ display: none; }}
.progress-wrap {{ margin-top: 0.75rem; }}
.progress-bar {{ background: #e5e5e5; border-radius: 6px; height: 20px; overflow: hidden; }}
.progress-fill {{ background: #2a7; height: 100%; width: 0%; transition: width 0.3s ease; }}
.progress-label {{ font-size: 0.85rem; color: #444; margin-top: 0.3rem; }}
.progress-log {{ background: #111; color: #ddd; padding: 0.75rem; border-radius: 6px; white-space: pre-wrap; font-size: 0.8rem; margin-top: 0.5rem; max-height: 220px; overflow-y: auto; }}
.progress-result {{ margin-top: 0.5rem; }}
.progress-result.ok {{ color: #1a7a1a; }}
.progress-result.err {{ color: #c33; }}
</style></head>
<body>
<h1>Suno Mastering</h1>

<div class="token-box">
  <div class="field">
    <label for="hf_token">Hugging Face access token</label>
    <input type="password" id="hf_token" name="hf_token" placeholder="{'hf_&hellip; (already saved)' if hf_token else 'hf_...'}">
    <button type="button" onclick="saveToken()">Save token</button>
  </div>
  <p class="desc">
    Needed only for stem separation (Demucs downloads its model from Hugging Face on first use).
    Don't have one? <a href="{_HF_TOKEN_URL}" target="_blank" rel="noopener">Create a free token at {_HF_TOKEN_URL}</a>
    (a "Read" token is enough). You only need to save it once &mdash; it's stored in this project's
    <code>.env</code> file and reused for every future run.
    {token_status_html}
    <span class="token-msg" id="tokenMsg"></span>
  </p>
</div>

<form id="masterForm">
  <div class="run-bar">
    {error_html}
    <div class="field">
      <label for="input_path">Input WAV path</label>
      <input type="text" id="input_path" name="input_path" placeholder="C:\\path\\to\\track.wav" required>
      <button type="button" onclick="browse()">Browse&hellip;</button>
    </div>
    <div class="field">
      <label for="output_dir">Output dir (optional)</label>
      <input type="text" id="output_dir" name="output_dir">
    </div>
    <div class="diagnose-bar">
      <button type="button" onclick="diagnose()">Diagnose &amp; suggest settings</button>
      <span class="diagnose-status" id="diagnoseStatus"></span>
      <button type="submit" id="runBtn">Run mastering</button>
    </div>
  </div>
  <div id="diagnosePanel"></div>
  <div id="progressWrap" class="progress-wrap hidden">
    <div class="progress-bar"><div class="progress-fill" id="progressFill"></div></div>
    <div class="progress-label" id="progressLabel"></div>
    <pre class="progress-log" id="progressLog"></pre>
    <div class="progress-result" id="progressResult"></div>
  </div>
  {''.join(top_sections)}
  {''.join(nested_sections)}
  {advanced_section}
</form>
<script>
async function browse() {{
  const res = await fetch('/browse');
  const data = await res.json();
  if (data.path) document.getElementById('input_path').value = data.path;
}}

async function saveToken() {{
  const val = document.getElementById('hf_token').value;
  const msg = document.getElementById('tokenMsg');
  if (!val.trim()) {{ msg.textContent = 'Enter a token first.'; return; }}
  msg.textContent = 'Saving...';
  try {{
    const res = await fetch('/token', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/x-www-form-urlencoded'}},
      body: 'token=' + encodeURIComponent(val.trim())
    }});
    const data = await res.json();
    msg.textContent = data.ok ? 'Saved.' : ('Failed: ' + data.error);
  }} catch (err) {{
    msg.textContent = 'Failed: ' + err;
  }}
}}

async function diagnose() {{
  const path = document.getElementById('input_path').value.trim();
  const statusEl = document.getElementById('diagnoseStatus');
  const panel = document.getElementById('diagnosePanel');
  if (!path) {{ statusEl.textContent = 'Enter or browse to an input file first.'; return; }}
  statusEl.textContent = 'Analysing (this reads the file but does not master it)...';
  panel.innerHTML = '';
  try {{
    const res = await fetch('/diagnose', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/x-www-form-urlencoded'}},
      body: 'input_path=' + encodeURIComponent(path)
    }});
    const data = await res.json();
    if (!data.ok) {{ statusEl.textContent = 'Diagnose failed: ' + data.error; return; }}
    statusEl.textContent = '';
    panel.innerHTML = data.html;
    for (const [field, value] of Object.entries(data.checks || {{}})) {{
      const el = document.querySelector('input[type=checkbox][name="' + field + '"]');
      if (el) {{
        el.checked = !!value;
        el.classList.add('diag-applied');
        const details = el.closest('details.section');
        if (details) details.open = true;
      }}
    }}
  }} catch (err) {{
    statusEl.textContent = 'Diagnose failed: ' + err;
  }}
}}

let polling = false;

async function pollStatus() {{
  const res = await fetch('/status.json');
  const data = await res.json();
  const total = data.total || 6;
  const stage = data.stage || 0;
  const pct = Math.max(0, Math.min(100, Math.round((stage / total) * 100)));
  document.getElementById('progressFill').style.width = pct + '%';
  document.getElementById('progressLabel').textContent = 'Stage ' + stage + ' of ' + total + ' (' + pct + '%)';
  document.getElementById('progressLog').textContent = data.log.join('\\n');
  if (data.done) {{
    polling = false;
    const resultEl = document.getElementById('progressResult');
    document.getElementById('runBtn').disabled = false;
    if (data.error) {{
      resultEl.className = 'progress-result err';
      resultEl.textContent = 'FAILED: ' + data.error;
    }} else {{
      resultEl.className = 'progress-result ok';
      resultEl.textContent = data.summary;
      document.getElementById('progressFill').style.width = '100%';
    }}
    return;
  }}
  if (polling) setTimeout(pollStatus, 1000);
}}

document.getElementById('masterForm').addEventListener('submit', async function(e) {{
  e.preventDefault();
  const runBtn = document.getElementById('runBtn');
  const progressWrap = document.getElementById('progressWrap');
  const resultEl = document.getElementById('progressResult');
  const params = new URLSearchParams(new FormData(this));
  runBtn.disabled = true;
  resultEl.className = 'progress-result';
  resultEl.textContent = '';
  document.getElementById('progressLog').textContent = '';
  document.getElementById('progressFill').style.width = '0%';
  document.getElementById('progressLabel').textContent = 'Starting...';
  progressWrap.classList.remove('hidden');
  try {{
    const res = await fetch('/run', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/x-www-form-urlencoded'}},
      body: params
    }});
    const data = await res.json();
    if (!data.ok) {{
      runBtn.disabled = false;
      resultEl.className = 'progress-result err';
      resultEl.textContent = data.error;
      return;
    }}
    polling = true;
    pollStatus();
  }} catch (err) {{
    runBtn.disabled = false;
    resultEl.className = 'progress-result err';
    resultEl.textContent = String(err);
  }}
}});
</script>
</body></html>"""


class _QueueReporter:
    def __init__(self, job: "_Job") -> None:
        self._job = job

    def emit(self, stage: int, label: str, detail: str | None = None, *, total: int | None = None) -> None:
        suffix = f" - {detail}" if detail else ""
        self._job.append_log(f"[Stage {stage}] {label}{suffix}", stage=stage, total=total)


class _Job:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.log: list[str] = []
        self.stage = 0
        self.total = 6
        self.done = False
        self.error: str | None = None
        self.summary: str = ""

    def append_log(self, line: str, *, stage: int | None = None, total: int | None = None) -> None:
        with self.lock:
            self.log.append(line)
            if stage is not None:
                self.stage = stage
            if total is not None:
                self.total = total

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "log": list(self.log),
                "stage": self.stage,
                "total": self.total,
                "done": self.done,
                "error": self.error,
                "summary": self.summary,
            }

    def finish(self, *, error: str | None = None, summary: str = "") -> None:
        with self.lock:
            self.done = True
            self.error = error
            self.summary = summary


_current_job: _Job | None = None
_job_lock = threading.Lock()
_browse_lock = threading.Lock()


def _run_job(job: _Job, input_path: str, output_dir: str | None, config: MasteringConfig) -> None:
    try:
        reporter = _QueueReporter(job)
        result = master(input_path, output_dir=output_dir, config=config, reporter=reporter)
        output_path = Path(result.output_path)
        report_md_path = output_path.with_name(output_path.stem + "_report.md")
        report_json_path = output_path.with_name(output_path.stem + "_report.json")
        report_md_path.write_text(render_markdown(result.report), encoding="utf-8")
        report_json_path.write_text(render_json(result.report), encoding="utf-8")
        solver = result.report.solver
        summary = (
            f"Output: {result.output_path}\n"
            f"Report: {report_md_path}\n"
            f"Achieved: {solver['achieved_lufs']:.2f} LUFS, "
            f"{solver['achieved_true_peak_dbtp']:.2f} dBTP, "
            f"DR{solver['achieved_dr']:.0f}"
        )
        job.append_log("Done.")
        job.finish(summary=summary)
    except MasteringError as exc:
        job.append_log(f"ERROR: {exc}")
        job.finish(error=str(exc))
    except Exception as exc:  # pragma: no cover - defensive top-level guard
        job.append_log(f"ERROR: {type(exc).__name__}: {exc}")
        job.finish(error=f"{type(exc).__name__}: {exc}")


def _build_config_from_form(form: dict) -> MasteringConfig:
    base = MasteringConfig()
    hints = _hints(MasteringConfig)
    overrides: dict = {}
    for f in dataclasses.fields(MasteringConfig):
        tp = hints[f.name]
        if dataclasses.is_dataclass(tp):
            nested = getattr(base, f.name)
            nested_hints = _hints(tp)
            nested_overrides = {}
            for nf in dataclasses.fields(tp):
                key = f"{f.name}.{nf.name}"
                if key in form:
                    nested_overrides[nf.name] = _coerce(form[key], nested_hints[nf.name])
            if nested_overrides:
                overrides[f.name] = dataclasses.replace(nested, **nested_overrides)
        elif f.name in form:
            overrides[f.name] = _coerce(form[f.name], tp)
    return dataclasses.replace(base, **overrides)


# Maps an ArtifactFlag.artifact_type to the MasteringConfig stage it would be
# fixed by. DIGITAL_HAZE has no corresponding repair stage -- surfaced as a
# reading only. All three mapped stages require the suno_dsp C++ extension.
_ARTIFACT_TO_STAGE = {
    "STATIONARY_WHISTLE": ("repair_whistles.enabled", "Whistle repair"),
    "SMEARED_TRANSIENT": ("shape_transients.enabled", "Transient shaping"),
    "PHASE_SWISH": ("collapse_swish.enabled", "Swish collapse"),
}


def _suno_dsp_available() -> bool:
    """Whether the suno_dsp C++ extension can actually be imported -- checked
    via find_spec rather than a real import, so this stays cheap even though
    it's called on every diagnose request. Gates whether diagnose auto-ticks
    the repair_whistles/shape_transients/collapse_swish suggestions: they're
    real detector findings either way, but only actionable settings when the
    extension is present (a packaged build doesn't bundle it)."""
    import importlib.util

    try:
        return importlib.util.find_spec("suno_dsp") is not None
    except (ImportError, ValueError):
        return False


def _diagnose(input_path: str) -> dict:
    """Run the pipeline's own pre-master measurement (analysis.measure_all,
    the same code Stage [1] uses) against a default MasteringConfig, and turn
    the flagged results into readings + suggested settings. Deliberately does
    not enable stem separation or any suno_dsp stage for this pass -- it only
    needs to be fast and safe to run on every file dropped in.
    """
    cfg = MasteringConfig()
    ingest_result = ingest_audio(input_path, cfg)
    m = measure_all(ingest_result.audio, ingest_result.sample_rate, cfg)

    # Each group is (title, [(status, text)]) -- status in "ok"/"flag"/"info",
    # rendered as a colour-coded badge. Every row explains not just the raw
    # number but what it means against the relevant target/threshold and,
    # where useful, what the pipeline will do about it.
    groups: list[tuple[str, list[tuple[str, str]]]] = []
    extra_readings: list[str] = []  # artifact findings with no dedicated group

    groups.append(("Format", [
        ("info", f"{m.duration_seconds:.1f}s, {m.sample_rate} Hz, {'mono' if m.is_mono else 'stereo'}"),
    ]))

    loud_rows = []
    if m.integrated_lufs > cfg.lufs_ceiling:
        loud_rows.append(("flag", f"Loudness {m.integrated_lufs:.2f} LUFS -- already above the ceiling ({cfg.lufs_ceiling:.1f}); the solver will pull this down."))
    elif m.integrated_lufs < cfg.lufs_target_low:
        loud_rows.append(("info", f"Loudness {m.integrated_lufs:.2f} LUFS -- below the target band ({cfg.lufs_target_low:.1f} to {cfg.lufs_ceiling:.1f}); the solver will raise this."))
    else:
        loud_rows.append(("ok", f"Loudness {m.integrated_lufs:.2f} LUFS -- already within the target band ({cfg.lufs_target_low:.1f} to {cfg.lufs_ceiling:.1f})."))
    if m.true_peak_dbtp > cfg.true_peak_ceiling_dbtp:
        loud_rows.append(("flag", f"True peak {m.true_peak_dbtp:.2f} dBTP -- already above the ceiling ({cfg.true_peak_ceiling_dbtp:.1f}); the limiter will bring this down."))
    else:
        loud_rows.append(("ok", f"True peak {m.true_peak_dbtp:.2f} dBTP -- {cfg.true_peak_ceiling_dbtp - m.true_peak_dbtp:.1f} dB of headroom under the ceiling ({cfg.true_peak_ceiling_dbtp:.1f})."))
    if m.dynamic_range_db < cfg.dr_floor:
        loud_rows.append(("flag", f"Dynamic range DR{m.dynamic_range_db:.0f} -- already below the floor (DR{cfg.dr_floor:.0f}); the solver may not be able to hit the loudness target without a DR-floor error."))
    else:
        loud_rows.append(("ok", f"Dynamic range DR{m.dynamic_range_db:.0f} -- above the floor (DR{cfg.dr_floor:.0f}), room for the solver to work with."))
    groups.append(("Loudness, peak & dynamics", loud_rows))

    fb = m.frequency_balance
    freq_rows = []
    for band, name in ((fb.low_end, "Low end (20-120 Hz)"), (fb.low_mid_mud, "Low-mid/mud (200-500 Hz)"),
                        (fb.presence_harsh, "Presence/harsh (2-5 kHz)")):
        status = "flag" if band.flagged else "ok"
        note = " -- outside the genre reference; the automatic corrective EQ will pull this in." if band.flagged else " -- within the genre reference."
        freq_rows.append((status, f"{name}: {band.deviation_db:+.1f} dB vs. reference{note}"))
    groups.append(("Frequency balance", freq_rows))

    stereo_status = "ok" if m.stereo_phase.mono_compatible else "flag"
    stereo_note = (
        "mono-compatible."
        if m.stereo_phase.mono_compatible
        else "below the mono-compatible floor -- may partially cancel when summed to mono (phone speaker, club system)."
    )
    stereo_rows = [(stereo_status, f"Stereo correlation {m.stereo_phase.overall_correlation:.2f} -- {stereo_note}")]
    clip_status = "flag" if m.clipping.has_clipping else "ok"
    clip_note = f"clipping detected ({m.clipping.severity})." if m.clipping.has_clipping else "no clipping detected."
    stereo_rows.append((clip_status, clip_note[0].upper() + clip_note[1:]))
    groups.append(("Stereo & clipping", stereo_rows))

    suggestions: list[dict] = []
    checks: dict[str, bool] = {}

    if not m.stereo_phase.mono_compatible and not cfg.stem_config.enabled:
        suggestions.append({
            "field": "stem_config.enabled",
            "label": "Stem separation",
            "what": _FIELD_HELP.get("stem_config.enabled", ""),
            "reason": (
                f"Stereo correlation measured {m.stereo_phase.overall_correlation:.2f}, below the "
                f"mono-compatible floor ({cfg.phase_correlation_floor:.1f}). Stem separation's bass "
                "mono-summing (stem_config.bass_mono_cutoff_hz) directly targets this."
            ),
        })
        checks["stem_config.enabled"] = True

    if fb.presence_harsh.flagged and not cfg.adaptive_harshness.enabled:
        suggestions.append({
            "field": "adaptive_harshness.enabled",
            "label": "Adaptive harshness correction",
            "what": _FIELD_HELP.get("adaptive_harshness.enabled", ""),
            "reason": (
                f"Presence/harsh band measured {fb.presence_harsh.deviation_db:+.1f} dB "
                f"vs. reference (threshold {cfg.harshness_threshold_db:.1f} dB)."
            ),
        })
        checks["adaptive_harshness.enabled"] = True

    artifact_result = m.artifact_detection
    dsp_available = _suno_dsp_available()
    if artifact_result is not None:
        best_by_type: dict[str, float] = {}
        for flag in artifact_result.artifact_flags:
            best_by_type[flag.artifact_type] = max(
                best_by_type.get(flag.artifact_type, 0.0), flag.confidence_score
            )
        for atype, confidence in best_by_type.items():
            if confidence < CONFIDENCE_THRESHOLD_TO_WARN:
                continue
            mapping = _ARTIFACT_TO_STAGE.get(atype)
            if mapping is None:
                extra_readings.append(("flag", f"{atype.replace('_', ' ').title()} detected (confidence {confidence:.2f}) -- no automatic fix for this one, listen and edit manually if it's audible."))
                continue
            field_name, label = mapping
            if not dsp_available:
                # A real detector finding, but not an actionable setting on
                # this install -- the suno_dsp extension isn't present, so
                # ticking the box would just fail the run with
                # DependencyError. Surface it as a reading, not a suggestion.
                extra_readings.append((
                    "flag",
                    f"{atype.replace('_', ' ').title()} detected (confidence {confidence:.2f}) -- "
                    f"{label} could fix this, but the suno_dsp C++ extension isn't built on this install."
                ))
                continue
            suggestions.append({
                "field": field_name,
                "label": label,
                "what": _FIELD_HELP.get(field_name, ""),
                "reason": (
                    f"{atype.replace('_', ' ').title()} detected (confidence {confidence:.2f})."
                ),
            })
            checks[field_name] = True

    if extra_readings:
        groups.append(("Detected artifacts", extra_readings))

    html_parts = ["<div class='diag'>"]
    for title, rows in groups:
        html_parts.append(f"<div class='diaggroup'><h4>{title}</h4>")
        for status, text in rows:
            html_parts.append(f"<div class='diagrow {status}'><span class='badge'>{status}</span><span>{text}</span></div>")
        html_parts.append("</div>")
    if suggestions:
        html_parts.append("<div class='diaggroup'><h4>Suggested settings (pre-filled below)</h4>")
        for s in suggestions:
            html_parts.append(
                "<div class='suggestion'>"
                f"<div class='sugtitle'>{s['label']} &rarr; on</div>"
                f"<span class='diagwhat'>{s['what']}</span>"
                f"<span class='diagwhy'>Why: {s['reason']}</span>"
                "</div>"
            )
        html_parts.append("</div>")
    else:
        html_parts.append("<div class='diaggroup'><h4>Suggested settings</h4><p>Nothing flagged above the confidence/threshold bar; defaults look fine.</p></div>")
    html_parts.append("</div>")

    return {"ok": True, "html": "".join(html_parts), "checks": checks}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quieter stdout
        pass

    def _send_html(self, body: str, status: int = 200) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_json(self, obj: dict) -> None:
        encoded = json.dumps(obj).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802 - stdlib method name
        if self.path in ("/", ""):
            self._send_html(build_form_html(MasteringConfig(), hf_token=_read_env_token()))
        elif self.path == "/status.json":
            job = _current_job
            self._send_json(
                job.snapshot() if job
                else {"log": [], "stage": 0, "total": 6, "done": True, "error": None, "summary": ""}
            )
        elif self.path == "/browse":
            self._send_json({"path": _pick_file()})
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:  # noqa: N802 - stdlib method name
        global _current_job
        if self.path == "/diagnose":
            self._handle_diagnose()
            return
        if self.path == "/token":
            self._handle_save_token()
            return
        if self.path != "/run":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8")
        parsed = parse_qs(raw, keep_blank_values=True)
        form = {k: v[-1] for k, v in parsed.items()}

        input_path = form.get("input_path", "").strip()
        output_dir = form.get("output_dir", "").strip() or None

        if not input_path or not Path(input_path).exists():
            self._send_json({"ok": False, "error": f"Input file does not exist: {input_path}"})
            return

        try:
            config = _build_config_from_form(form)
        except (ValueError, TypeError) as exc:
            self._send_json({"ok": False, "error": f"Invalid setting: {exc}"})
            return

        with _job_lock:
            if _current_job is not None and not _current_job.done:
                self._send_json({"ok": False, "error": "A mastering run is already in progress."})
                return
            job = _Job()
            _current_job = job

        thread = threading.Thread(target=_run_job, args=(job, input_path, output_dir, config), daemon=True)
        thread.start()

        self._send_json({"ok": True})

    def _handle_diagnose(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8")
        parsed = parse_qs(raw, keep_blank_values=True)
        input_path = parsed.get("input_path", [""])[-1].strip()

        if not input_path or not Path(input_path).exists():
            self._send_json({"ok": False, "error": f"Input file does not exist: {input_path}"})
            return
        try:
            self._send_json(_diagnose(input_path))
        except MasteringError as exc:
            self._send_json({"ok": False, "error": str(exc)})
        except Exception as exc:  # pragma: no cover - defensive top-level guard
            self._send_json({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    def _handle_save_token(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8")
        parsed = parse_qs(raw, keep_blank_values=True)
        token = parsed.get("token", [""])[-1].strip()

        if not token:
            self._send_json({"ok": False, "error": "Token was empty."})
            return
        try:
            _write_env_token(token)
        except OSError as exc:
            self._send_json({"ok": False, "error": f"Could not write .env: {exc}"})
            return
        self._send_json({"ok": True})


def _pick_file() -> str:
    with _browse_lock:
        try:
            import tkinter
            from tkinter import filedialog

            root = tkinter.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            path = filedialog.askopenfilename(
                title="Select a WAV file",
                filetypes=[("WAV files", "*.wav"), ("All files", "*.*")],
            )
            root.destroy()
            return path or ""
        except Exception:
            return ""


def run(host: str = HOST, port: int = PORT, *, open_browser: bool = True) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}/"
    print(f"Suno Mastering UI running at {url} (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
