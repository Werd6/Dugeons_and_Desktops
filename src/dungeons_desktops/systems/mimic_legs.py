"""The mimic's spider legs, out on walls and undersides: eight two-bone IK chains.

Each hip is fixed on its box; each foot plants on a surface in world space and stays
put while the body moves on. A planted foot that falls more than `STEP_THRESHOLD`
behind where it wants to be (its rest spot, a little ahead the way the body is moving,
projected onto the surface it's climbing) lifts and swings along an arc to there over
`STEP_TIME`, then plants again. The legs step in two alternating tetrapod groups: one
can't lift while the other group has a foot in the air (unless it's overstretched),
and no more than `MAX_STEPPING` are ever up at once. With no surface in reach (mid-air,
or folding away) a foot just follows the body, splayed, tucked or crumpled.

Everything is drawn flat, so each leg works in its surface frame: x along the surface
(`along`), y out from it. Knees always bend out away from the body, the same way for a
given leg, so they never flip.

The rig is the mimic's by default; other creatures pass their own `LegShape` (bone
lengths and step timing) and legs, and may hang each hip off its own frame (a point and
way up on a bending body) rather than the one box.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep
from dungeons_desktops.navigation.terrain import Surface

UPPER = 11.0
LOWER = 12.0
REACH = UPPER + LOWER
STEP_THRESHOLD = 6.0
"""A planted foot this far from where it wants to be steps."""
STRETCH = 0.94
"""A foot farther than this fraction of `REACH` from its hip steps whatever the gait..."""
SNAP = 1.3
"""...and one this far out lifts even if that's more than `MAX_STEPPING` up at once."""
STEP_TIME = 0.09
LONG_STEP = 18.0
"""A step longer than this (catching up, out of turn) takes proportionally longer."""
STEP_HEIGHT = 3.5
LEAD = 0.12
"""Seconds of the body's motion a step lands ahead by..."""
MAX_LEAD = 10.0
"""...up to this far."""
MAX_STEPPING = 4
FOLLOW_RATE = 12.0
"""How fast (per second) a foot with nothing to stand on eases to where it hangs,
carried along with the body..."""
FOLLOW_SPEED = 160.0
"""...and no faster than this (px/s) on top of that."""
HIP_RISE = 1.0
"""Hips sit this far up off the bottom of its box."""
ZERO = Vec2(0.0, 0.0)


def along(up: Vec2) -> Vec2:
    return Vec2(-up.y, up.x)


@dataclass(frozen=True)
class LegShape:
    """Bone lengths and stepping of a rig's legs (the mimic's by default)."""

    upper: float = UPPER
    lower: float = LOWER
    step_time: float = STEP_TIME
    step_height: float = STEP_HEIGHT
    threshold: float = STEP_THRESHOLD
    long_step: float = LONG_STEP
    max_stepping: int = MAX_STEPPING
    reach_out: bool = False
    """With its rest spot out of reach, plant as far toward it as it can reach (else
    the foot finds nothing to stand on)."""

    @property
    def reach(self) -> float:
        return self.upper + self.lower


MIMIC_SHAPE = LegShape()
REACH_OUT = 0.82
"""How far out (of its plain reach) a reaching-out foot plants, leaving it room to
carry the body on a way before it has to step again."""


def knee_for(
    hip: Vec2,
    foot: Vec2,
    up: Vec2,
    bend: int,
    scale: float = 1.0,
    shape: LegShape = MIMIC_SHAPE,
) -> Vec2:
    """Where the knee goes between `hip` and `foot` (bones `scale`d), bending to the
    `bend` side (+1 or -1 along the surface frame) out away from the body."""
    x_axis = along(up)
    rel = foot - hip
    local = Vec2(rel.dot(x_axis), rel.dot(up))
    a_len, b_len = shape.upper * scale, shape.lower * scale
    distance = local.length()
    if distance < 1e-6:
        local, distance = Vec2(0.0, -1.0), 1.0
    way = local * (1.0 / distance)
    reach = clamp(distance, abs(a_len - b_len) + 1e-3, a_len + b_len - 1e-3)
    a = (a_len * a_len - b_len * b_len + reach * reach) / (2.0 * reach)
    h = math.sqrt(max(0.0, a_len * a_len - a * a))
    perp = Vec2(-way.y, way.x)
    knee = way * a + perp * (h * bend)
    return hip + x_axis * knee.x + up * knee.y


