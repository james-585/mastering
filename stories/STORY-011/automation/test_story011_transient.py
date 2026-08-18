import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from implementation.transient_restoration import (
    _local_attack_ratio,
    apply_stem_transient_restoration,
)


SR = 48000
SR44 = 44100


def _sine_wave(freq_hz: float, duration_s: float, amplitude: float = 0.2) -> np.ndarray:
    t = np.linspace(0.0, duration_s, int(SR * duration_s), endpoint=False)
    return amplitude * np.sin(2.0 * np.pi * freq_hz * t)


def _slow_attack_transient(duration_s: float = 0.75, attack_ms: float = 80.0) -> np.ndarray:
    n = int(SR * duration_s)
    x = np.zeros(n, dtype=np.float64)
    attack_samples = int(SR * attack_ms / 1000.0)
    ramp = np.linspace(0.0, 1.0, attack_samples + 1)[1:]
    x[:attack_samples] = 0.2 * ramp
    x[attack_samples:attack_samples + 200] = 0.5
    x[attack_samples + 200:] = 0.15 * np.sin(np.linspace(0.0, 2.0 * np.pi, n - attack_samples - 200))
    return x


def _sharp_attack_transient(duration_s: float = 0.75) -> np.ndarray:
    n = int(SR * duration_s)
    x = np.zeros(n, dtype=np.float64)
    x[:10] = 0.5 * np.linspace(0.0, 1.0, 10)
    x[10:50] = 0.9
    x[50:] = 0.1 * np.sin(np.linspace(0.0, 2.0 * np.pi, n - 50))
    return x


def test_tc0111_drum_transient_restoration():
    stem = {"drums": _slow_attack_transient(duration_s=0.6, attack_ms=90.0)}

    processed, actions = apply_stem_transient_restoration(stem, SR)

    assert "drums" in processed
    assert actions
    assert actions[0].stem_name == "drums"
    assert actions[0].gain_db > 0.0
    assert np.abs(processed["drums"]).max() <= 1.0


def test_tc0112_bass_transient_restoration():
    stem = {"bass": _slow_attack_transient(duration_s=0.9, attack_ms=120.0)}

    processed, actions = apply_stem_transient_restoration(stem, SR)

    assert actions
    assert actions[0].stem_name == "bass"
    assert actions[0].reason.lower().find("attack") >= 0 or actions[0].reason.lower().find("bass") >= 0
    assert processed["bass"].shape == stem["bass"].shape


def test_tc0113_vocal_articulation_recovery():
    stem = {"vocals": _slow_attack_transient(duration_s=0.7, attack_ms=70.0) + 0.1 * _sine_wave(220.0, 0.7)}

    processed, actions = apply_stem_transient_restoration(stem, SR)

    assert actions
    assert actions[0].stem_name == "vocals"
    assert np.mean(np.abs(processed["vocals"])) >= np.mean(np.abs(stem["vocals"])) * 0.98


def test_tc0114_synth_no_op_on_clean_input():
    clean = _sine_wave(330.0, 0.5, amplitude=0.2)
    stem = {"synth": clean}

    processed, actions = apply_stem_transient_restoration(stem, SR)

    assert not actions
    assert np.allclose(processed["synth"], clean)


# ---------------------------------------------------------------------------
# DEF-011-01 / DEF-011-02 rework coverage (2026-08-17 architecture revision).
# TC-0115 is INVALIDATED — it asserted ValueError on a legal 0.99-peak input,
# encoding the rejected pre-gain abort method. It is REPLACED (not tuned) by
# TC-0121 (hot stem with deficit -> skipped_headroom, no raise), TC-0122
# (raise only when input peak > 1.0, with boundary coverage) and TC-0123
# (hot healthy stem -> unchanged, no action).
# ---------------------------------------------------------------------------


def _window_consts(n_samples: int, fs: int) -> tuple[int, int]:
    """Derived window constants per the architecture's verbatim formulas."""
    W = min(n_samples, max(32, int(0.08 * fs)))
    T = min(W, max(16, int(0.005 * fs)))
    return W, T


