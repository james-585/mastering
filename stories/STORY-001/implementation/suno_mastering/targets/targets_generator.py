"""Generate targets.json from a reference_set_report.json containing ReferenceMeasurements.

Usage: call main(report_path, out_path) or run as module.

Note on sample rates: the five reference tracks in reference_set_report.json are
at 48000 Hz (Nyquist = 24000 Hz).  Architecture §4.3 states "All three contributing
tracks are expected to be at 44100 Hz" — this is factually incorrect for the actual
tracks used.  The generator formula (min(24000, min Nyquist across contributors))
is correct and produces 24000 Hz for the current tracks; the architecture §4.3
expected value of 22050 Hz is wrong.  DEF-604 documents this discrepancy.
"""
from __future__ import annotations
import json
from pathlib import Path
from statistics import median
from typing import Any, Dict, List
import unicodedata


CONTRIBUTING = [
    "Chemical Brothers — Live Again",
    "GusGus — Over (Arabian Horse)",
    "Black Flute (Remastered)",
]

# Band classification per architecture §7 / DEF-604:
# "soft" = corrective EQ applied (sub, low_mid)
# "informational" = no corrective EQ; measurement only
_BAND_CLASSIFICATION: Dict[str, str] = {
    "sub":      "soft",
    "low":      "informational",
    "low_mid":  "soft",
    "mid":      "informational",
    "high_mid": "informational",
    "high":     "informational",
    "air":      "informational",
}

# Correction cap for "soft" bands only (2.0 dB, fixed policy per architecture §9 Cat B)
_CORRECTION_CAP_DB: Dict[str, float] = {
    "sub":     2.0,
    "low_mid": 2.0,
}

# Fixed correction parameters for the stereo_width block.
# These are policy values (Category C in architecture §9) — not derived from
# reference measurements.  Applied identically to sub and low bands.
_STEREO_WIDTH_CORRECTION_PARAMS: Dict[str, float] = {
    "near_mono_threshold":  0.15,
    "correction_aim_point": 0.15,
    "correction_floor":     0.10,
    "max_correction_step":  0.15,
}


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s).strip().casefold()


def _norm_identifier(s: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else " " for ch in s)
    return " ".join(cleaned.split()).strip().casefold()


def _find_track(entries: List[Dict[str, Any]], name: str) -> Dict[str, Any]:
    target = _norm(name)
    target_id = _norm_identifier(name)
    for e in entries:
        label = e.get("label") or ""
        if _norm(label) == target or _norm_identifier(label) == target_id:
            return e
        # fallback: filename stem
        path = e.get("track_path") or ""
        stem = path.split("/")[-1].rsplit(".", 1)[0]
        if _norm(stem) == target or _norm_identifier(stem) == target_id:
            return e
        stem_id = _norm_identifier(stem)
        if target_id and stem_id and target_id in stem_id:
            return e
        if target_id and stem_id and stem_id in target_id:
            return e
        target_words = set(target_id.split())
        stem_words = set(stem_id.split())
        if target_words and stem_words and target_words.issubset(stem_words):
            return e
    raise ValueError(f"contributing track not found in report: {name}")


