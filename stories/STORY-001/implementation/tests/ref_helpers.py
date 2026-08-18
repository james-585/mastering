"""Shared helpers for STORY-002's automated test suite (test_ref_*.py).

Deliberately a plain importable module, not a conftest.py addition -- this
keeps zero risk of touching STORY-001's existing `tests/conftest.py` (and
therefore zero risk of an accidental STORY-001 regression introduced by this
QA pass). Reuses STORY-001's own signal-builder conventions (`conftest.sine`,
`to_stereo`, etc.) by importing them directly, rather than reimplementing.
"""
from __future__ import annotations

import dataclasses
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from suno_mastering.reference_analysis.config import ReferenceAnalysisConfig
from suno_mastering.analysis.types import (
    Measurements, FrequencyBalanceResult, BandMeasurement, StereoPhaseResult, ClippingResult,
)
from suno_mastering.analysis.reference_types import (
    ReferenceMeasurements, LraResult, SevenBandResult, SevenBandMeasurement,
    HfExtensionResult, PerBandWidthResult, PerBandWidthMeasurement,
    MonoSumResult, BandCancellation, ProvenanceResult,
)

from .conftest import sine, to_stereo, dbfs_to_amplitude, write_wav  # noqa: F401

_SEVEN_BAND_KEYS = ("sub", "low", "low_mid", "mid", "high_mid", "high", "air")


def _band(flagged=False):
    return BandMeasurement(range_hz=(0.0, 1.0), relative_db=0.0, reference_db=0.0,
                            deviation_db=0.0, flagged=flagged)


def make_stub_measurements(
    track_path: str,
    *,
    integrated_lufs: float = -14.0,
    true_peak_dbtp: float = -3.0,
    dynamic_range_db_exact: float = 9.5,
    lra_lu: float = 6.0,
    sample_rate: int = 44100,
    is_mono: bool = False,
    lossless: bool = True,
    container: str = "wav",
    hf_rolloff_hz: float = 18000.0,
    hf_insufficient_duration: bool = False,
    overall_correlation: float = 0.5,
    mono_sum_level_change_db: float = -3.0,
    seven_band_relative_db: float = 0.0,
    per_band_width: float = 0.5,
) -> ReferenceMeasurements:
    """A hand-constructed ReferenceMeasurements stand-in, per architecture.md
    Section 12's own recommendation: exercises [R3] aggregation/exclusion
    logic against known, hand-computable per-track values without any real
    audio decode -- fast, deterministic, and precise."""
    core = Measurements(
        sample_rate=sample_rate,
        channels=1 if is_mono else 2,
        duration_seconds=60.0,
        is_mono=is_mono,
        integrated_lufs=integrated_lufs,
        true_peak_dbtp=true_peak_dbtp,
        dynamic_range_db=round(dynamic_range_db_exact),
        frequency_balance=FrequencyBalanceResult(
            low_end=_band(), low_mid_mud=_band(), presence_harsh=_band()
        ),
        stereo_phase=StereoPhaseResult(
            is_mono=is_mono, overall_correlation=overall_correlation,
            mono_compatible=overall_correlation >= 0.0,
        ),
        clipping=ClippingResult(
            sample_peak_clipped_count=0, sample_peak_clip_events=0,
            inter_sample_over_count=0, inter_sample_peak_dbtp=true_peak_dbtp, severity="none",
        ),
    )

    seven_band = SevenBandResult(bands=[
        SevenBandMeasurement(band=k, range_hz=(0.0, 1.0), relative_db=seven_band_relative_db)
        for k in _SEVEN_BAND_KEYS
    ])

    # Field names fixed from stale v1.4 names (rolloff_hz, per_segment_rolloff_hz)
    # to match the current HfExtensionResult dataclass contract (reference_types.py):
    # hf_band_limit_hz, hf_band_limit_confidence, per_segment_hf_band_limit_hz.
    hf_extension = HfExtensionResult(
        hf_band_limit_hz=None if hf_insufficient_duration else hf_rolloff_hz,
        hf_band_limit_confidence=0.0,
        stable=True, per_segment_hf_band_limit_hz=[], insufficient_duration=hf_insufficient_duration,
    )

    per_band_width = None
    mono_sum = None
    if not is_mono:
        per_band_width = PerBandWidthResult(bands=[
            PerBandWidthMeasurement(band=k, range_hz=(0.0, 1.0), width=per_band_width_v)
            for k, per_band_width_v in [(k, per_band_width) for k in _SEVEN_BAND_KEYS]
        ])
        # Field names fixed from stale v1.4 names (level_change_db,
        # excess_cancellation_db) to match the current MonoSumResult dataclass
        # contract (reference_types.py): mono_sum_level_change_db,
        # mono_sum_excess_cancellation (bool, derived from the level value vs
        # the -4.5 dB threshold per architecture.md Section 2.3).
        mono_sum = MonoSumResult(
            mono_sum_level_change_db=mono_sum_level_change_db,
            mono_sum_excess_cancellation=mono_sum_level_change_db < -4.5,
            band_cancellations=[
                BandCancellation(band=k, range_hz=(0.0, 1.0), delta_db=0.0,
                                  excess_delta_db=0.0, cancellation=False)
                for k in _SEVEN_BAND_KEYS
            ],
        )

    provenance = ProvenanceResult(
        container=container, lossless=lossless, bitrate_kbps=None if lossless else 320,
        decoder="stub-decoder",
    )

    return ReferenceMeasurements(
        core=core,
        dynamic_range_db_exact=dynamic_range_db_exact,
        lra=LraResult(lra_lu=lra_lu, n_gated_blocks=10, self_consistency_delta_lu=0.0),
        seven_band=seven_band,
        hf_extension=hf_extension,
        per_band_stereo_width=per_band_width,
        mono_sum=mono_sum,
        provenance=provenance,
        track_path=track_path,
        label=None,
    )


