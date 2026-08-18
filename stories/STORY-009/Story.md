# STORY-009: Wire the `suno_dsp` C++ DSP extension into the mastering chain

## User Story
As the tool owner, I want the three DSP functions already implemented in
`src_cpp/spectral_repair.cpp` (`repair_whistles`, `shape_transients`,
`collapse_swish`) — currently built but never called — wired into the real
Python mastering pipeline as gated, logged pipeline stages, so the DSP work
already done is either put to use under proper domain review or explicitly
held back until it clears one.

## Contract
```
Consumes:  src_cpp/spectral_repair.cpp (suno_dsp pybind11 module, built via
           CMakeLists.txt), STORY-007 artifact-detector output
           (Measurements.artifact_detection.artifact_flags — for
           repair_whistles only)
Produces:  three new/extended pipeline stages in
           stories/STORY-001/implementation/suno_mastering/pipeline.py
           calling into suno_dsp, each config-gated and default-off, with
           every invocation logged to the returned actions payload and the
           mastering report
Consumed by: mastering pipeline (pipeline.py) — terminal for this story;
           no further downstream consumer
```

## Background
`suno_dsp` exists and builds but is dead code — nothing in the Python
pipeline imports or calls it. None of the three functions has been through
a story/Gate 1 process. This story's job is requirements + Gate 1 grounding
for wiring them in as pipeline stages; implementation and architecture are
explicitly out of scope for this document (see `requirements.md`).

See `docs/BACKLOG.md` STORY-009 for the originating scope draft and
`.claude/docs/CLAUDE.md` §4.2a for the surgical-notching exception that
makes `repair_whistles` permissible at all.
