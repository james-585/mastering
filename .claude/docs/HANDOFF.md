# Handoff Protocol

Why stories were being rerun, and the rules that stop it.

---

## Part 1 — Root cause analysis of observed rework

Five failures, each traced to a specific structural gap.

### F1 — DEF-201: wrong method survived two rounds

**What happened**: threshold-based band-limit detection was specified,
implemented, tested green, and shipped impossible values (a commercial CD
master at 1979 Hz). The fix raised the threshold 6→20 dB. Numbers changed,
method unchanged, values still impossible.

**Gap**: no domain review between method selection and implementation. The
architect chose a method and the next agent to see it was the developer,
who implemented it faithfully.

**Fix**: Gate 1 — mastering-engineer reviews architecture.md before
implementation. Blockers must be resolved before the developer starts.

**Second gap**: a wrong *method* was addressed by tuning a *parameter*.

**Fix**: rule H6 below — every defect fix must state whether it is a
parameter change or a method change, and a method-caused defect cannot be
closed by a parameter change.

### F2 — DEF-203: an asserted constant was never derived

**What happened**: a −6.02 dB mono-sum baseline was written into
architecture.md and never questioned. It is wrong by 3 dB. It survived
DEF-101 and DEF-104 review.

**Gap**: no rule requiring constants to be derived rather than asserted.

**Fix**: rule H4 — every constant a measurement is compared against must
have its derivation shown in architecture.md and be verified against
synthetic signals with analytically known answers.

### F3 — DEF-202: STORY-002's output was consumed by nothing

**What happened**: reference analysis produced a machine-readable aggregate.
The mastering stage kept using hardcoded placeholders. The two halves of the
project never connected.

**Gap**: stories declared what they would *produce* but never what would
*consume* it. No interface contract.

**Fix**: rule H1 — every story states its Produces/Consumes contract, and a
story producing an artifact nothing consumes must name the consuming story.

### F4 — DEF-204: tests passed while measurements were wrong

**What happened**: three defects, one producing physically impossible
output, passed a full green suite.

**Gap**: tests verified execution and type plausibility, not correctness.

**Fix**: rules H2 and H3 — ground-truth expected values derived by
construction, plus mandatory negative controls.

### F5 — decisions relitigated across sessions

**What happened**: reference subset choice, RoEx exclusion, spectral
soft-nudge rationale — all decided, none recorded where agents could read
them. Each session risks contradicting them.

**Gap**: no persistent project context.

**Fix**: `CLAUDE.md` at repo root. Read first, every session.

---

## Part 2 — Rules

### H1 — Interface contracts are mandatory

Every story states, before requirements are written:

```
## Contract
Consumes: <artifact/file, produced by which story>
Produces: <artifact/file, in what format>
Consumed by: <which story or stage, or "terminal — nothing consumes this">
```

A story producing an artifact with no named consumer is incomplete. Either
name the consumer or justify "terminal".

The architect must specify the **format** of every produced artifact
precisely enough that the consuming stage can be written against it without
inspecting the producer's code.

### H2 — Ground truth, not regression locks

Every measurement function needs at least one test whose expected value is
derivable **from how the test signal was constructed**, not from running the
tool.

If the expected value can only be obtained by running the implementation, it
is a regression test. Regression tests detect change; they cannot detect
that the current value is wrong. Label them as such. One can never stand in
for a correctness test.

Each ground-truth test states its derivation in a comment — the reasoning,
not just the number.

### H3 — Negative controls are mandatory

Every detector needs at least one test on a signal that must **not** trigger
it.

DEF-201 would have been caught by one test: full-band pink noise, no cutoff,
must report NO CUTOFF. A detector tested only on positive cases passes
happily while producing false positives on everything real.

Rule: for every "X must be detected" test, there is a "Y must not be
detected" test, where Y is the realistic near-miss — declining spectrum
without a cutoff, correlated-but-not-identical channels, quiet-but-not-silent
passages.

### H4 — Constants are derived, not asserted

Any constant a measurement is compared against — baselines, floors, expected
levels — must:
1. Have its derivation shown in architecture.md
2. Be verified against synthetic signals with analytically known answers
3. Never be changed without re-deriving

Changing a constant to make results look right, without re-derivation, is
prohibited.

### H5 — Plausibility gate before any result is reported

No measurement is reported without passing:
1. **Internal consistency** — does one value make another impossible?
2. **Material plausibility** — is this possible for what the file is?
   (See `DOMAIN.md` §3.)
3. **Spread check** — do dissimilar inputs produce suspiciously similar
   values? That indicates measuring the calculation, not the audio.
