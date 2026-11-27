"""A slow undead pack using the shared biped hunting and ragdoll lifecycle."""

import math

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.actors.base import Actor
from dungeons_desktops.game.actors.spacing import reserve_opening, separate_pack
from dungeons_desktops.game.adventurers.actor import Stickman
from dungeons_desktops.game.defenders.goblins.actor import REPLAN_EVERY, Goblin, GoblinPack, _hunt
from dungeons_desktops.game.defenders.zombies.model import build_zombie
from dungeons_desktops.game.defenders.zombies.posture import ZombieClaws
from dungeons_desktops.game.defenders.zombies.spacing import (
    SEPARATION_SPEED,
    personal_space,
)
from dungeons_desktops.game.world.api import World
from dungeons_desktops.navigation.planner import Anchor, Planner
from dungeons_desktops.rig.locomotion import PoseMode

ZOMBIE_HP = 6
ZOMBIE_DAMAGE = 1
ZOMBIE_PACK = 10
ATTACK_COOLDOWN = 0.75
PLAGUE_SIZE = 1.2
"""Legendary Plague Horde figure scale."""
FRENZY_DURATION = 3.0
"""Seconds of pack frenzy after a Plague Horde zombie dies or scores a kill."""
FRENZY_SPEED = 2.35
"""Movement multiplier while frenzying (walk, climb, hang)."""
FRENZY_ATTACK = 2.35
"""Attack-cooldown multiplier while frenzying."""
FRENZY_DAMAGE = 2
"""Claw damage while frenzying (base `ZOMBIE_DAMAGE` otherwise)."""


class ZombiePack(GoblinPack):
    def separate(self, dt: float, movable: set["Zombie"]) -> None:
        """Gently unstack supported zombies, including newly spawned pack members."""
        separate_pack(
            self.goblins,
            self.planner,
            dt,
            movable,
            personal_space,
            SEPARATION_SPEED,
        )

    @property
    def goblins(self) -> list["Zombie"]:
        return self.world.zombies

    @property
    def planner(self) -> Planner:
        return self.world.zombie_planner

    @property
    def flag(self) -> None:
        return None


class Zombie(Goblin):
    max_hp = ZOMBIE_HP

    def __init__(self, world: World, anchor: Anchor, *, legendary: bool = False) -> None:
        layout = build_zombie(size=PLAGUE_SIZE if legendary else 1.0)
        self.weapon = ZombieClaws(layout)
        Actor.__init__(self, world, layout, anchor, upper=self.weapon)
        self.kind = "sword"  # Shared pack routing: close to melee range, no ranged weapon.
        self.crowned = False
        self.warband_horn_cooldown = 0.0
        self.warband_boost = 0.0
        self.legendary = legendary
        self.size = PLAGUE_SIZE if legendary else 1.0
        self.cooldown = world.random.uniform(0.3, 1.0)
        self.target: Stickman | None = None
        self.hunt = _hunt()
        self.held_at: Vec2 | None = None
        self._replan_wait = world.random.uniform(0.0, REPLAN_EVERY)
        self.ragdoll = None
        self._shamble_phase = world.random.uniform(0.0, math.tau)
        self.frenzy = 0.0

    @property
    def planner(self) -> Planner:
        return self.world.zombie_planner

    @property
    def pack(self) -> ZombiePack:
        return self.world.zombie_pack

    def _make_room(self, anchor: Anchor) -> Anchor:
        """Reserve a nearby opening across the whole surface, even for a large horde."""
        return reserve_opening(self, anchor, personal_space(anchor.surface))

    def update(self, dt: float) -> None:
        if self.frenzy > 0.0:
            self.frenzy = max(0.0, self.frenzy - dt)
        super().update(dt)

    def _boost_speed(self) -> float:
        if self.frenzy > 0.0:
            return FRENZY_SPEED
        return super()._boost_speed()

    def _boost_attack(self) -> float:
        if self.frenzy > 0.0:
            return FRENZY_ATTACK
        return super()._boost_attack()

    def _start_pack_frenzy(self) -> None:
        """Plague Horde: whip the living pack into a short frenzy."""
        if not getattr(self, "legendary", False):
            return
        for other in self.world.zombies:
            if not other.dead:
                other.frenzy = max(other.frenzy, FRENZY_DURATION)

    def _regroup_pace(self) -> float:
        if self.locomotion.mode is not PoseMode.WALK:
            return 1.0
        # Lurch, then drag the trailing foot; never exceed the slow planner speed.
        phase = math.tau * self.locomotion.walk.cycle + self._shamble_phase
        pace = 0.8 + 0.2 * math.sin(phase)
        if getattr(self, "legendary", False):
            wounded = 1.0 - max(0.0, self.hp) / self.max_hp
            pace *= 1.0 + 0.8 * wounded
        return pace

    def die(self, point: Vec2, push: Vec2) -> None:
        self._start_pack_frenzy()
        super().die(point, push)

    def _blade_point(self, toward: Vec2) -> Vec2:
        reach = 9.0 * self.size
        if self.locomotion.mode in self.weapon.cling_modes:
            return self.center() + (toward - self.center()).normalized() * reach
        side = 1.0 if toward.x >= self.contact().x else -1.0
        return self.center() + Vec2(side * reach, -3.0 * self.size)

    def _head_out(self, dt: float) -> None:
        if self.weapon.busy and self.locomotion.mode in self.weapon.cling_modes:
            return
        super()._head_out(dt)

    def _try_attack(self, target: Stickman) -> None:
        if self._in_reach(target):
            if self.locomotion.mode in self.weapon.cling_modes:
                self.halt()
                shoulder = self.transforms()[self.layout.torso].end
                toward = target.center() - shoulder
                self.weapon.claw_direction = Vec2(self.facing * toward.x, toward.y).normalized()
            else:
                self._face(target.center())
            self.weapon.start()
            self.cooldown = ATTACK_COOLDOWN

    def _resolve_attack(self) -> None:
        if not self.weapon.take_strike():
            return
        target = self.target
        if target is not None and self._in_reach(target):
            spawn_at = target.contact()
            inherited_hp = self.hp
            damage = FRENZY_DAMAGE if self.frenzy > 0.0 else ZOMBIE_DAMAGE
            killed = target.hurt_from(
                self,
                damage,
                self._blade_point(target.center()),
                Vec2(self.facing * 80.0, -35.0),
                "zombie",
                "Clawed down by a zombie!",
            )
            if killed:
                newborn = self.world.add_zombie(
                    spawn_at, legendary=getattr(self, "legendary", False)
                )
                newborn.damage = newborn.max_hp - inherited_hp
                self._start_pack_frenzy()
