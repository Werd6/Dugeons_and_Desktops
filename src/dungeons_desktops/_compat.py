"""One-release compatibility helpers for modules moved into feature packages."""

from __future__ import annotations

import importlib
import sys
import warnings
from types import ModuleType


def moved_module(old: str, new: str) -> ModuleType:
    """Return the canonical module for a deprecated import path."""
    module = importlib.import_module(new)
    warnings.warn(
        f"{old} moved to {new}; update the import before the next release",
        DeprecationWarning,
        stacklevel=2,
    )
    sys.modules[old] = module
    return module
