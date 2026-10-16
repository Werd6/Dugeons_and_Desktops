"""The chimera's serpent tail: on its own, it strikes at whoever comes near, out to
`BEHIND_RANGE` from the hip behind the lion or only `FRONT_RANGE` from the shoulder
in front of it. A strike is a quick coil back, a dash of its head at him, and a
recoil to rest, then a short wait before it can strike again. Its bite is plain
damage, once a strike.

This only says where its head should be (`head_goal`); the chimera bends the chain
of its body there from its fixed root at the rump.
"""

from __future__ import annotations

import math
from enum import Enum
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Vec2, smoothstep

if TYPE_CHECKING:
    from dungeons_desktops.game.adventurers.actor import Stickman
    from dungeons_desktops.game.defenders.chimera.actor import Chimera

BEHIND_RANGE = 75.0
FRONT_RANGE = 40.0
COIL_TIME = 0.15
STRIKE_TIME = 0.12
RECOIL_TIME = 0.3
STRIKE_COOLDOWN = 1.0
COIL_PULL = 6.0
"""How far its head draws back from rest before it strikes."""
REACH = 0.95
"""The farthest its head goes, as a fraction of its length from its root."""
BITE_MARGIN = 3.0
BITE_DAMAGE = 4
BITE_PUSH = 150.0
BITE_DEATH = "Bitten by the chimera's serpent!"
FACING_DEADBAND = 0.15


class Strike(Enum):
    REST = "rest"
    COIL = "coil"
    STRIKE = "strike"
    RECOIL = "recoil"
    COOLDOWN = "cooldown"


class SnakeTail:
    def __init__(self) -> None:
        self.state = Strike.REST
        self.timer = 0.0
        self.target: Stickman | None = None
        self.start = Vec2(0.0, 0.0)
        """Where its head was when this phase began."""
        self.aim = Vec2(0.0, 0.0)
        """The point it strikes at."""
        self.struck = False
        self.facing = 1
        """Which way its head is drawn while it strikes (see `GoatHead.facing`)."""
        self.jaw = 0.0
        self.catches = 0

    @property
    def active(self) -> bool:
        return self.state in (Strike.COIL, Strike.STRIKE, Strike.RECOIL)

    def _progress(self, total: float) -> float:
        return smoothstep(1.0 - max(0.0, self.timer) / total)

    def update(self, dt: float, chimera: Chimera) -> None:
        """Its next phase. Called before the chimera poses its tail."""
        self.timer -= dt
        head = chimera.snake_head
        if self.state is Strike.REST:
            target = self._spot(chimera)
            if target is not None:
                self.state, self.timer, self.target = Strike.COIL, COIL_TIME, target
                self.start, self.struck = head, False
                self.aim = self._reach(chimera, target.center())
        elif self.state is Strike.COIL:
            if self.target is not None and self.target.prey:
                self.aim = self._reach(chimera, self.target.center())
            if self.timer <= 0.0:
                self.state, self.timer, self.start = Strike.STRIKE, STRIKE_TIME, head
        elif self.state is Strike.STRIKE and self.timer <= 0.0:
            self.state, self.timer, self.start = Strike.RECOIL, RECOIL_TIME, head
        elif self.state is Strike.RECOIL and self.timer <= 0.0:
            self.state, self.timer, self.target = Strike.COOLDOWN, STRIKE_COOLDOWN, None
        elif self.state is Strike.COOLDOWN and self.timer <= 0.0:
            self.state = Strike.REST
        if self.active:
            side = (self.aim - chimera.tail[0]).dot(chimera.forward * chimera.facing)
            if abs(side) > FACING_DEADBAND:
                self.facing = 1 if side > 0 else -1
        opening = 1.0 if self.state in (Strike.COIL, Strike.STRIKE) else 0.0
        self.jaw += (opening - self.jaw) * min(1.0, dt * 18.0)

    def head_goal(self, rest: Vec2) -> Vec2 | None:
        """Where its head should be this frame, or None to hang at `rest`."""
        if self.state is Strike.COIL:
            back = (rest - self.aim).normalized()
            return self.start.lerp(rest + back * COIL_PULL, self._progress(COIL_TIME))
        if self.state is Strike.STRIKE:
            return self.start.lerp(self.aim, self._progress(STRIKE_TIME))
        if self.state is Strike.RECOIL:
            return self.start.lerp(rest, self._progress(RECOIL_TIME))
        return None

    def bite(self, chimera: Chimera) -> None:
        """Called once its tail is posed: a strike reaching its quarry bites him."""
        quarry = self.target
        if self.state is not Strike.STRIKE or self.struck or quarry is None or not quarry.prey:
            return
        head = chimera.snake_head
        if not quarry.hits(head, BITE_MARGIN):
            return
        self.struck = True
        push = (quarry.center() - chimera.tail[-2]).normalized() * BITE_PUSH
        if quarry.hurt_from(chimera, BITE_DAMAGE, head, push, "chimera", BITE_DEATH):
            self.catches += 1

    def reset(self) -> None:
        self.state, self.target = Strike.REST, None

    def _reach(self, chimera: Chimera, point: Vec2) -> Vec2:
        root = chimera.tail[0]
        offset = point - root
        most = chimera.snake_length * REACH
        if offset.length() > most:
            return root + offset.normalized() * most
        return point

    def _spot(self, chimera: Chimera) -> Stickman | None:
        best, best_distance = None, math.inf
        forward = chimera.forward
        for stickman in chimera.world.stickmen:
            if not stickman.prey:
                continue
            middle = stickman.center()
            if (middle - chimera.body).dot(forward) < 0.0:
                distance = middle.distance_to(chimera.hip)
                inside = distance <= BEHIND_RANGE
            else:
                distance = middle.distance_to(chimera.shoulder)
                inside = distance <= FRONT_RANGE
            if inside and distance < best_distance:
                best, best_distance = stickman, distance
        return best
