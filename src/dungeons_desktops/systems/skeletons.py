"""The dead the lich raises: adventurers his spells killed, back on their feet as
skeletons that fight for him.

A `Skeleton` is a goblin swordsman in an adventurer's bones: the same pathing,
quarry-picking and overhead chop (see `goblins`), on the adventurers' own rig and
planner. Skeletons hunt as a `SkeletonPack` that never has a standard bearer, so
each runs down the adventurer nearest itself, keeping elbow room from the others.
One claws its way up out of the ground over `RISE_TIME` before it moves. It has
`SKELETON_HP`; its blows do `SKELETON_DAMAGE`, and whoever it kills stays dead.
They aren't the defender: they don't count toward the lich's health bar. When no
lich is left they crumble, `CRUMBLE_AFTER` later.
"""

from __future__ import annotations

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.creatures import stick_figure
from dungeons_desktops.navigation.planner import Anchor, Planner
from dungeons_desktops.rig.weapons import GoblinSword
from dungeons_desktops.systems.actors import Actor, Stickman, World
from dungeons_desktops.systems.goblins import (
    REPLAN_EVERY,
    SWORD_LEAD,
    SWORD_PUSH,
    SWORD_STRIKE_REACH,
    Goblin,
    GoblinPack,
    _hunt,
)
from dungeons_desktops.systems.mortal import SKELETON_HP

SKELETON_DAMAGE = 1
SKELETON_CAP = 8
RISE_TIME = 1.1
CRUMBLE_AFTER = 1.0
BLADE_REACH = 9.0
"""How far in front of its middle its blade lands."""
ELBOW_ROOM = 14.0
"""Room it leaves between itself and the next skeleton."""
STAND_OFF = 10.0
"""How far short of its quarry it stops, so it isn't standing inside him."""


class SkeletonPack(GoblinPack):
    @property
    def goblins(self) -> list[Goblin]:
        return self.world.skeletons

    @property
    def planner(self) -> Planner:
        return self.world.planner

    @property
    def flag(self) -> Goblin | None:
        return None


class Skeleton(Goblin):
    max_hp = SKELETON_HP
    linger = 2.0

    def __init__(self, world: World, anchor: Anchor, variant: str = "fighter") -> None:
        layout = stick_figure.build_stick_figure()
        self.weapon = GoblinSword(layout)
        Actor.__init__(self, world, layout, anchor, upper=self.weapon)
        self.kind = "sword"
        self.variant = variant
        """The class of the adventurer it was."""
        self.cooldown = world.random.uniform(0.3, 0.8) + RISE_TIME
        self.target: Stickman | None = None
        self.hunt = _hunt()
        self.held_at: Vec2 | None = None
        self._replan_wait = world.random.uniform(0.0, REPLAN_EVERY)
        self.ragdoll = None
        self.risen = 0.0
        """Seconds since it began clawing its way up (done at `RISE_TIME`)."""
        self.crumble: float | None = None
        """Seconds until it falls apart, once its master is gone."""
        self.kills = 0

    @property
    def planner(self) -> Planner:
        return self.world.planner

    @property
    def pack(self) -> GoblinPack:
        return self.world.skeleton_pack

    @property
    def rising(self) -> float:
        """0 -> 1 as it climbs out of the ground."""
        return min(1.0, self.risen / RISE_TIME)

    def update(self, dt: float) -> None:
        if self.risen < RISE_TIME:
            self.risen += dt
            self.locomotion.update(dt, self.follower.command())
            self._track_velocity(dt)
            return
        super().update(dt)

    def _head_out(self, dt: float) -> None:
        target = self.target
        if target is None:
            super()._head_out(dt)
            return
        goal = target.contact() + target.velocity * SWORD_LEAD
        away = self.contact().x - goal.x
        goal = goal + Vec2(STAND_OFF if away >= 0.0 else -STAND_OFF, 0.0)
        if self._go(goal):
            self.pack.reached(self)
        else:
            self.pack.unreachable(self, REPLAN_EVERY)

    def _elbow_room(self, other: Goblin) -> float:
        return ELBOW_ROOM

    def _blade_point(self, toward: Vec2) -> Vec2:
        side = 1.0 if toward.x >= self.contact().x else -1.0
        return self.center() + Vec2(side * BLADE_REACH, 0.0)

    def _resolve_attack(self) -> None:
        target = self.target
        if not self.weapon.take_strike():
            return
        if target is not None and self._in_reach(target, slack=SWORD_STRIKE_REACH):
            push = Vec2(self.facing * SWORD_PUSH, -SWORD_PUSH * 0.5)
            point = self._blade_point(target.center())
            if target.hurt_from(
                self,
                SKELETON_DAMAGE,
                point,
                push,
                "skeleton",
                "Hacked down by a skeleton!",
            ):
                self.kills += 1
