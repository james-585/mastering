import numpy as np

from final_quality_review import evaluate_quality_review


SR = 48000


def _stereo_signal(freq_hz=220.0, amplitude=0.25, width=0.10, duration=0.5):
    t = np.linspace(0.0, duration, int(SR * duration), endpoint=False)
    tone = np.sin(2 * np.pi * freq_hz * t)
    left = tone * amplitude
    right = tone * (amplitude * (1.0 + width))
    return np.column_stack([left, right]).astype(np.float64)


def test_good_master_passes_review():
    original = _stereo_signal(freq_hz=220.0, amplitude=0.34, width=0.11)
    processed = _stereo_signal(freq_hz=220.0, amplitude=0.30, width=0.18)
    processed[:, 0] += 0.18 * np.sin(2 * np.pi * 12.0 * np.linspace(0.0, 0.5, processed.shape[0], endpoint=False))
    processed[:, 1] += 0.14 * np.sin(2 * np.pi * 9.0 * np.linspace(0.0, 0.5, processed.shape[0], endpoint=False))

    result = evaluate_quality_review(original, processed)

    assert result.decision == "pass"
    assert result.summary.lower().startswith("pass")
    assert "dullness" not in " ".join(result.flags).lower()


def test_dull_or_overprocessed_master_is_rejected():
    original = _stereo_signal(freq_hz=180.0, amplitude=0.32, width=0.16)
    processed = np.clip(original * 0.35, -0.8, 0.8)
    processed = processed * 0.6
    processed[:, 0] *= 0.65
    processed[:, 1] *= 0.65

    result = evaluate_quality_review(original, processed)

    assert result.decision == "reject"
    assert any(flag in {"dullness", "over_processing", "fatigue"} for flag in result.flags)


def test_quieter_flatter_master_is_not_passed():
    original = _stereo_signal(freq_hz=220.0, amplitude=0.34, width=0.11)
    processed = _stereo_signal(freq_hz=220.0, amplitude=0.28, width=0.08)
    processed[:, 0] += 0.03 * np.sin(2 * np.pi * 12.0 * np.linspace(0.0, 0.5, processed.shape[0], endpoint=False))
    processed[:, 1] += 0.02 * np.sin(2 * np.pi * 9.0 * np.linspace(0.0, 0.5, processed.shape[0], endpoint=False))

    result = evaluate_quality_review(original, processed)

    assert result.decision != "pass"
    assert any(flag in {"dullness", "over_processing", "fatigue"} for flag in result.flags)


def test_fatigued_or_artificial_master_is_flagged():
    original = _stereo_signal(freq_hz=160.0, amplitude=0.26, width=0.12)
    processed = _stereo_signal(freq_hz=170.0, amplitude=0.26, width=0.55)
    processed[:, 0] += 0.5 * np.sin(2 * np.pi * 7000.0 * np.linspace(0.0, 0.5, processed.shape[0], endpoint=False))
    processed[:, 1] += 0.5 * np.sin(2 * np.pi * 7200.0 * np.linspace(0.0, 0.5, processed.shape[0], endpoint=False))

    result = evaluate_quality_review(original, processed)

    assert result.decision in {"reject", "refine"}
    assert any(flag in {"fatigue", "artificial_width"} for flag in result.flags)


def test_clean_mix_remains_stable():
    original = _stereo_signal(freq_hz=240.0, amplitude=0.28, width=0.13)

    result = evaluate_quality_review(original, original.copy())

    assert result.decision == "pass"
    assert "stable" in result.summary.lower()


def test_human_review_signal_matches_decision():
    original = _stereo_signal(freq_hz=210.0, amplitude=0.25, width=0.10)
    processed = _stereo_signal(freq_hz=210.0, amplitude=0.24, width=0.16)

    result = evaluate_quality_review(original, processed, human_review={"decision": "pass", "note": "Clear, controlled, and less fatiguing"})

    assert result.human_decision == "pass"
    assert result.decision == "pass"
    assert "Clear, controlled" in result.human_note