def _smeared_onset_fixture(p: float, fs: int = SR44, n_samples: int = 22050) -> np.ndarray:
    """Smeared-onset fixture with sample peak exactly p by construction.

    x[n] = p * r[n] * cos(2*pi*(fs/100)*n/fs) for n < W, else a 0.2-amplitude
    tone; r[n] = min(1, 0.05 + 0.95*n/3000). The tone period is exactly 100
    samples and r reaches 1.0 at n = 3000 == 0 (mod 100), so x[3000] = p and
    no sample exceeds p: max|x[:W]| == max|x| == p exactly (verified
    numerically: float cos(2*pi*30) rounds to 1.0, x[3000] == p bit-exact).
    """
    freq = fs / 100.0
    n = np.arange(n_samples, dtype=np.float64)
    tone = np.cos(2.0 * np.pi * freq * n / fs)
    W, _ = _window_consts(n_samples, fs)
    r = np.minimum(1.0, 0.05 + 0.95 * n / 3000.0)
    return np.where(n < W, p * r * tone, 0.2 * tone)


def _healthy_fixture(p: float, fs: int = SR44, n_samples: int = 22050) -> np.ndarray:
    """Healthy fixture: constant-amplitude tone (r == 1), no onset deficit.

    Documented fixture-construction deviation: the shared convention's 441 Hz
    tone spans 220.5 cycles in 22050 samples, and the FFT-based Hilbert
    envelope then shows a wrap-boundary spike at n=0 that inflates the
    measured attack ratio to 2.419 on a materially constant signal (logged
    as DEF-011-03). This fixture uses an integer cycle count (220 cycles ->
    440 Hz at 44100/22050), which measures 1.0000000000000986 through the
    identical code path, so the healthy no-op semantics are tested without
    masking DEF-011-03. Peak == p exactly at n = 0 (cos(0) == 1.0).
    """
    cycles = int(n_samples * 440.0 / fs)
    freq = cycles * fs / n_samples
    n = np.arange(n_samples, dtype=np.float64)
    return p * np.cos(2.0 * np.pi * freq * n / fs)


def _assert_envelope_shape(x: np.ndarray, out: np.ndarray, gain_db: float, fs: int) -> None:
    """TC-0119 Hann fade-out envelope assertions against the closed form."""
    W, T = _window_consts(x.shape[0], fs)
    g_lin = 10.0 ** (gain_db / 20.0)
    idx = np.arange(W)
    in_w = x[:W]
    mask = np.abs(in_w) >= 1e-6  # skip exact cosine zero crossings
    E = out[:W][mask] / in_w[mask]
    n = idx[mask]
    # E[0] == g_lin: full gain from sample 0, no leading taper
    assert np.isclose(E[n == 0][0], g_lin, rtol=1e-12)
    # flat region: E[n] == g_lin for 0 <= n < W - T
    flat = n < W - T
    assert np.allclose(E[flat], g_lin, rtol=1e-12)
    # fade region closed form, k = 0..T-1 at n = W - T + k
    fade = n >= W - T
    k = (n[fade] - (W - T)).astype(np.float64)
    expected = 1.0 + (g_lin - 1.0) * 0.5 * (1.0 + np.cos(np.pi * k / (T - 1)))
    assert np.allclose(E[fade], expected, rtol=1e-12, atol=1e-12)
    # observed E monotonic non-increasing across the fade
    assert np.all(np.diff(E[fade]) <= 1e-12)
    # E[W-1] == 1.0 exactly: no discontinuity at the window edge
    assert E[n == W - 1][0] == 1.0
    # samples at and beyond W untouched, bit-exact
    assert np.array_equal(out[W:], x[W:])


def _assert_action_contract(a) -> None:
    """TC-0116 amended action-record contract (global sanity assertions)."""
    assert a.action_type in (
        "attack_boost",
        "attack_boost_headroom_clamped",
        "skipped_headroom",
    )
    for field in (
        "requested_gain_db",
        "onset_peak_before",
        "onset_peak_after",
        "global_peak_before",
    ):
        assert isinstance(getattr(a, field), float)
    assert a.gain_db <= a.requested_gain_db + 1e-12
    assert (a.gain_db == a.requested_gain_db) == (a.action_type == "attack_boost")
    if a.gain_db > 0.0:
        assert a.onset_peak_after <= 0.98 + 1e-12
    for peak in (a.onset_peak_before, a.onset_peak_after, a.global_peak_before):
        assert 0.0 <= peak <= 1.0
    assert "true-peak safe" not in a.reason.lower()