@dataclass
class Leg:
    side: int
    """-1 or +1 along its surface frame."""
    outer: bool
    near: bool
    """In front of the box (drawn over it) rather than behind."""
    group: int
    """Its tetrapod group (0 or 1)."""
    foot: Vec2 = ZERO
    planted: bool = False
    step_from: Vec2 | None = None
    """Where a step lifted off (None: not stepping)..."""
    step_to: Vec2 = ZERO
    """...and where it'll plant."""
    step_time: float = 0.0
    step_length: float = STEP_TIME
    hip: Vec2 = ZERO
    knee: Vec2 = ZERO
    target: Vec2 | None = None
    """Where it wants to stand (None: nothing in reach)."""
    hip_at: float | None = None
    """Its hip along the body frame, and where its foot rests, overriding the mimic's
    spider layout..."""
    rest_at: float | None = None
    bend: int | None = None
    """...and which way its knee bends (default: out to its `side`)."""
    up: Vec2 = Vec2(0.0, -1.0)
    """The way up of the frame its hip hangs off, as of the last update."""

    @property
    def stepping(self) -> bool:
        return self.step_from is not None

    @property
    def hip_x(self) -> float:
        if self.hip_at is not None:
            return self.hip_at
        return self.side * (3.4 if self.outer else 1.1) + (0.0 if self.near else 0.8)

    @property
    def rest_x(self) -> float:
        if self.rest_at is not None:
            return self.rest_at
        return self.side * (14.0 if self.outer else 10.0) + (0.0 if self.near else 1.2)

    @property
    def knee_way(self) -> int:
        return self.side if self.bend is None else self.bend


def _legs() -> list[Leg]:
    legs = []
    for near in (False, True):
        for side in (-1, 1):
            for outer in (True, False):
                group = (side > 0) ^ outer ^ near
                legs.append(Leg(side, outer, near, int(group)))
    return legs


