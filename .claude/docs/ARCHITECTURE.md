# Target Architecture

Stage boundaries and contracts. Story-level architecture.md files must
conform to this; where they conflict, this document wins.

---

## 1. Principles

1. **Stages are independently testable.** Each takes defined input, returns
   defined output, no hidden state.
2. **Targets are data, never code.** No spectral or dynamics constant
   appears in mastering source or config. All are read from the reference
   aggregate.
3. **Analysis and processing are separate.** Analysis never modifies audio.
   Processing never decides its own targets.
4. **The mix boundary is preserved.** The mastering stage consumes *a stereo
   mix*, not *a file*. Today one file provides it. Later a stem-sum stage
   may. This costs nothing now and avoids a rewrite later.
5. **Float64 internally, convert only at I/O.**

---

## 2. Pipeline

```
                    ┌──────────────────────┐
  reference files ─►│  ANALYSIS            │─► per-track measurements
                    │  (measure only)      │
                    └──────────┬───────────┘
                               ▼
                    ┌──────────────────────┐
                    │  TARGET DERIVATION   │─► targets.json
                    │  (aggregate subset)  │
                    └──────────┬───────────┘
                               │
  ┌─────────────┐              │
  │ MIX SOURCE  │              │   ← stem-sum stage may replace this later
  │ (stereo in) │              │
  └──────┬──────┘              │
         ▼                     ▼
  ┌──────────────────────────────────────┐
  │  ANALYSIS (same code path)           │─► source measurements
  └──────────────────┬───────────────────┘
                     ▼
  ┌──────────────────────────────────────┐
  │  MASTERING CHAIN                     │
  │  EQ → dynamics → loudness → dither   │
  └──────────────────┬───────────────────┘
                     ▼
  ┌──────────────────────────────────────┐
  │  ANALYSIS (same code path)           │─► post measurements
  └──────────────────┬───────────────────┘
                     ▼
              mastering report + output WAV
```

**Analysis appears three times and must be the same code.** If reference,
pre-master, and post-master measurements come from different paths, they are
not comparable and the entire target mechanism is void.

---

## 3. Stage contracts

### 3.1 MIX SOURCE

```
Input:   path to audio file
Output:  AudioBuffer
Guarantee: sample rate preserved; never resamples silently; input read-only
```

```python
@dataclass(frozen=True)
class AudioBuffer:
    samples: np.ndarray      # float64, shape (n_samples, n_channels)
    sample_rate: int
    source_path: Path
    source_format: str       # "wav" | "flac" | "mp3"
    is_lossless: bool
```

Shape is **always 2-D**, even for mono `(n, 1)`. No stage may accept both
1-D and 2-D.

**Extension point**: a future stem-sum stage returns the same `AudioBuffer`.
No downstream stage may assume it came from a single file.

### 3.2 ANALYSIS

```
Input:   AudioBuffer
Output:  Measurements
Guarantee: pure — no mutation, no I/O, deterministic
```

Fields: `integrated_lufs`, `true_peak_dbtp`, `sample_peak_dbfs`,
`dynamic_range_tt`, `lra_lu`, `seven_band_relative_db`,
`overall_correlation`, `per_band_width`, `mono_sum_level_change_db`,
`hf_band_limit_hz` (nullable), `hf_band_limit_confidence`,
`plausibility_warnings`.

Mandatory:
- `sample_peak_dbfs` and `true_peak_dbtp` are **both** reported. They must
  differ on inter-sample-peak content — this is the self-check that true
  peak is implemented.
- `hf_band_limit_hz` is **nullable**. No cliff found → `None`, never a
  fallback value.
- `plausibility_warnings` is populated by the H5 gate and appears in every
  report.

### 3.3 TARGET DERIVATION

```
Input:   list[Measurements], subset selector
Output:  Targets  →  targets.json
Guarantee: only subset-flagged tracks contribute; contributors recorded
```