def test_tc0117_local_window_gating_quiet_stem():
    # Near-silent healthy stem: low level must not read as a transient defect.
    quiet = 1e-4 * _healthy_fixture(1.0)
    processed, actions = apply_stem_transient_restoration({"drums": quiet}, SR44)
    assert actions == []
    assert np.array_equal(processed["drums"], quiet)


def test_tc0117_silent_stem_divide_by_zero_guard():
    # All-zero stem: ratio-based metric must not blow up on a zero baseline.
    silent = np.zeros(22050, dtype=np.float64)
    processed, actions = apply_stem_transient_restoration({"drums": silent}, SR44)
    assert actions == []
    assert np.array_equal(processed["drums"], silent)


def test_tc0118_ground_truth_headroom_clamp():
    p = 0.90
    x = _smeared_onset_fixture(p)
    W, _ = _window_consts(x.size, SR44)
    headroom_db = 20.0 * math.log10(0.98 / p)  # 0.7397 dB; linear 0.98/0.90

    processed, actions = apply_stem_transient_restoration({"drums": x}, SR44)

    assert len(actions) == 1
    a = actions[0]
    _assert_action_contract(a)
    assert a.action_type == "attack_boost_headroom_clamped"
    # Precondition: the fixture must request more than the available headroom
    # (severity mapping is an open question in test-cases.md; the clamp is
    # asserted against requested_gain_db, not a hardcoded request level).
    assert a.requested_gain_db > headroom_db
    assert a.gain_db == pytest.approx(headroom_db, abs=1e-4)
    assert a.requested_gain_db > a.gain_db
    assert a.onset_peak_before == pytest.approx(p, abs=1e-12)
    assert a.global_peak_before == pytest.approx(p, abs=1e-12)
    g_lin = 10.0 ** (a.gain_db / 20.0)
    assert abs(g_lin - 0.98 / 0.90) < 1e-6
    # Bound semantics under the Hann-tapered envelope (gate-1 F2).
    assert a.onset_peak_after <= p * g_lin + 1e-12
    assert p * g_lin <= 0.98 + 1e-12
    out = processed["drums"]
    assert np.array_equal(out[W:], x[W:])
    assert np.abs(out).max() <= 0.98 + 1e-12
    assert out.shape == x.shape and out.dtype == np.float64
    # Clamped reason convention: requested vs applied dB and the 0.98 ceiling.
    assert "requested" in a.reason and "applied" in a.reason and "0.98" in a.reason


@pytest.mark.parametrize("fs,n_samples", [(44100, 22050), (48000, 24000)])
def test_tc0119_gain_envelope_hann_fade_out(fs, n_samples):
    # Positive applied gain, unclamped (p = 0.40 -> headroom 7.78 dB).
    x = _smeared_onset_fixture(0.40, fs=fs, n_samples=n_samples)
    processed, actions = apply_stem_transient_restoration({"drums": x}, fs)
    assert len(actions) == 1
    assert actions[0].action_type == "attack_boost"
    assert actions[0].gain_db > 0.0
    _assert_envelope_shape(x, processed["drums"], actions[0].gain_db, fs)


def test_tc0119_envelope_shape_clamped_run():
    # Same shape from a clamped run: the envelope is a pure function of
    # (W, T, g_applied).
    x = _smeared_onset_fixture(0.90)
    processed, actions = apply_stem_transient_restoration({"drums": x}, SR44)
    assert actions[0].action_type == "attack_boost_headroom_clamped"
    _assert_envelope_shape(x, processed["drums"], actions[0].gain_db, SR44)


def test_tc0119_short_file_variant():
    # n_samples = 64 -> W = 64, T = 64: the fade spans the whole window and
    # the n >= W condition is vacuous. 10-sample-period tone with a fast
    # 12-sample ramp so the onset deficit is measurable inside 64 samples.
    fs = SR44
    n = np.arange(64, dtype=np.float64)
    tone = np.cos(2.0 * np.pi * (fs / 10.0) * n / fs)
    s = np.minimum(1.0, 0.02 + 0.98 * n / 12.0)
    x = 0.40 * s * tone

    processed, actions = apply_stem_transient_restoration({"other": x}, fs)

    assert len(actions) == 1
    assert actions[0].gain_db > 0.0
    _assert_envelope_shape(x, processed["other"], actions[0].gain_db, fs)


