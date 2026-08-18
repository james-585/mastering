# STORY-020 — Architecture: Demucs inference parameter optimization

## Pipeline placement
Insert immediately around the Demucs inference call, before the optional stem-processing stages, so that all parameter choices are made at the source-separation boundary.

## Design decisions
- This story is performance-only; it does not alter the mastering algorithm itself.
- The tuning harness should be deterministic, reproducible, and built around fixed fixtures and measured output.
- All tuning results must be logged as artifact-quality trade-offs rather than opaque default behavior.

## Business analyst confirmation

- Story intent: benchmark Demucs inference parameters only—shifts, overlap, and segment length—without touching the mastering DSP path or adding hidden pre-processing.
- Benchmark surface: runtime, peak memory, artifact score, invalid-profile rejection, and default-profile selection across a fixed deterministic fixture set.
- Scope limit: no changes to loudness, EQ, transient, stereo width, or final mastering logic; this remains a pre-separation tuning harness.
- Acceptance criteria: a valid configuration must produce explicit runtime/memory/artifact metrics; unstable or invalid profiles are rejected before defaulting; repeated runs must remain stable; and the default profile must be explicit and versioned.
- Ambiguity check: none material remained after requirements review. The story remains strictly an inference-parameter optimization story and does not drift into mastering DSP work.

## Safety gates and benchmark contract
- Input audio must be finite float64 stereo data; otherwise the benchmark returns `status="rejected"` with a failure reason.
- Profile validation rejects any config whose shift count, overlap, or segment length violates the explicit contract.
- Benchmark output must include `status`, `failure_reason`, `runtime_s`, `peak_memory_mb`, `artifact_score`, `sample_rate`, and `signal_peak`.
- A configuration is only eligible for default selection if it passes the stability and safety gate and records acceptable cost/quality trade-offs.
- Default profile selection is explicit and versioned; there is no hidden fall-through to a magic constant.

## Module boundaries
- Module: `demucs_tuning.py`
- Public API:
  - `benchmark_demucs_config(input_audio, sample_rate, config) -> BenchmarkResult`
  - `select_default_demucs_profile(fixture_reports) -> dict`
- Helper functions:
  - `_run_inference_once()`
  - `_measure_memory()`
  - `_measure_runtime()`
  - `_artifact_score()`

## Data contract
- Each tuning profile includes: shift count, overlap, segment length, and output settings.
- Results must include quality score, runtime, memory peak, and failure classification.
- Output cannot be accepted if it introduces clipping or unstable phase behavior.

## Library choices
- `numpy` and `time` for benchmark measurement
- `psutil` or equivalent runtime memory introspection if available
- Demucs remains the source-separation engine

## Implementation constraints
- The default configuration must be explicit and versioned.
- Tuning should not be hidden in a single global constant.
- Any configuration that fails the signal-safety gate must not become a default path.

## Gate 1 review (mastering engineer)

**Verdict:** PASS-ON-SCOPE

- The tuning surface is correctly limited to Demucs inference settings—shift count, overlap, and segment length—without altering the mastering logic or any downstream DSP path.
- The artifact score and runtime/memory measurements reflect real trade-offs the workflow can report and audit, rather than placeholder values.
- The design correctly treats unstable phase or non-finite output as a rejection condition, which matches the project’s float64 and no-silent-clipping safety rules.
- The default profile logic is explicit and versioned, which is the correct way to preserve reproducibility in a local-only CLI workflow.
- No blocker was identified in the proposed architecture as specified; the story is acceptable to proceed into implementation.

## Review disposition (mastering engineer)
- Accepted as-is: the tuning stays entirely in the Demucs pre-separation boundary and does not touch the mastering chain.
- Accepted as-is: runtime, memory, and artifact score are all explicit outputs that can be reported in CLI or JSON without hidden defaults.
- Accepted as-is: the safety gate rejects non-finite output, clipping risk, and unstable phase behavior before a profile can become default.
- Action item: keep the default profile versioned and logged with the exact shift/overlap/segment values used in each run.
- Action item: when a candidate is rejected, record the precise failure reason in the benchmark result so the audit trail remains clear.
- Action item: retain deterministic fixtures and compare repeated runs within the configured tolerance to preserve reproducibility on the same hardware.

## Required production contract: CLI integration

When implemented, `StemConfig` owns the live run-only inference profile with explicit defaults:
`shifts=1`, `overlap=0.25`, `segment_seconds=None`, and
`profile_version="demucs-default-v1"`. These are the upstream-compatible
defaults, not quality-optimal values inferred from the synthetic tuning harness.
No segment override is active until a real Demucs fixture benchmark supports it.

`cli.py` decodes nested JSON `stem_config` data into `StemConfig`, then merges
only explicit CLI overrides into the existing object. It exposes model, shifts,
overlap, segment-seconds, and profile-version controls. Changing a run control
requires an explicit non-empty profile version so reports cannot misidentify a
modified profile as the default.

`run_stem_preprocessing` passes the complete `StemConfig` unchanged to the
separation boundary. The live `apply_model` call uses explicit keyword arguments:
`device`, `shifts`, `overlap`, `segment`, `split=True`, and `progress=False`.
Run-only controls do not participate in model-cache identity.

The compatibility profile does not promise bit-identical output. Runtime
provenance records RNG state or seed where available, deterministic-backend
settings, Demucs/Torch/model/device/profile versions, and the model's resolved
effective segment behavior. Repeatability claims require measured tolerances on
representative programme material; structural fake tests prove wiring only.

Validation rejects boolean or sub-one shifts, non-finite overlap outside
`[0.0, 1.0)`, a non-positive/non-finite segment duration, an empty profile
version, non-finite/non-stereo audio, and a non-positive sample rate before
model lookup. Tests inject fake Torch, loader, and apply functions to prove exact
argument pass-through without claiming Demucs performance or separation quality.

## Business-analysis blocker disposition

The environment has no Demucs installation, so it cannot support a tuned segment
override or performance claim. This blocks promotion of a new optimized profile,
but not explicit workflow wiring. `segment_seconds=None` therefore preserves the
model default, while the compatibility profile remains versioned and reportable.
The harness value `segment_length=4096` is sample-domain test data and must never
be passed directly to Demucs as a duration.

## Gate 1 follow-up disposition

- Accepted with revision: `shifts=1`, `overlap=0.25`, and no segment override
  are an untuned compatibility profile, not a deterministic or optimized one.
- Changed: the integration section is a required production contract until the
  active package and focused tests implement it.
- Deferred to release evidence: real repeatability, artifact, runtime, and memory
  claims remain blocked until measured with installed Demucs on programme audio.

## Revision history
- 2026-08-17: Initial architecture for the Demucs parameter-tuning story.
- 2026-08-17: Added business-analyst confirmation, explicit safety gate contract, and mastering-review disposition for the inference-only tuning path.
- 2026-08-17: Defined active CLI profile ownership, upstream-compatible defaults, exact inference arguments, validation, and the no-Demucs blocker disposition.
- 2026-08-17: Dispositioned mastering review by narrowing reproducibility claims, requiring full run provenance, and marking integration as required production work.
