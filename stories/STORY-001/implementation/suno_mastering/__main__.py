"""Enables `python -m suno_mastering <input.wav> [...]`."""
import sys

from .cli import main

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - final guard against unexpected runtime faults
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
