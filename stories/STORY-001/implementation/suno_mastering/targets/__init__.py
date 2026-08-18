from .loader import load_targets
from .schema import TargetsDocument
from .targets_generator import main as generate_targets

__all__ = ["load_targets", "TargetsDocument", "generate_targets"]