def independent_noise_stereo(sr: int, duration_s: float, sigma: float = 0.05, seed: int = 0) -> np.ndarray:
    """Two independent, equal-power Gaussian-noise channels -- ordinary,
    healthy, fully-decorrelated wide stereo (rho=0). This is exactly the
    DEF-101 regression fixture (architecture.md Section 4.5 / defects.md
    DEF-101 verification case 2)."""
    rng = np.random.default_rng(seed)
    n = int(round(duration_s * sr))
    left = rng.normal(0.0, sigma, n)
    right = rng.normal(0.0, sigma, n)
    return np.stack([left, right], axis=1)


def pink_noise_mono(sr: int, duration_s: float, seed: int = 0, amplitude: float = 0.1) -> np.ndarray:
    """Cheap pink-ish noise via 1/f shaping in the frequency domain (good
    enough for exercising non-degenerate per-band energy, not for precision
    spectral assertions)."""
    n = int(round(duration_s * sr))
    rng = np.random.default_rng(seed)
    white = rng.normal(0.0, 1.0, n)
    spectrum = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(n, d=1.0 / sr)
    scale = np.ones_like(freqs)
    nonzero = freqs > 0
    scale[nonzero] = 1.0 / np.sqrt(freqs[nonzero])
    shaped = np.fft.irfft(spectrum * scale, n=n)
    shaped = shaped / (np.max(np.abs(shaped)) + 1e-12) * amplitude
    return shaped


def pink_noise_stereo(sr: int, duration_s: float, seed: int = 0, amplitude: float = 0.1) -> np.ndarray:
    return to_stereo(pink_noise_mono(sr, duration_s, seed=seed, amplitude=amplitude))


