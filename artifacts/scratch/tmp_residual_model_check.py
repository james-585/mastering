import numpy as np

sr=44100
n=sr*2
f=55.0
t=np.arange(n)/sr
x=np.sin(2*np.pi*f*t)

def hp2(x, cutoff, sr):
    q=0.70710678
    omega=2*np.pi*cutoff/sr
    sin_w=np.sin(omega); cos_w=np.cos(omega); alpha=sin_w/(2*q)
    b0=(1+cos_w)*0.5; b1=-(1+cos_w); b2=(1+cos_w)*0.5; a0=1+alpha; a1=-2*cos_w; a2=1-alpha
    b0n,b1n,b2n=b0/a0,b1/a0,b2/a0; a1n,a2n=a1/a0,a2/a0
    y=np.empty_like(x); x1=x2=y1=y2=0.0
    for i,s in enumerate(x):
        y[i]=b0n*s+b1n*x1+b2n*x2 - a1n*y1-a2n*y2
        x2,x1=x1,s; y2,y1=y1,y[i]
    return y

hp = hp2(x, 150.0, sr)
link = np.abs(hp)
base = np.empty_like(link)
res = np.empty_like(link)
prev = 0.0
fast = np.empty_like(link)
slow = np.empty_like(link)
fast_alpha = 1.0 - np.exp(-1.0 / (0.002 * sr))
slow_alpha = 1.0 - np.exp(-1.0 / (0.250 * sr))
base[0] = link[0]
res[0] = max(0.0, link[0] - base[0])
fast[0] = slow[0] = res[0]
for i in range(1, len(link)):
    base[i] = 0.995 * base[i-1] + 0.005 * link[i]
    res[i] = max(0.0, link[i] - base[i])
    attack = max(0.0, res[i] - prev)
    prev = res[i]
    fast[i] = fast_alpha * attack + (1-fast_alpha) * fast[i-1]
    slow[i] = slow_alpha * attack + (1-slow_alpha) * slow[i-1]

diff = fast - slow
ratio = diff / (slow + 1e-6)
ratio = np.clip(ratio, -1.0, 1.0)
gain = np.ones_like(ratio)
mask = diff > 0
gain[mask] = 1.0 + (10**(3/20)-1.0) * ratio[mask]
gain[~mask] = 1.0 + (10**(-3/20)-1.0) * (-ratio[~mask])
mag = np.abs(np.fft.rfft(gain))
freqs = np.fft.rfftfreq(len(gain), d=1.0/sr)
idx = np.argmax(mag[1:]) + 1
print('peak_hz', freqs[idx])
print('110mag', mag[np.argmin(np.abs(freqs-110.0))])
print('165mag', mag[np.argmin(np.abs(freqs-165.0))])
print('gain_range', gain.min(), gain.max())
print('max_link', link.max(), 'max_res', res.max(), 'max_diff', diff.max())
