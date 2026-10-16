"""Drow riding giant wall lizards, and drow fighting on foot.

A `Lizard` gets about like the displacer beast does (it is one, underneath: the same
terrain puts its feet on window tops, flat on their sides and upside down along their
undersides, its body rolling round every corner along a bending `Spine`), only it
never leaps or pounces: its planner (`LIZARD_MOVES`) climbs down walls rather than
drop, hopping only across gaps it can't climb round. It's low and sprawling on four IK legs
(`mimic_legs.LegRig` with a lizard's `LegShape`) whose feet plant on whatever it's
climbing. With nobody about it patrols, darting now and then to another window.
With an adventurer within `SKIRMISH_RANGE` it skirmishes: it picks a perch
`PERCH_RANGE` off from him (a wall or underside by preference) and holds it a few
seconds before moving on to another, scurrying off at a lope if anyone gets within
`SCURRY_RANGE`. Anyone right at its head gets bitten (`BITE_DAMAGE`).

Its drow rider picks his own mark, whatever the lizard is doing: the nearest
adventurer within `CROSSBOW_RANGE`, one already lit by faerie fire first. He shoots
him with his hand crossbow (`CROSSBOW_DAMAGE`) every `CROSSBOW_COOLDOWN`, and every
`GLOBE_COOLDOWN` throws an orb of darkness (`systems.darkness`) where the most of them
are bunched together. The mounted drow can't be hit: blows meant for him land on his
lizard.

When the lizard dies the drow leaps clear and fights on foot (`Drow`): a goblin
swordsman's brain, run on the adventurers' own rig and planner at `DROW_HASTE` times
the pace, slashing with two scimitars (`rig.weapons.TwinScimitars`, `SCIMITAR_DAMAGE`
a cut). The drow on foot hunt as a `DrowPack` with no standard bearer, so each runs
down whoever is nearest it.
"""

from __future__ import annotations

import math
import random
from dataclasses import replace
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Vec2, clamp
from dungeons_desktops.game.adventurers.actor import Actor, Stickman, World
from dungeons_desktops.game.defenders.displacer import actor as displacer
from dungeons_desktops.game.defenders.displacer.actor import Displacer, Intent, along
from dungeons_desktops.game.defenders.drakes.drake import Missile, lobbed, step_arrows
from dungeons_desktops.game.defenders.drow import model as drow_body
from dungeons_desktops.game.defenders.drow.weapons import TwinScimitars
from dungeons_desktops.game.defenders.goblins.actor import (
    REPLAN_EVERY,
    SWORD_LEAD,
    SWORD_START_REACH,
    SWORD_STRIKE_REACH,
    Goblin,
    GoblinPack,
    _hunt,
)
from dungeons_desktops.game.defenders.mimic.legs import Leg, LegRig, LegShape
from dungeons_desktops.navigation.planner import Anchor, Move, Planner
from dungeons_desktops.navigation.terrain import Surface, TerrainChange

if TYPE_CHECKING:
    from dungeons_desktops.game.world.simulation import SimWorld

# ----- the lizard's body (its frame: x toward the head, y toward its feet, from the
# displacer's body center, `BODY_HEIGHT` off the surface) ------------------------------

LIZARD_HP = 5
DROW_HP = 1

BODY_Y = 6.0
"""Its belly-to-back middle: it lies low, 7 px off its surface."""
BODY_HALF = 9.0
"""Body middle to the shoulders and to the hips."""
BODY_RADIUS = 4.5
HEAD = Vec2(17.5, 5.0)
HEAD_RADIUS = 3.6
MOUTH = Vec2(22.0, 6.0)
HIP_Y = 6.8
LEG_X = {True: 8.5, False: -8.0}
"""Shoulder (front) and hip (rear) along its body."""
LEG_REST = {True: 3.5, False: -1.5}
"""Where each foot rests, ahead of (or behind) its hip."""
FAR_LEG = Vec2(1.5, -1.0)
"""Its far-side legs' hips sit this much further along and up its body (as drawn)."""
LIZARD_LEGS = LegShape(
    upper=6.4,
    lower=7.0,
    step_time=0.08,
    step_height=2.4,
    threshold=12.0,
    long_step=20.0,
    max_stepping=2,
    reach_out=True,
)
FOOT_SEARCH = 32.0
"""Surfaces this near its body are ones its feet may plant on."""

