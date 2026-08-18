import numpy as np
import scipy.signal
import sys
sys.path.insert(0, 'stories/STORY-001/implementation')
from suno_mastering.analysis.artifact_detection import WINDOW_DURATION_S, HOP_SIZE_S

rng = np.random.default_rng(42)
sr = 44100
n = int(sr * 6)
hf_white = rng.standard_normal(n).astype(np.float64)
sos_hf = scipy.signal.butter(6, [8000 / (sr / 2.0), 0.995], btype='band', output='sos')
hf_filtered = scipy.signal.sosfilt(sos_hf, hf_white)
hf_filtered /= (np.std(hf_filtered) + 1e-10)
lf_white = rng.standard_normal(n).astype(np.float64)
sos_lf = scipy.signal.butter(4, [200 / (sr / 2.0), 2000 / (sr / 2.0)], btype='band', output='sos')
lf_filtered = scipy.signal.sosfilt(sos_lf, lf_white)
lf_filtered /= (np.std(lf_filtered) + 1e-10)
signal = lf_filtered * 0.30
signal[int(1.0 * sr):int(4.5 * sr)] += hf_filtered[int(1.0 * sr):int(4.5 * sr)] * 0.10
ws = int(WINDOW_DURATION_S * sr)
hs = int(HOP_SIZE_S * sr)
f, _, Z = scipy.signal.stft(signal, fs=sr, window='hann', nperseg=ws, noverlap=ws - hs, nfft=ws)
mag = np.abs(Z)
hf_mask = (f >= 8000) & (f <= 16000)
lf_mask = (f >= 200) & (f <= 2000)
E_HF = np.sqrt(np.mean(mag[hf_mask, :] ** 2, axis=0))
E_LF = np.sqrt(np.mean(mag[lf_mask, :] ** 2, axis=0))
print('median HF', float(np.median(E_HF)))
print('p90 HF', float(np.percentile(E_HF, 90)))
print('p99 HF', float(np.percentile(E_HF, 99)))
print('median LF', float(np.median(E_LF)))
print('p90 LF', float(np.percentile(E_LF, 90)))
print('p99 LF', float(np.percentile(E_LF, 99)))
print('haze-window stats:')
for i in range(len(E_HF) - 7):
    hw = E_HF[i:i+8]
    lw = E_LF[i:i+8]
    mh = float(np.mean(hw))
    ml = float(np.mean(lw))
    if mh < 1e-10:
        continue
    tmi = float(np.std(hw) / mh)
    sh = float(np.std(hw)); sl = float(np.std(lw))
    cc = 0.0 if sh < 1e-10 or sl < 1e-10 else float(np.corrcoef(hw, lw)[0,1])
    if not np.isfinite(cc):
        cc = 0.0
    if i >= int(1.0*sr/ws) and i <= int(4.5*sr/ws):
        print('window', i, 'meanHF', mh, 'tmi', tmi, 'cc', cc, 'ratio', mh/(ml+1e-12))
        break
print('qual count base', sum(1 for i in range(len(E_HF)-7) if (np.std(E_HF[i:i+8])/np.mean(E_HF[i:i+8]) < 0.10) and (np.corrcoef(E_HF[i:i+8], E_LF[i:i+8])[0,1] < 0.30 if np.std(E_HF[i:i+8])>1e-10 and np.std(E_LF[i:i+8])>1e-10 else True)))
