"""Repro check for DEF-011-03 (wrap-boundary Hilbert envelope spike)."""
import sys
import numpy as np

sys.path.insert(0, r"c:\Users\james\Documents\suno-mastering\stories\STORY-011\implementation")
from transient_restoration import _local_attack_ratio

sr = 44100
t = np.arange(int(0.5 * sr)) / sr

# Non-integer-cycle constant-amplitude tone: true attack ratio is 1.0
x441 = 0.99 * np.cos(2 * np.pi * 441 * t)
# Integer-cycle control
x440 = 0.99 * np.cos(2 * np.pi * 440 * t)

r441 = _local_attack_ratio(x441, sr)
r440 = _local_attack_ratio(x440, sr)
print(f"441 Hz (non-integer cycles): ratio = {r441:.4f}")
print(f"440 Hz (integer cycles):     ratio = {r440:.4f}")