def test_tc0120_clamp_negative_control():
    p = 0.40  # headroom 20*log10(0.98/0.40) = 7.7833 dB >> any request
    x = _smeared_onset_fixture(p)
    W, _ = _window_consts(x.size, SR44)

    processed, actions = apply_stem_transient_restoration({"drums": x}, SR44)

    assert len(actions) == 1
    a = actions[0]
    _assert_action_contract(a)
    assert a.action_type == "attack_boost"
    assert a.gain_db == a.requested_gain_db  # exact float equality
    g_lin = 10.0 ** (a.gain_db / 20.0)
    assert a.onset_peak_after <= p * g_lin + 1e-12
    reason = a.reason.lower()
    assert "clamp" not in reason and "skip" not in reason
    assert np.array_equal(processed["drums"][W:], x[W:])


def test_tc0121_hot_stem_skipped_not_aborted():
    # DEF-011-01 reproduction: p = 0.9831 is the exact Twilight Caverns stem
    # peak from the original abort. Headroom 20*log10(0.98/0.9831) =
    # -0.0274 dB < 0, so the skip branch is the analytically forced outcome.
    p = 0.9831
    x = _smeared_onset_fixture(p)

    processed, actions = apply_stem_transient_restoration({"drums": x}, SR44)

    assert len(actions) == 1
    a = actions[0]
    _assert_action_contract(a)
    assert a.action_type == "skipped_headroom"
    assert a.gain_db == 0.0
    assert a.requested_gain_db > 0.0
    assert a.onset_peak_before == pytest.approx(p, abs=1e-12)
    assert a.global_peak_before == pytest.approx(p, abs=1e-12)
    assert np.array_equal(processed["drums"], x)  # unchanged, bit-identical
    # Skip reason convention: onset-window peak and "returned unchanged".
    assert "0.9831" in a.reason
    assert "unchanged" in a.reason


def test_tc0122_input_legality_guard_and_boundary():
    # 1. Peak > 1.0 raises, naming the stem key and the measured peak.
    illegal = np.zeros(256, dtype=np.float64)
    illegal[0] = 1.05
    with pytest.raises(ValueError) as exc_info:
        apply_stem_transient_restoration({"drums": illegal}, SR44)
    assert "drums" in str(exc_info.value)
    assert "1.05" in str(exc_info.value)

    # 2. Boundary: peak exactly 1.0 with an onset deficit -> legal, no raise;
    # headroom 20*log10(0.98/1.0) = -0.1754 dB < 0 -> skipped_headroom.
    x = _smeared_onset_fixture(1.0)
    processed, actions = apply_stem_transient_restoration({"drums": x}, SR44)
    assert actions[0].action_type == "skipped_headroom"
    assert np.array_equal(processed["drums"], x)

    # 3. Just under the ceiling: p = 0.979 -> headroom +0.0089 dB; the
    # request exceeds it -> clamped to the headroom value.
    x = _smeared_onset_fixture(0.979)
    processed, actions = apply_stem_transient_restoration({"drums": x}, SR44)
    a = actions[0]
    assert a.action_type == "attack_boost_headroom_clamped"
    assert a.requested_gain_db > 20.0 * math.log10(0.98 / 0.979)
    assert a.gain_db == pytest.approx(20.0 * math.log10(0.98 / 0.979), abs=1e-4)
    assert a.onset_peak_after <= 0.98 + 1e-12

    # 4. Just over the ceiling: p = 0.981 -> headroom -0.0088 dB -> skipped,
    # no raise. (Never a raise for any input peak in (0.98, 1.0].)
    x = _smeared_onset_fixture(0.981)
    processed, actions = apply_stem_transient_restoration({"drums": x}, SR44)
    assert actions[0].action_type == "skipped_headroom"
    assert np.array_equal(processed["drums"], x)