4. **Round-number check** — targets at exactly −1.50, −3.00 are placeholders.

Failing any of these is a defect, **even if every assertion passed**.

### H6 — Parameter change vs method change

Every defect fix states which it is:

- **Parameter change** — the method is correct, a value was wrong
- **Method change** — the approach was wrong and has been replaced

**A defect whose root cause is a wrong method cannot be closed by a
parameter change.** If the fix only adjusts a value, and the underlying
method has the flaw, the defect stays open.

QA must verify this before closing: "was the method changed, or a number?"

### H7 — Defect closure requires independent verification

Only qa-automation-engineer closes defects. Before closing:
1. The failing test that demonstrates the defect existed, now passes
2. That test was written **before** the fix and confirmed failing
3. H5 plausibility gate passes on the new output
4. H6 answered
5. For a reopened defect: what specifically differs from the previous
   attempt, stated explicitly

### H8 — Fresh-context handoff

Agents start with no memory of the main conversation. Every handoff prompt
must name:
- The story folder
- Which upstream files to read (they will not go looking)
- `CLAUDE.md` and `docs/DOMAIN.md` — always
- Any cross-story files (agents do not read other story folders unless told)

---

## Part 3 — Definition of Done

A story is done only when **all** hold:

- [ ] Contract (H1) satisfied — produced artifacts exist in the stated
      format, and the named consumer can read them
- [ ] Gate 1 review complete, no unresolved Blockers
- [ ] Every measurement function has a ground-truth test (H2)
- [ ] Every detector has a negative control (H3)
- [ ] Every constant has a shown derivation (H4)
- [ ] H5 plausibility gate passed on real output, not just test fixtures
- [ ] Gate 2 review complete, Blockers raised as defects
- [ ] No `Open` or `Fixed-Pending-Retest` defects remain
- [ ] Full suite runs in under 60 seconds
- [ ] **Human listening check**: James has A/B'd level-matched output on two
      systems and confirmed it does not sound worse. Automated tests cannot
      hear. A story that measures correctly and sounds worse is not done.

---

### H9 — Token discipline

Context is not free. Every agent's context reads are scoped in its own
definition — those scopes are binding, not suggestions.

**Reading rules, all agents:**
- Read the named sections, not whole files, where a section is specified
- **Grep before Read** on implementation code. Locate the module, read that
  file. Never read an implementation directory wholesale.
- Do not read other stories' folders unless the Contract names them
- Do not read files that are not yours: the developer does not read the test
  suite, the test-case-writer does not read the implementation

**Output rules, all agents:**
- Do not echo input back. The reader has it.
- Do not restate the plan before executing it
- Do not paste full test output — counts plus failure detail
- Do not summarise a file you just wrote; the file exists

**Defect ledger hygiene**: every agent reads `defects.md` on every run, so it
must stay small. When a story completes, move `Closed` entries to
`defects-archive.md`. The audit trail is preserved and the per-run read
halves.

**Orchestration**: invoke agents one at a time and inspect the output before
invoking the next, rather than chaining the whole pipeline in one
instruction. Chaining forces the main session to hold every intermediate
result, and it delays discovery of problems until the end.

**The largest saving is not reading less.** Two rounds of DEF-201 cost more
than every rule above combined. Specification documents are expensive per
run and cheap per story not repeated.

## Part 4 — Invocation templates

### Full story
```
Read CLAUDE.md and docs/DOMAIN.md first.

Run business-analyst on stories/STORY-XXX. Also read <upstream files>.
Then software-architect on the same story.
Then mastering-engineer in Gate 1 mode to review architecture.md.
Resolve any Blockers before continuing.
Then python-developer and test-case-writer in parallel.
Then qa-automation-engineer.
Then mastering-engineer in Gate 2 mode on the measurement output.
Then qa-automation-engineer again to raise defects from the Gate 2 review.
```

### Defect fix
```
Read CLAUDE.md and docs/DOMAIN.md first.

Fix DEF-XXX in stories/STORY-YYY/defects.md.
Per H6, state whether this is a parameter change or a method change.
Per H7, write the failing test first and confirm it fails before fixing.
Then qa-automation-engineer to verify and close.
Then mastering-engineer Gate 2 on the resulting output.
```

### Reopened defect
```
Read CLAUDE.md and docs/DOMAIN.md first.

DEF-XXX is REOPENED. The previous fix was <what was done> and it did not
work because <evidence>.
Per H6 this requires a METHOD change, not a parameter change.
State explicitly what differs from the previous attempt before implementing.
```
