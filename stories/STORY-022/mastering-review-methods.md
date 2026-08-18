# STORY-022 — Mastering-Engineer Gate 1 Review (Methods)

## Finding 1

- **Severity:** Blocker
- **What is proposed:** After strict bundle validation, assign the complete reconstruction residual to `other` for both four- and six-stem models, then use exact no-DSP re-summation as the identity check.
- **Why it fails, or under what conditions:** Name, count, shape, length, and finite-value validation says nothing about residual magnitude or content. Adding `input - sum(stems)` to `other` forces identity by construction, so the subsequent identity check is tautological and can pass even if separation is badly wrong. A large full-band residual can put drums, vocals, piano, or guitar back into `other`; in six-stem mode that directly weakens the promised piano/guitar isolation and makes later `other` DSP act on material assigned to explicit stems. It can also create stem-level peak or true-peak risk after validation. This is acceptable only as a bounded mixture-consistency correction, not as an unconditional reconstruction repair.
- **What to do instead:** Measure and report the residual before correction. Derive an acceptance limit from real Demucs outputs on representative programme material using at least residual peak and energy relative to the input, plus listening checks; reject or flag runs outside it. Apply any accepted mixture-consistency correction before stem DSP, then revalidate finite values and amplitude. Architect must justify why asymmetric assignment to `other` is preferable to a documented mixture-consistency projection for each model. Keep the original pre-correction residual metric; do not present post-correction identity as evidence of separation quality.

## Finding 2

- **Severity:** Note
- **What is proposed:** Map tensor indices through the selected model instance's ordered `model.sources`, require an exact unique source-name set for the registry contract, and emit stems in canonical registry order.
- **Why it fails, or under what conditions:** This is the correct protection against alternate valid source ordering and silent label swaps. Exact count, unique names, tensor shape, stereo channel count, sample length, and finite-value checks are appropriate contract gates for both four- and six-stem output.
- **What to do instead:** Accept this method. Keep model-reported source order in provenance alongside canonical output order, and retain a real installed-model smoke check because fake models cannot establish compatibility with the shipped Demucs/model versions.

## Finding 3

- **Severity:** Concern
- **What is proposed:** Dynamic source-name mapping and structural validation are treated as protection for real programme material.
- **Why it fails, or under what conditions:** They protect labels and bundle integrity, not musical semantics. A model can return the exact expected names and valid arrays while placing piano transients in `other`, guitar harmonics in vocals, or producing pumping and phasey leakage on dense electronic material. Synthetic fixtures and name checks cannot prove that piano/guitar isolation remains usable on real mixes.
- **What to do instead:** Keep structural validation as a hard gate, but describe it narrowly. Require representative real-programme evaluation of leakage, transient damage, phase stability, residual size, and re-summed sound before claiming the six-stem path is musically safe. Do not infer source quality from metadata correctness.

## Finding 4

- **Severity:** Blocker
- **What is proposed:** The active registry section describes four supported CLI models, exact four/six-stem contracts, strict output validation, and six-stem-aware reporting in the production separation boundary.
- **Why it fails, or under what conditions:** The current active CLI does not offer `htdemucs_6s`; `StemConfig` documents only the older four-stem path; and active separation hard-codes the four-name expected set. It does use `model.sources` for index mapping, but it does not validate the full returned tensor shape/count, finite stem values, or six-stem contracts before assigning residual. The revised section is therefore not a truthful description of current active behavior.
- **What to do instead:** Architect must mark the section as required production work until the active path implements the registry and validation contract. Six-stem release must remain blocked on a real `htdemucs_6s` source-list smoke check and representative programme-material review.

## Verdict

**BLOCKED.** Dynamic source-order mapping is sound, but current active code is still four-stem-only and unconditional residual assignment can hide a failed separation. Residual-to-`other` is conditionally acceptable for both model families only when bounded, reported, revalidated, and shown not to compromise the explicit stem semantics.

## Second Gate 1 review

**APPROVED FOR IMPLEMENTATION: WORKFLOW WIRING ONLY. NOT YET APPROVED AS A TUNED, CROSS-DEVICE-EQUIVALENT, OR MUSICALLY VALIDATED DEMUCS RELEASE PATH.**

Exact model-source mapping, exhaustive structural validation, and uncorrected
residual telemetry may proceed. No forced identity correction or residual
assignment to `other` is acceptable. Real `htdemucs_6s` compatibility, leakage,
transient, phase, residual, and listening evidence remains a release gate. There
is no remaining blocker to implementing the specified wiring contract.
