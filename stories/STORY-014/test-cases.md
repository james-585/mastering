# STORY-014 — Test Cases

## TC-0141 bus glue without flattening
- Input: a corrected multi-stem mix with audible but not severe internal imbalance.
- Expected: the output feels more cohesive, but transients remain distinct and the arrangement does not collapse into a flat, pressure-heavy bus.
- Pass condition: the stage returns at least one action with a conservative gain change and the final peak remains under the safe ceiling.

## TC-0142 dynamic balance on a minimalist arrangement
- Input: sparse arrangement with broad dynamic movement but little dense low-end energy.
- Expected: no destructive pumping or envelope collapse; the micro-dynamics remain audible and the emotional contour stays intact.
- Pass condition: the dynamic-balance path applies only a small correction and does not reduce transient definition.

## TC-0143 final loudness and true-peak safety
- Input: a full mix that is near the project target range but has a strong transient or small inter-sample overshoot risk.
- Expected: final loudness remains in range and the oversampled true peak stays below the configured ceiling.
- Pass condition: the implementation reports the before/after metrics and applies attenuation only when a safety risk is real.

## TC-0144 no-op on already-cohesive material
- Input: an already stable and well-mixed bus.
- Expected: no final bus processing is applied.
- Pass condition: the stage returns zero actions for a material that already passes the cohesion check.

## TC-0145 transient preservation and emotional contour
- Input: a mix with punchy drums, a vocal phrase, and clear dynamic movement.
- Expected: the bus stage does not smear the transient, hide the phrasing, or remove the track’s forward motion.
- Pass condition: the transient timing remains aligned after processing and the output does not exhibit a flattened dynamic envelope.

## TC-0146 clip-risk and oversampling guard
- Input: a bus with a near-full-scale transient or inter-sample peak risk.
- Expected: a safety attenuator engages before the final output leaves the stage.
- Pass condition: the final bus peak is under the project ceiling and the report clearly records the safety action.

## TC-0147 report visibility
- Input: any treated or untouched bus.
- Expected: the report shows whether the stage performed bus glue, dynamic balance, or a safety clamp, and why.
- Pass condition: every action includes a reason string and measurable before/after values.
