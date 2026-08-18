from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict

import numpy as np
from scipy.signal import hilbert

# Clamp ceiling below digital full scale. Derivation recorded in
# stories/STORY-011/architecture.md ("Clamp ceiling 0.98"); do not tune
# without an architecture re-derivation (H4/H6).
CLAMP_CEILING = 0.98

# Onset window / taper durations from the architecture's headroom-management
# and gain-envelope contracts.
ONSET_WINDOW_S = 0.08
TAPER_S = 0.005
MIN_ONSET_WINDOW_SAMPLES = 32
MIN_TAPER_SAMPLES = 16


@dataclass
class TransientRestorationAction:
    stem_name: str
    action_type: str  # "attack_boost" | "attack_boost_headroom_clamped" | "skipped_headroom"
    gain_db: float  # APPLIED gain; 0.0 when skipped
    requested_gain_db: float  # pre-clamp gain from the severity mapping
    onset_peak_before: float  # sample peak of the onset window before gain
    onset_peak_after: float  # MEASURED onset-window peak after applied gain
    global_peak_before: float  # sample peak over the entire stem before processing
    reason: str
    severity: float


def _coerce_stems(audio: np.ndarray) -> np.ndarray:
    arr = np.asarray(audio, dtype=np.float64)
    if arr.ndim in (1, 2):
        return arr
    raise ValueError(f"Unsupported stem shape {arr.shape}; expected 1D or 2D audio")


def _input_legality_guard(stem_name: str, audio: np.ndarray) -> None:
    peak = float(np.abs(audio).max()) if audio.size else 0.0
    if peak > 1.0:
        raise ValueError(
            f"Transient restoration illegal input: stem '{stem_name}' sample peak "
            f"{peak:.4f} exceeds 1.0"
        )


def _clip_guard(stem_name: str, audio: np.ndarray) -> None:
    peak = float(np.abs(audio).max()) if audio.size else 0.0
    if peak > 1.0:
        raise ValueError(
            f"Transient restoration produced out-of-range audio: stem '{stem_name}' "
            f"peak {peak:.4f} exceeds 1.0"
        )


def _onset_window_length(n_samples: int, sample_rate: int) -> int:
    # n_samples is the length of the SAMPLE axis (arr.shape[0]), never arr.size.
    return min(n_samples, max(MIN_ONSET_WINDOW_SAMPLES, int(ONSET_WINDOW_S * sample_rate)))


