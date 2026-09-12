"""Enables `python -m suno_mastering.reference_analysis <reference_dir> [...]`."""
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
