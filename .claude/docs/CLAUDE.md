# Suno Mastering Tool — Project Context

**Read this file before doing anything else in this repository.** It records
standing decisions. Do not relitigate them, do not contradict them, and do
not silently deviate. If a decision here blocks a task, raise it as an
`Architectural` defect rather than working around it.

---

## 1. What this project is

A local Python-first mastering and cleanup tool for Suno-generated audio,
with a stem-first workflow built around explicit upstream stems when they are
available. When the source already contains valid separated stems, the product
must use them as the primary signal domain. Stereo-only processing remains a
fallback mode for degraded or single-file inputs, not the default product
strategy.

### Historical C++ status

The repository contains historical C++ and CMake scaffolding from an earlier
experimental DSP path, including `CMakeLists.txt` and `src_cpp/`. This is not
part of the active product strategy. The active product remains Python-first
and CLI-oriented. C++ is only considered if profiling proves a demonstrated
bottleneck in a real production workflow; it is not a feature requirement for
this project and must not be treated as a deliverable in current story work.

This project is aimed at real musical improvement, not just metric compliance:
- better transient realism
- reduced fatigue and harshness
- more natural stereo depth and width
- stronger tonal shape without over-processing
- controlled loudness and true-peak safety

**Owner**: James. Single developer, local-only, Windows.

---

## 2. Product intent and scope

The project is intentionally built for generated music cleanup and mastering,
not generic plugin hosting or cloud mastering. The product is local-only,
CLI-oriented, and designed to work in a batch workflow.

### In scope
- Local audio analysis and mastering
- HTDemucs-based stem extraction from a stereo source where the workflow
  explicitly uses stems
- Per-stem corrective EQ, de-haze, transient shaping, width control, and bus
  glue
- Before/after reporting that explains what changed and why
- Loudness/true-peak safety with measured reference targets

### Out of scope
- VST3 / AU plugin hosting
- Cloud mastering APIs or model-hosted services
- Real-time processing
- GUI-first design as the core product shape
- Fake “magic fixes” that claim to recover lost source information
- Source separation from stereo as a silent or hidden fallback without an
  explicit upstream stem workflow

---

## 3. Central design principle

**The product must prefer stems when they exist.**

A stem-first mastering workflow is not just convenient; it is the route to
musical realism. The mix is broken into its real signal components: drums,
bass, vocals, synths/pads, ambience, and accompaniment. Each stem can be
corrected with more specificity than a single stereo sum allows.

This is the core product direction for the coming phase of the project.

### What this means in practice
- HTDemucs and equivalent upstream stem workflows are valid and preferred when
  available.
- Per-stem processing is acceptable and encouraged where the signal is truly
  separate.
- Stereo-only master processing remains acceptable as a fallback for single-file
  or degraded inputs, but it is not the primary product design.
- The product must not claim to recover missing information that was never in
  the source. It may only correct measured deficits in the actual signal.

---

## 4. Realistic engineering constraints

### 4.1 Stem-first product rule

When valid stems are available, the master should operate on them.
Examples:
- restore transient attack on drums without over-brightening the whole mix
- reduce harshness on a vocal stem without dulling synths or pads
- preserve center stability on bass and lead vocals while widening ambience
- reduce fatigue by fixing the specific stem causing the issue

This is the correct product direction for the sound the project now wants to
achieve: more resolution, cleaner transients, natural width, less fatigue,
and more believable depth.

### 4.2 Stereo-only fallback rule

Stereo-only mastering remains valid only when:
- the input is already a finished stereo file
- no valid stems are available
- the workflow is explicitly a fallback mode
- the operation is clearly described as a limited correction pass rather than a
  full reconstructive master

A stereo-only pass may still do useful work, but it must be framed honestly as
limited by the information present in the mix sum.

### 4.3 No magical source recovery

The project must not promise or imply:
- per-element repair from a stereo sum alone
- re-creating missing source detail that was never captured
- removing baked-in ambience or source-stage artifact from a finished mix
- source separation from a stereo mix as a hidden feature of the master chain

Any requirement that implies these outcomes must be rejected at the
requirements stage.

---

## 5. Product quality goals

The project target is not merely “pass a compliance metric.” The target is a
musically credible result.

### Important quality goals
- more resolution and better transient definition
- cleaner attack without brittle, over-sharp top end
- more natural width and spatial depth
- less listening fatigue
- stronger tonal control without flattening the mix
- greater dynamic presence and musical control

### This means
- metrics are necessary, but not sufficient
- the real product value is perceived musical quality
- a technically compliant but musically flat output is not a success