LIZARD_GAITS = {
    "stalk": {Move.WALK: 20.0, Move.CLIMB: 20.0, Move.HANG: 19.0},
    "prowl": {Move.WALK: 35.0, Move.CLIMB: 33.0, Move.HANG: 31.0},
    "lope": {Move.WALK: 60.0, Move.CLIMB: 56.0, Move.HANG: 52.0},
}
"""Pixels a second along a top, up or down a side and along an underside: it takes
walls and ceilings in its stride."""
LIZARD_MOVES = replace(
    displacer.MOVES,
    walk_speed=35.0,
    climb_speed=33.0,
    hang_speed=31.0,
    hop_penalty=120.0,
    hop_height_penalty=0.4,
)
"""Its routes: it climbs down a wall rather than drop off a window, jumping or dropping
only across a gap it can't climb round."""

SKIRMISH_RANGE = 300.0
PERCH_RANGE = (130.0, 230.0)
PERCH_IDEAL = 170.0
PERCH_TIME = (2.5, 4.5)
"""How long it holds a perch before moving on to another."""
PERCH_SPACING = 60.0
"""It perches no nearer than this to where the other lizard is or is headed."""
PERCH_TRIES = 40
SCURRY_RANGE = 70.0
SCURRY_WAIT = 1.5

BITE_REACH = 4.0
BITE_TIME = 0.35
BITE_COOLDOWN = 1.2
BITE_DAMAGE = 1
BITE_PUSH = 110.0

# ----- the rider ------------------------------------------------------------------------

SEAT = Vec2(-1.5, 1.8)
"""His hips, on its back."""
RIDER_TORSO = 7.0
"""Shoulder height off the saddle: a stickman's torso length."""
RIDER_NECK = 5.0
"""Shoulder to the center of his head: a stickman's head bone."""
RIDER_HEAD = 4.5
"""His head radius, matching every other stickman."""
CROSSBOW_RANGE = 320.0
CROSSBOW_COOLDOWN = (2.0, 2.6)
CROSSBOW_DAMAGE = 2
BOLT_SPEED = 500.0
BOLT_GRAVITY = 120.0
GLOBE_RANGE = 260.0
GLOBE_COOLDOWN = 12.0
GLOBE_CLUSTER = 55.0
"""Adventurers this near one another count as bunched together for a globe."""
CAST_TIME = 0.45
"""How long his throwing arm is up as the orb leaves his hand."""
DISMOUNT_LEAP = Vec2(-40.0, -140.0)

# ----- on foot --------------------------------------------------------------------------

DROW_HASTE = drow_body.HASTE
"""His pace on the adventurers' planner: 1.6 times a goblin's."""
SCIMITAR_DAMAGE = 2
SCIMITAR_PUSH = 140.0
SCIMITAR_COOLDOWN = 0.45
BLADE_REACH = 10.0
"""How far in front of its middle its blades land."""
ELBOW_ROOM = 12.0
STAND_OFF = 9.0

ZERO = Vec2(0.0, 0.0)


def _lizard_legs() -> list[Leg]:
    """Front near and far, rear near and far; diagonal pairs step together."""
    legs = []
    for front in (True, False):
        for near in (True, False):
            group = int(front != near)
            legs.append(Leg(1, front, near, group, hip_at=0.0, rest_at=0.0))
    return legs


