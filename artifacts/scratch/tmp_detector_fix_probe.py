import numpy as np

sr = 44100
n = sr * 2
f = 55.0
t = np.arange(n) / sr
x = np.sin(2 * np.pi * f * t)
audio = np.stack([x, x], axis=1).astype(np.float32)

def hp_2nd_order(x, sr, cutoff):
    q = 0.70710678
    omega = 2 * np.pi * cutoff / sr
    sin_w = np.sin(omega)
    cos_w = np.cos(omega)
    alpha = sin_w / (2 * q)
    b0 = (1 + cos_w) * 0.5
    b1 = -(1 + cos_w)
    b2 = (1 + cos_w) * 0.5
    a0 = 1 + alpha
    a1 = -2 * cos_w
    a2 = 1 - alpha
    b0n, b1n, b2n = b0 / a0, b1 / a0, b2 / a0
    a1n, a2n = a1 / a0, a2 / a0
    y = np.empty_like(x)
    x1 = x2 = y1 = y2 = 0.0
    for i, s in enumerate(x):
        y[i] = b0n * s + b1n * x1 + b2n * x2 - a1n * y1 - a2n * y2
        x2, x1 = x1, s
        y2, y1 = y1, y[i]
    return y

# current model variant: transient-only high-frequency energy detector
cutoff = 1500.0
hp0 = hp_2nd_order(audio[:, 0], sr, cutoff)
hp1 = hp_2nd_order(audio[:, 1], sr, cutoff)
link = np.maximum(np.abs(hp0), np.abs(hp1))
# attack signal as positive rise in detector level
attack = np.maximum(0.0, np.diff(np.r_[0.0, link]))
# slow env smoothing
fast_alpha = 1.0 - np.exp(-1.0 / (0.002 * sr))
slow_alpha = 1.0 - np.exp(-1.0 / (0.250 * sr))
fast_env = np.empty_like(link)
slow_env = np.empty_like(link)
fast_env[0] = attack[0]
slow_env[0] = attack[0]
for i in range(1, len(link)):
    fast_env[i] = fast_alpha * attack[i] + (1.0 - fast_alpha) * fast_env[i-1]
    slow_env[i] = slow_alpha * attack[i] + (1.0 - slow_alpha) * slow_env[i-1]

diff = fast_env - slow_env
r = diff / (slow_env + 1e-6)
r = np.clip(r, -1.0, 1.0)
gain = np.ones_like(r)
mask = diff > 0
if np.any(mask):
    gain[mask] = 1.0 + (10 ** (3/20) - 1.0) * r[mask]
if np.any(~mask):
    gain[~mask] = 1.0 + (10 ** (-3/20) - 1.0) * (-r[~mask])

# inspect gain flutter around 110 Hz
gain_fft = np.fft.rfft(gain)
mag = np.abs(gain_fft)
frequencies = np.fft.rfftfreq(len(gain), d=1/sr)
peak_hz = frequencies[np.argmax(mag[1:])+1]
print('peak_hz', peak_hz)
print('110Hz', mag[np.argmin(np.abs(frequencies-110.0))])
print('165Hz', mag[np.argmin(np.abs(frequencies-165.0))])
print('gain_minmax', gain.min(), gain.max())
print('gain_mean', gain.mean())
