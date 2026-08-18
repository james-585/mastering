# STORY-011 — Architecture: stem-aware transient restoration

## Pipeline placement
Insert immediately after stem separation and stem analysis, before final bus glue and loudness/true-peak safety.

The order is:
1. ingest
2. optional stem separation (HTDemucs, if valid stems are present)
3. stem analysis and issue detection
4. transient restoration per stem
5. de-haze / harshness control per stem
6. stereo width and depth control per stem
7. final bus glue
8. loudness / true peak safety
9. export and report

## Design decisions
- The algorithm operates on each stem individually and never on the summed mix as a primary correction path.
- The stage is evidence-based: a local attack deficit metric must exceed a threshold before any gain is applied.
- The restoration is local to the onset region and intentionally capped to avoid broad dynamic distortion.
- Final mix assembly is performed from corrected stems, not from a globally boosted stereo sum.
- The stage emits a structured action record with stem name, reason, gain, and evidence metrics.
- Hot-but-legal stems (peak in (0.98, 1.0]) never abort the pipeline; their gain is deterministically clamped to the available onset headroom, or the stem is returned unchanged with a report-visible action. See "Headroom-management contract" below.

## Module boundaries
- Module: `transient_restoration.py`
- Public API (signature UNCHANGED by the DEF-011-01 revision):
  `apply_stem_transient_restoration(stems: dict[str, np.ndarray], sample_rate: int) -> tuple[dict[str, np.ndarray], list[TransientRestorationAction]]`
- Helper functions:
  - `_coerce_stems()` — normalise channel layout and dtype to float64.
  - `_local_attack_score()` — compute a local onset-attack score from the stem envelope. The Hilbert envelope MUST be computed along the sample axis for both 1-D and 2-D inputs — see "Bundled correctness fix: Hilbert transform axis (DEF-011-02)".
  - `_stem_severity()` — convert the attack evidence into a conservative stem-specific severity score.
  - `_apply_transient_gain()` — apply a band-limited, onset-local gain shape to the stem through the tapered gain envelope specified in "Gain-envelope specification" (Hann fade-out at the window edge; no leading taper).
  - `_input_legality_guard()` — fail loudly only when a stem's input sample peak exceeds ±1.0 (corrupt/illegal input in a float64 pipeline).
  - `_headroom_clamp()` — compute the maximum gain dB whose conservative post-gain onset-peak bound stays at or below the 0.98 clamp ceiling.
  - `_clip_guard()` — fail loudly if the corrected signal exceeds ±1.0 without explicit allowance. Retained as a defensive invariant check; unreachable while the output `np.clip` remains in place.

## Data contract
- Input sample arrays must be float64, shape (samples,) or (samples, channels), with channels either 1 or 2.
- Output arrays maintain the same shape, dtype, and sample rate as the input.
- A no-op stem (no deficit, or gain clamped to zero) must be returned unchanged, not replaced with a modified copy.
- The stage is stem-count- and stem-name-agnostic: it iterates `dict[str, np.ndarray]` and applies identical per-stem semantics for the 4-stem `htdemucs` bundle and the 6-stem `htdemucs_6s` bundle (STORY-022). Unknown stem names (e.g. `piano`, `guitar`) use the existing default severity threshold; no per-name special-casing is added for headroom handling.

### Action record (public contract — changed by the DEF-011-01 revision and the 2026-08-17 gate-1 amendments)

```python
@dataclass
class TransientRestorationAction:
    stem_name: str
    action_type: str          # "attack_boost" | "attack_boost_headroom_clamped" | "skipped_headroom"
    gain_db: float            # APPLIED gain; 0.0 when skipped
    requested_gain_db: float  # pre-clamp gain from the severity mapping; equals gain_db when unclamped
    onset_peak_before: float  # sample peak of the onset window before gain
    onset_peak_after: float   # MEASURED onset-window peak after applied gain (measured, not predicted — see F2 disposition)
    global_peak_before: float # NEW (gate-1 F5) — sample peak over the entire stem before processing
    reason: str
    severity: float
```

