from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict
import json

from ..errors import TargetsLoadError


@dataclass
class TargetsDocument:
    """In-memory representation of targets.json.

    Fields match the top-level keys of the schema (architecture §7, STORY-006).
    stereo_width was named per_band_stereo_width in the original generator;
    DEF-604 renames it and adds per-band correction parameters.
    """
    version: str
    provenance: Dict[str, Any]
    hard_targets: Dict[str, Any]
    spectral_bands: Dict[str, Any]
    de_mud: Dict[str, Any]
    stereo_width: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TargetsDocument":
        required = [
            "version",
            "provenance",
            "hard_targets",
            "spectral_bands",
            "de_mud",
            "stereo_width",
        ]
        for k in required:
            if k not in d:
                raise TargetsLoadError(
                    f"missing required key in targets.json: '{k}' — "
                    f"regenerate targets.json with generate_targets.py",
                    path="",
                )
        return cls(
            version=d["version"],
            provenance=d["provenance"],
            hard_targets=d["hard_targets"],
            spectral_bands=d["spectral_bands"],
            de_mud=d["de_mud"],
            stereo_width=d["stereo_width"],
            metadata=d.get("metadata", {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version":        self.version,
            "provenance":     self.provenance,
            "hard_targets":   self.hard_targets,
            "spectral_bands": self.spectral_bands,
            "de_mud":         self.de_mud,
            "stereo_width":   self.stereo_width,
            "metadata":       self.metadata,
        }

    def dump(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