def test_tc0123_hot_healthy_stem_noop():
    # Direct replacement for the invalidated TC-0115 semantics: a 0.99-peak
    # stem with no onset deficit is legal programme material -> no ValueError,
    # stem bit-identical, and no action emitted (silence means clean no-op).
    x = _healthy_fixture(0.99)
    processed, actions = apply_stem_transient_restoration({"drums": x}, SR44)
    assert actions == []
    assert np.array_equal(processed["drums"], x)


def test_tc0124_determinism():
    stems = {
        "drums": _smeared_onset_fixture(0.90),    # clamp path
        "bass": _smeared_onset_fixture(0.9831),   # skip path
        "vocals": _healthy_fixture(0.5),          # no-op path
    }

    out1, act1 = apply_stem_transient_restoration(dict(stems), SR44)
    out2, act2 = apply_stem_transient_restoration(dict(stems), SR44)

    for name in stems:
        assert np.array_equal(out1[name], out2[name])
    # Dataclass equality pins every field (incl. requested_gain_db, peaks,
    # reason, severity) with exact float equality and identical ordering.
    assert act1 == act2


def test_tc0125_six_stem_compatibility():
    stems = {
        "drums": _healthy_fixture(0.5),
        "bass": _healthy_fixture(0.5),
        "vocals": _healthy_fixture(0.5),
        "other": _healthy_fixture(0.5),
        "piano": _smeared_onset_fixture(0.9831),   # -> skipped_headroom
        "guitar": _smeared_onset_fixture(0.90),    # -> headroom clamped
    }

    processed, actions = apply_stem_transient_restoration(stems, SR44)

    by_name = {a.stem_name: a for a in actions}
    assert set(by_name) == {"piano", "guitar"}
    for a in actions:
        _assert_action_contract(a)
    piano = by_name["piano"]
    assert piano.action_type == "skipped_headroom"
    assert piano.gain_db == 0.0
    assert np.array_equal(processed["piano"], stems["piano"])
    guitar = by_name["guitar"]
    assert guitar.action_type == "attack_boost_headroom_clamped"
    # Clamp identity for EVERY emitted action regardless of stem name
    # (unknown names use the default severity threshold; headroom handling
    # is name-agnostic). Skipped pins gain_db == 0.0 == max(0, min(...)).
    for a in actions:
        expected = max(
            0.0,
            min(a.requested_gain_db, 20.0 * math.log10(0.98 / a.onset_peak_before)),
        )
        assert a.gain_db == pytest.approx(expected, abs=1e-4)
    for name in ("drums", "bass", "vocals", "other"):
        assert np.array_equal(processed[name], stems[name])


def test_tc0126_stereo_known_attack_ratio():
    """DEF-011-02 regression guard (hilbert axis). Mono fixtures cannot catch
    this bug.

    Re-derived expectation (documented per H-rules): test-cases.md's band
    [1.8, 2.2] assumed a metric whose baseline is the post-onset level
    (0.60/0.30 = 2.0). The implementation's `_local_attack_ratio` instead
    takes baseline = median of the FIRST 1200 samples of the analysis window
    and peak = max over the first 12000 samples. For this fixture the
    baseline window lies entirely inside the 0.60 onset region, so the
    analytically derivable values for THIS metric are:
      - correct axis (axis=0 + cross-channel max): baseline 0.60, peak 0.60,
        ratio = 1.0 (ideal). Measured 1.216: amplitude-step ringing at
        n=3840 inflates the peak statistic; the band below absorbs it.
      - broken axis (default axis=-1, the N=2 transform is the identity):
        envelope = rectified waveform max(|L|,|R|); baseline median
        (sqrt(2)/2)*0.60 = 0.42426, peak 0.60 (grid hits the sine peak),
        ratio = sqrt(2) = 1.41421. Measured on simulated broken code:
        1.4149 -- outside the asserted band, so this test provably fails on
        the unfixed implementation.
    The 2:1 onset:baseline envelope ratio ground truth is unchanged; only
    the metric-convention mapping is re-derived.
    """
    fs = 48000
    N = 24000
    n = np.arange(N, dtype=np.float64)
    tone = np.sin(2.0 * np.pi * 480.0 * n / fs)  # period exactly 100 samples
    left = np.where(n < 3840, 0.60, 0.10) * tone
    right = 0.30 * tone
    x = np.column_stack([left, right])

    ratio = _local_attack_ratio(x, fs)
    assert 0.9 <= ratio <= 1.35  # correct-axis analytic 1.0; broken sqrt(2)

    # Apply path: healthy 2:1 onset:baseline attack -> no boost, output
    # bit-identical, no action.
    processed, actions = apply_stem_transient_restoration({"drums": x}, fs)
    assert actions == []
    assert np.array_equal(processed["drums"], x)