- `action_type="attack_boost"`: requested gain applied in full (`requested_gain_db == gain_db`).
- `action_type="attack_boost_headroom_clamped"`: gain reduced by the headroom clamp; `reason` must state both requested and applied gain.
- `action_type="skipped_headroom"`: clamp yielded ≤ 0 dB; stem returned unchanged; `gain_db=0.0`, `requested_gain_db` records what would have been applied; `reason` must state the onset-window peak and that the stem was returned unchanged.
- `global_peak_before` is always populated (one `np.max(np.abs(arr))` over the pre-gain stem). Its purpose is report context: it lets a reader distinguish "stem hot everywhere, skip obviously correct" from "only the onset is hot" without re-measuring.
- Reason-string conventions (report visibility):
  - clamped: `"<stem action>: requested {requested:.2f} dB, applied {applied:.2f} dB after onset headroom clamp (ceiling 0.98)"`
  - skipped: `"<stem action> skipped: onset-window peak {p:.4f} leaves no headroom below the 0.98 ceiling; stem returned unchanged"`
- **Reporting rule (gate-1 F1):** 0.98 is a *sample-peak* ceiling, not a true-peak guarantee — a stem at 0.98 sample peak can exceed 0 dBTP under oversampled measurement. No reason string or report text may describe a clamped stem as "true-peak safe". True-peak ownership remains with stage 8 (loudness / true-peak safety).

## Library choices
- `numpy` for array operations and gain conversion.
- `scipy.signal.hilbert` for analytic envelope estimation in the local attack metric — MUST be called with `axis=0` (transform along samples) for the project's (samples, channels) layout; see "Bundled correctness fix: Hilbert transform axis (DEF-011-02)".
- `soundfile` is permitted at I/O boundaries for WAV/FLAC read/write; not used for internal processing.
- `librosa` is not required, and the project must not use `librosa.load(..., sr=...)` because that silently resamples. The code should either use `soundfile` or keep `sr=None` if a librosa path is ever introduced.
- No VST/AU host, no cloud APIs, no GUI code.

## Implementation constraints
- All internal calculations use float64, including attack estimation and gain shaping.
- The stage must be default-off from a pipeline orchestration standpoint until a stem-specific deficit has been identified.
- The restoration must never claim to restore absent source information; it only amplifies or reshapes what is actually present.
- For any operation that can push signal beyond ±1.0, the code must raise a ValueError or log a hard failure to avoid silent clipping.
- The true-peak check must utilize oversampling and not rely on `np.max(np.abs(x))`.
- Envelope/transform operations on stem arrays must run along the sample axis (axis 0 for (samples, channels) layout), never across the channel axis.

## Headroom-management contract (added 2026-08-17, resolves DEF-011-01; revised 2026-08-17 per gate-1 review gate1-review-clamp-2026-08-17.md)

This section replaces the undocumented 0.98 sample-peak abort with a
deterministic clamp-then-report contract. It is the authoritative safety
contract for this stage.

### Derivation of the constants (H4)

- **Hard bound 1.0**: digital full scale. Internally float64, but integer
  conversion at the I/O boundary clips at ±1.0; any sample beyond ±1.0 is a
  defect, not headroom. This is the `_clip_guard` bound and needs no
  empirical derivation.
- **Conservative predictability of the post-gain onset peak**: the
  restoration gain is applied through a shaped gain envelope over a single
  window `W = min(n_samples, max(32, int(0.08 * sample_rate)))` samples
  (`n_samples` is the length of the sample axis — `arr.shape[0]` for 2-D —
  never `arr.size`). Every envelope value lies in `[1, g_lin]` where
  `g_lin = 10^(g_applied/20)` (see "Gain-envelope specification"), so the
  post-gain onset peak is bounded — exactly computable before any sample is
  modified — by `p_onset * 10^(g_applied/20)`. Under the original uniform
  (rectangular) envelope this was an equality; the Hann fade-out adopted
  per gate-1 finding F2 makes it a conservative upper bound. The clamp
  remains deterministic: it is a pure function of (onset-window peak,
  requested gain), and the envelope is a pure function of (W, T, g_applied).
  `onset_peak_after` is recorded as measured, not predicted.
