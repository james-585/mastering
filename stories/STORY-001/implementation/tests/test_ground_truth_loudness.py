"""STORY-003 ground-truth tests -- loudness (LUFS), AC4, test-cases.md
TC-001 through TC-005.

TC-001 (AC4a) is already satisfied by STORY-001's existing test_tc010
(tests/test_ac2_loudness.py) -- recorded here only for this suite's own
traceability, not duplicated as a new assertion.
"""
from __future__ import annotations

import pytest

from suno_mastering.analysis.loudness import measure_integrated_lufs

from .conftest import sine, rms_amplitude_for_dbfs_sine

pytestmark = pytest.mark.ground_truth

SR = 44100


def test_tc002_six_db_gain_moves_loudness_by_exactly_six_lu():
    """AC4b. LUFS is a log-power measure; a fixed linear gain of 10**(6/20)
    (NOT 2.0, which is 6.0206 dB) applied uniformly to a signal whose gate/
    threshold behavior is unaffected shifts every gated block's log-power by
    exactly the same additive 6.0 dB, hence the integrated result too."""
    amp1 = rms_amplitude_for_dbfs_sine(-20.0)
    amp2 = amp1 * (10 ** (6.0 / 20.0))
    sine1 = sine(1000, SR, 4.0, amplitude=amp1)
    sine2 = sine(1000, SR, 4.0, amplitude=amp2)
    lufs1 = measure_integrated_lufs(sine1, SR)
    lufs2 = measure_integrated_lufs(sine2, SR)
    assert abs((lufs2 - lufs1) - 6.0) < 0.1


def test_tc003_below_absolute_gate_reads_exactly_minus_inf():
    """Below the -70 LUFS absolute gate -- every block fails, so pyloudnorm
    returns exactly -inf (spec-conformant, already exercised for the
    pure-silence case by STORY-001's test_silence_dynamics.py; this is the
    "quiet but not literally zero" variant). At -80 dBFS RMS the signal is
    comfortably below the gate regardless of the exact 1 kHz net offset
    (see TC-004's docstring for that derivation and why it is NOT simply
    "-0.691 dB"), so no precise boundary arithmetic is needed here."""
    amp = rms_amplitude_for_dbfs_sine(-80.0)
    audio = sine(1000, SR, 4.0, amplitude=amp)
    lufs = measure_integrated_lufs(audio, SR)
    assert lufs == float("-inf")


def test_tc004_just_above_absolute_gate_reads_finite_negative_control():
    """Negative control for TC-003: -68 dBFS RMS must read a finite value
    close to the actual measured 1 kHz net offset -- NOT -inf, and not a
    wildly different number (gain-staging-blows-up failure mode).

    CORRECTION to test-cases.md TC-004's own stated derivation (flagged as
    a test-cases.md internal-consistency defect, not applied here): TC-004's
    text computes the expected value as "dbfs - 0.691" (i.e. -68.69 LUFS),
    treating the -0.691 dB BS.1770 fixed offset as uncancelled at 1 kHz.
    This directly contradicts the SAME document's own TC-001 derivation,
    which states 1 kHz is BS.1770's calibration-neutral frequency BECAUSE
    the K-weighting high-shelf's partial gain at 1 kHz combines with the
    -0.691 dB offset to net ~=0 dB, so LUFS ~= input dBFS RMS directly (not
    dBFS - 0.691) -- this is also exactly what STORY-001's existing
    test_tc010 (-20 dBFS RMS -> -20.0 +/- 0.1 LUFS) already demonstrates
    empirically. Measured directly here (not assumed): at 1 kHz the net
    offset is ~-0.0354 dB (not -0.691 dB) across every RMS level tested,
    dbfs in {-80,-68,-65,-60,-50,-30,-20}, confirming the offset is a fixed,
    level-independent, frequency-dependent constant -- consistent with
    TC-001's framing, not TC-004's. The correct absolute-gate boundary is
    therefore ~-69.96 dBFS RMS (not TC-004's implied ~-71.3 dBFS), and the
    correct expected LUFS at -68 dBFS RMS is ~-68.04, not -68.69."""
    amp = rms_amplitude_for_dbfs_sine(-68.0)
    audio = sine(1000, SR, 4.0, amplitude=amp)
    lufs = measure_integrated_lufs(audio, SR)
    assert lufs != float("-inf")
    assert abs(lufs - (-68.0354)) < 0.1


def test_tc005_dc_offset_does_not_materially_move_lufs():
    """BS.1770-4 Annex 1's K-weighting stage includes a high-pass filter
    (corner ~38 Hz) whose response at 0 Hz is a deep, spec-mandated null --
    DC content is removed before power integration by design."""
    amp = rms_amplitude_for_dbfs_sine(-20.0)
    plain = sine(1000, SR, 4.0, amplitude=amp)
    with_dc = plain + 0.2  # well below clipping for a -20 dBFS tone
    lufs_plain = measure_integrated_lufs(plain, SR)
    lufs_dc = measure_integrated_lufs(with_dc, SR)
    assert abs(lufs_dc - lufs_plain) < 0.1