def _band_map(entry: Dict[str, Any]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for b in entry.get("seven_band", {}).get("bands", []):
        out[b["band"]] = float(b["relative_db"])
    return out


def _width_map(entry: Dict[str, Any]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for b in entry.get("per_band_stereo_width", {}).get("bands", []):
        out[b["band"]] = float(b["width"])
    return out


def main(report_path: str, out_path: str) -> None:
    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    entries = report
    if isinstance(report, dict) and "per_track" in report:
        entries = report["per_track"]

    # Resolve contributors — hard failure if any name is missing (§4.2)
    resolved: List[Dict[str, Any]] = []
    for name in CONTRIBUTING:
        resolved.append(_find_track(entries, name))

    assert len(resolved) == len(CONTRIBUTING), (
        f"expected {len(CONTRIBUTING)} contributing tracks, resolved {len(resolved)}"
    )

    # Seven-band spectral statistics across the three contributing tracks
    bands = ["sub", "low", "low_mid", "mid", "high_mid", "high", "air"]
    spectral_stats: Dict[str, Dict[str, float]] = {}
    for band in bands:
        vals = []
        for e in resolved:
            bm = _band_map(e)
            if band not in bm:
                raise ValueError(f"band {band!r} missing for track {e.get('label')!r}")
            vals.append(bm[band])
        spectral_stats[band] = {
            "min": min(vals),
            "max": max(vals),
            "median": median(vals),
        }

    # Per-band stereo width statistics
    width_stats: Dict[str, Dict[str, float]] = {}
    for band in bands:
        vals = []
        for e in resolved:
            wm = _width_map(e)
            if band not in wm:
                raise ValueError(f"width band {band!r} missing for track {e.get('label')!r}")
            vals.append(wm[band])
        width_stats[band] = {
            "min": min(vals),
            "max": max(vals),
            "median": median(vals),
        }

    # Dynamic range statistics — DEF-604 fix 1: use range_min/range_max/target_median
    dr_vals = [float(e["dynamic_range_db_exact"]) for e in resolved]
    dr = {
        "range_min":     min(dr_vals),
        "range_max":     max(dr_vals),
        "target_median": median(dr_vals),
    }

    # Air band upper edge — DEF-604 fix 4: lower edge is fixed at 10000 Hz (seven-band scheme)
    # Air upper edge: min(24000, min Nyquist across contributing tracks)
    # Note: actual tracks are at 48000 Hz (Nyquist = 24000 Hz); architecture §4.3 states
    # 44100 Hz which is factually incorrect for the current reference set.
    srs = [int(e.get("core", {}).get("sample_rate", 44100)) for e in resolved]
    nyquists = [sr // 2 for sr in srs]
    air_upper = min(24000, min(nyquists))

    def _entry_label(entry: Dict[str, Any]) -> str:
        label = entry.get("label")
        if label:
            return label
        path = entry.get("track_path") or ""
        return Path(path).stem if path else ""

    # Frequency band bounds — DEF-604 fix 4: high/air boundary fixed at 10000 Hz
    freq_map: Dict[str, List[int]] = {
        "sub":      [20,    60],
        "low":      [60,    120],
        "low_mid":  [120,   500],
        "mid":      [500,   2000],
        "high_mid": [2000,  5000],
        "high":     [5000,  10000],   # fixed boundary (seven-band scheme)
        "air":      [10000, air_upper],  # fixed lower edge at 10000 Hz
    }

    # Build spectral_bands with classification and correction_cap_db (DEF-604 fix 2)
    spectral_bands: Dict[str, Any] = {}
    for band in bands:
        entry: Dict[str, Any] = {
            "freq_hz":         freq_map[band],
            "classification":  _BAND_CLASSIFICATION[band],
            "range_db_re_mid": {
                "min": spectral_stats[band]["min"],
                "max": spectral_stats[band]["max"],
            },
            "median_db_re_mid": spectral_stats[band]["median"],
        }
        if band in _CORRECTION_CAP_DB:
            entry["correction_cap_db"] = _CORRECTION_CAP_DB[band]
        spectral_bands[band] = entry

    # Build stereo_width block — DEF-604 fix 5:
    # renamed from per_band_stereo_width; correction parameters added per band
    stereo_width: Dict[str, Any] = {}
    for band in bands:
        stereo_width[band] = {
            "min":    width_stats[band]["min"],
            "max":    width_stats[band]["max"],
            "median": width_stats[band]["median"],
            **_STEREO_WIDTH_CORRECTION_PARAMS,
        }

    targets = {
        "version": "1.0",
        "provenance": {
            "contributing_tracks": CONTRIBUTING,
            "excluded_tracks": [
                _entry_label(t)
                for t in entries
                if t not in resolved
            ],
            "exclusion_reason": (
                "See STORY-006 requirements: Leftfield and Wavy Gravy excluded by design"
            ),
        },
        "hard_targets": {
            "integrated_lufs": {"value": -13.5, "tolerance_lu": 0.5},
            "true_peak_dbtp":  {"ceiling": -1.0},
            "dynamic_range_db": dr,
        },
        "spectral_bands": spectral_bands,
        # DEF-604 fix 3: add applies_to_band
        "de_mud": {
            "flag_threshold_db_above_mid": 4.0,
            "correction_aim_point_db":     2.0,
            "applies_to_band":             "low_mid",
        },
        # DEF-604 fix 5: renamed from per_band_stereo_width
        "stereo_width": stereo_width,
        "metadata": {"air_upper_edge_hz": air_upper},
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(targets, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print(
            "usage: python -m suno_mastering.targets.targets_generator "
            "<report.json> <targets.json>"
        )
        sys.exit(2)
    main(sys.argv[1], sys.argv[2])