- **Clamp ceiling 0.98**: margin `M = -20*log10(0.98) ≈ 0.175 dB` below full
  scale. The margin absorbs float rounding at the clip boundary and nothing
  else. In particular it does **not** — and cannot — absorb re-sum peak
  growth at bus glue: worst-case coherent re-sum of two stems clamped at
  0.98 with coincident same-sign onsets peaks at 1.96 (+6.02 dB), and four
  coherent stems would reach +12 dB. Coincident onsets are ordinary: all
  stems share the same window (the first 80 ms of the file) and, on material
  starting on a downbeat, drum and bass onsets separated from the same kick
  transient are correlated by construction. No per-stem ceiling margin can
  bound that growth.

  The ceiling is nonetheless safe because the load-bearing fact is
  different: **the intermediate chain is float64 end to end, integer
  conversion happens only at final I/O boundaries (CLAUDE.md hard
  constraint), and stage 8 (loudness / true-peak safety) owns the
  −1.0 dBTP ceiling with oversampled metering.** In a float64 intermediate,
  a re-summed bus momentarily above 1.0 is level, not clipping; the final
  safety stage measures it and turns it down.

  Under that invariant the per-stem ceiling's real jobs are only:
  (a) **per-stem legality margin** — keeping each stem individually legal
  for any per-stem integer export or per-stem clip check; and
  (b) **bounding injected crest** — limiting how much extra peak energy
  this stage adds. For those jobs 0.98 is harmless conservatism. The value
  0.98 is retained as already present in the implementation (H6 — no
  re-derivation without cause); only the derivation was wrong, and it is
  corrected here per gate-1 finding F1.

  **Invariant requirement:** no stage between transient restoration and the
  final loudness/true-peak safety stage may perform integer conversion or a
  ±1.0 clip. If any stage ever does, this ceiling must be re-derived in
  this document against the true re-sum bound (+6.02 dB per coincident stem
  pair), not tuned in code.

### Raise conditions (complete and exhaustive)

The stage raises `ValueError` only when:
1. `sample_rate <= 0` (existing).
2. Any stem's **input** sample peak > 1.0 — corrupt/illegal input; fail
   loudly per CLAUDE.md. The error must name the stem and the measured peak.
3. Any **output** stem peak > 1.0 after processing — defensive `_clip_guard`
   invariant; unreachable while the output `np.clip` remains in place.

The stage must **never** raise for an input peak in (0.98, 1.0]. A
near-full-scale stem is ordinary programme material: stems are partially
uncorrelated, so an individual stem peak legitimately exceeds the re-summed
mix peak.

### Clamp algorithm (implement verbatim)

For each stem, after the severity mapping yields requested gain `g_req`:
1. `W = min(n_samples, max(32, int(0.08 * sample_rate)))` — the same window
   the gain will be applied to.
2. `p_onset = max(abs(arr[:W]))` over all channels (scalar).
3. If `g_req <= 0`: return the stem unchanged; emit no action (existing
   no-op behaviour).
4. `headroom_db = 20*log10(0.98 / p_onset)` if `p_onset > 0` else `+inf`.
5. `g_applied = min(g_req, headroom_db)`.
6. If `g_applied <= 0`: return the stem **unchanged** and emit a
   `skipped_headroom` action per the action-record contract above.
7. Else apply `g_applied` to the window through the tapered gain envelope
   specified in "Gain-envelope specification" (retaining the output
   `np.clip` to ±1.0 as defense-in-depth) and emit `attack_boost` if
   `g_applied == g_req`, else `attack_boost_headroom_clamped`. Record
   `onset_peak_after` as the **measured** post-gain onset-window peak.

### Gain-envelope specification (implement verbatim; added per gate-1 F2)

- Window: `W = min(n_samples, max(32, int(0.08 * sample_rate)))` (unchanged).
- Taper length: `T = min(W, max(16, int(0.005 * sample_rate)))` — a 5 ms
  fade-out, minimum 16 samples. Since `W >= 32` by construction, `T >= 16`
  and the `k / (T - 1)` form below is always well-defined.
- Taper weights (Hann fade-out, endpoints exact):
  `w[k] = 0.5 * (1 + cos(pi * k / (T - 1)))` for `k = 0 .. T-1`,
  giving `w[0] = 1.0` and `w[T-1] = 0.0` exactly.
- Gain envelope (float64, `g_lin = 10^(g_applied/20)`):
  - `E[n] = g_lin`                    for `0 <= n < W - T`
  - `E[W - T + k] = 1 + (g_lin - 1) * w[k]`  for `0 <= k < T`
  - `E[n] = 1.0`                      for `n >= W`
