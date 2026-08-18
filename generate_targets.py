"""Repository shim to generate targets.json from a reference_set_report.json

Usage:
  python generate_targets.py "Reference Tracks/reference_set_report.json" targets.json
"""
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
fallback = root / "stories" / "STORY-001" / "implementation"
if str(fallback) not in sys.path:
    sys.path.insert(0, str(fallback))

from suno_mastering.targets.targets_generator import main


def _main(argv):
    if len(argv) != 3:
        print("usage: python generate_targets.py <report.json> <targets.json>")
        return 2
    _, report, out = argv
    main(report, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
