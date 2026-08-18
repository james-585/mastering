# Audio Domain Reference

Authored by the mastering engineer. This is the shared factual basis for
every agent. Where this document and an agent's assumption disagree, this
document wins.

Purpose: stop each story rediscovering the same audio facts and avoid
repeating the project’s earlier mistakes.

---

## 1. Measurement definitions — these are not interchangeable

| Term | Definition | Common error |
|---|---|---|
| **Sample peak** | `max(abs(x))` on the sample values | Reported as true peak |
| **True peak (dBTP)** | Peak of the reconstructed continuous waveform. Requires ≥4× (prefer 8×) oversampling | Computed as sample peak |
| **RMS** | Root mean square level | Reported as loudness |
| **LUFS** | K-weighted, gated loudness per ITU-R BS.1770 | Substituted with RMS |
| **LRA** | Loudness range — spread of short-term loudness across a track, gated | Computed as peak-to-trough of the whole file, ungated |
| **TT DR** | Crest-factor-based dynamic range (TT meter algorithm) | Conflated with LRA |
| **Correlation** | Phase relationship between left and right channels, range [−1, 1] | Conflated with width |
| **Stem** | A separated source signal such as drums, bass, vocals, or accompaniment | Treated as a generic mix element without its own profile |

**Sample peak and true peak must return different values** on a signal with
inter-sample peak behaviour. If they match, the true-peak calculation is not
implemented correctly.

---

## 2. Spectra of real programme material

**Music has a naturally declining spectrum**, roughly −3 to −6 dB/octave
above the low mids, steeper on dark or heavily filtered material.

This fact invalidates threshold-based band-limit detection. On a dark record,
a fixed threshold can be crossed by ordinary programme tilt, which is not a
band limit.

**Band limits are cliffs, not slopes.** A codec or generation limit leaves a
near-vertical wall: sustained ≥24 dB/octave across adjacent bins, followed by a
floor. Detect the wall.

**A band limit is a fixed property of a file.** It does not vary across the
track. A detector reporting a varying cutoff is measuring programme content or
a broken method.

### Expected band limits by source

| Source | Band limit |
|---|---|
| CD master / lossless release | ~20–22 kHz |
| MP3 320 kbps | ~20 kHz |
| MP3 256 kbps | ~19 kHz |
| MP3 192 kbps | ~18 kHz |
| MP3 128 kbps | ~16 kHz |
| Suno / generative export | ~13–16 kHz, may drift within one file |

**Any reported cutoff below ~10 kHz on a commercial release is a measurement
error.** No commercial master cuts there.

---

## 3. Plausibility ranges

Use these to sanity-check output. Values outside them are suspect until
explained.

### Loudness by era

| Era / style | Integrated LUFS | TT DR |
|---|---|---|
| Mid-90s CD master | −14 to −17 | DR12–16 |
| Loudness-war era (~2000–2012) | −6 to −9 | DR5–8 |
| Contemporary streaming-aware | −9 to −14 | DR8–12 |

Outside −20 to −5 LUFS on commercial material: scrutinise.

### Dynamics
- DR < 5 — severe limiting
- DR > 16 — unusual outside classical or ambient material
- LRA on club-oriented electronic material: typically 3–8 LU; values above 15
  usually indicate structural dynamics or measurement contamination

### Stereo
- Overall correlation on commercial electronic material: 0.5–0.9
- Correlation < 0: significant out-of-phase content, usually audible as a problem
- Sub and low bands near-mono (width < 0.15) on club material — deliberate
- **Mono-sum level change for normal stereo: around −3 dB**

### Mono summing — derivation

Summing to mono as `(L + R) / 2`:

- **Identical channels (ρ = 1.0)**: sum = L, level change **0 dB**
- **Uncorrelated equal power (ρ = 0.0)**: powers add, amplitude halves →
  level change **−3.01 dB**
- **Inverted (ρ = −1.0)**: complete cancellation → **−∞ dB**

The −3.01 dB value is the correct floor for normal uncorrelated stereo. A
reported −6.02 dB is not the correct stereo-floor assumption; it arises from an
incorrect derivation.

### Spectral (relative to mid band, 500–2000 Hz)
- low and low_mid: within roughly ±9 dB
- progressive fall through high_mid, high, air is normal
- air band 10–25 dB below mid is normal, not a defect

---

## 4. What mastering can and cannot fix

