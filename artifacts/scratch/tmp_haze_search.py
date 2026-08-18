import os, sys, numpy as np, soundfile as sf
from scipy.signal import stft
sys.path.insert(0, os.path.join('stories','STORY-001','implementation'))
from suno_mastering.analysis import artifact_detection as ad

ref = [
    'Reference Tracks/GusGus_-_Over_Arabian_Horse_Album.wav',
    'Reference Tracks/Black_Flute_Remastered.wav',
    'Reference Tracks/The_Chemical_Brothers_-_Live_Again_ft_Halo_Maud.wav',
    'Reference Tracks/Leftfield_-_Melt_Audio.wav',
    'Reference Tracks/Wavy_Gravy.wav',
]
noise = [
    'Reference Tracks/Cavernous Rave (Edit).wav',
    'Reference Tracks/Sunday Club.wav',
    'Reference Tracks/This one.wav',
]


def candidate_count(path, tmi_thr, cc_thr, hf_lf_ratio_min, e_hf_floor, min_consecutive=4):
    audio, sr = sf.read(path, always_2d=True)
    mono = audio[:,0].astype(np.float64)
    ws = int(ad.WINDOW_DURATION_S * sr)
    hs = int(ad.HOP_SIZE_S * sr)
    freqs, _, Zxx = stft(mono, fs=sr, window='hann', nperseg=ws, noverlap=ws-hs, nfft=ws)
    mag = np.abs(Zxx)
    hf_mask = (freqs >= 8000) & (freqs <= 16000)
    lf_mask = (freqs >= 200) & (freqs <= 2000)
    E_HF = np.sqrt(np.mean(mag[hf_mask, :] ** 2, axis=0))
    E_LF = np.sqrt(np.mean(mag[lf_mask, :] ** 2, axis=0))
    track_hf_median = float(np.median(E_HF))
    pos = []
    for i in range(len(E_HF) - 7):
        hf_w = E_HF[i:i+8]
        lf_w = E_LF[i:i+8]
        mean_hf = float(np.mean(hf_w))
        if mean_hf < 1e-10:
            continue
        tmi = float(np.std(hf_w)/mean_hf)
        std_hf = float(np.std(hf_w)); std_lf=float(np.std(lf_w))
        cc = 0.0 if std_hf < 1e-10 or std_lf < 1e-10 else float(np.corrcoef(hf_w, lf_w)[0,1])
        if not np.isfinite(cc): cc = 0.0
        ratio = mean_hf / (float(np.mean(lf_w)) + 1e-12)
        if (tmi < tmi_thr and cc < cc_thr and mean_hf > e_hf_floor and ratio > hf_lf_ratio_min and mean_hf > 1.5 * track_hf_median):
            pos.append(i)
    runs = []
    if pos:
        pos = sorted(set(pos))
        start = pos[0]; end = pos[0]
        for x in pos[1:]:
            if x == end + 1:
                end = x
            else:
                if end - start + 1 >= min_consecutive: runs.append((start,end))
                start = end = x
        if end - start + 1 >= min_consecutive: runs.append((start,end))
    return len(runs)

for tmi_thr in [0.05,0.06,0.07,0.08,0.09]:
    for cc_thr in [0.10,0.12,0.15,0.18,0.20]:
        for hf_ratio in [0.2,0.3,0.4,0.5,0.75,1.0]:
            for floor in [1e-5, 3e-5, 5e-5, 1e-4, 3e-4, 5e-4]:
                ref_total = sum(candidate_count(p, tmi_thr, cc_thr, hf_ratio, floor) for p in ref)
                noise_total = sum(candidate_count(p, tmi_thr, cc_thr, hf_ratio, floor) for p in noise)
                if ref_total == 0 and noise_total > 0:
                    print('candidate', {'tmi': tmi_thr, 'cc': cc_thr, 'ratio': hf_ratio, 'floor': floor, 'ref_total': ref_total, 'noise_total': noise_total})
                    raise SystemExit
print('NO_CANDIDATE_FOUND')
