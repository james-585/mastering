import os, sys
sys.path.insert(0, os.path.join('stories','STORY-001','implementation'))
import soundfile as sf
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

def count_haze(path, tmi_thr, cc_thr):
    audio, sr = sf.read(path, always_2d=True)
    ad._HAZE_TMI_THRESHOLD = tmi_thr
    ad._HAZE_CC_THRESHOLD = cc_thr
    _, res = ad.detect_artifacts(audio.astype('float64'), sr)
    return sum(1 for f in res.artifact_flags if f.artifact_type == 'DIGITAL_HAZE')

# Current thresholds
print('CURRENT_THRESHOLDS', ad._HAZE_TMI_THRESHOLD, ad._HAZE_CC_THRESHOLD)
for p in ref + noise:
    c = count_haze(p, ad._HAZE_TMI_THRESHOLD, ad._HAZE_CC_THRESHOLD)
    print(os.path.basename(p), c)

print('SEARCHING_FOR_ZERO_REFERENCE_PAIR')
for tmi in [0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.12, 0.15, 0.20, 0.25, 0.30]:
    for cc in [0.10, 0.12, 0.15, 0.18, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60, 0.70]:
        ref_counts = {os.path.basename(p): count_haze(p, tmi, cc) for p in ref}
        noise_counts = {os.path.basename(p): count_haze(p, tmi, cc) for p in noise}
        ref_total = sum(ref_counts.values())
        noise_total = sum(noise_counts.values())
        if ref_total == 0 and noise_total > 0:
            print('CANDIDATE', {'tmi': tmi, 'cc': cc, 'ref_counts': ref_counts, 'noise_counts': noise_counts, 'ref_total': ref_total, 'noise_total': noise_total})
            raise SystemExit
print('NO_ZERO_REFERENCE_CANDIDATE_FOUND')