def tilted_noise_mono(sr: int, duration_s: float, slope_db_per_octave: float = 6.0,
                       seed: int = 0, amplitude: float = 0.1) -> np.ndarray:
    """Full-band noise with a CONSTANT spectral tilt of `slope_db_per_octave`
    dB/octave power decline, all the way to Nyquist -- no lowpass filter
    anywhere (STORY-004 architecture.md Section 5.1's tilted-only negative-
    control construction, and the base signal for
    tilted_then_brickwall_mono below).

    Derivation (by construction, H4): amplitude spectrum A(f) is shaped as
    f**(-a). Power P(f) proportional to f**(-2a). Power decline per octave:
    10*log10(P(2f)/P(f)) = 10*log10(2**(-2a)) = -2a*10*log10(2)
    = -6.0206*a dB/octave. Solving for the requested slope:
    a = slope_db_per_octave / (20*log10(2)). At slope_db_per_octave=6.0,
    a ~= 0.9966 (NOT 1.0 -- 6.0/6.0206, not a round number by design, this
    is what makes the tilt exactly 6 dB/octave rather than the 6.0206
    dB/octave that a=1 would give). At slope_db_per_octave=3.0, this
    reduces to plain pink-noise shaping (a~=0.4989), consistent with
    pink_noise_mono's own -3 dB/octave construction above -- not
    reimplemented separately to avoid two independently-tunable pink-noise
    generators drifting apart.
    """
    n = int(round(duration_s * sr))
    rng = np.random.default_rng(seed)
    white = rng.normal(0.0, 1.0, n)
    spectrum = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(n, d=1.0 / sr)
    a = slope_db_per_octave / (20.0 * np.log10(2.0))
    scale = np.ones_like(freqs)
    nonzero = freqs > 0
    scale[nonzero] = freqs[nonzero] ** (-a)
    shaped = np.fft.irfft(spectrum * scale, n=n)
    shaped = shaped / (np.max(np.abs(shaped)) + 1e-12) * amplitude
    return shaped


def tilted_then_brickwall_mono(sr: int, duration_s: float, cutoff_hz: float,
                                slope_db_per_octave: float = 6.0, seed: int = 0,
                                amplitude: float = 0.2) -> np.ndarray:
    """STORY-004 architecture.md Section 5.1 (Gate-1-corrected): a genuine
    spectral tilt (NOT a bare/white brickwall -- a 0 dB/octave pre-slope
    trivially clears any passband-tilt gate and does not exercise the
    gate->drop->floor interaction, which is the actually load-bearing case
    near Nyquist per the Gate 1 review) brickwall-filtered at `cutoff_hz`.
    Used for the 20 kHz/48 kHz near-Nyquist positive ground-truth fixture
    (TC-404/TC-404b)."""
    tilted = tilted_noise_mono(sr, duration_s, slope_db_per_octave=slope_db_per_octave,
                                seed=seed, amplitude=1.0)
    n = tilted.size
    spectrum = np.fft.rfft(tilted)
    freqs = np.fft.rfftfreq(n, d=1.0 / sr)
    spectrum[freqs > cutoff_hz] = 0.0
    filtered = np.fft.irfft(spectrum, n=n)
    filtered = filtered / (np.max(np.abs(filtered)) + 1e-12) * amplitude
    return filtered


