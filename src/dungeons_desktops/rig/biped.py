"""Which bones of a skeleton play which role in a two-legged walker."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from dungeons_desktops.rig.ik import IkChain
from dungeons_desktops.rig.skeleton import Skeleton

if TYPE_CHECKING:
    from dungeons_desktops.rig.climb import ClimbSettings
    from dungeons_desktops.rig.walk import WalkSettings

UP = -math.pi / 2


@dataclass(frozen=True)
class BipedLayout:
    skeleton: Skeleton
    pelvis: str
    torso: str
    head: str
    legs: tuple[IkChain, ...]
    arms: tuple[IkChain, ...]
    head_radius: float
    walk: WalkSettings | None = None
    climb: ClimbSettings | None = None
    scale: float = 1.0
    """Size relative to the creature's reference size; props, hit radii and drawn line
    widths that aren't derived from bone lengths multiply by it."""

    @property
    def chains(self) -> tuple[IkChain, ...]:
        return self.legs + self.arms

    @property
    def leg_length(self) -> float:
        return sum(self.skeleton.bone(name).length for name in self.legs[0].bones)
