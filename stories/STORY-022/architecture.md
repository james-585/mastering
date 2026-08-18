# STORY-022 — Architecture: 6-stem HTDemucs extraction

## Pipeline placement
Insert as a model-selection branch in the stem separation stage. As of 2026-08-17, `htdemucs_6s` is the product default for stem separation (see revision history); the four-stem models remain available as explicit overrides.

## Business analyst confirmation

- Story intent: support `htdemucs_6s` as an explicit optional branch so piano and guitar are isolated as semantic outputs instead of being silently folded into `other`.
- Stem contract: the product must preserve the existing 4-stem path and add a distinct 6-stem contract with the exact ordered names `drums`, `bass`, `other`, `vocals`, `piano`, `guitar`.
- Acceptance criteria: a valid 6-stem bundle is accepted only when all six names are present; partial/incomplete bundles are rejected before mastering; recombination remains mathematically deterministic and identity-safe; and the model selection is logged with its semantic mapping.
- Scope limit: this is a model-selection and validation branch only; it does not rewrite the mastering DSP path, add cloud processing, or broaden the pipeline beyond the explicit stem-hand-off contract.
- Ambiguity check: no material ambiguity remains around the 6-stem semantics, the 4-stem path, or the required validation gate. The story is clearly scoped to the optional 6-stem extraction branch and does not turn into a general overhaul of the whole pipeline.

## Design decisions
- The architecture must support both the legacy 4-stem contract and the new 6-stem contract.
- Piano and guitar are explicit tracked outputs, not silent collapses into `other`.
- Re-summing logic must be deterministic and must validate shape, sample count, and channel consistency before the signal is handed off to mastering.
- 6-stem validation must happen before any mastering path proceeds so incomplete or invalid bundles fail loudly and early.

## Module boundaries
- Module: `stem_model_registry.py`
- Public API:
  - `resolve_model(model_name) -> dict`
  - `split_stems(audio, sr, model_name)`
  - `recombine_stems(stems, mode)`
- Helper functions:
  - `_validate_stem_count()`
  - `_map_6stem_names()`
  - `_final_sum_guard()`

## Data contract
- 4-stem mode: drums, bass, other, vocals
- 6-stem mode: drums, bass, other, vocals, piano, guitar
- Each stem bundle must carry its semantic name and exact sample count.
- Partial bundles are invalid and must raise a clear error instead of being silently merged.

## Library choices
- `demucs` runtime and model registry
- `numpy` for validation and recombination checks
- `soundfile` only at I/O boundaries

## Implementation constraints
- Must not silently push a 6-stem result into a 4-stem contract.
- Must keep float64 internal math and explicit safety checks.
- Must not claim source recovery beyond the real separated signal.

## Gate 1 review (mastering engineer)

**Verdict:** PASS-ON-SCOPE

- The 6-stem branch is correctly scoped as an optional model-selection pathway and does not replace the legacy four-stem flow; that preserves the existing contract while enabling the more detailed extraction path when explicitly requested.
- The semantic mapping is plausible and correct for HTDemucs 6-stem output: `piano` and `guitar` are explicit, real outputs rather than hidden `other` content, which matches the product’s stem-first goals and the requirements for precise musical correction.
- The guardrail to reject incomplete 6-stem bundles before the mastering path proceeds is the correct safety design; allowing partial bundles to pass would create ambiguous reconstruction and hidden signal loss.
- Deterministic recombination with an identity check on the full six-stem bundle is the correct way to validate that the re-summed signal is faithful to the original under the configured tolerance, while the 4-stem path remains distinct and explicit.
- The architecture remains compliant with the project’s local-only, CLI-first, no-cloud, no-GUI constraints and does not broaden into a hidden source-recovery feature.