- **No leading taper.** The window begins at sample 0 (the file boundary);
  no preceding sample exists, so the leading edge can introduce no
  discontinuity, and full gain from sample 0 preserves the attack boost the
  stage exists to deliver. The taper's first weight is unity (1.0), i.e.
  the fade begins at full applied gain and returns to unity gain (0 dB)
  exactly at the window edge: `E[W-1] = 1.0` and `E[W] = 1.0`, so the gain
  shape is continuous across the boundary.
- Application: per channel, `out[:W] = arr[:W] * E[:W]` (broadcast across
  the channel axis for (samples, channels) layout); samples at and beyond
  W are untouched.
- The existing output `np.clip` to ±1.0 is retained as defense-in-depth;
  with the clamp bound holding it is unreachable.

**Safety property (restated for the taper):** since `1 <= E[n] <= g_lin`
throughout the window,
`max |out[:W]| <= p_onset * g_lin = p_onset * 10^(g_applied/20) <= 0.98`.
The clamp's ≤ 0.98 guarantee is preserved as a **conservative bound** (no
longer an exact equality), and the edge click of the rectangular window —
a discontinuity of magnitude `(g_lin − 1)·|x[W]|` — is removed.

Properties the implementation must preserve:
- **Deterministic**: the clamp is a pure function of (onset-window peak,
  requested gain); identical inputs produce identical outputs and actions.
- **Stem-count agnostic**: no dependence on the number or names of stems;
  serves both the 4-stem and the STORY-022 6-stem paths unchanged.
- **No pre-gain input-peak abort**: the pre-gain guard checks legality
  (> 1.0) only, never headroom.
- **Report visibility**: every clamped or skipped stem produces an action
  record; silence in the report means every stem received its full requested
  gain or was a clean no-op.

### Bundled correctness fix: Hilbert transform axis (DEF-011-02)

To be landed in the **same rework** as the clamp; QA to log as DEF-011-02.

- **Defect:** `scipy.signal.hilbert` defaults to `axis=-1`. Stems arrive as
  `(samples, 2)`, so the transform currently runs across the 2-sample
  **channel** axis. A Hilbert transform of a 2-point signal is meaningless;
  the "envelope" on stereo stems — the normal case — is garbage, and every
  attack ratio derived from it measures numerical noise, not attack
  strength. Mono fixtures hide the bug; the downstream 2-D `np.max` /
  `np.median` flattening launders the garbage into a plausible scalar.
- **Required correction (mandatory):** compute the analytic envelope along
  the sample axis for both layouts:
  `env = np.abs(hilbert(x, axis=0))` where `x` is `(samples,)` or
  `(samples, channels)`. For 1-D input `axis=0` coincides with the default,
  so this single form is correct for both.
- **Channel reduction:** for 2-D input, reduce the per-channel envelopes to
  one time series before computing baseline/peak statistics:
  `env = env.max(axis=1)` (peak envelope across channels per sample). The
  baseline/peak/median logic then runs on a genuine 1-D envelope.
- **Regression coverage (for the test-case-writer):** fixtures must include
  a stereo case with a known-by-construction attack ratio so this cannot
  regress silently; mono-only fixtures are insufficient.

### Downstream impact

- Call sites `stories/STORY-001/implementation/suno_mastering/pipeline.py`
  and `stories/STORY-016/implementation/orchestration.py` need **no
  changes**: the exception simply stops propagating for hot-but-legal
  inputs. The new action records flow into the existing report path.
- `stories/STORY-011/automation/test_story011_transient.py` is now partially
  stale: the test asserting a `ValueError` on input peak > 0.98 encodes the
  rejected method and must be replaced by the test-case-writer. See the
  testability additions below.
- The DEF-011-02 Hilbert-axis fix changes the attack metric on stereo
  material only; mono behaviour is unchanged. Any existing stereo fixtures'
  expected ratios were computed against the broken axis and must be
  re-derived by the test-case-writer.

