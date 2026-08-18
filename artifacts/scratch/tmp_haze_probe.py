import os, sys, numpy as np, soundfile as sf
from scipy.signal import stft
sys.path.insert(0, os.path.join('stories','STORY-001','implementation'))
from suno_mastering.analysis import artifact_detection as ad

paths = [
    ('Black_Flute_Remastered.wav', 'Reference Tracks/Black_Flute_Remastered.wav'),
    ('Chemical_Brothers.wav', 'Reference Tracks/The_Chemical_Brothers_-_Live_Again_ft_Halo_Maud.wav'),
    ('Leftfield.wav', 'Reference Tracks/Leftfield_-_Melt_Audio.wav'),
    ('Wavy_Gravy.wav', 'Reference Tracks/Wavy_Gravy.wav'),
    ('Cavernous_Rave.wav', 'Reference Tracks/Cavernous Rave (Edit).wav'),
    ('Sunday_Club.wav', 'Reference Tracks/Sunday Club.wav'),
]

for label, p in paths:
    audio, sr = sf.read(p, always_2d=True)
    mono = audio[:,0].astype(np.float64)
    ws = int(ad.WINDOW_DURATION_S * sr)
    hs = int(ad.HOP_SIZE_S * sr)
    freqs, _, Zxx = stft(mono, fs=sr, window='hann', nperseg=ws, noverlap=ws-hs, nfft=ws)
    mag = np.abs(Zxx)
    hf_mask = (freqs >= 8000) & (freqs <= 16000)
    lf_mask = (freqs >= 200) & (freqs <= 2000)
    E_HF = np.sqrt(np.mean(mag[hf_mask, :] ** 2, axis=0))
    E_LF = np.sqrt(np.mean(mag[lf_mask, :] ** 2, axis=0))
    print('\nFILE', label)
    hits = []
    for i in range(len(E_HF) - 7):
        hf_w = E_HF[i:i+8]
        lf_w = E_LF[i:i+8]
        mean_hf = float(np.mean(hf_w)); mean_lf = float(np.mean(lf_w))
        if mean_hf < 1e-10:
            continue
        tmi = float(np.std(hf_w) / mean_hf)
        std_hf = float(np.std(hf_w)); std_lf = float(np.std(lf_w))
        cc = 0.0 if std_hf < 1e-10 or std_lf < 1e-10 else float(np.corrcoef(hf_w, lf_w)[0,1])
        if not np.isfinite(cc): cc = 0.0
        if tmi < 0.10 and cc < 0.30:
            hits.append((i, tmi, cc, mean_hf, mean_lf, mean_hf/(mean_lf + 1e-12)))
    print('qualifying windows', len(hits))
    for row in hits[:8]:
        print('  win', row[0], 'tmi', round(row[1],4), 'cc', round(row[2],4), 'hf', round(row[3],6), 'lf', round(row[4],6), 'ratio', round(row[5],4))