def _local_attack_ratio(audio: np.ndarray, sample_rate: int) -> float:
    if audio.size == 0:
        return 0.0

    # DEF-011-02: transform along the sample axis for both (samples,) and
    # (samples, channels); a 2-point transform across the channel axis is
    # meaningless and launders garbage into the attack statistics.
    env = np.abs(hilbert(audio.astype(np.float64), axis=0))
    if env.ndim == 2:
        env = env.max(axis=1)  # peak envelope across channels per sample
    if env.size < 4:
        return 0.0

    attack_window = max(64, int(0.08 * sample_rate))
    analysis_window = min(env.size, max(attack_window, int(0.25 * sample_rate)))
    onset = env[:analysis_window]
    if onset.size < 4:
        return 0.0

    baseline_window = max(8, analysis_window // 10)
    baseline = np.median(onset[:baseline_window])
    # DEF-011-03: skip a short lead-in before taking the peak so the FFT
    # wrap-boundary spike at n=0 cannot inflate the ratio on non-integer-cycle
    # steady content (e.g. synth pads). The spike decays within ~1 ms.
    leadin = max(4, int(0.001 * sample_rate))
    peak = np.max(onset[leadin:]) if onset.size > leadin else np.max(onset)
    if baseline <= 0.0:
        return 0.0
    return float(peak / baseline)


def _stem_threshold(stem_name: str) -> float:
    lower = {
        "drums": 2.4,
        "bass": 2.1,
        "vocals": 1.9,
        "synth": 1.8,
        "other": 1.7,
    }
    return lower.get(stem_name.lower(), 1.8)


def _gain_for_stem(stem_name: str, ratio: float) -> float:
    threshold = _stem_threshold(stem_name)
    if ratio <= threshold:
        return 0.0
    return min(3.5, max(0.4, (ratio - threshold) * 1.6))


def _action_label(stem_name: str) -> str:
    stem_label = stem_name.lower()
    if "bass" in stem_label:
        return "bass transient punch restoration"
    if "drum" in stem_label:
        return "drum attack restoration"
    if "vocal" in stem_label:
        return "vocal articulation restoration"
    if "synth" in stem_label:
        return "synth transient preservation"
    return "transient attack restoration"


def _reason_for_stem(stem_name: str, gain_db: float) -> str:
    return f"{_action_label(stem_name)}: gain {gain_db:.2f} dB on local onset energy"


def _headroom_clamp(onset_peak: float) -> float:
    """Maximum gain dB whose post-gain onset-peak bound stays <= CLAMP_CEILING."""
    if onset_peak <= 0.0:
        return math.inf
    return 20.0 * math.log10(CLAMP_CEILING / onset_peak)


def _gain_envelope(window: int, sample_rate: int, gain_db: float) -> np.ndarray:
    """Hann fade-out gain envelope per the architecture's gain-envelope spec.

    E[n] = g_lin for 0 <= n < W - T; E[W - T + k] = 1 + (g_lin - 1) * w[k]
    with w[k] = 0.5 * (1 + cos(pi * k / (T - 1))). No leading taper: E[0] is
    full gain and E[W - 1] == 1.0 exactly, so the shape is continuous across
    the window edge.
    """
    g_lin = 10.0 ** (gain_db / 20.0)
    taper = min(window, max(MIN_TAPER_SAMPLES, int(TAPER_S * sample_rate)))
    envelope = np.ones(window, dtype=np.float64)
    flat = window - taper
    envelope[:flat] = g_lin
    if taper >= 2:
        k = np.arange(taper, dtype=np.float64)
        weights = 0.5 * (1.0 + np.cos(np.pi * k / (taper - 1)))
        envelope[flat:] = 1.0 + (g_lin - 1.0) * weights
    else:
        # Degenerate sub-16-sample stem: no meaningful fade, keep full gain.
        envelope[flat:] = g_lin
    return envelope


def _apply_transient_gain(
    arr: np.ndarray, window: int, sample_rate: int, gain_db: float
) -> tuple[np.ndarray, float]:
    """Apply onset-local gain through the tapered envelope; clip as
    defense-in-depth. Returns (output, measured post-gain onset-window peak).
    Samples at and beyond the window are untouched."""
    envelope = _gain_envelope(window, sample_rate, gain_db)
    output = arr.copy()
    if arr.ndim == 2:
        output[:window] = arr[:window] * envelope[:, np.newaxis]
    else:
        output[:window] = arr[:window] * envelope
    output = np.clip(output, -1.0, 1.0)
    onset_region = output[:window]
    onset_peak_after = float(np.abs(onset_region).max()) if onset_region.size else 0.0
    return output, onset_peak_after


def apply_stem_transient_restoration(
    stems: Dict[str, np.ndarray], sample_rate: int
) -> tuple[dict[str, np.ndarray], list[TransientRestorationAction]]:
    """Apply conservative onset-local transient restoration to each stem.

    Gain is applied only when a stem shows a measured local attack deficit,
    and is deterministically clamped to the available onset headroom
    (clamp-then-report, architecture "Headroom-management contract"). Only
    corrupt input (sample peak > 1.0) raises; hot-but-legal stems are clamped
    or returned unchanged with a report-visible action.
    """
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")

    processed: Dict[str, np.ndarray] = {}
    actions: list[TransientRestorationAction] = []

    for stem_name, audio in stems.items():
        arr = _coerce_stems(audio)
        _input_legality_guard(stem_name, arr)

        global_peak_before = float(np.abs(arr).max()) if arr.size else 0.0
        window = _onset_window_length(arr.shape[0], sample_rate)
        onset_region = arr[:window]
        p_onset = float(np.abs(onset_region).max()) if onset_region.size else 0.0

        ratio = _local_attack_ratio(arr, sample_rate)
        requested_gain_db = _gain_for_stem(stem_name, ratio)

        if requested_gain_db <= 0.0:
            processed[stem_name] = arr.copy()
            continue

        headroom_db = _headroom_clamp(p_onset)
        applied_gain_db = min(requested_gain_db, headroom_db)

        if applied_gain_db <= 0.0:
            processed[stem_name] = arr.copy()
            actions.append(
                TransientRestorationAction(
                    stem_name=stem_name,
                    action_type="skipped_headroom",
                    gain_db=0.0,
                    requested_gain_db=requested_gain_db,
                    onset_peak_before=p_onset,
                    onset_peak_after=p_onset,
                    global_peak_before=global_peak_before,
                    reason=(
                        f"{_action_label(stem_name)} skipped: onset-window peak "
                        f"{p_onset:.4f} leaves no headroom below the 0.98 ceiling; "
                        f"stem returned unchanged"
                    ),
                    severity=ratio,
                )
            )
            continue

        output, onset_peak_after = _apply_transient_gain(
            arr, window, sample_rate, applied_gain_db
        )
        _clip_guard(stem_name, output)
        processed[stem_name] = output

        if applied_gain_db == requested_gain_db:
            action_type = "attack_boost"
            reason = _reason_for_stem(stem_name, applied_gain_db)
        else:
            action_type = "attack_boost_headroom_clamped"
            reason = (
                f"{_action_label(stem_name)}: requested {requested_gain_db:.2f} dB, "
                f"applied {applied_gain_db:.2f} dB after onset headroom clamp "
                f"(ceiling 0.98)"
            )
        actions.append(
            TransientRestorationAction(
                stem_name=stem_name,
                action_type=action_type,
                gain_db=applied_gain_db,
                requested_gain_db=requested_gain_db,
                onset_peak_before=p_onset,
                onset_peak_after=onset_peak_after,
                global_peak_before=global_peak_before,
                reason=reason,
                severity=ratio,
            )
        )

    return processed, actions
