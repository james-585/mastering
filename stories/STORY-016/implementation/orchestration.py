from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FOR_IMPORT = [
    _REPO_ROOT / "stories" / "STORY-011" / "implementation",
    _REPO_ROOT / "stories" / "STORY-012" / "implementation",
    _REPO_ROOT / "stories" / "STORY-013" / "implementation",
    _REPO_ROOT / "stories" / "STORY-014" / "implementation",
    _REPO_ROOT / "stories" / "STORY-015" / "implementation",
    _REPO_ROOT / "stories" / "STORY-025" / "implementation",
]
for _path in _FOR_IMPORT:
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from final_bus_glue import apply_final_bus_glue
from grounded_quality_review import evaluate_quality_review
from harshness_control import apply_stem_harshness_control
from stem_stereo_imaging import apply_stem_stereo_imaging
from transient_restoration import apply_stem_transient_restoration


class MasteringOrchestrator:
    """Coordinate the validated stem-first mastering stages into one auditable product flow."""

    STAGE_ORDER = [
        "ingest",
        "analysis",
        "stem_choice",
        "transient_restoration",
        "harshness_control",
        "stereo_imaging",
        "bus_glue",
        "final_safety",
        "quality_review",
    ]

    def run(
        self,
        audio: np.ndarray,
        sample_rate: int,
        stems: Optional[Dict[str, np.ndarray]] = None,
        use_stems: bool = True,
        allow_stereo_fallback: bool = False,
        human_review: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")

        source = np.asarray(audio, dtype=np.float64)
        if source.ndim not in {1, 2}:
            raise ValueError(f"Unsupported audio shape: {source.shape}; expected 1D or 2D")

        audit: list[dict[str, Any]] = []
        audit.append(self._audit_step("ingest", "ok", "Input audio accepted and converted to float64 for downstream processing."))

        original = source.copy()
        analysis = self._analyze_input(original, sample_rate)
        audit.append(self._audit_step("analysis", "ok", analysis["summary"]))

        mode = "stem_first"
        stage_stems: Dict[str, np.ndarray]
        if stems is not None and use_stems:
            stage_stems = {name: np.asarray(value, dtype=np.float64) for name, value in stems.items()}
            if not stage_stems:
                raise ValueError("Stem-aware pipeline requires at least one valid stem when use_stems=True")
            mode = "stem_first"
            audit.append(self._audit_step("stem_choice", "ok", "Stem-first workflow selected; stage corrections continue on real stem data."))
        elif stems is None and allow_stereo_fallback and use_stems:
            stage_stems = {"mix": original.copy()}
            mode = "stereo_fallback"
            audit.append(self._audit_step("stem_choice", "fallback", "No valid stems were provided; explicit stereo fallback was invoked. This is a limited path and must be reported."))
        elif stems is not None and not use_stems:
            stage_stems = {"mix": np.asarray(stems.get("mix", original), dtype=np.float64)} if "mix" in stems else {
                "mix": np.asarray(next(iter(stems.values())), dtype=np.float64)
            }
            mode = "stereo_only"
            audit.append(self._audit_step("stem_choice", "manual", "Stem processing was intentionally bypassed for a direct stereo-only pass."))
        elif stems is None and not use_stems:
            stage_stems = {"mix": original.copy()}
            mode = "stereo_only"
            audit.append(self._audit_step("stem_choice", "manual", "Direct stereo pass selected without stem processing."))
        else:
            raise ValueError("Stem-aware workflow requires valid stems or an explicit stereo fallback allowance.")

        transient_processed, transient_actions = apply_stem_transient_restoration(stage_stems, sample_rate)
        audit.append(self._audit_step("transient_restoration", "ok", self._summarize_actions(transient_actions, "transient restoration")))

        harsh_processed, harsh_actions = apply_stem_harshness_control(transient_processed, sample_rate)
        audit.append(self._audit_step("harshness_control", "ok", self._summarize_actions(harsh_actions, "harshness control")))

        stereo_processed, stereo_actions = apply_stem_stereo_imaging(harsh_processed, sample_rate)
        audit.append(self._audit_step("stereo_imaging", "ok", self._summarize_actions(stereo_actions, "stereo imaging")))

        bus_processed, bus_actions = apply_final_bus_glue(stereo_processed, sample_rate)
        mix = bus_processed.get("mix", self._recombine_bus(stereo_processed))
        mix = self._renormalize_to_input(original, mix)
        audit.append(self._audit_step("bus_glue", "ok", self._summarize_actions(bus_actions, "bus glue and dynamic balance")))

        final_mix, final_peak, final_safety_note = self._apply_final_safety(mix)
        audit.append(self._audit_step("final_safety", "ok", final_safety_note))

        # DEF-2501 (architecture.md §3.1): the unchanged-signal short-circuit no
        # longer overwrites review.decision with a fabricated "pass" -- it is left
        # exactly as evaluate_quality_review() returned it (ordinarily
        # "pending_human_review" when no human review was supplied).
        review = evaluate_quality_review(original, final_mix, sr=sample_rate, human_review=human_review)
        if np.allclose(original, final_mix, atol=1e-6, rtol=1e-6):
            audit.append(self._audit_step(
                "quality_review", review.decision,
                "The processed result is effectively unchanged from the source; no processing occurred, "
                "but the musical review verdict is left as returned (not forcibly overwritten).",
            ))
        else:
            audit.append(self._audit_step("quality_review", review.decision, review.summary))

        # DEF-2501 (architecture.md §3.1): export_allowed is a strictly mechanical
        # export-safety gate (finite samples + true-peak ceiling), decoupled from
        # review.decision. It answers "is it safe to write this file to disk,"
        # not "is this a good master."
        mechanically_safe = bool(np.isfinite(final_mix).all()) and final_peak <= 1.0

        if human_review is not None and review.decision in {"pass", "reject", "refine"}:
            # A real human verdict was supplied inline: honor it.
            export_allowed = mechanically_safe and (review.decision == "pass")
        else:
            # review.decision == "pending_human_review": no trusted musical verdict
            # is available inline; export_allowed answers only the safety question.
            export_allowed = mechanically_safe

        result = {
            "decision": review.decision,
            "mode": mode,
            "output": final_mix,
            "source_shape": tuple(source.shape),
            "sample_rate": sample_rate,
            "final_peak": float(final_peak),
            "audit": audit,
            "quality_report": review.to_dict(),
            "export_allowed": export_allowed,
            "override_reason": human_review.get("note", "") if human_review else "",
            "quality_verdict_pending": review.decision == "pending_human_review",
        }

        if not mechanically_safe:
            result["export_reason"] = (
                "Export blocked: signal contains non-finite samples or exceeds the true-peak safety ceiling."
            )
        elif human_review is not None and review.decision == "reject":
            result["export_reason"] = "Final quality review rejected the output; export requires a pass result or a documented override reason."
        elif human_review is not None and review.decision == "refine":
            result["export_reason"] = "Final quality review requires refinement before export."
        elif review.decision == "pending_human_review":
            result["export_reason"] = "Export permitted on mechanical safety grounds only; no human quality verdict has been supplied for this file."
        else:
            result["export_reason"] = "Approved for export."

        return result

    @staticmethod
    def _audit_step(stage: str, status: str, summary: str) -> Dict[str, Any]:
        return {"stage": stage, "status": status, "summary": summary}

    @staticmethod
    def _analyze_input(audio: np.ndarray, sample_rate: int) -> Dict[str, Any]:
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        width = 0.0
        if audio.ndim == 2 and audio.shape[1] == 2:
            left = audio[:, 0]
            right = audio[:, 1]
            mid = 0.5 * (left + right)
            side = 0.5 * (left - right)
            mid_rms = float(np.sqrt(np.mean(mid ** 2)))
            side_rms = float(np.sqrt(np.mean(side ** 2)))
            width = float(side_rms / (mid_rms + 1e-9))
        return {
            "sample_rate": sample_rate,
            "peak": peak,
            "stereo_width": width,
            "summary": f"Input analysis captured sample rate {sample_rate} Hz, peak {peak:.4f}, and stereo width {width:.4f}.",
        }

    @staticmethod
    def _summarize_actions(actions: Iterable[Any], stage_name: str) -> str:
        items = list(actions)
        if not items:
            return f"{stage_name}: no change required; the signal was already within safe limits."
        summary = "; ".join(
            f"{item.stem_name}: {item.action_type} ({item.gain_db:.2f} dB)" if hasattr(item, "gain_db") else str(item)
            for item in items[:3]
        )
        if len(items) > 3:
            summary = summary + f"; +{len(items) - 3} additional actions"
        return f"{stage_name}: {summary}"

    @staticmethod
    def _recombine_bus(stems: Dict[str, np.ndarray]) -> np.ndarray:
        if "mix" in stems:
            return np.asarray(stems["mix"], dtype=np.float64).copy()
        if not stems:
            raise ValueError("No stems available for final recombination")
        first = np.asarray(next(iter(stems.values())), dtype=np.float64)
        mix = np.zeros_like(first, dtype=np.float64)
        for value in stems.values():
            arr = np.asarray(value, dtype=np.float64)
            if arr.shape != mix.shape:
                raise ValueError(f"Stem shape mismatch in bus recombination: {arr.shape} vs {mix.shape}")
            mix = mix + arr
        return mix

    @staticmethod
    def _renormalize_to_input(original: np.ndarray, processed: np.ndarray) -> np.ndarray:
        orig = np.asarray(original, dtype=np.float64)
        proc = np.asarray(processed, dtype=np.float64)
        if proc.size == 0:
            return proc.copy()

        orig_peak = float(np.max(np.abs(orig))) if orig.size else 0.0
        proc_peak = float(np.max(np.abs(proc))) if proc.size else 0.0
        if orig_peak <= 0.0 or proc_peak <= 0.0:
            return proc.copy()

        scale = min(1.0, orig_peak / proc_peak)
        if np.isclose(scale, 1.0):
            return proc.copy()
        return proc * scale

    @staticmethod
    def _true_peak(audio: np.ndarray, oversample: int = 8) -> float:
        arr = np.asarray(audio, dtype=np.float64)
        mono = arr.mean(axis=1) if arr.ndim == 2 else arr
        if mono.size == 0:
            return 0.0
        x = np.arange(mono.size, dtype=np.float64)
        up = np.arange(0, mono.size, 1.0 / oversample, dtype=np.float64)
        oversampled = np.interp(up, x, mono)
        return float(np.max(np.abs(oversampled)))

    @staticmethod
    def _apply_final_safety(mix: np.ndarray) -> tuple[np.ndarray, float, str]:
        arr = np.asarray(mix, dtype=np.float64)
        if arr.size == 0:
            return arr.copy(), 0.0, "Final safety: empty signal remained empty."

        peak = MasteringOrchestrator._true_peak(arr)
        if peak <= 1.0:
            return arr.copy(), peak, "Final safety: true peak remained under the project ceiling; no attenuation needed."
        attenuation = 0.98 / peak
        out = arr * attenuation
        out = np.clip(out, -1.0, 1.0)
        final_peak = MasteringOrchestrator._true_peak(out)
        return out, final_peak, "Final safety: oversampled true peak exceeded the safe ceiling, so a measured attenuation was applied."


__all__ = ["MasteringOrchestrator"]
