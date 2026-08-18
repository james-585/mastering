# STORY-002 automated test suite — location note

The executable pytest suite for this story lives at
`stories/STORY-001/implementation/tests/`, in the `test_ref_*.py` files
specifically, not physically under this `automation/` directory. This
mirrors STORY-001's own already-documented decision
(`stories/STORY-001/automation/README.md`) for the same reasons:

- STORY-002's implementation lives inside
  `stories/STORY-001/implementation/suno_mastering/` (per this story's own
  explicit "modify STORY-001's implementation in place, do not create a
  separate tree" instruction) and is installed editable from that same
  directory. The test suite imports the package the same way STORY-001's
  own tests do (`from suno_mastering...`, relative imports rooted at
  `stories/STORY-001/implementation/`).
- The `test_ref_*.py` filename prefix namespaces STORY-002's suite from
  STORY-001's own `test_ac*.py`/`test_*.py` files in the same directory, so
  the two suites can be run together, separately, or filtered
  (`pytest -k test_ref_`) without ambiguity, while both still share
  STORY-001's own `tests/conftest.py` fixtures where useful.
- `tests/ref_helpers.py` (plain importable module, not a `conftest.py`
  addition) holds STORY-002-specific fixture builders (synthetic
  decorrelated-stereo/lowpassed-noise/calibrated-tone generators, FLAC/MP3
  fixture writers via ffmpeg, a `make_stub_measurements()` factory for
  aggregation-level tests that don't need a real audio decode, and a
  `ref_config()` helper for boundary-condition `ReferenceAnalysisConfig`
  overrides). Deliberately not added to STORY-001's existing
  `tests/conftest.py` — zero risk of an accidental STORY-001 regression
  introduced by this QA pass.
- One test function per `test-cases.md` entry, traceable by name
  (`test_tcNNN_...`), same convention as STORY-001. A handful of test cases
  (TC-262–TC-265, TC-307) are parametrized into a single function rather
  than four/three near-duplicate ones, per normal pytest style — still one
  `test_tcNNN`-per-case in spirit, traceable via the parametrize table.

## Running the suite

From `stories/STORY-001/implementation/`:

```
pip install -e .
python -m pytest tests/test_ref_*.py -q -m "not slow"                # fast subset (excludes TC-380/381/382 NFR timing/memory tests)
python -m pytest tests/test_ref_*.py -q -m "slow and not isolated"   # TC-380/TC-382 (slow but safe to combine)
python -m pytest tests/test_ref_*.py -q -m isolated                  # TC-381 ONLY -- see below, must stay isolated
```

**`test_tc381_whole_set_budget_under_5_minutes_worst_case` (DEF-110,
defects.md; architecture.md v3 Section 16) must always be run in its own
dedicated pytest invocation, on its own, never folded into a combined-suite
run.** Confirmed directly this session: it fails dramatically (1129.6s vs.
its 300s budget) at the tail of an oversized combined STORY-001+STORY-002
run, but passes cleanly (well under budget) when run as part of its own
isolated `test_ref_*.py` suite. This is the same DEF-110 session-position
sensitivity as STORY-001's `test_tc150` and must be run the same way:

```
python -m pytest tests/test_ref_nfr.py -q -m isolated
```

**Do not run `python -m pytest -q` (STORY-001 + STORY-002 combined,
unfiltered) as the final/sign-off invocation** -- it puts `test_tc150` and
`test_tc381` at the tail of a large session and can produce false FAILs per
DEF-110, on both tests, independently confirmed this session. For a
full-suite sign-off pass, run STORY-001's `not isolated` subset, this
suite's `not isolated` subset, and the two `isolated` tests as separate,
dedicated invocations, then combine the reported counts. **Also do not use
a bare `-m slow` invocation as the isolation vehicle** -- `test_tc381`
still carries the pre-existing `slow` marker alongside the new `isolated`
one (additive, not a replacement), so a plain `-m slow` run would collect
it together with `test_tc380`/`test_tc382` and reintroduce the same
tail-of-session risk `isolated` exists to avoid. Always select on
`isolated` specifically, per the commands above.

`ffmpeg`/`ffprobe` must be on `PATH` for the MP3-fixture-encoding helpers
(`write_mp3_ffmpeg`, `write_mp3_vbr_no_header`) and the MP3-related test
cases; those tests are individually `skipif`-guarded
(`ffmpeg_available()`) and skip cleanly, not fail, if unavailable.

See `stories/STORY-002/defects.md` for the running defects ledger
(DEF-101–DEF-103 carried forward from the implementation pass; DEF-104
onward filed by this QA pass) and the QA report (delivered as this agent's
final response, not a separate file per house convention) for the latest
full-suite pass/fail/skip counts and shippability verdict.
