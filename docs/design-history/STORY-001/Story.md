# STORY-001: World-class streaming master for Suno tracks

## User Story
As a producer, I want a tool that takes a raw Suno-generated WAV
export and analyses it against the same criteria a world-class
mastering engineer would use, then masters it to be release-ready
and optimised for streaming platforms, so that every track meets a
consistent professional standard without manual trial and error in
Audacity/bx_mastering.

## Assessment criteria (what "world-class" means, measurably)
- Integrated loudness (LUFS)
- True peak level (dBTP)
- Dynamic range / crest factor
- Frequency balance (flag muddiness, harshness, thin low-end)
- Stereo width and mono compatibility (phase issues)
- Clipping / distortion detection

## Mastering targets
- Integrated loudness: -14 LUFS (streaming-normalised baseline;
  should not be significantly louder — over-limiting gets turned
  down and gains nothing)
- True peak ceiling: -1 dBTP (headroom for lossy transcoding)
- Preserve dynamic range appropriate to a long-form, build-driven
  track — do not flatten dynamics in service of raw loudness
- Full mono compatibility check on stereo-widened elements

## Notes
- Input: raw Suno export, WAV, loudness/quality inconsistent
- Genre context: deep/melodic progressive house and melodic
  techno, 124 BPM, long-form (7+ min), dynamics matter to the
  track's build/payoff — this is not EDM-festival loudness-war
  material
- Output: mastered WAV, ready for LANDR distribution and Spotify
- Tool should report the "before" measurements against these
  criteria, then the "after" measurements, so the improvement is
  visible and verifiable