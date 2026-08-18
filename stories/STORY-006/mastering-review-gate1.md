# Mastering-Engineer Gate 1 Review — STORY-006
Reviewer: mastering-engineer
Date: 2026-08-10

## 1. Reference subset — which tracks contribute to targets

Three tracks contribute: **Black Flute (Remastered)**, **GusGus — Over (Arabian Horse)**, and **Chemical Brothers — Live Again**.

Leftfield — Melt (−15.62 LUFS, DR14.86) and Wavy Gravy (−13.11 LUFS, DR13.91) are excluded. Both are mid-90s masters with loudness 5–7 dB quieter than the modern subset and dynamic range nearly double. Including them produces a five-track range of 8 dB in loudness and DR6.6–14.9 — a span that describes no consistent aesthetic. The resulting medians would describe a record that does not exist in the set. They remain in the reference set for listening context only and must not contribute to any computed target.

This matches CLAUDE.md §4.1 exactly.

The JSON aggregates provided to downstream agents currently include all five tracks. Those aggregates are wrong for target derivation and must not be used. Every downstream target computation must be derived from the three-track subset only, with that provenance stated explicitly in the report.

---

## 2. What mastering alone can and cannot achieve on Suno material

### Can address

**Integrated loudness.** Bring to −13.5 LUFS. This is not reference-derived — the three reference tracks sit at −7.56 to −8.70 LUFS, which streaming platforms normalise down to ~−14 LUFS, wasting the dynamics in the process. −13.5 LUFS is the correct streaming-aware target.

**True peak.** Apply a −1.0 dBTP ceiling. All three target-derivation references exceed 0 dBTP (+0.52 to +0.68 dBTP), which is normal for commercial masters of their era but creates clip risk in lossy transcode. Our Suno masters should be more conservative.

**Dynamic range.** Compression and limiting can target DR8.3 (three-track median; range 6.60–8.65). The subset agrees tightly enough here for this to be a hard target.

**Broad tonal balance.** Shelves and wide-bell EQ at small gains (max ±2 dB) can nudge the Suno track toward the reference range on any band where it falls outside. "Toward the range" — not toward a single median — because the reference set disagrees by far more than 4 dB on every band.

**Stereo width.** Width on the sum can be adjusted. Suno material tends to be narrower in sub and low bands, which aligns with deliberate practice on club material. Width in mid and high bands may be widened slightly if the source is unusually mono. Report first; correct only on explicit requirement.

**Consistency.** If multiple Suno tracks are being mastered, targets applied consistently will help them sit together as a body of work.

### Cannot address — do not attempt or promise

**Content above the generation band limit.** Suno generates to approximately 12–14 kHz based on the HF extension measurements (caveated below). Everything above that limit is silence, not attenuated programme material. A high-shelf boost above the cutoff raises only the noise floor. No information is recovered.

**Transient smearing and metallic cymbal artifacts.** These arise because the generative model never rendered fast-attack transients correctly. The information was not masked — it was never produced. No compressor, limiter, or transient shaper at the mastering stage can reconstruct what was never encoded.

**Baked-in reverb and ambience.** Suno's model bakes its spatial rendering into the stereo sum. Removing or reducing it requires source separation, which is outside project scope (CLAUDE.md §2) and not solvable at acceptable quality on a stereo mixdown.

**Per-element balance.** Kick-to-bass relationship, vocal level, relative element loudness — these require per-element access. At the stereo sum stage they are inextricably combined.

### What the listener will still hear as Suno after mastering

The 12–14 kHz band limit is audible as a characteristic dullness in the top octave and a lack of air compared to studio-recorded material (where HF extension reaches 20–22 kHz). Loudness-matching the master to a studio reference will make this contrast more audible, not less. Stereo width and DR can be aligned, but the frequency ceiling remains a permanent marker of the generative source.

---

## 3. Recommended corrective approach and target constraints

### Hard targets (apply to every master)

| Metric | Target | Source |
|---|---|---|
| Integrated loudness | −13.5 LUFS | Fixed — streaming-aware, per CLAUDE.md §4.2 |
| True peak | −1.0 dBTP ceiling | Fixed — lossy transcode headroom |
| Dynamic range (TT DR) | DR8.3 (range 6.60–8.65) | 3-track subset: 8.26, 8.65, 6.60 |

### Guidance-only (report; do not correct without explicit requirement)

| Metric | 3-track range | Notes |
|---|---|---|
| LRA | 3.21–12.20 LU | Subset spans 9 LU. No single target is defensible. |
| Stereo width | Per-band — see below | Report deviation from sub-band near-mono convention |
| HF extension | ~12–15 kHz (unreliable — see below) | Report only; not validated to target-setting precision |

### Spectral balance — ranges, not medians

Every band in the three-track subset disagrees by more than 4 dB. Per DOMAIN.md §5: "where references disagree by more than ~4 dB in a band, the median is a shape no record has." The targets below are **ranges** only. The Suno source must be corrected only if it falls outside the range; never corrected toward the median within it; and never corrected by more than ±2 dB in a single pass.