def steep_air_band_brickwall_mono(sr: int, duration_s: float, shelf_hz: float = 4000.0,
                                   slope_db_per_octave: float = 10.5,
                                   cutoff_hz: float = 20000.0,
                                   seed: int = 0, amplitude: float = 0.2) -> np.ndarray:
    """STORY-004 architecture.md §5.1 NEW — REQUIRED (v1.5a): flat-spectrum noise
    below shelf_hz (~4 kHz), spectral tilt of slope_db_per_octave (~10.5 dB/oct)
    above it, brickwalled at cutoff_hz (20 kHz). Target SR=48000.

    Construction (by design, H4):
      A(f) = 1.0                     for f <= shelf_hz
      A(f) = (f / shelf_hz)^(-a)    for f > shelf_hz
      where a = slope_db_per_octave / (20 * log10(2))
      Power decline above shelf_hz: -2a * 10*log10(2) = -slope_db_per_octave dB/oct.

    At slope_db_per_octave=10.5: a ≈ 1.7441, power decline ≈ -10.5 dB/oct.
    Firmly between 6 dB/oct (ordinary-tilt range) and 12 dB/oct (gate-rejection
    ceiling), so the 20 kHz brickwall candidate is gate-admissible while exercising
    the steep-air-band case tilted_then_brickwall_mono's 6 dB/oct cannot.

    v1.5 failure mode (H7 criterion 2 not met — v1.5 code no longer available;
    documented per TC-432 precedent): under v1.5's trailing-octave tracker, Welch
    noise could push individual octave windows from the 10.5 dB/oct pre-slope above
    the 12 dB/oct freeze threshold, anchoring passband_level mid-spectrum (~8–15 kHz)
    and producing a wrong number. Under v1.5a, freeze_index = i_max from _gate_scan
    (highest qualifying candidate ≈ 20 kHz); no early freeze fires (§6 risk 13 retired).
    """
    n = int(round(duration_s * sr))
    rng = np.random.default_rng(seed)
    white = rng.normal(0.0, 1.0, n)
    spectrum = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(n, d=1.0 / sr)
    a = slope_db_per_octave / (20.0 * np.log10(2.0))
    scale = np.ones_like(freqs)
    above_shelf = freqs > shelf_hz
    scale[above_shelf] = (freqs[above_shelf] / shelf_hz) ** (-a)
    spectrum *= scale
    spectrum[freqs > cutoff_hz] = 0.0
    filtered = np.fft.irfft(spectrum, n=n)
    filtered = filtered / (np.max(np.abs(filtered)) + 1e-12) * amplitude
    return filtered


def tilt_nonstationary_no_cutoff_mono(sr: int, seg_duration_s: float = 2.0, n_segments: int = 4,
                                       seed: int = 0, amplitude: float = 0.15) -> np.ndarray:
    """STORY-004 architecture.md Section 5.1's primary DEF-204 negative
    control: concatenation of several tilted-noise segments with
    deliberately DIFFERENT per-segment spectral tilt exponent and gain
    (construction pattern analogous to mono_low_decorrelated_high_stereo's
    crossover approach elsewhere in this module), none containing any
    band-limiting filter, all genuinely full-band to Nyquist. Exercises
    the tilt/non-stationarity confound TC-024 (stationary) and TC-025
    (genuine cutoff-frequency drift, not a cutoff-free tilt change) cannot
    expose (requirements.md DEF-204 scope; architecture.md Section 9)."""
    slopes = [4.0, 6.0, 8.0, 5.0]
    gains = [1.0, 0.6, 1.4, 0.8]
    segments = []
    for i in range(n_segments):
        seg = tilted_noise_mono(
            sr, seg_duration_s,
            slope_db_per_octave=slopes[i % len(slopes)],
            seed=seed + i,
            amplitude=amplitude * gains[i % len(gains)],
        )
        segments.append(seg)
    return np.concatenate(segments)


def silent_stereo(sr: int, duration_s: float) -> np.ndarray:
    """All-zero, exact digital silence, both channels -- STORY-004 TC-453
    (both-channels-exact-silence mono-sum guard fixture)."""
    n = int(round(duration_s * sr))
    return np.zeros((n, 2), dtype=np.float64)