```python
@dataclass(frozen=True)
class Targets:
    dynamic_range_tt: TargetRange        # hard
    seven_band_relative_db: dict[str, TargetRange]   # soft, max ±2 dB
    integrated_lufs: float               # NOT derived — fixed −13.5
    true_peak_ceiling_dbtp: float        # NOT derived — fixed −1.0
    lra_lu: TargetRange                  # guidance only
    contributing_tracks: list[str]
    excluded_tracks: list[str]
    derived_at: datetime

@dataclass(frozen=True)
class TargetRange:
    median: float
    min: float
    max: float
    is_hard_target: bool
    max_correction_db: float | None
```

**Every target carries its range.** A bare median is prohibited — it is what
allowed correction toward a shape no reference has.

`integrated_lufs` and `true_peak_ceiling_dbtp` are deliberately not derived.
See `CLAUDE.md` §4.2.

### 3.4 MASTERING CHAIN

```
Input:   AudioBuffer, Targets
Output:  AudioBuffer, list[CorrectiveAction]
Guarantee: no target constants in code or config; all from Targets
```

Order is fixed (see `DOMAIN.md` §5): corrective EQ → dynamics → loudness and
limiting → dither.

- Loudness measured **after** limiting
- Dither last, once, at final bit-depth reduction only
- Spectral correction applies only when source is **outside** the target
  range, and only to the nearest edge, capped at `max_correction_db`
- Every action recorded in `CorrectiveAction` with before/after values

**Prohibited**: any numeric spectral or dynamics target in this stage's
source or config. If `Targets` is unavailable, fail loudly — do not fall
back to defaults.

### 3.5 REPORTING

```
Input:   pre Measurements, post Measurements, Targets, actions
Output:  markdown report + machine-readable JSON
```

Must state: contributing and excluded reference tracks; target ranges, not
just medians; all plausibility warnings; input and output hashes; which
measurements are report-only vs target-setting.

---

## 4. Extension points

| Point | Purpose | Cost now |
|---|---|---|
| `MIX SOURCE` returns `AudioBuffer` | Stem-sum stage can replace file load without touching downstream | Zero — a dataclass |
| `Targets` carries ranges | Soft correction, per-band policy | Zero |
| `hf_band_limit_hz` nullable | Honest "no cutoff found" | Zero |
| `Measurements` is a flat dataclass | New metrics added without breaking consumers | Zero |

Design for these now. **Do not implement stem processing** — it is out of
scope per `CLAUDE.md` §2.

---

## 5. Verification requirements

Per `HANDOFF.md` H2/H3/H4, each stage must have:

| Stage | Ground truth | Negative control | Derived constants |
|---|---|---|---|
| MIX SOURCE | Known-content file round-trips unchanged | Unsupported format raises | — |
| ANALYSIS: loudness | BS.1770 signal → known LUFS ±0.1 | — | K-weighting per standard |
| ANALYSIS: true peak | Inter-sample-peak signal → true > sample | Sine at bin centre → true ≈ sample | Oversample factor ≥4 |
| ANALYSIS: band limit | Noise cut at 15 kHz → ~15 kHz | **Full-band pink noise → None** | Cliff slope ≥24 dB/oct |
| ANALYSIS: correlation | Identical → 1.0; inverted → −1.0 | Slightly decorrelated → not 1.0 | — |
| ANALYSIS: mono sum | ρ=0 → −3.01 dB (derive) | ρ=1 → 0 dB | −3.01 dB, derivation shown |
| ANALYSIS: spectral | Single-band noise → that band dominates | Energy at band edge → correct band | Band edges |
| TARGET DERIVATION | Known inputs → known median/range | Excluded track does not shift result | — |
| MASTERING: EQ | Known imbalance → corrected within cap | **In-range source → no correction** | From Targets only |
| MASTERING: loudness | Known input → target ±0.1 LU | Already at target → minimal gain | −13.5 LUFS |
| MASTERING: limiting | Peaks above ceiling → at/below | Below ceiling → untouched | −1.0 dBTP |

The two bolded negative controls are the ones whose absence caused shipped
defects.
