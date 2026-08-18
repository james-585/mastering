# STORY-002: Reference track analysis — deriving real targets

## User Story
As a producer, I want to measure a set of commercially released
reference tracks that represent the sound I am aiming for, so that my
mastering targets are derived from real records in my genre rather
than generic streaming compliance numbers.

## Why this comes before more processing features
Hitting -14 LUFS and -1 dBTP proves a master is *compliant*, not that
it is *good*. A record that measures correctly can still sound flat,
harsh, or thin next to a commercial release. This story establishes
what "good" actually measures like for deep/melodic progressive house
and melodic techno, so that every subsequent processing story has a
real target to aim at.

## Builds on
STORY-001 (stories/STORY-001/) — reuses the existing analysis stage.
Modify stories/STORY-001/implementation/ directly; do not create a
separate implementation folder or duplicate analysis logic.

## Scope
Analysis and reporting only. This story changes no audio and adds no
processing. Its output is measurements.

## Reference set

Commercially released records in the target genre (Anjunadeep, Lost &
Found and similar) that represent the sound being aimed for. These
define what a professionally produced record in this style measures
like.

## Source format handling — this materially affects the results

Reference files may be lossless (WAV/FLAC) or lossy (MP3). The tool
must detect which, record it against every measurement, and handle the
difference explicitly:

- **High-frequency extension must NOT be reported as a target from a
  lossy source.** MP3 encoders apply their own lowpass (roughly 20 kHz
  at 320 kbps, lower at lower bitrates), so measuring a lossy file
  reports the encoder's cutoff, not the mastering engineer's decision.
  Flag or exclude these from the HF aggregate.
- **True peak from a lossy source is approximate.** Decoding
  introduces inter-sample peaks not present in the original master, so
  dBTP will read high. Flag accordingly.
- **Loudness, loudness range, crest factor, spectral balance and
  stereo width are reliable from 320 kbps MP3** and can be aggregated
  normally.

The report must make source format visible per track, so a target
derived largely from lossy files is never mistaken for a clean one.

Source Suno material is WAV — the asymmetry is on the reference side
only.

## Requirements

Given a folder of reference audio files, measure each and produce a
comparison report covering:

- **Integrated loudness** (LUFS, ITU-R BS.1770)
- **Loudness range** (LRA) — how much the loudness varies across the
  track, which matters more than peak dynamics for long-form material
- **True peak** (dBTP, oversampled — not sample peak)
- **Crest factor / dynamic range**
- **Spectral balance** — energy distributed across bands (sub, low,
  low-mid, mid, high-mid, high, air), expressed so two tracks can be
  compared directly
- **High-frequency extension** — where the spectrum effectively rolls
  off, and whether that cutoff is stable across the track
- **Stereo width** — correlation coefficient, and per-band width
  (a wide top end with a mono low end is the normal target)
- **Mono compatibility** — level change and any cancellation when
  summed to mono

The report must also produce **aggregate statistics across the whole
reference set** (median and range for each measurement), since a
single record is not a target — the territory the set occupies is.

## Acceptance criteria
1. Given a folder of reference tracks, the tool measures every file
   and reports all metrics above per track
2. The tool produces aggregate statistics (median, min, max) across
   the set for each metric
3. The tool can measure a Suno export using the identical code path
   and present it side by side against the reference aggregate, so
   the gap is directly visible
4. Source format (lossless vs lossy, and bitrate where applicable) is
   detected and reported alongside every track's measurements
5. High-frequency extension measurements from lossy sources are
   excluded from or explicitly flagged in the aggregate
6. Loudness measurement is verifiable against a known-loudness test
   signal to within ±0.1 LU
7. True peak measurement uses oversampled detection and is
   demonstrably different from sample peak on a signal engineered to
   have inter-sample peaks
8. Analysis does not modify or overwrite any input file
9. Output is both human-readable and machine-readable (so later
   stories can consume the targets programmatically)

## Non-functional
- Full-track analysis is inherently slower than synthetic-signal
  tests; analysis of a 7-minute track should still complete in
  seconds, not minutes
- Must handle 44.1 kHz and 48 kHz, mono and stereo, WAV and FLAC

## Notes
- Reference material: contemporary deep/melodic progressive house and
  melodic techno — Anjunadeep, Lost & Found, and similar. Long-form
  (7+ min) tracks where dynamics carry the build, not
  loudness-war festival masters.
- These are commercially released tracks being measured for private
  analysis. The tool reads and measures them; it does not reproduce,
  redistribute, or derive audio from them.
- The reference set should be 5+ tracks. A single record's
  measurements are not a target — outliers exist in every catalogue.
- Lossless references (WAV/FLAC from Beatport or Bandcamp) are
  strongly preferred. Even two or three lossless tracks alongside
  lossy ones is enough to establish a trustworthy HF picture.

## Open questions
- Which specific tracks form the commercial reference set? (Needs to
  be chosen before meaningful aggregate targets can be derived.)
- Should the reference set be split by sub-style (e.g. hypnotic/
  minimal vs driving/melodic), given these may have measurably
  different dynamics profiles?