def brickwall_lowpass_noise_mono(sr: int, duration_s: float, cutoff_hz: float, seed: int = 0,
                                  amplitude: float = 0.2) -> np.ndarray:
    """Genuine brickwall (rectangular frequency-domain) lowpass: FFT white
    noise, zero every bin strictly above cutoff_hz, inverse FFT. Unlike
    lowpassed_white_noise (Butterworth + sosfiltfilt, a finite-slope filter),
    this produces a vertical spectral edge: the detector's reported rolloff
    coincides with cutoff_hz REGARDLESS OF WHICH dB THRESHOLD
    hf_rolloff_threshold_db uses (to within Welch-PSD leakage, a few bins --
    negligible at this story's fixture lengths). A finite-slope filter's
    threshold-crossing frequency moves when the threshold moves (STORY-003
    architecture.md Section 2.5); a true brickwall's does not. Matches
    story.md's own literal "brickwalled at exactly 15 kHz" language."""
    n = int(round(duration_s * sr))
    rng = np.random.default_rng(seed)
    white = rng.normal(0.0, 1.0, n)
    spectrum = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(n, d=1.0 / sr)
    spectrum[freqs > cutoff_hz] = 0.0
    filtered = np.fft.irfft(spectrum, n=n)
    filtered = filtered / (np.max(np.abs(filtered)) + 1e-12) * amplitude
    return filtered


def brickwall_lowpass_noise_with_drift(sr: int, first_s: float, second_s: float,
                                        cutoff1_hz: float, cutoff2_hz: float, seed: int = 0,
                                        amplitude: float = 0.3) -> np.ndarray:
    """Cutoff changes partway through -- AC6e drift/instability fixture."""
    return np.concatenate([
        brickwall_lowpass_noise_mono(sr, first_s, cutoff1_hz, seed=seed, amplitude=amplitude),
        brickwall_lowpass_noise_mono(sr, second_s, cutoff2_hz, seed=seed + 1, amplitude=amplitude),
    ])


def brickwall_lowpass_noise_with_floor_mono(sr: int, duration_s: float, cutoff_hz: float,
                                             floor_below_db: float, seed: int = 0,
                                             passband_sigma: float = 0.15) -> np.ndarray:
    """TC-023: a finite (non-silent), known-depth stopband floor, distinct
    from brickwall_lowpass_noise_mono's exactly-silent (-inf dB) stopband.

    Construction (architecture.md-equivalent derivation, STORY-003
    test-cases.md TC-023):
      1. passband = white noise ~ N(0, passband_sigma), brickwall-filtered
         (FFT-zero above cutoff_hz) -- NOT peak-renormalized, sigma-controlled
         throughout so the dB ratio below is exact.
      2. floor = an independent (different seed), UNFILTERED, full-band white
         noise ~ N(0, floor_sigma) -- present above cutoff_hz too, unlike
         every other HF-extension fixture in this suite.
      3. audio = passband + floor.
      4. floor_sigma = passband_sigma * 10**(-floor_below_db/20).

    Derivation of the exact floor depth (by construction, not measurement):
    white noise's single-sided PSD is flat at sigma**2/(sr/2). Passband
    density = passband_sigma**2/(sr/2) + floor_sigma**2/(sr/2) (both present
    below cutoff) ~= passband_sigma**2/(sr/2) to within
    10*log10(1+10**(-floor_below_db/10)) -- negligible for floor_below_db>=20.
    Stopband density = floor_sigma**2/(sr/2) exactly (passband is exactly
    zero above cutoff_hz). Ratio: 20*log10(floor_sigma/passband_sigma) =
    -floor_below_db exactly, by the floor_sigma formula above -- the
    stopband sits floor_below_db dB below the passband/reference density,
    by construction."""
    n = int(round(duration_s * sr))
    rng = np.random.default_rng(seed)
    floor_sigma = passband_sigma * 10.0 ** (-floor_below_db / 20.0)

    passband_white = rng.normal(0.0, passband_sigma, n)
    spectrum = np.fft.rfft(passband_white)
    freqs = np.fft.rfftfreq(n, d=1.0 / sr)
    spectrum[freqs > cutoff_hz] = 0.0
    passband = np.fft.irfft(spectrum, n=n)

    rng_floor = np.random.default_rng(seed + 1000)
    floor = rng_floor.normal(0.0, floor_sigma, n)

    return passband + floor