## Guardrails
- No global stereo-sum repair as the primary path.
- No broad waveform sharpening across the full length of a stem.
- No offset gain that ignores stem identity or onset-window locality.
- No threshold-based detector that blindly marks dark real music as a problem; local onset evidence must be used instead.
- No default "fix everything" behaviour. A valid stem with no deficit returns the original array.
- No headroom abort on legal sub-full-scale stems; headroom is managed by the clamp contract above, never by crashing the run.
- No tuning of the 0.98 ceiling without re-derivation recorded in this document (H4/H6).
- No integer conversion or ±1.0 clip in any stage between transient restoration and the final loudness/true-peak safety stage; the 0.98 ceiling's derivation depends on this float64-intermediate invariant (gate-1 F1).
- No report or reason string may describe a clamped stem as "true-peak safe"; 0.98 is a sample-peak ceiling and true-peak ownership stays with stage 8 (gate-1 F1).
- No uniform rectangular gain window: the gain envelope must use the specified Hann fade-out so the stage does not introduce an edge click while removing artifacts (gate-1 F2).

## Testability notes
- Each stem can be tested in isolation with short synthetic signals: sharp-attack impulse, smeared attack, silence, and a clean control.
- Synthetic fixtures should use deterministic amplitudes and known sample rates to make the attack scoring reproducible.
- The stage should expose one pure function for the metric and one wrapper for the final processing to simplify unit-testing.
- **Ground-truth clamp test (H2)**: construct a stem whose onset-window peak `p` is known by construction with a requested gain `g_req` forced above the headroom; expected applied gain is exactly `min(g_req, 20*log10(0.98/p))` — derivable without running the tool. With the tapered envelope the clamp computation itself remains exact; the post-gain peak assertion becomes a bound: measured `onset_peak_after <= p * 10^(g_applied/20) <= 0.98`.
- **Envelope-shape test**: with a forced gain, verify `E[0] == g_lin` (full gain from sample 0), `E[W-1] == 1.0` exactly (no discontinuity at the window edge), and monotonic non-increasing weights across the fade region.
- **Negative control (H3)**: a stem with onset-window peak well below 0.98 and modest requested gain must receive its full requested gain (`attack_boost`, `requested_gain_db == gain_db`) — the clamp must not fire spuriously.
- **Defect-reproduction test**: a stem peaking at 0.9831 with the peak inside the onset window must return unchanged with a `skipped_headroom` action and must NOT raise.
- **Legality test**: an input stem peaking above 1.0 must still raise `ValueError`.
- **Determinism test**: two runs over the same stem dict produce identical actions.
- **6-stem compatibility test**: a six-stem dict (including `piano`, `guitar`) follows identical per-stem clamp semantics.
- **Stereo envelope test (DEF-011-02)**: a stereo fixture with a known-by-construction attack ratio must reproduce that ratio; guards against regressing the Hilbert transform axis.

## Architectural risks
- Stem separation quality is external to this stage; if stems are missing or invalid, the restoration stage must report that instead of manufacturing a fix.
- Real music can have naturally soft or dark transients that are not source defects; therefore any threshold must be conservative and local, not a fixed dB drop across the whole spectrum.
- Any method that relies on a single global crest-factor threshold will fail on real programme material; use local onset-window evidence and stem-specific interpretation.
- The 0.98 ceiling is valid only under the float64-intermediate invariant. If any future stage between transient restoration and the final safety stage introduces integer conversion or a ±1.0 clip, the ceiling derivation in this document is void and the ceiling must be re-derived against the true re-sum bound (+6.02 dB per coincident stem pair).
- With the tapered envelope, the clamp's post-gain peak prediction is a bound, not an equality; on some material the applied gain is slightly more conservative than strictly necessary. Accepted per gate-1 F2 — the cost is negligible against removing the edge click.
- The Hilbert-axis defect (DEF-011-02) means all attack ratios measured on stereo stems to date are untrustworthy; until the fix lands, the stage must not be trusted on real (stereo) material. The clamp contract itself is independent of how `g_req` is derived and is unaffected.

## Mastering-review disposition

### Action item 1 — Accepted as-is
- Finding: Stem-local transient restoration should remain evidence-driven, stem-specific, local to the transient region, and no-op when the stem is already good.
- Architect decision: Accepted as-is.
- Reason: This matches the repo's domain constraints and avoids the known wrong patterns: no broad stereo-sum correction, no global thresholds, and no "repair missing source" claims.
- Implementation requirement: Keep the onset metric local, preserve default-off behavior, and return the original stem unchanged when no valid transient deficit is detected.

