"""Compatibility exports for equipment moved to feature packages."""

from __future__ import annotations

import warnings

warnings.warn(
    "dungeons_desktops.rig.weapons moved to rig.equipment and game feature packages",
    DeprecationWarning,
    stacklevel=2,
)

from dungeons_desktops.rig.equipment import *  # noqa: E402,F403