class Lizard(Displacer):
    max_hp = LIZARD_HP
    linger = 4.0
    gaits = LIZARD_GAITS

    def __init__(self, world: SimWorld, anchor: Anchor, heading: int = 1, slot: int = 0) -> None:
        self.slot = slot
        self.rig = LegRig(legs=_lizard_legs(), shape=LIZARD_LEGS)
        super().__init__(world, anchor, heading)
        rng = world.random
        self._fx = random.Random(slot * 7919 + 11)
        self.mounted = True
        """The drow is still in the saddle."""
        self.bolts: list[Missile] = []
        self.aim = Vec2(float(heading), -0.3).normalized()
        self.mark: Stickman | None = None
        """Who the rider has his crossbow on."""
        self.crossbow_cooldown = rng.uniform(0.6, 1.4)
        self.globe_cooldown = rng.uniform(2.5, 5.0)
        self.cast = 0.0
        self.perch_wait = 0.0
        self.scurry_wait = 0.0
        self.bite_left = 0.0
        self.bite_wait = 0.0
        self._bitten = False
        self.flick = 0.0
        """0 to 1 and back as its tongue flicks out."""
        self._flick_wait = rng.uniform(0.8, 2.5)
        self._step_legs(0.0)

    @property
    def planner(self) -> Planner:
        return self.world.lizard_planner

    def _try_leap(self, anchor: Anchor, kind: str) -> bool:
        """It never leaps or pounces: it scurries everywhere it goes."""
        return False

    # ----- its drawn body ------------------------------------------------------------

    def frame_at(self, x: float) -> tuple[Vec2, Vec2]:
        """A point on its center line `x` along its body (toward the head) and its way up
        there."""
        yaw = self.yaw_at(x)
        point, up = self.spine().frame(x * math.cos(yaw))
        return point + self.slide, up

    def center(self) -> Vec2:
        return self.to_world(Vec2(0.0, BODY_Y))

    @property
    def head(self) -> Vec2:
        return self.to_world(HEAD)

    @property
    def mouth(self) -> Vec2:
        lunge = math.sin(math.pi * clamp(1.0 - self.bite_left / BITE_TIME, 0.0, 1.0))
        reach = 4.0 * lunge if self.bite_left > 0.0 else 0.0
        return self.to_world(MOUTH + Vec2(reach, 0.0))

    def parts(self) -> list[Vec2]:
        parts = [
            self.to_world(Vec2(0.0, BODY_Y)),
            self.to_world(Vec2(BODY_HALF, BODY_Y)),
            self.to_world(Vec2(-BODY_HALF, BODY_Y)),
            self.head,
        ]
        if self.mounted:
            parts.append(self.rider_shoulder)
        return parts

    def hits(self, point: Vec2, margin: float = 0.0) -> bool:
        middle, shoulders, hips, head = self.parts()[:4]
        segments = [(hips, middle, BODY_RADIUS), (middle, shoulders, BODY_RADIUS)]
        if self.mounted:
            segments.append((self.seat, self.rider_shoulder, 2.5))
            if self.rider_head.distance_to(point) <= RIDER_HEAD + margin:
                return True
        for a, b, radius in segments:
            span = b - a
            t = clamp((point - a).dot(span) / max(span.length_sq(), 1e-9), 0.0, 1.0)
            if point.distance_to(a + span * t) <= radius + margin:
                return True
        return point.distance_to(head) <= HEAD_RADIUS + margin

    # ----- the rider (drawn and aimed from) ---------------------------------------------

    @property
    def rider_up(self) -> Vec2:
        return self.frame_at(SEAT.x)[1]

    @property
    def seat(self) -> Vec2:
        return self.to_world(SEAT)

    @property
    def rider_shoulder(self) -> Vec2:
        return self.seat + self.rider_up * RIDER_TORSO

    @property
    def rider_head(self) -> Vec2:
        return self.rider_shoulder + self.rider_up * RIDER_NECK

    @property
    def crossbow(self) -> Vec2:
        return self.rider_shoulder + self.aim * 7.0

    @property
    def crossbow_draw(self) -> float:
        """0 just loosed to 1 spanned and ready."""
        if self.dead or not self.mounted:
            return 0.0
        return clamp(1.0 - self.crossbow_cooldown / 1.2, 0.0, 1.0)

    @property
    def forward(self) -> Vec2:
        return along(self.frame_at(0.0)[1]) * float(self.heading)

    # ----- simulation -----------------------------------------------------------------

    def update(self, dt: float) -> None:
        self.bite_wait -= dt
        self.scurry_wait -= dt
        if self.bite_left > 0.0:
            self._biting(dt)
        super().update(dt)
        self._flicker(dt)
        if self.mounted:
            self._shoot(dt)
        self._step_legs(dt)
        self.bolts = self._fly_bolts(dt)

    def update_dead(self, dt: float) -> None:
        super().update_dead(dt)
        self._step_legs(dt)
        self.bolts = self._fly_bolts(dt)

    def _fly_bolts(self, dt: float) -> list[Missile]:
        death = "Shot by a drow crossbow!"
        return step_arrows(self.world, self.bolts, dt, BOLT_GRAVITY, CROSSBOW_DAMAGE, "drow", death)

    def _flicker(self, dt: float) -> None:
        self._flick_wait -= dt
        if self._flick_wait <= 0.0:
            self._flick_wait = self._fx.uniform(1.2, 3.5)
            self.flick = 0.001
        if self.flick > 0.0:
            self.flick += dt / 0.35
            if self.flick >= 1.0:
                self.flick = 0.0

    def _prey(self) -> list[Stickman]:
        return [s for s in self.world.stickmen if s.prey]

    # ----- the lizard's mind -----------------------------------------------------------

    def _think(self, dt: float) -> None:
        self.perch_wait -= dt
        if self.bite_left > 0.0:
            return
        prey = self._prey()
        if self.bite_wait <= 0.0:
            mouth = self.mouth
            if any(s.hits(mouth, BITE_REACH) for s in prey):
                self._start_bite()
                return
        body = self.center()
        near = min(prey, key=lambda s: s.center().distance_to(body), default=None)
        distance = near.center().distance_to(body) if near is not None else math.inf
        if near is not None and distance < SCURRY_RANGE and self.scurry_wait <= 0.0:
            self.scurry_wait = SCURRY_WAIT
            if self._perch(near, scurry=True):
                self.perch_wait = self.world.random.uniform(*PERCH_TIME)
                return
        if near is not None and distance <= SKIRMISH_RANGE:
            self._skirmish(near)
            self._check_stuck(dt)
            return
        if self.intent is Intent.STALK:
            self.intent = Intent.WANDER
            self._drop_goal()
        self._wander(dt)
        self._check_stuck(dt)

    def _skirmish(self, near: Stickman) -> None:
        self.intent = Intent.STALK
        here = near.center()
        goal = self.goal
        low, high = PERCH_RANGE
        placed = goal is not None and low - 30.0 <= goal.distance_to(here) <= high + 40.0
        if goal is None or self.perch_wait <= 0.0 or not placed:
            if self._perch(near):
                self.perch_wait = self.world.random.uniform(*PERCH_TIME)
            else:
                self.perch_wait = 0.5
            return
        follower = self.follower
        if follower is not None and follower.route is None:
            self._face(here)

    def _perch(self, target: Stickman, scurry: bool = False) -> bool:
        """Route to a perch `PERCH_RANGE` off from `target`, clear of the other lizards
        (scurrying: any spot farther from him than it is now, at a lope)."""
        rng = self.world.random
        here = target.center()
        others = [
            lizard.goal if lizard.goal is not None else lizard.body
            for lizard in self.world.lizards
            if lizard is not self
        ]
        low, high = PERCH_RANGE
        now = self.body.distance_to(here)
        spots: list[tuple[float, Anchor]] = []
        for _ in range(PERCH_TRIES):
            anchor = self._random_anchor()
            if anchor is None:
                break
            distance = anchor.point.distance_to(here)
            if not low <= distance <= high or (scurry and distance <= now):
                continue
            if any(anchor.point.distance_to(o) < PERCH_SPACING for o in others):
                continue
            score = abs(distance - PERCH_IDEAL) / 100.0 + rng.random() * 0.6
            if not anchor.surface.walkable:
                score -= 0.5
            score += anchor.point.distance_to(self.body) / 600.0
            spots.append((score, anchor))
        spots.sort(key=lambda spot: spot[0])
        for _, anchor in spots[:4]:
            if self._route_to(anchor.point, max_time=16.0):
                self.goal = anchor.point
                far = anchor.point.distance_to(self.body) > 160.0
                self.gait = "lope" if scurry or far else "prowl"
                return True
        return False

    def _start_bite(self) -> None:
        self.bite_left = BITE_TIME
        self.bite_wait = BITE_COOLDOWN
        self._bitten = False
        self._drop_goal()

    def _biting(self, dt: float) -> None:
        self.bite_left = max(0.0, self.bite_left - dt)
        if self._bitten or self.bite_left > BITE_TIME * 0.5:
            return
        self._bitten = True
        mouth = self.mouth
        for stickman in self._prey():
            if stickman.hits(mouth, BITE_REACH + 2.0):
                push = self.forward * BITE_PUSH + self.up * 60.0
                stickman.hurt_from(
                    self, BITE_DAMAGE, mouth, push, "lizard", "Bitten by a drow's lizard!"
                )
                return

    @property
    def biting(self) -> float:
        """0 to 1 and back over a bite: how far its jaws gape and its head lunges."""
        if self.bite_left <= 0.0:
            return 0.0
        return math.sin(math.pi * (1.0 - self.bite_left / BITE_TIME))

    # ----- the rider's crossbow and darkness ----------------------------------------------

    def _shoot(self, dt: float) -> None:
        self.crossbow_cooldown -= dt
        self.globe_cooldown -= dt
        self.cast = max(0.0, self.cast - dt)
        shoulder = self.rider_shoulder
        prey = [s for s in self._prey() if s.center().distance_to(shoulder) < CROSSBOW_RANGE]
        lit = [s for s in prey if s.faerie > 0.0]
        mark = min(lit or prey, key=lambda s: s.center().distance_to(shoulder), default=None)
        self.mark = mark
        if mark is None:
            rest = (self.forward + self.rider_up * 0.4).normalized()
            self.aim = self.aim.lerp(rest, min(1.0, dt * 5.0)).normalized()
            return
        if self.globe_cooldown <= 0.0 and self._throw_globe(mark):
            return
        velocity = lobbed(self.crossbow, mark.center(), BOLT_SPEED, BOLT_GRAVITY)
        want = velocity.normalized()
        self.aim = self.aim.lerp(want, min(1.0, dt * 14.0)).normalized()
        if self.crossbow_cooldown <= 0.0 and self.cast <= 0.0 and self.aim.dot(want) > 0.97:
            self.bolts.append(Missile(self.crossbow + want * 2.0, velocity))
            self.crossbow_cooldown = self._fx.uniform(*CROSSBOW_COOLDOWN)

    def _throw_globe(self, mark: Stickman) -> bool:
        """An orb of darkness at the middle of the biggest bunch of adventurers in range
        (nearest his mark when it's a tie)."""
        hand = self.rider_shoulder
        prey = [s for s in self._prey() if s.center().distance_to(hand) <= GLOBE_RANGE]
        if not prey:
            return False

        def bunch(s: Stickman) -> tuple[int, float]:
            center = s.center()
            count = sum(1 for o in prey if o.center().distance_to(center) <= GLOBE_CLUSTER)
            return (-count, center.distance_to(mark.center()))

        heart = min(prey, key=bunch)
        group = [s for s in prey if s.center().distance_to(heart.center()) <= GLOBE_CLUSTER]
        spot = ZERO
        for s in group:
            spot += s.center()
        spot = spot * (1.0 / len(group))
        self.world.darkness.throw(hand + self.rider_up * 3.0, spot)
        self.globe_cooldown = GLOBE_COOLDOWN
        self.cast = CAST_TIME
        self.aim = (spot - hand).normalized()
        return True

    # ----- legs --------------------------------------------------------------------------

    def _step_legs(self, dt: float) -> None:
        surfaces: list[Surface] = []
        if self.follower is not None and not self.airborne:
            body = self.body
            surfaces = [
                s
                for s in self.planner.surfaces
                if s.closest_point(body).distance_to(body) <= FOOT_SEARCH
            ]
        frames = []
        for leg in self.rig.legs:
            front = leg.outer
            x = LEG_X[front] + (0.0 if leg.near else FAR_LEG.x)
            hip = self.to_world(Vec2(x, HIP_Y + (0.0 if leg.near else FAR_LEG.y)))
            _, up = self.frame_at(x)
            leg.side = self.heading
            leg.bend = -self.heading if front else self.heading
            leg.rest_at = self.heading * (LEG_REST[front] + (0.0 if leg.near else FAR_LEG.x))
            frames.append((hip, up))
        tuck = 1.0 if self.airborne and not self.dead else 0.0
        crumple = 1.0 if self.dead else 0.0
        self.rig.update(dt, self.body, self.up, HIP_Y, surfaces, tuck, crumple, frames=frames)

    # ----- terrain and death -------------------------------------------------------------

    def terrain_changed(self, change: TerrainChange) -> None:
        support = self.support
        delta = change.delta_for(support.box) if support is not None else None
        super().terrain_changed(change)
        if delta is not None:
            self.rig.shift(delta)

    def die(self, point: Vec2, push: Vec2) -> None:
        seat, forward = self.seat, self.forward
        super().die(point, push)
        self.bite_left = 0.0
        if self.mounted:
            self.mounted = False
            leap = forward * DISMOUNT_LEAP.x + Vec2(0.0, DISMOUNT_LEAP.y)
            self.world.add_drow(seat, facing=1 if forward.x >= 0.0 else -1, leap=leap)