### Can
- Integrated loudness and true peak
- Broad tonal balance — shelves and wide bells, small gains
- Dynamics control and glue
- Stereo width on the sum when appropriate
- Consistency across a body of work
- Per-stem treatment when valid stems are available
- Stem-aware loudness, transient shaping, and width control

### Cannot — do not attempt or promise
| Problem | Why |
|---|---|
| Transient smearing / metallic cymbals | Fast attack was never rendered; information is absent, not masked. |
| Content above the band limit | Silence. A shelf boost mostly amplifies the noise floor. |
| Baked-in ambience or reverb | Requires source information or stem separation, not broadband EQ. |
| Kick/bass masking or buried element balancing | Requires per-element access. The sum does not retain that data. |
| Source recovery from a final stereo mix | The missing information is not present in the stereo sum. |
| Arbitrary “fix everything” repairs from one stereo file | The file is not a full mix representation at the element level. |

**Requirements implying any of these must be rejected at requirements stage.**

### Narrow exception — confirmed whistle artifacts (2026-08-16)

The "Cannot" table above is the general rule for processing based on a
spectral-balance target. It does not cover artifact removal at a
**machine-confirmed coordinate**. `suno_dsp`'s `repair_whistles` may notch
specific frequencies only when they come from a detector as a confirmed
`STATIONARY_WHISTLE` flag, never from arbitrary user-specified or hardcoded
frequencies. See CLAUDE.md §4.2a for the authoritative rule.

This exception applies only to the specific whistle-removal workflow. It does
not extend to general notching, broad EQ, or per-element source repair.

---

## 5. Why stems are now a first-class product tool

The project now explicitly prefers stem-aware workflows when the signal is
available. This changes the product’s realistic ceiling for improvement.

### Historical C++ note

Older C++ / CMake build artifacts in this repository are historical
experiment scaffolding, not a required product path. They do not define the
product identity, do not represent the active mastering workflow, and must not
be treated as a customer-facing feature set. The product is judged by
Python-first stem-aware mastering behavior, not by C++ build presence.

### With valid stems, we can meaningfully improve:
- drum attack and punch
- bass articulation and control
- vocal clarity and comfort
- bright synths without adding fatigue
- ambience and pad width without fake stereo
- mix depth and emotional feel

### Without valid stems, we must be conservative:
- broad tonal correction only
- gentle width adjustments on the sum
- loudness and peak control
- modest dynamic glue
- clear reporting that this is a limited, not reconstructive, process

This distinction is critical. A master on stems is a real mastering tool. A
master on a stereo sum only is a limited corrective pass.

---

## 6. Correction discipline

**Correct toward agreement, not toward a median.** Where reference tracks
disagree by more than ~4 dB in a band, the median is a shape no real record
has. Correcting hard toward it makes the master worse.

Rule: report the target **range**. Correct only where the source falls outside
that range and only enough to approach the nearest edge.

**Chain order matters:**
1. Corrective EQ or targeted stem EQ
2. Stem-specific transient or harshness correction
3. Stereo width and depth decisions on the correct signal domain
4. Dynamics / glue
5. Loudness and limiting
6. Dither — **last, once, at final bit-depth reduction only**

Loudness is measured *after* limiting, never before.

---

## 7. Streaming normalisation

Platforms normalise playback: Spotify ~−14 LUFS, Apple Music ~−16, YouTube
~−14. A louder master is turned down, which discards the extra loudness and
often preserves the damage from over-limiting.

**Consequence**: mastering to the reference set’s −8.5 LUFS would be
counterproductive. The project targets streaming-aware values, not raw reference
loudness. This is a product choice, not a mistake.

**Consequence for listening tests**: A/B against raw reference masters will
sound quieter unless the listening level is matched.

---

## 8. Product quality benchmark

A successful result is not merely a file that is technically within bounds.
It must also feel:
- more defined
- less artificial
- more controlled
- less fatiguing
- more real and dimensional

This is especially true for stem-aware work. The final output should be
audibly better to the human ear and not just numerically cleaner on a report.

---

## 9. Correction strategy for the stem-first product

The stem-first mastering workflow uses the following logic:

1. Separate or identify actual stems
2. Measure each stem for tone, width, and transient behaviour
3. Correct the actual problem in the actual stem
4. Keep correction local and conservative
5. Recombine stems with bus glue and final safety processing
6. Report the before/after effect by stem and by final mix

This makes the mastering chain realistic and defensible. It also keeps the
project aligned with its real product goal: make generated music feel more
musical and less synthetic, without pretending it can recover information that
was never there.