### Action item 2 — Accepted as-is
- Finding: The architecture should keep the hard safety guardrails: no global crest-factor rule, no blanket gain stage, and no silent clipping.
- Architect decision: Accepted as-is.
- Reason: The architecture already states per-stem treatment, no global mix correction, local onset evidence, and explicit peak safety reporting.
- Implementation requirement: The restoration stage must continue to use local onset evidence, hard clipping checks, and report-visible action logs rather than a fixed dB threshold or broad gain stage.

### DEF-011-01 disposition (2026-08-17) — blocker resolved

- **Finding 1 — the guard's premise is wrong for stem-domain input.**
  Architect decision: **Method change** (H6) — replace the pre-gain
  input-peak abort with the onset-window headroom clamp specified in
  "Headroom-management contract" (QA's Option A).
  Reason: partially uncorrelated stems legitimately peak above the re-summed
  mix; a sub-full-scale stem peak is a normal signal property, not a fault.
  The clamp exploits the computable bound on the post-gain onset peak, so
  safety is preserved by construction rather than by aborting.
- **Finding 2 — the 0.98 constant was undocumented.**
  Architect decision: **Resolved by documentation and role change** — 0.98
  is no longer an abort threshold; it is the clamp ceiling with its
  derivation and margin rationale recorded per H4 (derivation subsequently
  corrected per gate-1 F1 — see below).
- **Finding 3 — the failure mode (whole-run abort at the final stage) is wrong.**
  Architect decision: **Resolved** — hot-but-legal inputs degrade gracefully
  (clamped gain or unchanged stem) with a mandatory report-visible action
  record. Only corrupt input (peak > 1.0) raises. All completed upstream
  work (separation, tonal, width) is preserved.
- **STORY-022 compatibility note — Accepted as-is.**
  The contract is defined per-stem over `dict[str, np.ndarray]`; the 6-stem
  `htdemucs_6s` bundle (adding `piano`, `guitar`) requires no contract
  change. Unknown names use the existing default severity threshold.
- **Rejected options (recorded for the audit trail):**
  - Option B (pre-Stage-8 broadband trim): rejected — non-local remedy;
    changes the input to every downstream stem detector and violates
    "if the signal is already good, do not change it" (CLAUDE.md §8.2).
  - Option C (keep the abort): rejected — deterministic total run loss on
    ordinary hot material; contradicts degrade-gracefully for legal signals.
  - Raising the 0.98 threshold: rejected — H6 known-wrong parameter tuning
    of a wrong method.

### Gate-1 review disposition (2026-08-17 — gate1-review-clamp-2026-08-17.md; verdict APPROVED-WITH-CONDITIONS)

- **F1 — Concern (approval condition): 0.98 derivation asserted a physically false margin.**
  Architect decision: **Action item — derivation rewritten; value retained.**
  Reason: the review is correct that coherent re-sum growth (+6.02 dB per
  coincident stem pair, +12 dB for four) is unbounded by any per-stem
  margin; the 0.175 dB margin absorbs float rounding only. The "Clamp
  ceiling 0.98" derivation bullet now states the float64-end-to-end /
  integer-only-at-final-I/O invariant plus stage 8's ownership of the
  −1.0 dBTP ceiling as the load-bearing safety fact, deletes the re-sum
  absorption claim, and records 0.98's real jobs (per-stem legality margin;
  bounding injected crest). Added: the intermediate-chain invariant
  requirement (no integer conversion or ±1.0 clip between this stage and
  final safety, else re-derive) and the reporting rule that no reason
  string may call a clamped stem "true-peak safe" (sample-peak ceiling ≠
  true-peak). **Approval condition met.**
- **F2 — Concern: uniform rectangular gain window locks in an audible edge click.**
  Architect decision: **Action item — contract amended to a tapered gain
  envelope.** The review's recommendation is adopted. Specified precisely
  in "Gain-envelope specification": Hann fade-out over the last
  `T = min(W, max(16, int(0.005 * sample_rate)))` samples,
  `w[k] = 0.5 * (1 + cos(pi * k / (T - 1)))` with `w[0] = 1.0` and
  `w[T-1] = 0.0` exactly; no leading taper (the window starts at the file
  boundary, so no discontinuity is possible there, and full gain from
  sample 0 preserves the attack boost). The exact-predictability claim is
  restated as a conservative bound — every envelope value lies in
  `[1, g_lin]`, so post-gain onset peak `<= p_onset * 10^(g_applied/20)
  <= 0.98` — verified sound: the clamp computation is unchanged and the
  ≤ 0.98 guarantee holds a fortiori. `onset_peak_after` is now recorded as
  measured, not predicted. Determinism is unaffected (the envelope is a
  pure function of W, T, g_applied).
