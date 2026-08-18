import glob, os
import numpy as np
import scipy.signal
import soundfile as sf


def get_stats(signal, sr):
    ws = int(0.5 * sr)
    hs = int(0.25 * sr)
    f, _, Z = scipy.signal.stft(signal, fs=sr, window='hann', nperseg=ws, noverlap=ws - hs, nfft=ws)
    mag = np.abs(Z)
    hf_mask = (f >= 8000) & (f <= 16000)
    lf_mask = (f >= 200) & (f <= 2000)
    E_HF = np.sqrt(np.mean(mag[hf_mask, :] ** 2, axis=0))
    E_LF = np.sqrt(np.mean(mag[lf_mask, :] ** 2, axis=0))
    vals = []
    for i in range(len(E_HF) - 7):
        hf_win = E_HF[i:i+8]
        lf_win = E_LF[i:i+8]
        mean_hf = float(np.mean(hf_win))
        mean_lf = float(np.mean(lf_win))
        if mean_hf < 1e-10:
            continue
        local_start = max(0, i - 8)
        local_end = min(len(E_HF), i + 16)
        local = np.concatenate((E_HF[local_start:i], E_HF[i+8:local_end]))
        if local.size == 0:
            local = E_HF
        floor = float(np.median(local))
        tmi = float(np.std(hf_win) / mean_hf)
        std_hf = float(np.std(hf_win)); std_lf = float(np.std(lf_win))
        cc = 0.0 if std_hf < 1e-10 or std_lf < 1e-10 else float(np.corrcoef(hf_win, lf_win)[0, 1])
        if not np.isfinite(cc):
            cc = 0.0
        vals.append({
            'ratio': mean_hf / (floor + 1e-12),
            'mean_hf': mean_hf,
            'floor': floor,
            'tmi': tmi,
            'cc': cc,
            'hf_lf_ratio': mean_hf / (mean_lf + 1e-12),
        })
    if not vals:
        return None
    ratios = np.array([v['ratio'] for v in vals], dtype=float)
    return {
        'min': float(ratios.min()),
        'p50': float(np.percentile(ratios, 50)),
        'p90': float(np.percentile(ratios, 90)),
        'p95': float(np.percentile(ratios, 95)),
        'p99': float(np.percentile(ratios, 99)),
        'max': float(ratios.max()),
        'count': len(vals),
        'top': sorted(vals, key=lambda v: v['ratio'], reverse=True)[:5],
    }

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
print('synthetic', get_stats(signal, sr))

for path in sorted(glob.glob('Reference Tracks/*.wav')):
    audio, sr = sf.read(path, always_2d=True)
    mono = audio[:,0].astype(np.float64)
    print(os.path.basename(path), get_stats(mono, sr))
