# Copilot instructions for Suno Mastering

This repository is a local Python audio mastering tool for Suno-generated audio. Follow these instructions in all code and analysis work.

## Project context

- Read [.claude/docs/CLAUDE.md](../.claude/docs/CLAUDE.md) first before doing anything substantive in this repo.
- Respect the project scope and do not re-litigate standing decisions.
- This tool is local-only and CLI-based. Do not propose cloud APIs, GitHub/GitLab CI, GUI work, VST3/AU plugin hosting, or real-time processing.
- Mastering operates on the stereo sum. Do not promise per-element fixes, stem separation, transient repair, or reverb removal.

## Hard constraints

- No VST3 / AU plugin hosting unless explicitly required by a story and approved.
- No cloud mastering APIs or API-key-based services.
- No source separation or stem extraction from stereo.
- No GUI. This is a CLI tool.
- Do not overwrite or degrade input files; preserve originals read-only.
- Use float64 internally and convert to integer only at final I/O boundaries.
- Never silently clip; fail loudly or report when audio can exceed ±1.0.
- True peak is not sample peak. Use oversampling (minimum 4x, preferably 8x) for dBTP calculations.
- Do not use librosa.load without sr=None.
- Use the project-specified libraries; do not substitute silently.

## Known-wrong patterns to avoid

- Threshold-based band-limit detection using a fixed dB drop. This fails on naturally dark music.
- Asserting a baseline constant without derivation.
- Using np.max(np.abs(x)) as true peak.
- Hardcoded placeholder targets like -1.50, -3.00, or -4.00.
- Reporting a fixed property as varying across a file.
- Fixing a wrong method by tuning its parameter instead of replacing the method.

## Story workflow

For any user story, follow the project sequence:

1. Business analyst: define requirements.
2. Architect: define pipeline design and library choices.
3. Mastering engineer: review method plausibility.
4. Developer: implement against requirements and architecture.
5. Test case writer: define measurable test cases.
6. QA automation: run pytest, log defects, and triage code-vs-architectural issues.

## Implementation standards

- Use a virtual environment and keep dependencies pinned where required.
- Prefer the narrowest correct library for the task.
- Keep functions small and single-purpose.
- Use small, explicit constants instead of magic numbers.
- Capture the input/output contract clearly: sample rate, array shape, mono vs stereo, dtype, and file format.
- When working with existing code, locate the exact symbol or module first, then read only the relevant file or section.
- Do not read entire implementation directories just to browse context.

## Audio quality guidance

- For loudness, use LUFS as required by the story and project standards, not RMS.
- Use a proper reference-derived target when specified by the story and architecture.
- For spectrum analysis, treat a sustained steep cliff as evidence of a real cutoff; a gentle spectral tilt is ordinary music content.
- For stereo material, use the correct sum conventions and note the derivation of any baseline used in analysis.
- When measurements disagree strongly across references, report a range instead of a hard single target.

## Defect handling

- If a defect is caused by a wrong method, replace the method, not just a parameter value.
- QA is the only agent that creates or closes defects.
- If an implementation choice conflicts with architecture or domain constraints, raise it as an architectural issue instead of silently working around it.
- Do not mark work as complete in defect logs; that belongs to QA.

## Before finishing work

- Re-check the relevant story architecture and requirements.
- Confirm you did not deviate from the agreed pipeline contract.
- Verify the change satisfies the user story and does not reintroduce a known defect pattern.

## Architect follow-up rule for mastering-review findings

- The software-architect must convert every mastering-engineer finding into an explicit action item or an explicit “accepted as-is” decision.
- If a finding is a blocker, the architecture must be revised and the revision history updated before implementation proceeds.
- If a finding is not a blocker, the architect must still record a written disposition so the review is not silently ignored.
- “No blockers” is not enough by itself; the architect must state what was accepted or changed, and why.
- This applies repo-wide to every story and must be preserved in the architecture artifact for that story.