class DrowPack(GoblinPack):
    @property
    def goblins(self) -> list[Goblin]:
        return self.world.drow

    @property
    def planner(self) -> Planner:
        return self.world.planner

    @property
    def flag(self) -> Goblin | None:
        return None


class Drow(Goblin):
    """A drow on foot: quick, light, and cutting with two scimitars."""

    max_hp = DROW_HP
    linger = 3.0

    def __init__(self, world: World, anchor: Anchor, facing: int = 1) -> None:
        layout = drow_body.build_drow()
        self.weapon = TwinScimitars(layout)
        Actor.__init__(self, world, layout, anchor, upper=self.weapon)
        self.follower.facing = facing
        self.kind = "sword"
        self.cooldown = world.random.uniform(0.2, 0.5)
        self.target: Stickman | None = None
        self.hunt = _hunt()
        self.held_at: Vec2 | None = None
        self._replan_wait = 0.0
        self.ragdoll = None
        self.kills = 0
        self.time = 0.0

    @property
    def planner(self) -> Planner:
        return self.world.planner

    @property
    def pack(self) -> GoblinPack:
        return self.world.drow_pack

    def update(self, dt: float) -> None:
        super().update(dt)
        self.time += dt

    def update_dead(self, dt: float) -> None:
        super().update_dead(dt)
        self.time += dt

    def _regroup_pace(self) -> float:
        return DROW_HASTE

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

    def _try_attack(self, target: Stickman) -> None:
        if self._in_reach(target, slack=SWORD_START_REACH):
            self._face(target.center())
            self.weapon.start()
            self.cooldown = SCIMITAR_COOLDOWN

    def _resolve_attack(self) -> None:
        target = self.target
        while self.weapon.take_strike():
            if target is None or not self._in_reach(target, slack=SWORD_STRIKE_REACH):
                continue
            push = Vec2(self.facing * SCIMITAR_PUSH, -SCIMITAR_PUSH * 0.4)
            point = self._blade_point(target.center())
            if target.hurt_from(
                self, SCIMITAR_DAMAGE, point, push, "drow", "Cut to ribbons by a drow!"
            ):
                self.kills += 1
                return
