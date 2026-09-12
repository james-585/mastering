from __future__ import annotations

import json

from ..errors import TargetsLoadError
from .schema import TargetsDocument


def load_targets(path: str | None) -> TargetsDocument:
    """Load and validate targets.json, returning a TargetsDocument.

    Raises TargetsLoadError (a MasteringError subclass) on:
    - path is None / not configured
    - file not found at the given path
    - file is not valid JSON
    - required schema keys are missing (raised inside TargetsDocument.from_dict)

    This error propagates immediately as a startup failure; no audio processing
    occurs when targets.json is absent or malformed (architecture §16, DEF-606).
    """
    if path is None:
        raise TargetsLoadError(
            "targets_json_path is not configured — targets.json is required "
            "to run the mastering pipeline; set config.targets_json_path",
            path="",
        )

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise TargetsLoadError(
            f"targets.json not found: {path}",
            path=path,
        )
    except json.JSONDecodeError as exc:
        raise TargetsLoadError(
            f"targets.json is not valid JSON ({exc}): {path}",
            path=path,
        )

    # TargetsDocument.from_dict raises TargetsLoadError on missing/invalid keys
    return TargetsDocument.from_dict(data)
