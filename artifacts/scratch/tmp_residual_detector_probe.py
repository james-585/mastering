import numpy as np

sr=44100
n=sr*2
f=55.0
t=np.arange(n)/sr
x=np.sin(2*np.pi*f*t)
audio=np.stack([x,x],axis=1)

def hp(x, cutoff=1500.0):
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

hp0 = hp(audio[:,0], 1500.0)
hp1 = hp(audio[:,1], 1500.0)
link = np.maximum(np.abs(hp0), np.abs(hp1))
# use energy residual model
base = np.empty_like(link)
res = np.empty_like(link)
prev_res = 0.0
fast = np.empty_like(link)
slow = np.empty_like(link)
fast_alpha = 1.0 - np.exp(-1.0/(0.002*sr))
slow_alpha = 1.0 - np.exp(-1.0/(0.250*sr))
base[0] = link[0]**2
res[0]=max(0.0, link[0]**2 - base[0])
fast[0]=slow[0]=res[0]
for i in range(1, len(link)):
    e = link[i]**2
    base[i] = 0.15 * e + 0.85 * base[i-1]
    res[i] = max(0.0, e - base[i])
    attack = max(0.0, res[i] - prev_res)
    prev_res = res[i]
    fast[i] = fast_alpha * attack + (1.0-fast_alpha)*fast[i-1]
    slow[i] = slow_alpha * attack + (1.0-slow_alpha)*slow[i-1]

diff = fast-slow
r = diff/(slow + 1e-6)
r = np.clip(r, -1, 1)
gain = np.ones_like(r)
mask = diff > 0
gain[mask] = 1 + (10**(3/20)-1)*r[mask]
gain[~mask] = 1 + (10**(-3/20)-1)*(-r[~mask])
# evaluate smooth gain change spectrum
mag=np.abs(np.fft.rfft(gain))
freqs=np.fft.rfftfreq(len(gain),1/sr)
idx=np.argmax(mag[1:])+1
print('peak_hz', freqs[idx])
print('110', mag[np.argmin(np.abs(freqs-110.0))])
print('165', mag[np.argmin(np.abs(freqs-165.0))])
print('gain_range', gain.min(), gain.max())
print('max attack', np.max(res), np.max(diff), np.max(link), np.max(np.abs(hp0)))