---

## 6. Standing decisions

### 6.1 Reference set

Five tracks measured. **Only three derive targets** (the modern-mastered
subset):

| Track | LUFS | DR | Role |
|---|---|---|---|
| GusGus — Over (Arabian Horse) | −7.56 | DR7 | Target derivation |
| Black Flute (Remastered) | −8.70 | DR8 | Target derivation |
| Chemical Brothers — Live Again | −8.53 | DR9 | Target derivation |
| Leftfield — Melt | −15.62 | DR15 | Listening only — EXCLUDED |
| Wavy Gravy | −13.11 | DR14 | Listening only — EXCLUDED |

Leftfield and Wavy Gravy stay in the reference set for reporting and
listening. They do not contribute to target derivation.

### 6.2 Targeting policy

| Metric | Status | Rationale |
|---|---|---|
| Dynamic range (TT DR) | Hard target with a reference-derived floor and range | Practical and repeatable |
| Integrated loudness | Streaming-aware target, not a blind reference match | Avoids wasted gain and excessive limiting |
| True peak | Fixed ceiling with oversampling | Safety for lossy playback |
| Spectral balance | Soft correction within a reference range | Avoids forcing a median no real record occupies |
| Stereo width | Guidance and stem-aware decisions | Must be natural, not fake |
| HF extension | Report-only unless justified by the actual signal | Do not overfit to metadata or fixed assumptions |

Spectral targets are reported as a range, not a single median. Deviation
within the reference span is acceptable and should not be forced to zero.

### 6.3 Loudness A/B caveat

Level-matching is mandatory before comparing a mastered result to a reference.
A target chosen for streaming and safety may sound quieter than the reference
when heard locally without matching levels.

---

## 7. Known-wrong patterns — do not reintroduce

These caused real defects and must not return.

| Pattern | Why it fails | Correct approach |
|---|---|---|
| Threshold-based band-limit detection | Music has naturally declining energy; fixed thresholds are wrong on real material | Detect sustained cliffs and actual band-limit evidence |
| Asserting a baseline constant without derivation | Wrong assumptions create incorrect gain and correction logic | Derive every constant and verify it against synthetic cases |
| `np.max(np.abs(x))` for true peak | That is sample peak, not true peak | Use oversampled metering and verify on inter-sample-peak signals |
| `librosa.load` without `sr=None` | Resampling destroys the signal being measured | Use `soundfile` or explicit `sr=None` when required |
| Hardcoded round-number targets | Placeholder values survive in production | Read targets from the reference aggregate |
| Fixing a wrong method by tuning its parameter | The method remains wrong | Replace the method when the root cause is wrong |
| Reporting a fixed property as varying | A fixed file property should not vary across a track | Treat instability as evidence the detector is wrong |
| Blanket global correction on one stereo sum | It ignores actual signal structure and creates false fixes | Prefer stem-aware, local correction when stems are available |

---

## 8. Implementation rules for the new direction

### 8.1 Stem-first default

The default workflow should be:
1. ingest stereo file
2. separate into stems when required or when the workflow indicates stems are
   available
3. analyze the stems individually
4. apply targeted per-stem corrections
5. recombine with bus glue and final safety stage
6. report before/after by stem and by full mix

### 8.2 Only repair what is actually there

Corrections must be evidence-driven and conservative.
- If a problem is broad and musical, use a broad correction
- If a problem is narrow and resonant, use a narrow correction
- If the signal is already good, do not change it
- If the issue is impossible to fix from the available source, say so clearly

### 8.3 No broad dulling or “fix everything” processing

Do not use a single blanket EQ or limiter as the product’s main identity.
The product is not a generic loudness bot or a magical enhancer. It is a
controlled, localized, musical correction and mastering tool.

### 8.4 Final quality is the real test

The product must improve the actual listening experience, not just the report.
A result that obeys all metrics but sounds flat, harsh, or lifeless is not a
successful master.

---

## 9. Agent pipeline

The repo’s agent pattern still applies. The project now explicitly values
stem-aware design and musical realism, but the process remains the same:

```
business-analyst → software-architect → mastering-engineer (Gate 1)
      → {python-developer, test-case-writer} → qa-automation-engineer
      → mastering-engineer (Gate 2) → QA raises defects
```

- **mastering-engineer reviews only.** Never writes code, tests, or architecture.
- **qa-automation-engineer is the only agent that creates or closes defects.**
- Gate 1 blockers must be resolved in architecture.md before implementation.
- Gate 2 blockers must become defect entries.

See `docs/HANDOFF.md` for the full protocol and the definition of done.