## Review disposition (mastering engineer)
- Accepted as-is: the 6-stem model remains an explicit optional branch rather than a silent replacement of the legacy 4-stem path.
- Accepted as-is: piano and guitar are treated as semantically real outputs and must remain distinct from `other` through validation and reporting.
- Accepted as-is: partial six-stem bundles are rejected before any mastering signal processing begins, which prevents ambiguous output and hidden loss.
- Accepted as-is: deterministic recombination and the bypass identity check are valid safety gates for the six-stem contract.
- Action item: keep the exact stem names and count visible in the resolved model metadata and any generated report.
- Action item: enforce sample-count, shape, channel, and name matching before the pipeline allows a 6-stem bundle to proceed.
- Action item: keep all arithmetic in float64 until the final I/O boundary and fail loudly on any non-finite or clipping-prone output.

## Required production contract: model registry and validation

`StemConfig.model_name` and `--stem-model` accept `htdemucs`, `htdemucs_ft`,
`mdx_extra`, and `htdemucs_6s`. `io/stem_separation.py` owns the production model
registry: the first three models require `drums`, `bass`, `other`, `vocals`, and
`htdemucs_6s` additionally requires `piano` and `guitar`.

Tensor indices are mapped using the selected model instance's ordered
`model.sources`, never an assumed index order. The actual source-name set must
exactly match the selected registry contract, while the returned dictionary and
report use canonical registry order. Alternate valid model source ordering is
therefore mapped correctly instead of mislabeled.

Validation runs immediately after inference and before residual handling, stem
DSP, fallback decisions, or reporting success. It requires shape
`(1, expected_stems, 2, input_samples)`, unique and exact semantic names,
float64 stereo arrays with matching sample counts, and finite values. Missing,
extra, duplicate, mono, length-mismatched, or non-finite outputs fail loudly and
do not trigger CPU fallback.

After validation, the uncorrected reconstruction residual is measured and reported
without changing any stem. Residual peak and energy relative to the input are
quality telemetry, not proof of separation quality and not a fabricated identity
pass. No stem receives an asymmetric correction until real programme-derived
acceptance bounds and a mixture-consistency method pass architecture and mastering
review. Piano and
guitar may pass through when no dedicated DSP policy applies, but they are never
dropped, folded into `other`, or omitted from summing and reporting.

Fake-model tests cover valid four/six-stem bundles, alternate source order, all
invalid bundle forms, and deterministic recombination. A real
`htdemucs_6s.model.sources` smoke check remains a release dependency-compatibility
check because Demucs is not installed in the current environment.

## Gate 1 follow-up disposition

- Accepted as-is: exact `model.sources` set/order mapping and structural output
  validation protect semantic labels and bundle integrity.
- Changed: unconditional residual assignment to `other` is removed; original
  residual metrics are retained and stems remain unmodified before DSP.
- Accepted with limitation: structural validation does not establish separation
  quality on programme material.
- Deferred to release evidence: installed-model source smoke checks, leakage,
  transient, phase, residual, and listening evaluation remain required before
  claiming the six-stem path is musically validated.
- Changed: the registry section is a required production contract until implemented.

## Revision history
- 2026-08-17: Initial architecture for the 6-stem model path.
- 2026-08-17: Added business-analyst confirmation and mastering-review disposition for the explicit 6-stem contract and validation guardrails.
- 2026-08-17: Defined active CLI registry ownership, source-order-safe mapping, dynamic validation, recombination, and no-Demucs compatibility checks.
- 2026-08-17: Dispositioned mastering review by removing forced residual correction, retaining uncorrected telemetry, narrowing quality claims, and marking integration as required production work.
- 2026-08-17: Product decision (owner): `htdemucs_6s` is now the default model for stem separation — `StemConfig.model_name` defaults to `htdemucs_6s` and `master_track.bat` passes `--stem-model htdemucs_6s` explicitly. The four-stem models (`htdemucs`, `htdemucs_ft`, `mdx_extra`) remain valid explicit overrides. This supersedes the earlier "four-stem default" statement; the 6-stem contract, validation gates, and review dispositions above are unchanged.
