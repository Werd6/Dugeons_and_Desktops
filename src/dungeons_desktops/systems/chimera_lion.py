"""The chimera's lion half, which does all its moving: the displacer beast's way of
getting about, a little slower, and never upside down.

It has its own terrain and planner (`world.chimera_planner`): window tops, the floor,
and flat against window sides and the screen edges, rolling its body round each
corner, but no undersides. Planned jumps and drops become ballistic leaps, and on top
of the planner it leaps straight across gaps to another window within `LEAP_RANGE`.

Every leap goes crouch (`CROUCH_TIME`), flight (an exact ballistic arc to the surface
it aims for, checked clear of every window before it goes), landing absorb
(`LAND_TIME`). If a window moves under it mid-flight it lands where that surface went;
if its target closes it falls and clings to the first window it hits.

With nobody near it wanders, prowling, loping on long routes, now and then leaping to
another window. An adventurer within `NOTICE_RANGE` gets stalked (low and slow once
he's within `STALK_CLOSE`) and pounced on from within `POUNCE_RANGE` (every
`POUNCE_COOLDOWN`): it lands right on him, mauling him for `POUNCE_DAMAGE` if he's
still there. Up close it stands its ground and faces him, and leaves the biting and
burning to its other two heads.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Rect, Vec2, clamp, smoothstep, wrap_angle
from dungeons_desktops.navigation.planner import (
    ALONG_MOVES,
    Anchor,
    Move,
    MoveSettings,
    Planner,
    Route,
    RouteStep,
)
from dungeons_desktops.navigation.terrain import Surface, TerrainChange
from dungeons_desktops.systems.hunt import nearest
from dungeons_desktops.systems.movement import RouteFollower

if TYPE_CHECKING:
    from dungeons_desktops.systems.actors import Stickman
    from dungeons_desktops.systems.chimera import Chimera
    from dungeons_desktops.systems.world import SimWorld

GRAVITY = 1100.0
HIP_HEIGHT = 18.0
"""Body center out from its feet."""

MOVES = MoveSettings(
    walk_speed=44.0,
    climb_speed=34.0,
    hang_speed=30.0,
    mantle_time=0.5,
    grab_time=0.45,
    swing_time=0.5,
    max_drop=320.0,
    max_hang_drop=1000.0,
    max_jump=90.0,
    gravity=GRAVITY,
    edge_clearance=4.0,
)
"""Its routes, timed at the prowl. Walls run the whole height of a window, and the
corner over a window top is `MANTLE_DEPTH` deep."""
MANTLE_DEPTH = 6.0
CLEARANCE = 15.0
"""Surfaces with another window closer than this (its body's room) are left out."""

GAITS = {
    "stalk": {Move.WALK: 22.0, Move.CLIMB: 20.0},
    "prowl": {Move.WALK: 44.0, Move.CLIMB: 34.0},
    "lope": {Move.WALK: 105.0, Move.CLIMB: 66.0},
}
"""Pixels a second along a top or floor, and up or down a side."""
ACCELERATION = 3.0
LOPE_DISTANCE = 240.0
"""Routes longer than this it lopes (unless it's stalking)."""

LEAP_RANGE = 260.0
LEAP_MIN = 70.0
LEAP_CHANCE = 0.25
"""Chance, picking where to wander next, that it leaps to another window instead."""
LEAP_COOLDOWN = 3.0
MAX_LEAP_SPEED = 800.0
LEAP_PACE = 560.0
"""Flight time grows with the distance at about this many px/s."""
BODY_CLEARANCE = 4.0
CROUCH_TIME = {"hop": 0.16, "leap": 0.35, "pounce": 0.45}
LAND_TIME = {"hop": 0.16, "leap": 0.3, "pounce": 0.4, "fall": 0.35}
CLING_REACH = 26.0
"""Falling, it clings to a window side or top within this of where it hits it."""
ESCAPE_REACH = 120.0

NOTICE_RANGE = 380.0
STALK_CLOSE = 260.0
POUNCE_RANGE = 220.0
POUNCE_MIN = 40.0
POUNCE_COOLDOWN = 6.0
POUNCE_DAMAGE = 3
POUNCE_HIT = 22.0
"""A pounce mauls its quarry if his middle comes this close to its body or jaws."""
POUNCE_PUSH = 240.0
HOLD_CLOSE = 30.0
"""Its feet this near his, it stops and faces him."""

TURN_COOLDOWN = 0.7
FACE_MARGIN = 20.0
TURN_MIN = 10.0
REPLAN_EVERY = 0.5
GOAL_SNAP = 80.0
ARRIVED = 3.0
REST_TIME = (0.8, 2.5)
STUCK_TIME = 3.0
ADVANCE_BUDGET = 0.6

ZERO = Vec2(0.0, 0.0)
UPRIGHT = Vec2(0.0, -1.0)
HOPS = (Move.JUMP, Move.DROP)


class Intent(Enum):
    WANDER = "wander"
    STALK = "stalk"


@dataclass
class Leap:
    """A ballistic flight of its body center from `start` to the `target` surface."""

    target: Anchor
    kind: str
    """"hop" (a planned jump or drop), "leap" or "pounce"."""
    quarry: Stickman | None = None
    """Who a pounce mauls if it reaches him."""
    start: Vec2 = ZERO
    velocity: Vec2 = ZERO
    time: float = 0.0
    elapsed: float = 0.0
    struck: bool = False


def along(up: Vec2) -> Vec2:
    """The +1 heading along a surface whose outward side is `up` (+x on a top)."""
    return Vec2(-up.y, up.x)


def _ease(value: float, target: float, rate: float, dt: float) -> float:
    return value + (target - value) * (1.0 - math.exp(-rate * dt))


def _grown(box: Rect, margin: float) -> Rect:
    return Rect(box.x - margin, box.y - margin, box.width + 2 * margin, box.height + 2 * margin)


def _planned_speed(move: Move) -> float:
    return MOVES.walk_speed if move is Move.WALK else MOVES.climb_speed


def _body_rate(step: RouteStep) -> float:
    """Roughly how fast its body goes (px/s) along `step` of a route at the prowl."""
    if step.move in ALONG_MOVES:
        return _planned_speed(step.move)
    turn = abs(wrap_angle(step.surface.normal.angle() - step.from_surface.normal.angle()))
    span = step.start.distance_to(step.end) + HIP_HEIGHT * turn
    return max(5.0, span / max(step.duration, 1e-3))


class LionController:
    """Where the chimera's feet are and which way up and along it faces, on a surface
    (`follower`) or in the air (`leap`, or a fall)."""

    def __init__(self, chimera: Chimera, world: SimWorld, anchor: Anchor, heading: int) -> None:
        self.chimera = chimera
        self.world = world
        self.follower: RouteFollower | None = None
        self.position = anchor.point
        """Its feet, on a surface."""
        self.up = UPRIGHT
        """Away from the surface its feet are on."""
        self.body = anchor.point
        """Its body center: the feet plus `up` * `HIP_HEIGHT` on a surface."""
        self.velocity = ZERO
        self.heading = heading
        """+1 or -1: which way along its surface it faces (see `along`)."""
        self.intent = Intent.WANDER
        self.hunt = nearest()
        self.target: Stickman | None = None
        self.goal: Vec2 | None = None
        self.gait = "prowl"
        self.pace = 1.0
        """Its speed as a multiple of the planner's (prowl) speeds."""
        self.pending: Leap | None = None
        """The leap it's crouching for."""
        self.crouch_left = 0.0
        self.leap: Leap | None = None
        """The leap it's in the air on (None in a fall)."""
        self.land_left = 0.0
        self.land_time = 1.0
        self.leap_wait = 1.0
        self.rest = 0.5
        self.turn_wait = 0.0
        self.moved = 0.0
        """How far its feet went this step (for the stride)."""
        self.speed = 0.0
        self.crouch = 0.0
        """0 standing to 1 crouched for a leap."""
        self._replan_wait = 0.0
        self._still = 0.0
        self._attach(anchor)

    @property
    def planner(self) -> Planner:
        return self.world.chimera_planner

    @property
    def airborne(self) -> bool:
        return self.follower is None

    @property
    def support(self) -> Surface | None:
        return self.follower.current_anchor().surface if self.follower is not None else None

    @property
    def landing(self) -> float:
        """1 just after touching down, easing to 0 over the landing absorb."""
        return clamp(self.land_left / self.land_time, 0.0, 1.0) if self.land_time > 0 else 0.0

    @property
    def pouncing(self) -> bool:
        leap = self.pending or self.leap
        return leap is not None and leap.kind == "pounce"

    @property
    def frame_up(self) -> Vec2:
        """Its body's way up: its surface's, or in the air its flight's (pitch-limited)."""
        if self.follower is not None:
            return self.up
        velocity = self.velocity
        if velocity.length() < 30.0:
            return UPRIGHT
        way = velocity.normalized()
        h = float(self.heading)
        up = Vec2(h * way.y, -h * way.x)
        pitch = clamp(wrap_angle(up.angle() + math.pi / 2), -0.5, 0.5)
        return Vec2.from_angle(-math.pi / 2 + pitch)

    # ----- simulation ----------------------------------------------------------

    def update(self, dt: float) -> None:
        self.moved = 0.0
        self.leap_wait -= dt
        self.turn_wait -= dt
        self.target = self.hunt.update(dt, self.body, self.world.stickmen)
        if self.pending is not None:
            self._crouching(dt)
        elif self.follower is None:
            self._fly(dt)
        else:
            if self.land_left > 0.0:
                self.land_left -= dt
            elif not self.follower.in_transition:
                self._think(dt)
            if self.follower is not None and self.pending is None:
                self._crawl(dt)
        self._animate(dt)

    def _think(self, dt: float) -> None:
        target = self.target
        distance = target.center().distance_to(self.body) if target is not None else math.inf
        if target is not None and distance <= NOTICE_RANGE:
            self._stalk(dt, target, distance)
        else:
            if self.intent is Intent.STALK:
                self.intent = Intent.WANDER
                self._drop_goal()
            self._wander(dt)
        self._check_stuck(dt)

    def _stalk(self, dt: float, target: Stickman, distance: float) -> None:
        self.intent = Intent.STALK
        self.gait = "stalk" if distance <= STALK_CLOSE else "prowl"
        ready = self.leap_wait <= 0.0
        if ready and POUNCE_MIN <= distance <= POUNCE_RANGE and self._pounce(target):
            return
        if target.contact().distance_to(self.position) <= HOLD_CLOSE:
            if self.follower is not None and self.follower.route is not None:
                self._drop_goal()
            self._face(target.center())
            return
        self._replan_wait -= dt
        if self._replan_wait > 0.0:
            return
        self._replan_wait = REPLAN_EVERY
        self.goal = target.contact()
        if self._route_to(self.goal):
            self.hunt.reached()
            return
        self.goal = None
        self.hunt.unreachable(REPLAN_EVERY, 2.0)
        if ready and not (distance <= LEAP_RANGE and self._pounce(target)):
            self._leap_closer(target)

    def _wander(self, dt: float) -> None:
        follower = self.follower
        assert follower is not None
        if self.goal is not None:
            if follower.route is None:
                if follower.current_anchor().point.distance_to(self._goal_point()) <= ARRIVED:
                    self._arrive()
                    return
                self._replan_wait -= dt
                if self._replan_wait <= 0.0:
                    self._replan_wait = REPLAN_EVERY
                    if not self._route_to(self.goal):
                        self._arrive()
            return
        if self.rest > 0.0:
            self.rest -= dt
            return
        self._pick_goal()

    def _arrive(self) -> None:
        self.goal = None
        self.rest = self.world.random.uniform(*REST_TIME)

    def _goal_point(self) -> Vec2:
        assert self.goal is not None
        anchor = self.planner.anchor_near(self.goal, GOAL_SNAP)
        return anchor.point if anchor is not None else self.goal

    def _pick_goal(self) -> None:
        random = self.world.random
        if self.leap_wait <= 0.0 and random.random() < LEAP_CHANCE and self._leap_somewhere():
            return
        for _ in range(10):
            anchor = self._random_anchor()
            if anchor is None:
                return
            if anchor.point.distance_to(self.position) < 40.0:
                continue
            if self._route_to(anchor.point, max_time=30.0):
                self.goal = anchor.point
                self.gait = "prowl"
                return
        self.rest = 0.5

    def _leap_somewhere(self) -> bool:
        """A leap to a spot on another window (top or side) or the floor within range."""
        here = self.support
        for _ in range(24):
            anchor = self._random_anchor()
            if anchor is None or here is None:
                return False
            if anchor.surface.box == here.box and anchor.surface.box is not None:
                continue
            if not LEAP_MIN <= anchor.point.distance_to(self.position) <= LEAP_RANGE:
                continue
            if self._arc(self.body, anchor) is not None:
                self._crouch(Leap(anchor, "leap"))
                return True
        return False

    def _leap_closer(self, target: Stickman) -> bool:
        """With no way to walk or climb to `target`, a leap to anywhere (a window's top
        or side) well nearer him."""
        aim = target.contact()
        near = aim.distance_to(self.position) - LEAP_MIN
        for _ in range(24):
            anchor = self._random_anchor()
            if anchor is None:
                return False
            if anchor.point.distance_to(aim) > near:
                continue
            if not LEAP_MIN <= anchor.point.distance_to(self.position) <= LEAP_RANGE:
                continue
            if self._arc(self.body, anchor) is not None:
                self._crouch(Leap(anchor, "leap"))
                return True
        return False

    def _random_anchor(self) -> Anchor | None:
        surfaces = [s for s in self.planner.surfaces if s.length >= 8.0]
        if not surfaces:
            return None
        random = self.world.random
        weights = [math.sqrt(s.length) * (1.0 if s.walkable else 0.6) for s in surfaces]
        surface = random.choices(surfaces, weights=weights)[0]
        inset = min(10.0, surface.length * 0.5)
        return Anchor(
            surface, surface.point_at(random.uniform(surface.low + inset, surface.high - inset))
        )

    def _route_to(self, point: Vec2, max_time: float = math.inf) -> bool:
        follower = self.follower
        if follower is None or follower.in_transition:
            return False
        goal = self.planner.anchor_near(point, GOAL_SNAP)
        if goal is None:
            return False
        start = follower.current_anchor()
        if goal.surface is start.surface and goal.point.distance_to(start.point) < 2.0:
            follower.reset(start)
            return True
        route = self.planner.plan(start, goal)
        if route is None or route.duration > max_time:
            return False
        follower.reset(start)
        follower.set_route(route)
        return True

    def _drop_goal(self) -> None:
        self.goal = None
        if self.follower is not None and not self.follower.in_transition:
            self.follower.reset(self.follower.current_anchor())

    def _check_stuck(self, dt: float) -> None:
        if self.goal is None or self.speed > 2.0:
            self._still = 0.0
            return
        self._still += dt
        if self._still >= STUCK_TIME:
            self._still = 0.0
            self._drop_goal()
            self.rest = 0.3

    def _face(self, point: Vec2, force: bool = False) -> None:
        """Turn to face `point` if it's well behind it (and not just after a turn,
        unless `force`d)."""
        ahead = (point - self.body).dot(along(self.up))
        if force and abs(ahead) > 2.0:
            self._set_heading(1 if ahead > 0 else -1)
        elif abs(ahead) > FACE_MARGIN and self.turn_wait <= 0.0:
            self._set_heading(1 if ahead > 0 else -1)

    def _set_heading(self, heading: int) -> None:
        if heading != self.heading:
            self.heading = heading
            self.turn_wait = TURN_COOLDOWN

    # ----- leaps -----------------------------------------------------------------

    def _pounce(self, target: Stickman) -> bool:
        """Crouch for a leap that lands right on `target`."""
        anchor = self.planner.anchor_near(target.contact(), 40.0)
        if anchor is None or self._arc(self.body, anchor) is None:
            return False
        self._crouch(Leap(anchor, "pounce", target))
        return True

    def _crouch(self, leap: Leap) -> None:
        self.pending = leap
        self.crouch_left = CROUCH_TIME[leap.kind]
        self.goal = None if leap.kind != "hop" else self.goal
        follower = self.follower
        if follower is not None:
            follower.reset(follower.current_anchor())
            self._settle()
        self._face(leap.target.point + leap.target.surface.normal * HIP_HEIGHT, force=True)

    def _crouching(self, dt: float) -> None:
        leap = self.pending
        assert leap is not None
        self.crouch_left -= dt
        if self.crouch_left > 0.0:
            return
        self.pending = None
        quarry = leap.quarry
        if leap.kind == "pounce" and quarry is not None and quarry.prey:
            aimed = self.planner.anchor_near(quarry.contact(), 40.0)
            if aimed is not None and self._arc(self.body, aimed) is not None:
                leap.target = aimed
        if not self.planner.owns(leap.target.surface):
            return
        arc = self._arc(self.body, leap.target)
        if arc is None:
            if leap.kind != "hop":
                return
            arc = self._arc(self.body, leap.target, check=False)
            if arc is None:
                return
        self._launch(leap, *arc)

    def _launch(self, leap: Leap, velocity: Vec2, time: float) -> None:
        leap.start = self.body
        leap.velocity = velocity
        leap.time = time
        leap.elapsed = 0.0
        self.leap = leap
        self.follower = None
        self.velocity = velocity
        if abs(velocity.x) > 20.0:
            self._set_heading(1 if velocity.x > 0 else -1)
        if leap.kind == "pounce":
            self.leap_wait = POUNCE_COOLDOWN
        elif leap.kind == "leap":
            self.leap_wait = LEAP_COOLDOWN

    def _hop(self, step: RouteStep) -> None:
        """A planned jump or drop, done as a short leap."""
        follower = self.follower
        assert follower is not None
        follower.reset(Anchor(step.from_surface, step.start))
        self._settle()
        self._crouch(Leap(Anchor(step.surface, step.end), "hop"))

    def _arc(self, start: Vec2, anchor: Anchor, check: bool = True) -> tuple[Vec2, float] | None:
        """Launch velocity and flight time for a ballistic arc of the body center from
        `start` to standing on `anchor`, clear of every window, or None."""
        end = anchor.point + anchor.surface.normal * HIP_HEIGHT
        offset = end - start
        distance = offset.length()
        if distance < 1.0:
            return None
        base = clamp(0.22 + distance / LEAP_PACE, 0.28, 0.85)
        for scale in (1.0, 0.8, 1.25, 1.55, 0.65, 1.9):
            time = base * scale
            velocity = Vec2(offset.x / time, (offset.y - 0.5 * GRAVITY * time * time) / time)
            if velocity.length() > MAX_LEAP_SPEED:
                continue
            arriving = velocity.y + GRAVITY * time
            if anchor.surface.walkable and arriving < 60.0:
                continue
            if not check or self._clear(start, velocity, time):
                return velocity, time
        return None

    def _clear(self, start: Vec2, velocity: Vec2, time: float) -> bool:
        world = self.world
        boxes = [_grown(box, BODY_CLEARANCE) for box in world.boxes]
        count = max(8, int(velocity.length() * time / 8.0))
        for i in range(1, count):
            t = time * i / count
            body = start + velocity * t + Vec2(0.0, 0.5 * GRAVITY * t * t)
            if not world.left <= body.x <= world.width:
                return False
            if world.ceiling is not None and body.y < world.ceiling + HIP_HEIGHT * 0.5:
                return False
            if body.y > world.floor_y - HIP_HEIGHT * 0.5:
                return False
            if any(box.contains(body) for box in boxes):
                return False
            feet = body + Vec2(0.0, HIP_HEIGHT)
            if i < count - 1 and any(box.contains(feet) for box in world.boxes):
                return False
        return True

    # ----- on a surface ----------------------------------------------------------

    def _crawl(self, dt: float) -> None:
        follower = self.follower
        assert follower is not None
        step = follower.step
        if step is not None and step.move in HOPS:
            self._hop(step)
            return
        if self._turning_about():
            self.speed = _ease(self.speed, 0.0, 12.0, dt)
            return
        surface = step.surface if step is not None else follower.current_anchor().surface
        move = Move.WALK if surface.walkable else Move.CLIMB
        planned = _planned_speed(move)
        self.pace = _ease(self.pace, GAITS[self._gait()][move] / planned, ACCELERATION, dt)
        before = self.position
        self._advance(self.pace * planned * dt)
        self.moved = self.position.distance_to(before)
        self.speed = _ease(self.speed, self.moved / dt, 12.0, dt)
        if self.intent is Intent.STALK and follower.route is None and self.target is not None:
            self._face(self.target.center())

    def _turning_about(self) -> bool:
        """True while it waits out its last turn before turning round for a route that
        heads back the way it came (a short last step back it just takes backward)."""
        follower = self.follower
        assert follower is not None
        step = follower.step
        if step is None or step.move not in ALONG_MOVES or follower.route is None:
            return False
        ahead = (step.end - step.start).dot(along(step.surface.normal))
        way = 1 if ahead > 0 else -1
        last = follower.index == len(follower.route.steps) - 1
        short = follower.contact().distance_to(step.end) < TURN_MIN
        if abs(ahead) > 1e-6 and way != self.heading and not (last and short):
            if self.turn_wait > 0.0:
                return True
            self._set_heading(way)
        return False

    def _advance(self, distance: float) -> None:
        """Along its route until its feet have gone `distance`."""
        follower = self.follower
        assert follower is not None
        left = distance
        budget = ADVANCE_BUDGET
        wait: float | None = None
        for _ in range(10):
            step = follower.step
            if step is None or left <= 0.05 or budget <= 1e-6:
                return
            rate = _body_rate(step)
            wait = min(left / rate if wait is None else wait, budget)
            before = self.position
            follower.update(wait)
            budget -= wait
            step = follower.step
            if step is not None and step.move in HOPS:
                self._hop(step)
                return
            self._settle()
            gained = self.position.distance_to(before)
            left -= gained
            wait = left / rate if gained > 0.25 * wait * rate else wait * 2.0

    def _gait(self) -> str:
        if self.intent is Intent.STALK:
            return self.gait
        return "lope" if self._remaining() > LOPE_DISTANCE else "prowl"

    def _remaining(self) -> float:
        follower = self.follower
        if follower is None:
            return 0.0
        total = sum(step.start.distance_to(step.end) for step in follower.remaining_steps())
        if follower.step is None:
            return total
        return total - follower.contact().distance_to(follower.step.start)

    def _settle(self) -> None:
        """Feet and up from its route: along a surface, on it; round a corner, an eased
        roll from one surface onto the next."""
        follower = self.follower
        assert follower is not None
        step = follower.step
        if step is None or step.move in ALONG_MOVES or step.move in HOPS:
            anchor = follower.current_anchor()
            self.position, self.up = anchor.point, anchor.surface.normal
        else:
            t = 1.0 if step.duration <= 0.0 else clamp(follower.elapsed / step.duration, 0.0, 1.0)
            ease = smoothstep(t)
            self.position = step.start.lerp(step.end, ease)
            up = step.from_surface.normal.lerp(step.surface.normal, ease)
            if up.length() < 0.3:
                up = step.from_surface.normal if t < 0.5 else step.surface.normal
            self.up = up.normalized()
        self.body = self._offset(self.position + self.up * HIP_HEIGHT)

    def _offset(self, body: Vec2) -> Vec2:
        """`body` pushed out to its height off every surface it's nearer than that to
        (in an inside corner it sits back from both)."""
        for _ in range(2):
            pushed = False
            for surface in self.planner.surfaces:
                normal = surface.normal
                gap = (body - surface.start).dot(normal)
                if gap < 0.0 or gap >= HIP_HEIGHT - 1e-6:
                    continue
                coord = surface.coord(body)
                if not surface.low + 0.5 < coord < surface.high - 0.5:
                    continue
                body = body + normal * (HIP_HEIGHT - gap)
                pushed = True
            if not pushed:
                break
        return body

    def _attach(self, anchor: Anchor) -> None:
        self.follower = RouteFollower(anchor)
        self.velocity = ZERO
        self._replan_wait = 0.0
        self._settle()

    def _land(self, anchor: Anchor, kind: str) -> None:
        velocity = self.velocity
        self.leap = None
        self._attach(anchor)
        self.land_time = self.land_left = LAND_TIME[kind]
        self.pace = 0.6
        ahead = velocity.dot(along(self.up))
        if abs(ahead) > 20.0:
            self._set_heading(1 if ahead > 0 else -1)
        self.turn_wait = 0.0
        self.world.debris.burst(anchor.point, anchor.surface.normal, 6, 120.0, spread=1.4)

    def loose(self) -> None:
        """Off its surface and into a fall, the body where it was."""
        self.follower = None
        self.leap = None
        self.pending = None
        self.velocity = ZERO

    # ----- in the air ----------------------------------------------------------

    def _fly(self, dt: float) -> None:
        leap = self.leap
        if leap is not None:
            leap.elapsed += dt
            t = min(leap.elapsed, leap.time)
            body = leap.start + leap.velocity * t + Vec2(0.0, 0.5 * GRAVITY * t * t)
            velocity = leap.velocity + Vec2(0.0, GRAVITY * t)
            if leap.elapsed >= leap.time and self.planner.owns(leap.target.surface):
                self.velocity = velocity
                self.body = body
                self._maul(leap)
                self._land(leap.target, leap.kind)
                return
            blocked = any(box.contains(body) for box in self.world.boxes)
            if leap.elapsed < leap.time and not blocked:
                self.body, self.velocity = body, velocity
                self._maul(leap)
                return
            self.leap = None
        self._fall(dt)

    def _maul(self, leap: Leap) -> None:
        """A pounce reaching its quarry mauls him (once)."""
        quarry = leap.quarry
        if leap.struck or quarry is None or not quarry.prey:
            return
        middle = quarry.center()
        reach = min(self.body.distance_to(middle), self.chimera.lion_head.distance_to(middle))
        if reach > POUNCE_HIT:
            return
        leap.struck = True
        push = self.velocity.normalized() * POUNCE_PUSH + Vec2(0.0, -120.0)
        quarry.hurt_from(
            self.chimera, POUNCE_DAMAGE, middle, push, "chimera", "Mauled by the chimera!"
        )

    def _fall(self, dt: float) -> None:
        """Free fall: land on a top or the floor, or cling to a window it hits."""
        world = self.world
        before = self.body
        self.velocity += Vec2(0.0, GRAVITY * dt)
        after = before + self.velocity * dt
        low, high = world.left + HIP_HEIGHT, world.width - HIP_HEIGHT
        if not low <= after.x <= high:
            after = Vec2(clamp(after.x, low, high), after.y)
            self.velocity = Vec2(0.0, self.velocity.y)
        if world.ceiling is not None and after.y < world.ceiling + HIP_HEIGHT:
            after = Vec2(after.x, world.ceiling + HIP_HEIGHT)
            self.velocity = Vec2(self.velocity.x, max(0.0, self.velocity.y))
        feet_before = before + Vec2(0.0, HIP_HEIGHT)
        feet_after = after + Vec2(0.0, HIP_HEIGHT)
        if self.velocity.y >= 0.0:
            crossed = [
                s
                for s in self.planner.surfaces
                if s.walkable
                and s.low - 1.0 <= after.x <= s.high + 1.0
                and feet_before.y <= s.start.y + 0.5
                and feet_after.y >= s.start.y
            ]
            if crossed:
                surface = min(crossed, key=lambda s: s.start.y)
                self.body = after
                self._land(Anchor(surface, surface.closest_point(Vec2(after.x, 0.0))), "fall")
                return
        for box in world.boxes:
            entering = box.contains(after) or box.contains(feet_after)
            if not entering or box.contains(before):
                continue
            anchor = self.planner.anchor_near(after, CLING_REACH)
            if anchor is not None and anchor.surface.box is not None:
                self.body = after
                self._land(anchor, "fall")
                return
            if before.y >= box.bottom:
                after = Vec2(after.x, box.bottom + HIP_HEIGHT)
                self.velocity = Vec2(self.velocity.x, max(0.0, self.velocity.y))
            else:
                after = Vec2(before.x, after.y)
                self.velocity = Vec2(0.0, self.velocity.y)
        if feet_after.y >= world.floor_y:
            floor = [
                s
                for s in self.planner.surfaces
                if s.walkable and abs(s.start.y - world.floor_y) < 0.5
            ]
            if floor:
                nearest_floor = min(
                    floor, key=lambda s: abs(clamp(after.x, s.low, s.high) - after.x)
                )
                self.body = after
                point = nearest_floor.closest_point(Vec2(after.x, world.floor_y))
                self._land(Anchor(nearest_floor, point), "fall")
                return
            after = Vec2(after.x, world.floor_y - HIP_HEIGHT)
        self.body = after

    def _animate(self, dt: float) -> None:
        if self.pending is not None:
            total = CROUCH_TIME[self.pending.kind]
            self.crouch = smoothstep(min(1.0, (1.0 - self.crouch_left / total) * 1.6))
        else:
            self.crouch = _ease(self.crouch, 0.0, 14.0, dt)
        if self.follower is None or self.pending is not None or self.land_left > 0.0:
            self.speed = _ease(self.speed, 0.0, 12.0, dt)

    # ----- terrain -------------------------------------------------------------

    def terrain_changed(self, change: TerrainChange) -> None:
        """Ride the window it's on (or land where its target went); fall if it closes
        or moves out from under it."""
        follower = self.follower
        if follower is None:
            if change.shift is not None:
                self.body = self.body + change.shift
            leap = self.leap
            if leap is not None:
                if change.shift is not None:
                    leap.start = leap.start + change.shift
                target = self._moved(leap.target, change)
                if target is None:
                    self.leap = None
                else:
                    leap.target = target
            self._escape()
            return
        pending = self.pending
        step = follower.step
        if step is not None and follower.in_transition and self._carry_transition(step, change):
            return
        anchor = follower.current_anchor()
        moved = self._moved(anchor, change)
        if moved is None:
            self.body = self.body + (change.delta_for(anchor.surface.box) or ZERO)
            self.loose()
            self._escape()
            return
        self._attach(moved)
        if pending is not None:
            target = self._moved(pending.target, change)
            self.pending = (
                Leap(target, pending.kind, pending.quarry) if target is not None else None
            )

    def _escape(self) -> None:
        """Out of the window that just closed over it, onto the nearest surface."""
        if not any(box.contains(self.body) for box in self.world.boxes):
            return
        anchor = self.planner.anchor_near(self.body, ESCAPE_REACH)
        if anchor is not None:
            self._land(anchor, "fall")

    def _carry_transition(self, step: RouteStep, change: TerrainChange) -> bool:
        """Keep rolling round the corner it's on, onto the corner's new place."""
        follower = self.follower
        assert follower is not None
        start = self._moved(Anchor(step.from_surface, step.start), change)
        end = self._moved(Anchor(step.surface, step.end), change)
        if start is None or end is None:
            return False
        elapsed = follower.elapsed
        follower.reset(start)
        moved = RouteStep(
            step.move, start.point, end.point, step.duration, end.surface, start.surface
        )
        follower.set_route(Route((moved,)))
        follower.elapsed = elapsed
        self._settle()
        return True

    def _moved(self, anchor: Anchor, change: TerrainChange) -> Anchor | None:
        """`anchor` on the rebuilt terrain: the same kind of surface of the same window,
        carried along with it, or None if that's gone."""
        box = anchor.surface.box
        if change.removed(box):
            return None
        point = anchor.point + (change.delta_for(box) or ZERO)
        new_box = change.new_index(box)
        best: Anchor | None = None
        best_distance = 12.0
        for surface in self.planner.surfaces:
            if surface.kind is not anchor.surface.kind or surface.box != new_box:
                continue
            closest = surface.closest_point(point)
            distance = closest.distance_to(point)
            if distance <= best_distance:
                best, best_distance = Anchor(surface, closest), distance
        return best
