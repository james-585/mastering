"""Scratch sanity check for the DEF-011-01 clamp-then-report rework.

Not a pytest file. Exercises: hot stem (skip), modest deficit (full boost),
clamped stem, and illegal >1.0 stem (must raise).
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "stories" / "STORY-011" / "implementation"))

from transient_restoration import (  # noqa: E402
    CLAMP_CEILING,
    apply_stem_transient_restoration,
)

SR = 44100
N = SR  # 1 s stems


def make_stem(onset_peak: float, attack_spike: bool) -> np.ndarray:
    rng = np.random.default_rng(7)
    x = 0.05 * rng.standard_normal((N, 2))
    if attack_spike:
        # sharp onset transient inside the first 80 ms window
        x[100, :] = onset_peak
        x[101, :] = -0.6 * onset_peak
        # repeated strong attacks so the local attack ratio exceeds threshold
        for pos in range(2000, 9000, 400):
            x[pos, :] = 0.9 * onset_peak
            x[pos + 1, :] = -0.5 * onset_peak
    else:
        # hot but flat: peak sits at the onset with no attack deficit
        x[100, :] = onset_peak
        x[101, :] = -onset_peak
    return x.astype(np.float64)


def report(tag, stems):
    out, actions = apply_stem_transient_restoration(stems, SR)
    for name, arr in stems.items():
        o = out[name]
        pre = float(np.abs(arr).max())
        post = float(np.abs(o).max())
        print(
            f"[{tag}] {name}: pre_peak={pre:.4f} post_peak={post:.4f} "
            f"changed={not np.array_equal(arr, o)}"
        )
    for a in actions:
        print(
            f"  action: {a.action_type} gain_db={a.gain_db:.4f} "
            f"requested={a.requested_gain_db:.4f} "
            f"onset_before={a.onset_peak_before:.4f} onset_after={a.onset_peak_after:.4f} "
            f"global_before={a.global_peak_before:.4f}"
        )
        print(f"  reason: {a.reason}")
    return out, actions


print("=== 1. hot stem at 0.9831 (skip path, must NOT raise) ===")
hot = make_stem(0.9831, attack_spike=True)
_, acts = report("hot", {"drums": hot})
assert acts and acts[0].action_type == "skipped_headroom", acts
assert acts[0].gain_db == 0.0 and acts[0].requested_gain_db > 0.0

print("=== 2. modest deficit (full boost path) ===")
mild = make_stem(0.5, attack_spike=True)
_, acts = report("boost", {"other": mild})
assert acts and acts[0].action_type == "attack_boost", acts
assert acts[0].gain_db == acts[0].requested_gain_db
assert acts[0].onset_peak_after <= acts[0].onset_peak_before * 10 ** (acts[0].gain_db / 20) + 1e-12

print("=== 3. clamped stem (peak just under ceiling, high requested gain) ===")
clamped = make_stem(0.90, attack_spike=True)
_, acts = report("clamp", {"drums": clamped})
assert acts and acts[0].action_type == "attack_boost_headroom_clamped", acts
import math

expected = min(
    acts[0].requested_gain_db, 20.0 * math.log10(CLAMP_CEILING / acts[0].onset_peak_before)
)
assert math.isclose(acts[0].gain_db, expected, rel_tol=0, abs_tol=1e-12), (
    acts[0].gain_db,
    expected,
)
assert acts[0].onset_peak_after <= CLAMP_CEILING + 1e-12
assert "true-peak" not in acts[0].reason

print("=== 4. illegal stem > 1.0 (must raise, naming stem and peak) ===")
illegal = make_stem(0.5, attack_spike=True)
illegal[5000, 0] = 1.2
try:
    apply_stem_transient_restoration({"bass": illegal}, SR)
except ValueError as exc:
    print(f"  raised as required: {exc}")
    assert "bass" in str(exc) and "1.2000" in str(exc)
else:
    raise AssertionError("expected ValueError for input peak > 1.0")

print("=== 5. envelope shape spot check ===")
from transient_restoration import _gain_envelope, _onset_window_length  # noqa: E402

W = _onset_window_length(N, SR)
E = _gain_envelope(W, SR, 2.0)
g_lin = 10 ** (2.0 / 20)
assert E[0] == g_lin, E[0]
assert E[W - 1] == 1.0, E[W - 1]
T = min(W, max(16, int(0.005 * SR)))
fade = E[W - T :]
assert np.all(np.diff(fade) <= 1e-12), "fade must be monotonic non-increasing"
print(f"  W={W} T={T} E[0]={E[0]:.6f}==g_lin E[W-1]={E[W-1]:.17g} monotonic=OK")

print("=== 6. no-op healthy stem returned unchanged, no action ===")
t = np.arange(N, dtype=np.float64) / SR
tone = 0.3 * np.sin(2 * np.pi * 220 * t)
clean = np.column_stack([tone, tone]).astype(np.float64)  # flat envelope, ratio ~1
out, acts = report("noop", {"vocals": clean})
assert acts == [], acts
assert np.array_equal(out["vocals"], clean)

print("ALL SCRATCH CHECKS PASSED")