@dataclass
class LegRig:
    legs: list[Leg] = field(default_factory=_legs)
    shape: LegShape = MIMIC_SHAPE
    steps: int = 0
    """Steps taken, all told (`forced` of them overstretched)."""
    forced: int = 0
    _last: Vec2 | None = None
    _velocity: Vec2 = ZERO
    _clock: float = 0.0
    _turn: int = 0
    _idle: bool = True

    def place(self, position: Vec2, up: Vec2, lift: float) -> None:
        """Snap every leg to hang where it would with nothing to stand on."""
        for leg in self.legs:
            leg.up = up
            leg.hip = self._hip(leg, position, up, lift)
            leg.foot = self._hanging(leg, position, up, lift, 0.0, 0.0)
            leg.planted, leg.step_from, leg.target = False, None, None
            leg.knee = self._knee(leg, leg.foot)
        self._last = position

    def shift(self, delta: Vec2) -> None:
        """Carried along with the window it's on."""
        for leg in self.legs:
            leg.foot = leg.foot + delta
            leg.knee = leg.knee + delta
            if leg.step_from is not None:
                leg.step_from = leg.step_from + delta
                leg.step_to = leg.step_to + delta
        if self._last is not None:
            self._last = self._last + delta

    def update(
        self,
        dt: float,
        position: Vec2,
        up: Vec2,
        lift: float,
        surfaces: list[Surface],
        tuck: float = 0.0,
        crumple: float = 0.0,
        frames: list[tuple[Vec2, Vec2]] | None = None,
    ) -> None:
        """Step the legs for its bottom middle at `position` (its surface's way out
        `up`, held `lift` off it), its feet planting on `surfaces`. `frames` (one per
        leg) puts each hip right at its own point with its own way up instead."""
        if self._last is None:
            self.place(position, up, lift)
        carried = ZERO if self._last is None else position - self._last
        if dt > 0.0:
            self._velocity = self._velocity.lerp(carried * (1.0 / dt), min(1.0, dt * 20.0))
        self._last = position
        x_axis = along(up)
        lead = clamp(self._velocity.dot(x_axis) * LEAD, -MAX_LEAD, MAX_LEAD)
        for i, leg in enumerate(self.legs):
            if frames is None:
                leg.up = up
                leg.hip = self._hip(leg, position, up, lift)
            else:
                leg.hip, leg.up = frames[i]
            leg.target = self._target(leg, lead, surfaces)
        for leg in self.legs:
            if leg.target is None:
                leg.planted, leg.step_from = False, None
        self._gait(dt)
        for leg in self.legs:
            if not leg.planted and not leg.stepping:
                base = leg.hip - leg.up * (lift + HIP_RISE) - along(leg.up) * leg.hip_x
                hang = self._hanging(leg, base, leg.up, lift, tuck, crumple)
                foot = leg.foot + carried
                ease = (hang - foot) * min(1.0, FOLLOW_RATE * dt)
                limit = FOLLOW_SPEED * dt
                if ease.length() > limit:
                    ease = ease.normalized() * limit
                leg.foot = foot + ease
        for leg in self.legs:
            if leg.step_from is not None:
                self._swing(leg, leg.up, dt)
        for leg in self.legs:
            leg.knee = self._knee(leg, leg.foot)

    def points(
        self, position: Vec2, up: Vec2, lift: float, unfold: float
    ) -> list[tuple[bool, Vec2, Vec2, Vec2]]:
        """Each leg's (near, hip, knee, foot), drawn `unfold` (0..1) of the way out of
        where it folds away under the box."""
        unfold = smoothstep(clamp(unfold, 0.0, 1.0))
        if unfold <= 0.03:
            return []
        x_axis = along(up)
        result = []
        for leg in self.legs:
            fold = position + x_axis * (leg.hip_x * 0.9) + up * 0.5
            foot = fold.lerp(leg.foot, unfold)
            knee = knee_for(leg.hip, foot, up, leg.knee_way, max(unfold, 0.05), self.shape)
            result.append((leg.near, leg.hip, knee, foot))
        return result

    def _gait(self, dt: float) -> None:
        """Lift whichever legs step now. The two tetrapod groups take turns, a window of
        `STEP_TIME` each: when a window opens and any foot has fallen `STEP_THRESHOLD`
        behind, every foot of that window's group that's out of place lifts together.
        A foot that's overstretched or has nowhere planted yet lifts straight away. Never
        more than `MAX_STEPPING` are up at once."""
        shape = self.shape
        legs = [leg for leg in self.legs if leg.target is not None]
        up_count = sum(1 for leg in self.legs if leg.stepping)

        def lag(leg: Leg) -> float:
            assert leg.target is not None
            return leg.foot.distance_to(leg.target)

        def lift(leg: Leg) -> None:
            nonlocal up_count
            assert leg.target is not None
            self._lift(leg, leg.target)
            up_count += 1

        for leg in sorted(legs, key=lambda leg: -leg.foot.distance_to(leg.hip)):
            stretch = leg.foot.distance_to(leg.hip)
            if leg.stepping:
                continue
            if up_count >= shape.max_stepping and stretch <= shape.reach * SNAP:
                continue
            if not leg.planted:
                lift(leg)
            elif stretch > shape.reach * STRETCH:
                self.forced += 1
                lift(leg)
        self._clock += dt
        if self._clock < shape.step_time:
            return
        waiting = [leg for leg in legs if leg.planted and not leg.stepping]
        urgent = [leg for leg in waiting if lag(leg) > shape.threshold]
        if not urgent:
            self._clock = shape.step_time
            self._idle = True
            return
        if self._idle:
            self._turn = max(urgent, key=lag).group
        self._clock, self._idle = 0.0, False
        for leg in waiting:
            if leg.group == self._turn and lag(leg) > shape.threshold * 0.4:
                if up_count < shape.max_stepping:
                    lift(leg)
        self._turn = 1 - self._turn

    # ----- one leg -------------------------------------------------------------------

    def _hip(self, leg: Leg, position: Vec2, up: Vec2, lift: float) -> Vec2:
        return position + along(up) * leg.hip_x + up * (lift + HIP_RISE)

    def _knee(self, leg: Leg, foot: Vec2) -> Vec2:
        return knee_for(leg.hip, foot, leg.up, leg.knee_way, shape=self.shape)

    def _target(self, leg: Leg, lead: float, surfaces: list[Surface]) -> Vec2 | None:
        """Its rest spot (level with its hip, out to its side and `lead` ahead), on the
        nearest of `surfaces` in its reach on its own side of its hip."""
        if not surfaces:
            return None
        x_axis = along(leg.up)
        spot = leg.hip + x_axis * (leg.rest_x - leg.hip_x + lead)
        reach = self.shape.reach * 0.92
        best, best_distance = None, reach
        for surface in surfaces:
            point = surface.closest_point(spot)
            if (point - leg.hip).dot(x_axis) * leg.side < -2.0:
                continue
            distance = point.distance_to(leg.hip)
            if distance > reach and self.shape.reach_out:
                point = self._pulled_in(leg.hip, point, surface, reach * REACH_OUT)
                distance = reach if point is not None else math.inf
                if point is None or (point - leg.hip).dot(x_axis) * leg.side < -2.0:
                    continue
            if distance <= best_distance:
                best, best_distance = point, distance
        return best

    @staticmethod
    def _pulled_in(hip: Vec2, point: Vec2, surface: Surface, reach: float) -> Vec2 | None:
        """`point` on `surface` brought back toward `hip` until it's just in `reach`
        (None if no part of the surface is)."""
        foot = surface.closest_point(hip)
        drop = foot.distance_to(hip)
        if drop >= reach:
            return None
        run = point - foot
        if run.length() < 1e-6:
            return foot
        return surface.closest_point(foot + run.normalized() * math.sqrt(reach**2 - drop**2) * 0.98)

    def _hanging(
        self, leg: Leg, position: Vec2, up: Vec2, lift: float, tuck: float, crumple: float
    ) -> Vec2:
        """Where its foot hangs with nothing to stand on: splayed out under its side,
        drawn in mid-leap, sprawled when it's dead."""
        x = leg.rest_x + leg.side * 3.0 * crumple
        y = -0.4 * lift + 1.0 + (0.0 if leg.near else 0.6)
        x += (leg.hip_x * 1.15 + leg.side * 2.0 - x) * tuck * 0.7
        y += (-2.5 - y) * tuck * 0.7
        return position + along(up) * x + up * y

    def _lift(self, leg: Leg, target: Vec2) -> None:
        leg.step_from = leg.foot
        leg.step_to = target
        leg.step_time = 0.0
        shape = self.shape
        stride = leg.foot.distance_to(target) / shape.long_step
        leg.step_length = shape.step_time * clamp(stride, 1.0, 2.0)
        leg.planted = False
        self.steps += 1

    def _swing(self, leg: Leg, up: Vec2, dt: float) -> None:
        start, end = leg.step_from, leg.step_to
        assert start is not None
        leg.step_time += dt
        k = min(1.0, leg.step_time / leg.step_length)
        lift = self.shape.step_height * math.sin(math.pi * k)
        leg.foot = start.lerp(end, smoothstep(k)) + up * lift
        if k >= 1.0:
            leg.foot = end
            leg.step_from = None
            leg.planted = True
