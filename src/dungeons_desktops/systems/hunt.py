"""Picking a quarry: the stickman nearest some point, held onto unless a clearly
nearer one turns up, and given up on for a while when nobody can route to him.
Shared by the goblin pack, each goblin, the mind flayer, its thralls and the
intellect devourers."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Vec2

if TYPE_CHECKING:
    from dungeons_desktops.systems.actors import Stickman

RETARGET_EVERY = 1.5
SWITCH_IF_BETTER = 0.7
"""Switch quarry when another is nearer than this fraction of the current one."""
IGNORE_FOR = 6.0
NEAREST_RETARGET = 0.3
NEAREST_MARGIN = 30.0
"""For `nearest`: switch as soon as another is this much nearer, however far off."""


class Hunt:
    """One quarry: the stickman nearest some point, re-picked every `retarget_every`
    (switching only for a clearly nearer one), and dropped for `IGNORE_FOR` once
    nobody has been able to route to him for a while.

    Another stickman is clearly nearer when he's within `switch_if_better` of the
    quarry's distance, or more than `switch_margin` nearer (which, unlike the
    fraction, doesn't grow with the distance)."""

    def __init__(
        self,
        retarget_every: float = RETARGET_EVERY,
        switch_if_better: float = SWITCH_IF_BETTER,
        switch_margin: float = math.inf,
    ) -> None:
        self.target: Stickman | None = None
        self.retarget_every = retarget_every
        self.switch_if_better = switch_if_better
        self.switch_margin = switch_margin
        self._retarget = 0.0
        self._stuck = 0.0
        self._ignored: dict[Stickman, float] = {}

    def update(self, dt: float, origin: Vec2, stickmen: list[Stickman]) -> Stickman | None:
        self._ignored = {s: t - dt for s, t in self._ignored.items() if t > dt}
        prey = [s for s in stickmen if s.prey and s not in self._ignored]

        def distance(stickman: Stickman) -> float:
            return stickman.contact().distance_to(origin)

        target = self.target
        self._retarget -= dt
        if target is None or target not in prey:
            self.target = min(prey, key=distance, default=None)
            self._stuck = 0.0
            self._retarget = self.retarget_every
        elif self._retarget <= 0.0:
            self._retarget = self.retarget_every
            best = min(prey, key=distance)
            current = distance(target)
            if distance(best) < max(self.switch_if_better * current, current - self.switch_margin):
                self.target = best
                self._stuck = 0.0
        return self.target

    def unreachable(self, dt: float, patience: float) -> None:
        """No route to the quarry this time; after `patience` seconds of that, drop him."""
        self._stuck += dt
        if self._stuck >= patience and self.target is not None:
            self._ignored[self.target] = IGNORE_FOR
            self.target = None
            self._stuck = 0.0

    def reached(self) -> None:
        self._stuck = 0.0


def nearest() -> Hunt:
    """A hunt that keeps to whoever is nearest, re-checking often (without flip-flopping
    between two at about the same distance)."""
    return Hunt(NEAREST_RETARGET, switch_margin=NEAREST_MARGIN)