- **F3 — Note: onset-window clamp vs global peak is physically correct.**
  Architect decision: **Accepted as-is.** The review confirms the design;
  no contract change.
- **F4 — Note: skip-unchanged endorsed; Option B rejection rationale sound.**
  Architect decision: **Accepted as-is.** No contract change.
- **F5 — Note: optional global-peak field.**
  Architect decision: **Action item — adopted.** `global_peak_before` added
  to `TransientRestorationAction`, always populated (one
  `np.max(np.abs(arr))` over the pre-gain stem). It is cheap and lets the
  report distinguish "stem hot everywhere, skip obviously correct" from
  "only the onset is hot" without re-measuring.
- **F6 — Referred defect: `hilbert` transform axis on 2-D stems.**
  Architect decision: **Action item — correctness fix specified, to land in
  the same rework as the clamp.** The envelope must be computed along the
  sample axis for both 1-D and 2-D inputs (`hilbert(x, axis=0)` for the
  (samples, channels) layout), with per-sample cross-channel max reduction
  before baseline/peak statistics. Specified in "Bundled correctness fix:
  Hilbert transform axis (DEF-011-02)". **QA to log as DEF-011-02**; a
  stereo fixture with a known-by-construction attack ratio is mandatory so
  the bug cannot regress silently. The clamp contract is independent of how
  `g_req` is derived, so the clamp design is unchanged — but the stage must
  not be trusted on real (stereo) stems until the fix lands.

## Revision history
- 2026-08-16: Initial Story 11 architecture drafted for conservative, stem-local transient restoration with explicit safety and no-op guardrails.
- 2026-08-16: Added explicit mastering-review disposition, converting both note findings into architect action items with accepted-as-is decisions and implementation requirements.
- 2026-08-17: **DEF-011-01 resolution (blocker).** Replaced the undocumented 0.98 pre-gain input-peak abort with a deterministic onset-window headroom clamp (clamp-then-report). Added the "Headroom-management contract" section with H4 derivations, exhaustive raise conditions, the verbatim clamp algorithm, and the new `TransientRestorationAction` fields (`requested_gain_db`, `onset_peak_before`, `onset_peak_after`) and `action_type` values (`attack_boost_headroom_clamped`, `skipped_headroom`). Public function signature unchanged; both call sites (STORY-001 pipeline, STORY-016 orchestrator) require no changes. Downstream impact: the existing STORY-011 test asserting a ValueError on input peak > 0.98 is stale and must be replaced by the test-case-writer; the python-developer's implementation of `_peak_guard` is now stale and must be reworked against this revision before QA retest.
- 2026-08-17: **Gate-1 review amendments (verdict APPROVED-WITH-CONDITIONS, gate1-review-clamp-2026-08-17.md).** F1 (approval condition): rewrote the "Clamp ceiling 0.98" derivation — deleted the physically false re-sum-absorption claim; the load-bearing safety fact is now the float64-end-to-end / integer-only-at-final-I/O invariant with stage 8 owning the −1.0 dBTP ceiling; 0.98 retained per H6 with its real jobs recorded (per-stem legality margin, bounding injected crest); added the intermediate-chain invariant requirement and the ban on "true-peak safe" reason strings. F2: amended the clamp contract from a uniform rectangular gain window to the specified Hann fade-out gain envelope (5 ms taper, exact endpoints, no leading taper); exact predictability restated as a conservative bound (`onset peak ≤ p_onset × 10^(g_applied/20) ≤ 0.98`); `onset_peak_after` is now measured, not predicted. F3, F4: accepted as-is. F5: added `global_peak_before` to the action record (always populated). F6: specified the mandatory Hilbert-axis correction (`hilbert(x, axis=0)` plus per-sample cross-channel max reduction) to land in the same rework; referred to QA to log as DEF-011-02, with a stereo known-attack-ratio fixture required. Downstream impact: the python-developer's clamp rework must implement the tapered envelope, the measured `onset_peak_after`, the new `global_peak_before` field, and the Hilbert-axis fix together; the test-case-writer must derive the ground-truth clamp test against bound semantics, add the envelope-shape test, and add the stereo attack-ratio fixture.
