import numpy as np, scipy.signal, sys
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
haze_start = 1.0
haze_end = 4.5
haze_n = int((haze_end - haze_start) * sr)
signal[int(haze_start * sr):int(haze_end * sr)] += hf_filtered[int(haze_start * sr):int(haze_end * sr)] * 0.10
ws = int(WINDOW_DURATION_S * sr)
hs = int(HOP_SIZE_S * sr)
f, _, Z = scipy.signal.stft(signal, fs=sr, window='hann', nperseg=ws, noverlap=ws - hs, nfft=ws)
mag = np.abs(Z)
hf = (f >= 8000) & (f <= 16000)
lf = (f >= 200) & (f <= 2000)
E_HF = np.sqrt(np.mean(mag[hf, :] ** 2, axis=0))
E_LF = np.sqrt(np.mean(mag[lf, :] ** 2, axis=0))
print('mean_hf', float(np.mean(E_HF)))
print('median_hf', float(np.median(E_HF)))
print('p90_hf', float(np.percentile(E_HF, 90)))
print('mean_lf', float(np.mean(E_LF)))
print('median_lf', float(np.median(E_LF)))
print('p90_lf', float(np.percentile(E_LF, 90)))
qual = []
for i in range(len(E_HF) - 7):
    hw = E_HF[i:i+8]; lw = E_LF[i:i+8]
    mh = float(np.mean(hw)); ml = float(np.mean(lw))
    if mh < 1e-10: continue
    tmi = float(np.std(hw) / mh)
    sh = float(np.std(hw)); sl = float(np.std(lw))
    cc = 0.0 if sh < 1e-10 or sl < 1e-10 else float(np.corrcoef(hw, lw)[0,1])
    if not np.isfinite(cc): cc = 0.0
    qual.append((mh, tmi, cc, mh / (ml + 1e-12)))
print('qual_count_all_base', sum(1 for mh, tmi, cc, ratio in qual if tmi < 0.1 and cc < 0.3))
print('qual_count_strict', sum(1 for mh, tmi, cc, ratio in qual if tmi < 0.1 and cc < 0.3 and mh > 5e-4 and ratio > 0.25))
print('best_base', sorted(qual, key=lambda x: x[1])[:10])