def white_noise_mono(sr: int, duration_s: float, seed: int = 0, amplitude: float = 0.2) -> np.ndarray:
    """Plain full-band white noise -- symmetric with pink_noise_mono. Used
    for AC6c (no-cutoff negative control) and AC8b (equal-energy spectral
    balance)."""
    n = int(round(duration_s * sr))
    rng = np.random.default_rng(seed)
    return rng.normal(0.0, amplitude, n)


def band_limited_noise_mono(sr: int, duration_s: float, band_hz: tuple, seed: int = 0,
                             amplitude: float = 0.2, floor_amplitude: float = 0.001,
                             order: int = 8) -> np.ndarray:
    """Bandpassed noise confined to `band_hz`, summed with an independent
    low-amplitude broadband noise floor (required, not decorative -- without
    it every non-target seven-band power sits at the _MIN_POWER=1e-20 floor,
    making the "near-silent" comparison a floor/floor ratio). Used for AC8a.

    order=8/floor_amplitude=0.001 (NOT architecture.md's illustrative
    order=4/floor_amplitude=0.005 snippet -- test-cases.md TC-040 itself
    flags both as "not yet empirically verified," architecture.md Section
    10 risk #2) are the values empirically confirmed (STORY-003 QA pass) to
    keep the bandpass filter's own transition-band leakage into the
    immediately-adjacent "high" (5000-10000Hz) seven-band bin from eating
    into the required >=20dB dominance gap: at order=4, the measured gap to
    the nearest non-target band is only ~16.5-16.9dB regardless of
    floor_amplitude (the leakage is filter-slope-limited, not floor-noise-
    limited) -- order=8 restores a >=20dB gap with margin (measured
    ~20.4dB)."""
    from scipy.signal import butter, sosfiltfilt

    n = int(round(duration_s * sr))
    rng = np.random.default_rng(seed)
    sos = butter(order, band_hz, btype="band", fs=sr, output="sos")
    band = sosfiltfilt(sos, rng.normal(0.0, 1.0, n))
    band = band / (np.max(np.abs(band)) + 1e-12) * amplitude

    rng_floor = np.random.default_rng(seed + 1000)
    floor = rng_floor.normal(0.0, floor_amplitude, n)
    return band + floor


def inverted_stereo(mono: np.ndarray) -> np.ndarray:
    """L = mono, R = -mono -- exact rho=-1 stereo fixture. Used for AC9b/AC9d."""
    return np.stack([mono, -mono], axis=1)


def lowpassed_white_noise(sr: int, duration_s: float, cutoff_hz: float, seed: int = 0,
                           amplitude: float = 0.2, order: int = 8) -> np.ndarray:
    """White noise, steeply lowpassed at `cutoff_hz` via a zero-phase
    (sosfiltfilt) Butterworth filter -- per architecture.md TC-304's own
    derivation, using sosfiltfilt squares the magnitude response so the
    composite -6 dB point coincides exactly with the design cutoff."""
    from scipy.signal import butter, sosfiltfilt

    n = int(round(duration_s * sr))
    rng = np.random.default_rng(seed)
    white = rng.normal(0.0, 1.0, n)
    sos = butter(order, cutoff_hz, btype="low", fs=sr, output="sos")
    filtered = sosfiltfilt(sos, white)
    filtered = filtered / (np.max(np.abs(filtered)) + 1e-12) * amplitude
    return filtered