| Band | Range (3-track subset) | Span | Correction appropriate? |
|---|---|---|---|
| sub (20–60 Hz) | −3.75 to +1.94 dB | 5.7 dB | Soft nudge only if outside range; max ±2 dB |
| low (60–120 Hz) | +0.47 to +8.62 dB | 8.2 dB | Range too wide for meaningful correction. Report only. |
| low_mid (120–500 Hz) | −0.15 to +8.52 dB | 8.7 dB | Range too wide. Report only. |
| high_mid (2000–5000 Hz) | −1.24 to −13.41 dB | 12.2 dB | Range too wide. Do not correct. GusGus and Black Flute are aesthetically opposite in this band. |
| high (5000–10000 Hz) | −4.06 to −17.06 dB | 13.0 dB | Do not correct. 13 dB spread is not a target; it is three different records. |
| air (10000–24000 Hz) | −11.44 to −20.05 dB | 8.6 dB | Report only. Near-Nyquist metering caveat also applies here. |

The high_mid and high bands have a 12–13 dB spread driven by the contrast between GusGus (extremely dark, heavily low-passed at ~12 kHz) and Black Flute (relatively bright for the genre). These tracks represent genuinely different tonal aesthetics, not measurement error. Any requirement to correct Suno material to a "target" in these bands is targeting a position that none of the references occupy.

### Stereo width observations

Sub and low bands on the three target-derivation tracks are near-mono: sub widths 0.001–0.04, low widths 0.001–0.15. This is correct practice for club material and should be the expectation for Suno masters. If a Suno track has unusually wide sub or low bands, narrowing to near-mono on those bands is appropriate.

Wavy Gravy's air-band width of 0.73 is anomalous. That track is excluded from target derivation, but the value warrants notice: if air-band content is mostly noise floor, uncorrelated noise reads as high width. This is measurement artefact, not useful signal.

### Chain order

Per DOMAIN.md §5, order must be: corrective EQ → dynamics/glue → loudness and limiting → dither (last, once, at final bit-depth reduction only). Loudness is measured after limiting.

---

## 4. Permanent unfixable gap

**HF ceiling.** The three target-derivation tracks measure HF rolloff at approximately 12–15 kHz (GusGus 12066 Hz, Chemical Brothers 12775 Hz, Black Flute 14653 Hz — all subject to the method caveat below). Assuming the band limit is approximately correct, everything above it in Suno material is absence. High-shelf EQ above the cutoff adds only noise floor. No mastering process restores absent content. The listener will hear the top octave (15–20 kHz) as empty relative to a studio-recorded reference.

**Transient character.** Suno's generative rendering produces characteristic transient artifacts — smeared attacks, metallic or synthetic cymbal character. These arise from the model's limitations at fast-attack rendering. The information was not encoded to begin with. Transient shapers and parallel compression at the mastering stage cannot reconstruct what was never there; they can only change the envelope of what is present.

**Spatial bake.** The reverb tail, room character, and width relationships between elements are baked into the stereo sum at generation time. They cannot be adjusted per-element at mastering stage.

**Per-element relationships.** If Suno renders a kick and bass that mask each other, or a vocal that is 3 dB too loud, the mastering stage has no mechanism to address it. The sum is the sum.

---

## 5. Constraints this places on STORY-006 requirements.md

### Must not promise

- Restoration or improvement of content above Suno's generation band limit
- Removal or reduction of transient smearing or synthetic artifact character
- Removal of baked-in reverb or ambience
- Per-element level adjustment of any kind
- A spectral target in any single band for high_mid or high — the reference set disagrees by 12–13 dB in those bands
- LRA targeting — the reference subset spans 9 LU

### Hard limits that must be respected

- Integrated loudness target: −13.5 LUFS (not derived from references, not adjustable to "match" the references at −8.5 LUFS)
- True peak ceiling: −1.0 dBTP
- Dynamic range target: DR8.3, range 6.60–8.65 (three-track subset; state provenance)
- Spectral correction maximum: ±2 dB per band; correction only when source falls outside the stated range; never toward a median
- All spectral targets reported as ranges with provenance (three tracks named)
- Five-track JSON aggregates must not be used for target derivation — three-track subset only

### HF extension measurement — method concern requiring architecture attention

All five tracks in the reference set report `stable=False` for HF extension, with per-segment variation of 2–9 kHz within single files. A band limit is a fixed property of a file — it cannot vary across segments (CLAUDE.md §5, DOMAIN.md §2). The reported instability is measuring programme content (spectral tilt), not an actual band limit. The rolloff_hz values are therefore unreliable as written.

Leftfield — Melt reports a rolloff_hz of 8170 Hz with a segment reading of 5131 Hz. No commercial CD master cuts at 5 kHz. This is a measurement error, not a property of the track.

This is a method problem inherited from prior stories (CLAUDE.md §5 explicitly names threshold-based band-limit detection as a known-wrong pattern that caused DEF-201 twice). HF extension is currently status "Report only" per CLAUDE.md §4.2, which is the right call precisely because this method is unreliable. Requirements.md must not elevate HF extension to a hard target or a correction input without a validated cliff-detection method replacing the current threshold-based one.

This finding should be raised as a defect by qa-automation-engineer — it is a recurrence of the DEF-201 method error across the reference analysis.
