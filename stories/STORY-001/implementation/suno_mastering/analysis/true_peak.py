"""Custom oversampled true-peak metering (architecture.md Section 2: no
mature Python package implements ITU-R BS.1770-4 Annex 2 true-peak metering
directly).

v4 (DEF-002 residual resolution, defects.md): oversampling is a
purpose-built polyphase FIR interpolation filter
(`scipy.signal.firwin` design + `scipy.signal.upfirdn` application),
**not** `soxr`. `soxr` (and general-purpose resamplers generally) are
optimized for anti-aliased playback-rate conversion, which deliberately
pulls the passband cutoff in from Nyquist to leave transition-band margin --
the wrong optimization target for true-peak oversampling, where the
oversampled buffer is discarded after the peak search (never played back)
and near-Nyquist content is exactly the highest-risk region for
inter-sample peaks. This was the confirmed root cause of DEF-002's residual
TC-022 failure (soxr showing real, unavoidable-via-its-Python-binding
passband attenuation approaching Nyquist across all quality presets).
`soxr` remains in use elsewhere (`mastering/resample.py`, stage [3]'s
genuine format-rate conversion) -- unaffected by this change.

Method: oversample via a linear-phase Kaiser-windowed FIR lowpass
(`scipy.signal.firwin`) applied through `scipy.signal.upfirdn` (the standard
zero-stuff-and-filter polyphase interpolation approach), then take
max(abs(.)) of the oversampled buffer (excluding a small guard region --
see below). This is safety-critical (AC3: zero exceptions tolerated) -- see
architecture.md Section 9 risk #3: this is a `firwin`-designed
*approximation* of BS.1770 Annex 2's intent (not the standard's literal
published filter coefficients), and still needs cross-validation against a
known-good external true-peak meter (TC-024) before being fully trusted in
production.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import signal

_MIN_LINEAR = 1e-12

# --- FIR filter design parameters (v4) ---
#
# Two tuning attempts and their results, both numerically verified
# (2026-08-01, python-developer) -- kept here as the record of why the
# *symmetric*-cutoff design below was ultimately chosen over the
# more tempting "push cutoff past Nyquist" alternative:
#
# 1. cutoff=0.5 (exactly original Nyquist), numtaps=32x factor, beta=9.0
#    (the tuning this module originally shipped with). A single-frequency
#    freqz spot-check looked flat, but a full freqz SWEEP across the
#    passband shows real droop starting well before Nyquist (`firwin`'s
#    `cutoff` is the *center* of the transition band, not a hard passband
#    edge): ~0.02 dB by 0.85x Nyquist, ~0.4 dB by 0.9x, ~2 dB by 0.95x,
#    ~5.9 dB by 0.999x -- inside the architecture.md Section 7 target
#    (<0.01 dB) only up to ~0.8x Nyquist.
# 2. Attempted fix: push `cutoff` *above* Nyquist (edge_mult=1.15) so the
#    passband itself extends flat through 0.5. This DOES fix the passband
#    magnitude at the fundamental frequency (verified <0.002 dB ripple up
#    to 0.9998x Nyquist via freqz) -- but freqz alone is the wrong
#    instrument to verify an *interpolation* filter with: `upfirdn`'s
#    zero-stuffing before filtering creates a spectral image of the input
#    at (original_sample_rate - f) for every real input frequency f. As
#    f -> original Nyquist, that image frequency (1-f, in original-sr=1
#    normalized units) converges to the *same* frequency as f itself --
#    they become physically inseparable by any finite filter exactly at
#    Nyquist. Pushing `cutoff` (and therefore the filter's *stopband*,
#    which is what's supposed to reject that image) past Nyquist removes
#    exactly the rejection needed where the image is closest to the
#    fundamental, letting it leak through and beat with the fundamental in
#    the reconstructed time-domain signal -- verified this caused 5-6 dB
#    time-domain true-peak errors at 0.95-0.999x Nyquist (worse than either
#    tuning 1 or soxr), even though the frequency response alone looked
#    perfect. This is the actual, corrected root-cause understanding: a
#    linear-phase FIR interpolator's cutoff must stay centered AT (or
#    below) Nyquist for genuine image safety; you cannot have both
#    "flat magnitude response past Nyquist" and "adequate rejection of the
#    image that converges toward the same frequency" simultaneously.
#
# Given that hard physical constraint, achieving <0.01 dB ripple genuinely
# up to 0.999x Nyquist while keeping the image-rejecting (cutoff<=0.5)
# design requires an extremely narrow transition band -- verified via
# `scipy.signal.kaiserord` that this needs tens of thousands of taps
# (~40,000+ at factor=8 for an 80 dB-stopband, 0.999x-flat design), which
# is computationally infeasible within the 5-minute NFR processing budget
# (a single true-peak measurement on a representative 60s stereo buffer
# already costs ~1.1s at 257 taps vs ~4.3s at 1025 taps -- linear in
# numtaps, and the solver calls this dozens of times per run). Kept at
# numtaps=32x factor / beta=9.0 / cutoff=0.5 (image-safe, tuning 1 above) as
# the practical, safety-correct choice -- it measurably improves on soxr's
# documented ~0.54 dB droop at 94% Nyquist (this design: ~0.02 dB at 85%,
# ~0.4 dB at 90%, ~1.5 dB at 94%) but does NOT meet the aspirational
# <0.01 dB-to-0.999x-Nyquist target from architecture.md Section 7 above
# ~80-85% Nyquist. **Retagged Architectural in defects.md (DEF-002
# residual)** -- this is a genuine physical/compute-budget constraint, not
# a tuning oversight; see defects.md for the full write-up and options for
# software-architect to consider (e.g. relaxing the Section 7 target,
# increasing numtaps at the cost of processing time, or accepting this as
# a documented residual risk alongside Section 9 risk #3).
_FIR_TAPS_PER_FACTOR = 32
_FIR_KAISER_BETA = 9.0

_FIR_CACHE: dict[int, np.ndarray] = {}


def _design_fir(factor: int) -> np.ndarray:
    """Design (once, cached per factor) a linear-phase Kaiser-windowed FIR
    lowpass for `factor`x polyphase interpolation via upfirdn.

    Cutoff is placed at exactly the *original* Nyquist frequency -- see the
    tuning note above `_FIR_TAPS_PER_FACTOR` for why this (image-symmetric)
    placement is correct/necessary despite not being perfectly flat to
    Nyquist. Expressed via `firwin`'s explicit `fs=` argument: treating the
    original sample rate as 1.0 (Hz-equivalent, normalized) and the
    oversampled rate as `factor`, the original Nyquist is exactly 0.5 in
    those units.
    """
    if factor in _FIR_CACHE:
        return _FIR_CACHE[factor]

    numtaps = _FIR_TAPS_PER_FACTOR * factor
    if numtaps % 2 == 0:
        numtaps += 1  # odd length -> exact linear-phase symmetry, integer group delay

    fir = signal.firwin(
        numtaps, cutoff=0.5, fs=float(factor), window=("kaiser", _FIR_KAISER_BETA)
    )
    # upfirdn's zero-stuffing (inserting `factor - 1` zeros between samples
    # before convolution) reduces average energy by ~1/factor; compensate by
    # scaling the filter to unity gain at the oversampled rate (standard
    # polyphase-interpolation gain correction, same one scipy.signal.
    # resample_poly applies internally).
    fir = fir * factor

    _FIR_CACHE[factor] = fir
    return fir


@dataclass
class TruePeakResult:
    dbtp: float
    oversampled: np.ndarray  # kept for reuse by clipping.py (perf/consistency)


def oversample(audio: np.ndarray, sr: int, factor: int) -> np.ndarray:
    """Oversample audio by `factor` via a purpose-built polyphase FIR
    interpolation filter (firwin + upfirdn). Accepts mono (samples,) or
    multichannel (samples, channels) float arrays; returns the same layout
    at sr*factor."""
    if factor <= 1:
        return audio
    fir = _design_fir(factor)
    if audio.ndim == 1:
        return signal.upfirdn(fir, audio, up=factor)
    # upfirdn operates on a single 1-D signal at a time; apply per channel.
    channels = [signal.upfirdn(fir, audio[:, ch], up=factor) for ch in range(audio.shape[1])]
    return np.stack(channels, axis=1)


_EDGE_GUARD_MS = 5.0  # matches limiter.py's default lookahead window


def measure_true_peak_with_factor(audio: np.ndarray, sr: int, factor: int) -> TruePeakResult:
    """True-peak meter for a specific oversampling factor.

    Intended for internal solver use where we need an inexpensive provisional
    result before deciding whether to commit to the exact configured factor.
    """
    factor = max(1, int(factor))
    os_audio = oversample(audio, sr, factor)

    guard = int(round(sr * factor * (_EDGE_GUARD_MS / 1000.0)))
    if guard > 0 and os_audio.shape[0] > 2 * guard:
        scan_region = os_audio[guard:-guard]
    else:
        scan_region = os_audio

    peak_linear = float(max(scan_region.max(), -scan_region.min())) if scan_region.size else 0.0
    dbtp = 20.0 * np.log10(max(peak_linear, _MIN_LINEAR))
    return TruePeakResult(dbtp=dbtp, oversampled=os_audio)


def measure_true_peak(audio: np.ndarray, sr: int, config) -> TruePeakResult:
    # Respect config.true_peak_oversample_factor as given -- do NOT silently
    # clamp it to a minimum of 4x here. The BS.1770-4 Annex 2 >=4x floor is
    # enforced by config's own default (8x) and is a production/config
    # concern, not something this metering primitive should second-guess;
    # forcing a floor here previously made factor=1/2/4 all collapse to an
    # identical internal 4x oversample, which broke the oversampling-factor
    # sensitivity check (TC-022) that deliberately probes lower factors to
    # demonstrate *why* >=4x matters.
    factor = max(1, int(config.true_peak_oversample_factor))
    return measure_true_peak_with_factor(audio, sr, factor)

    # The oversampling filter's kernel (whether soxr's resampling filter, in
    # the pre-v4 implementation, or this FIR filter now) spans several dozen
    # to a few hundred oversampled-rate samples; near the very start/end of a
    # finite buffer that kernel only has real signal on one side (nothing
    # genuinely continues past the buffer edge), which can produce a
    # Gibbs-like edge transient read higher than the buffer's genuine
    # steady-state inter-sample peak (DEF-002). Padding the input before
    # oversampling was tried and rejected: any synthetic edge-extension
    # (replicate/reflect) itself introduces a *different* discontinuity
    # relative to the real (unknown) continuation, so it does not reliably
    # converge to the true value either -- verified empirically against the
    # BS.1770-style reference construction in test-cases.md TC-020 (edge-
    # replicate padding still read ~0.6 dB high, reflect-padding ~0.95 dB
    # high, regardless of pad length). Excluding a small guard region
    # directly from the peak scan (rather than trying to "correct" it) is
    # what actually converges to the correct value. A tight ~5ms guard
    # (rather than a generous 10%) keeps this from meaningfully blinding
    # real track-boundary content, at the cost of a small, bounded
    # theoretical risk of missing a genuine inter-sample-over within the
    # first/last ~5ms of a track -- an accepted, documented trade-off (see
    # defects.md DEF-002 fix notes) rather than a false-positive risk. This
    # guard comfortably covers the v4 FIR filter's own group delay (at
    # factor=8, ~128 samples at the oversampled rate vs. a ~1764-sample
    # guard) as well.
    guard = int(round(sr * factor * (_EDGE_GUARD_MS / 1000.0)))
    if guard > 0 and os_audio.shape[0] > 2 * guard:
        scan_region = os_audio[guard:-guard]
    else:
        scan_region = os_audio

    # DEF-103 fix (STORY-002 architecture.md Section 7.1): avoid allocating a
    # full-size float64 abs() copy of scan_region -- max(x)/min(x) are
    # in-place reductions and max(abs(x)) over a real array == max(max(x), -min(x)).
    peak_linear = float(max(scan_region.max(), -scan_region.min())) if scan_region.size else 0.0
    dbtp = 20.0 * np.log10(max(peak_linear, _MIN_LINEAR))
    # `oversampled` is still returned in full (untrimmed) for clipping.py's
    # inter-sample-over scan, which counts overs across the whole buffer
    # rather than relying on a single global max -- a handful of edge-guard
    # samples reading slightly high there is a much lower-stakes false
    # positive than the true-peak *ceiling* metering this function owns.
    return TruePeakResult(dbtp=dbtp, oversampled=os_audio)