def mono_low_decorrelated_high_stereo(sr: int, duration_s: float, low_crossover_hz: float = 120.0,
                                       high_crossover_hz: float = 5000.0, seed: int = 0) -> np.ndarray:
    """Stereo fixture per TC-309: content below `low_crossover_hz` identical
    in L/R (mono); content above `high_crossover_hz` independently-generated
    decorrelated noise. Crossovers deliberately at clean seven-band edges
    (120Hz = sub/low boundary, 5000Hz = high/air boundary) so each asserted
    band's expected value is unambiguous, per test-cases.md TC-309's own
    rationale for avoiding architecture.md's illustrative-but-band-splitting
    200Hz example."""
    from scipy.signal import butter, sosfiltfilt

    n = int(round(duration_s * sr))
    rng = np.random.default_rng(seed)
    sos_low = butter(4, low_crossover_hz, btype="low", fs=sr, output="sos")
    sos_high = butter(4, high_crossover_hz, btype="high", fs=sr, output="sos")

    shared_low = sosfiltfilt(sos_low, rng.normal(0.0, 0.1, n))
    indep_high_l = sosfiltfilt(sos_high, rng.normal(0.0, 0.05, n))
    indep_high_r = sosfiltfilt(sos_high, rng.normal(0.0, 0.05, n))

    left = shared_low + indep_high_l
    right = shared_low + indep_high_r
    return np.stack([left, right], axis=1)


def calibrated_tone_mono(sr: int, duration_s: float, dbfs_rms: float, freq: float = 1000.0) -> np.ndarray:
    """Genuinely single-channel (1-D) calibration tone at the given RMS
    dBFS. Deliberately mono, not dual-mono-stereo: BS.1770's channel-SUMMED
    convention means a dual-mono (L=R) buffer at this same per-channel RMS
    reads ~+3.01 dB *higher* than this mono buffer does (confirmed by
    STORY-001's own existing test_tc010b) -- using mono here is what
    actually reproduces STORY-001 TC-010's own -20.0-LUFS-at-(-20dBFS)
    result, which is the calibration this helper (and AC6) is meant to
    verify. See STORY-002 defects.md for the corresponding test-cases.md
    finding (TC-270-273's "dual-mono stereo... -20.0 +/- 0.1 LU" precondition
    would NOT reproduce -20.0 LUFS if actually built dual-mono/stereo)."""
    amp = dbfs_to_amplitude(dbfs_rms) * (2 ** 0.5)  # peak amplitude for a sine at the given RMS dBFS
    return sine(freq, sr, duration_s, amplitude=amp)


def write_flac(path, audio: np.ndarray, sr: int, subtype: str = "PCM_24") -> str:
    sf.write(str(path), audio, sr, format="FLAC", subtype=subtype)
    return str(path)


def write_mp3_ffmpeg(path, audio: np.ndarray, sr: int, bitrate_kbps: int = 320, tmp_wav=None) -> str:
    """Encode to MP3 CBR at an exact bitrate via an ffmpeg subprocess (used
    only to *construct test fixtures*, not part of the code under test --
    reliable, exact-bitrate control unlike libsndfile's compression_level
    knob)."""
    path = Path(path)
    tmp_wav = Path(tmp_wav) if tmp_wav else path.with_suffix(".src.wav")
    sf.write(str(tmp_wav), audio, sr, subtype="PCM_24")
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(tmp_wav),
         "-codec:a", "libmp3lame", "-b:a", f"{bitrate_kbps}k", str(path)],
        check=True,
    )
    tmp_wav.unlink(missing_ok=True)
    return str(path)


def write_mp3_vbr_no_header(path, audio: np.ndarray, sr: int, tmp_wav=None) -> str:
    """VBR MP3 with no reliable average-bitrate tag -- best-effort
    'bitrate unknown' fixture for TC-253. -write_xing 0 suppresses the
    Xing/VBRI header ffmpeg would otherwise write for a VBR stream."""
    path = Path(path)
    tmp_wav = Path(tmp_wav) if tmp_wav else path.with_suffix(".src.wav")
    sf.write(str(tmp_wav), audio, sr, subtype="PCM_24")
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(tmp_wav),
         "-codec:a", "libmp3lame", "-q:a", "4", "-write_xing", "0", str(path)],
        check=True,
    )
    tmp_wav.unlink(missing_ok=True)
    return str(path)


def ref_config(**overrides) -> ReferenceAnalysisConfig:
    return dataclasses.replace(ReferenceAnalysisConfig(), **overrides)


def ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except Exception:
        return False
