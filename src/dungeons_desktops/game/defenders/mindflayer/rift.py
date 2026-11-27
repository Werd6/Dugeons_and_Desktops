"""Thrall-forged rifts act as sentries: when prey (or a thrall) wanders within
`SENTRY_REACH`, a tentacle lashes out, seizes them as a ragdoll, and hauls them
through the tear. A rift collapses after `RIFT_MEALS` meals."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Vec2

if TYPE_CHECKING:
    from dungeons_desktops.game.adventurers.actor import Stickman
    from dungeons_desktops.game.defenders.mindflayer.actor import MindFlayer
    from dungeons_desktops.game.world.api import World

RIFT_OPEN_TIME = 0.55
"""Pause after the thrall detonation before the sentry arms."""
RIFT_MEALS = 5
"""How many bodies a rift must swallow before an aboleth emerges and it collapses."""
ABOLETH_DELIVER_HOLD = 1.05
"""How long the tear stays open after the fifth meal while the aboleth swims out."""
SENTRY_REACH = 200.0
"""How close an adventurer must stray before the tear lashes out."""
STRIKE_SPEED = 520.0
"""How fast a lashing tentacle tip closes on its mark."""
DRAG_SPEED = 110.0
"""How fast a seized ragdoll is hauled into the tear."""
EAT_REACH = 22.0
COOLDOWN = 0.35
"""Brief rest after a meal before the sentry can strike again."""


@dataclass
class RiftStrike:
    """One lash from the tear: tip flies out, then hauls a limp body back in."""

    tip: Vec2
    phase: float = 0.0
    victim: Stickman | None = None
    target: Stickman | None = None
    """Quarry the tip is still flying toward (before the grab lands)."""

    def body(self, root: Vec2, segments: int = 14) -> list[Vec2]:
        """Waving points from the tear to the tip for drawing."""
        line = self.tip - root
        length = line.length()
        if length < 1e-3:
            return [root, self.tip]
        along = line / length
        side = Vec2(-along.y, along.x)
        points = []
        for i in range(segments + 1):
            t = i / segments
            wave = math.sin(self.phase + t * 8.0) * (3.2 * t * (1.0 - 0.4 * t))
            curl = math.sin(self.phase * 1.6 + t * 4.5) * (1.6 * t * t)
            points.append(root + along * (length * t) + side * (wave + curl))
        return points


@dataclass
class Rift:
    """Sentry tear: lashes nearby prey, feeds, then delivers an aboleth and closes."""

    center: Vec2
    age: float = 0.0
    opened: bool = False
    eaten: int = 0
    strike: RiftStrike | None = None
    cooldown: float = 0.0
    delivered: bool = False
    close_after: float | None = None

    @property
    def full(self) -> bool:
        return self.eaten >= RIFT_MEALS

    @property
    def tentacles(self) -> list[RiftStrike]:
        """Active lashes (0 or 1) — kept for render/tests that iterate tentacles."""
        return [self.strike] if self.strike is not None else []

    @property
    def life(self) -> float:
        """0..1 fill for drawing: opens, then stays until fed."""
        if not self.opened:
            return min(1.0, self.age / max(RIFT_OPEN_TIME, 1e-3))
        fed = 1.0 - 0.15 * (self.eaten / RIFT_MEALS)
        if self.close_after is not None and self.age >= self.close_after - 0.35:
            closing = 1.0 - (self.close_after - self.age) / 0.35
            return max(0.0, fed * (1.0 - closing))
        return fed


def update_rift(rift: Rift, dt: float, world: World, flayer: MindFlayer) -> bool:
    """Advance one rift. Returns False once it should despawn (fed or abandoned)."""
    rift.age += dt
    if not rift.opened:
        if rift.age < RIFT_OPEN_TIME:
            return True
        rift.opened = True
        world.spells.sparkle(rift.center, "magic", 24, 200.0)
        world.spells.pulse(rift.center, 36.0)

    if not rift.full and not rift.delivered:
        rift.cooldown = max(0.0, rift.cooldown - dt)
        strike = rift.strike
        if strike is not None:
            strike.phase += dt * 4.0
            if strike.victim is not None:
                _drag(rift, strike, dt, world, flayer)
            else:
                _strike(rift, strike, dt, world)
        elif rift.cooldown <= 0.0:
            _try_lash(rift, world)

    if rift.full:
        _deliver_aboleth(rift, world, flayer)

    if rift.delivered:
        return rift.close_after is None or rift.age < rift.close_after
    return True


def _deliver_aboleth(rift: Rift, world: World, flayer: MindFlayer) -> None:
    if rift.delivered:
        return
    flayer.spawn_aboleth_from_rift(rift)
    rift.delivered = True
    rift.close_after = rift.age + ABOLETH_DELIVER_HOLD
    rift.strike = None
    rift.cooldown = 99.0
    world.spells.sparkle(rift.center, "magic", 36, 260.0)
    world.spells.pulse(rift.center, 48.0)

def _try_lash(rift: Rift, world: World) -> None:
    quarry = _nearest_meal(rift, world)
    if quarry is None:
        return
    rift.strike = RiftStrike(
        tip=rift.center + Vec2(0.0, -4.0),
        phase=world.random.uniform(0.0, math.tau),
        target=quarry,
    )
    world.spells.sparkle(rift.center, "magic", 6, 70.0)


def _strike(rift: Rift, strike: RiftStrike, dt: float, world: World) -> None:
    quarry = strike.target
    if quarry is None or not _meal_candidate(quarry):
        rift.strike = None
        rift.cooldown = COOLDOWN * 0.5
        return
    goal = quarry.center()
    span = strike.tip.distance_to(goal)
    step = STRIKE_SPEED * dt
    if span <= step or span <= 10.0:
        strike.tip = goal
        _seize(rift, strike, quarry, world)
        return
    strike.tip = strike.tip.lerp(goal, step / span)


def _seize(rift: Rift, strike: RiftStrike, victim: Stickman, world: World) -> None:
    """Claim a body: limp ragdoll, ignored by other defenders, hauled into the tear."""
    strike.victim = victim
    strike.target = None
    strike.tip = victim.center()
    victim.rift_held_by = rift
    if victim.weapon is not None:
        victim.weapon.cancel()
    victim.goal = None
    victim._resume_route = False
    victim._blow = None
    if victim.lure is not None:
        victim.free_from_lure()
    if victim.reeled is not None:
        victim.free_from_reel(drop=False)
    if victim.animated:
        victim.go_ragdoll()
    victim.knocked = True
    victim.stun = 1.0
    victim.down_time = 0.0
    world.spells.sparkle(victim.center(), "magic", 8, 90.0)


def _drag(
    rift: Rift, strike: RiftStrike, dt: float, world: World, flayer: MindFlayer
) -> None:
    victim = strike.victim
    assert victim is not None

    if victim.swallowed or victim.engulfed_by is not None or victim.gone:
        _drop(rift, victim)
        return
    if victim.rift_held_by is not rift:
        rift.strike = None
        return

    victim.rift_held_by = rift
    victim.knocked = True
    victim.stun = max(victim.stun, 0.8)
    victim.down_time = 0.0
    if victim.animated:
        victim.go_ragdoll()
        victim.knocked = True
        victim.stun = 1.0

    body = victim.center()
    strike.tip = body
    to_rift = rift.center - body
    distance = to_rift.length()
    if distance <= EAT_REACH:
        _eat(rift, strike, world, flayer)
        return

    step = min(distance, DRAG_SPEED * dt)
    desired = body + to_rift.normalized() * step
    offset = desired - body
    if offset.length() > 1e-6:
        victim.ragdoll.carry(offset, offset / max(dt, 1e-4))
    anchor = world.planner.anchor_near(desired)
    if anchor is not None:
        victim.follower.reset(anchor)
    strike.tip = victim.center()

    if strike.tip.distance_to(rift.center) <= EAT_REACH:
        _eat(rift, strike, world, flayer)


def _drop(rift: Rift, victim: Stickman | None) -> None:
    if victim is not None and victim.rift_held_by is not None:
        victim.rift_held_by = None
    rift.strike = None
    rift.cooldown = COOLDOWN


def _eat(rift: Rift, strike: RiftStrike, world: World, flayer: MindFlayer) -> None:
    """Yank them through: counted as a kill, then erased — no corpse, no blood."""
    victim = strike.victim
    assert victim is not None
    _ = flayer
    world.spells.sparkle(rift.center, "magic", 18, 160.0)
    world.spells.pulse(rift.center, 22.0)

    victim.rift_held_by = None
    head = victim.center()
    if victim.damage < victim.max_hp:
        victim.damage = victim.max_hp
    world.capture_adventurer_soul(victim, head)
    world.record_enemy_kill(victim, "elder thing herald", head)
    victim.say("Pulled into the rift!")
    # Mimic-style erase: gone immediately, nothing left on the desktop.
    victim.swallowed = True
    victim.knocked = False
    victim.stun = 0.0

    rift.eaten += 1
    rift.strike = None
    rift.cooldown = COOLDOWN


def _nearest_meal(rift: Rift, world: World) -> Stickman | None:
    meals = [
        s
        for s in world.stickmen
        if _meal_candidate(s) and s.center().distance_to(rift.center) <= SENTRY_REACH
    ]
    if not meals:
        return None
    return min(meals, key=lambda s: s.center().distance_to(rift.center))


def _meal_candidate(stickman: Stickman) -> bool:
    """Anyone the tear will feed on: free adventurers and thralls alike."""
    if stickman.rift_held_by is not None:
        return False
    if not stickman.animated:
        return False
    if stickman.engulfed_by is not None or stickman.reeled is not None:
        return False
    if stickman.swallowed:
        return False
    return stickman.prey or stickman.thrall