def test_tc0116_report_visibility():
    stem = {"drums": _slow_attack_transient(duration_s=0.5, attack_ms=100.0)}

    _, actions = apply_stem_transient_restoration(stem, SR)

    assert actions[0].reason
    assert actions[0].action_type
    assert "gain" in actions[0].reason.lower() or "attack" in actions[0].reason.lower() or "transient" in actions[0].reason.lower()

    # Amended 2026-08-17 contract: new fields on every emitted action, the
    # action_type enum, and the reason-string conventions for all three
    # action types.
    for p, expected_type in (
        (0.40, "attack_boost"),
        (0.90, "attack_boost_headroom_clamped"),
        (0.9831, "skipped_headroom"),
    ):
        _, acts = apply_stem_transient_restoration(
            {"drums": _smeared_onset_fixture(p)}, SR44
        )
        assert len(acts) == 1
        assert acts[0].action_type == expected_type
        _assert_action_contract(acts[0])

    _, clamped = apply_stem_transient_restoration(
        {"drums": _smeared_onset_fixture(0.90)}, SR44
    )
    r = clamped[0].reason
    assert "requested" in r and "applied" in r and "0.98" in r

    _, skipped = apply_stem_transient_restoration(
        {"drums": _smeared_onset_fixture(0.9831)}, SR44
    )
    r = skipped[0].reason
    assert "0.9831" in r and "unchanged" in r


def test_tc0127_non_integer_cycle_steady_tone_no_spurious_boost():
    """DEF-011-03 regression guard (Hilbert wrap-boundary spike at n=0).

    Before the fix, the FFT wrap discontinuity on a non-integer-cycle signal
    produced env[0] ≈ 2×amplitude, inflating np.max(onset) and returning
    ratio ≈ 2.42 for a flat 441 Hz tone. The fix skips a ~1 ms lead-in before
    the peak statistic.

    TC-0114 and TC-0123 use INTEGER-cycle tones (440 Hz) deliberately — that
    must not change, or this defect would be masked.
    """
    fs = SR44  # 44100 Hz
    duration_s = 0.5

    # Non-integer-cycle fixture: 441 Hz × 0.5 s = 220.5 cycles (wrap artefact)
    t_ni = np.linspace(0.0, duration_s, int(fs * duration_s), endpoint=False)
    non_integer = 0.5 * np.sin(2.0 * np.pi * 441.0 * t_ni)

    # Integer-cycle control: 440 Hz × 0.5 s = 220 cycles (no wrap artefact)
    t_i = np.linspace(0.0, duration_s, int(fs * duration_s), endpoint=False)
    integer_ctrl = 0.5 * np.sin(2.0 * np.pi * 440.0 * t_i)

    ratio_ni = _local_attack_ratio(non_integer, fs)
    ratio_int = _local_attack_ratio(integer_ctrl, fs)

    # Oracle bands from the mastering-engineer gate review (2026-08-18)
    assert 0.9 <= ratio_ni <= 1.3, (
        f"Non-integer-cycle fixture returned {ratio_ni:.4f} — expected [0.9, 1.3]; "
        f"ratio > 1.3 indicates the Hilbert wrap spike is still inflating the peak"
    )
    assert 0.95 <= ratio_int <= 1.05, (
        f"Integer-cycle control returned {ratio_int:.4f} — expected [0.95, 1.05]"
    )

    # Apply path: ratio ≈ 1.0 must not trigger a boost
    processed, actions = apply_stem_transient_restoration({"other": non_integer}, fs)
    assert actions == [], f"Spurious action emitted on flat steady-content stem: {actions}"
    assert np.array_equal(processed["other"], non_integer)
