"""The minotaur: a hulking bull-headed brute.

It has its own terrain and planner (`world.minotaur_planner`): it walks the floor and
window tops, and it never crawls walls or hangs from undersides. To get up a window
side (or a screen edge) it **climbs**: it grabs the wall and hauls itself up hand
over hand, hooves kicking, at a steady `CLIMB_SPEED`, then rolls over the lip onto the
top. Planned jumps and drops become ballistic arcs, and every landing is absorbed
with a crouch and a puff of dust, harder the further it fell. A landing with
real weight flattens anyone underneath it.

It is heavy: it speeds up and slows down gradually (`ACCELERATION`, `BRAKING`),
stops before it turns round, then turns at once, and only backs up (without
turning) for a short step back.

It hunts the nearest free adventurer (sticking with him `FOE_COMMIT`, switching for
one much nearer). With him on the same flat surface (the same window top, or the
floor) and `CHARGE_MIN`..`CHARGE_MAX` off with a clear run, it paws the ground and
lowers its horns (`CHARGE_WINDUP`), then **charges** along the surface: it can't
steer, skids to a stop past where he stood (or before the surface ends), and
tramples everyone it runs through (`TRAMPLE_DAMAGE`, knocked flat, each once). A lone
foe it only charges from `CHARGE_SOLO` away; two or more in the way it charges from
`CHARGE_MIN`. Up close it fights with its fists and its hooves: a **stomp** that lands
`STOMP_DAMAGE` on whoever the hoof comes down on and shakes the ground
(`STOMP_RADIUS`) so the others nearby go flat, or a **ground smash** with both fists
for anyone a step farther. With someone in its hands and another foe farther off, it
**hurls** the one it grabbed (`THROW_DAMAGE`, its hardest blow, then `THROW_COOLDOWN`).
It only starts a blow that will reach. Someone off the floor (up a wall, under a
window), it heads for the nearest spot on a wall it can reach him from: his wall, or
the one facing it across a narrow gap, maybe the very wall it's on. There it holds on
with one hand, swings its body out and **swipes** at him with the other (`SWIPE_DAMAGE`,
about 70 px from its shoulder, in any direction), or punches him if he's lined up on
its wall. It drops back to the ground if its blows there can't land or an archer is
shooting it from off that wall.

Hit by anything from range (an arrow, a missile, a vine, a bomb), it **enrages** for
`RAGE_TIME` (refreshed by every ranged hit): it moves and charges `RAGE_PACE` faster,
its cooldowns run faster, and it goes after whoever shot it, climbing walls to
get at him. With `MINOTAUR_HP` gone it topples onto its back.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep
from dungeons_desktops.game.actors.hunting import priority_prey
from dungeons_desktops.game.actors.mortal import Mortal
from dungeons_desktops.game.defenders.minotaur.combat import (
    Thrown,
)
from dungeons_desktops.game.defenders.minotaur.combat import (
    segment_distance as _segment_distance,
)
from dungeons_desktops.game.defenders.minotaur.movement import (
    Flight,
    Haul,
)
from dungeons_desktops.game.defenders.minotaur.movement import (
    approach as _approach,
)
from dungeons_desktops.game.defenders.minotaur.movement import (
    carry_on as _carry_on,
)
from dungeons_desktops.game.defenders.minotaur.movement import (
    sign as _sign,
)
from dungeons_desktops.game.effects.ballistics import lob_velocity
from dungeons_desktops.navigation.planner import Anchor, Move, MoveSettings, Planner, RouteStep
from dungeons_desktops.navigation.terrain import Surface, TerrainChange

if TYPE_CHECKING:
    from dungeons_desktops.game.adventurers.actor import Stickman
    from dungeons_desktops.game.world.simulation import SimWorld

MINOTAUR_HP = 26
LABYRINTH_SIZE = 1.3
"""How much larger the Labyrinth King is drawn and fought than a common bull."""

GRAVITY = 1250.0
HEIGHT = 64.0
"""Feet to the top of its hump (its horns stand above that)."""
HIP_HEIGHT = 27.0
SHOULDER = Vec2(4.0, -54.0)
"""Its body in its own frame: facing +x, feet at the origin, y down."""
CHEST = Vec2(3.9, -47.4)
WAIST = Vec2(0.2, -31.0)
HORNS = Vec2(38.8, -53.5)
"""Its horns, lowered for a charge."""
HEAD = Vec2(24.5, -53.5)
"""Its head, small, jutting out ahead of its great shoulders at their height."""
NECK = Vec2(12.6, -57.1)
BACK = Vec2(-13.3, -49.5)
"""Its near shoulder, a great hump of muscle at its back."""
STANCE = (Vec2(-12.0, -3.0), Vec2(13.0, -3.0))
"""Its hooves, roughly: braced wide."""
TORSO_RADIUS = 15.0
HEAD_RADIUS = 8.0
NECK_RADIUS = 7.0
BACK_RADIUS = 9.0
LEG_RADIUS = 7.0
WALL_GAP = 18.0
"""On a wall its feet are against the wall and its body this far out from it."""

MOVES = MoveSettings(
    walk_speed=38.0,
    climb_speed=100.0,
    hang_speed=1.0,
    mantle_time=0.6,
    grab_time=0.35,
    swing_time=0.6,
    max_drop=260.0,
    max_hang_drop=420.0,
    max_jump=100.0,
    gravity=GRAVITY,
    edge_clearance=12.0,
)
"""Its routes. A wall side reaches `HANG_REACH` below the window's bottom edge (its
feet hang that far below its hands), and the lip is `MANTLE_DEPTH` above its feet when
it grabs it. It has no undersides to hang from."""
HANG_REACH = 55.0
MANTLE_DEPTH = 40.0
CLEARANCE = 16.0
"""Floors and window tops with another window closer than this (its bulk) are left out
(but not walls: in a narrow slot it climbs anyway, its bulk clipping the window beside)..."""
HEADROOM = 56.0
"""...and floors and window tops with one lower than this above them (it can't stoop)."""

WALK_SPEED = 38.0
BACK_SPEED = 18.0
ACCELERATION = 70.0
BRAKING = 120.0
STRIDE = 36.0
"""Distance per full walk cycle (two steps)."""
TURN_TIME = 0.45
BACKSTEP = 36.0
"""A spot this little way behind it, it backs up to without turning round."""
LAND_TIME = (0.16, 0.5)
"""Absorbing a landing: a soft one to a hard one (`HARD_LANDING` px/s or more)."""
SOFT_LANDING = 150.0
HARD_LANDING = 520.0
CRUSH_REACH = 24.0
"""Anyone this close to its feet, on the surface it lands on, is flattened."""
CRUSH_DAMAGE = 5
CRUSH_FLING = 90.0
CRUSH_DOWN = 1.1
CRUSH_STUN = 0.6
JUMP_CROUCH = 0.3
JUMP_APEX = 18.0
"""How far over the higher end a jump's arc peaks."""
CLIMB_SPEED = 105.0
"""How fast it hauls itself up a wall, hand over hand, at a steady pace..."""
CLIMB_ACCEL = 420.0
"""...getting up to it (and down from it) smoothly..."""
CLIMB_REACH = 40.0
"""...climbing this far for each full cycle of its hands and hooves."""
SLIDE_SPEED = 110.0
"""Going down a wall it slides, hands and hooves dragging."""
MANTLE_TIME = 0.6
GRAB_TIME = 0.35

RAGE_TIME = 5.0
RAGE_PACE = 1.5
RAGE_COOLDOWN = 1.7
"""How much faster its cooldowns run while enraged."""

CHARGE_MIN = 100.0
CHARGE_MAX = 450.0
CHARGE_SOLO = 170.0
CHARGE_WINDUP = 0.55
CHARGE_SPEED = 230.0
CHARGE_ACCEL = 700.0
CHARGE_SKID = 650.0
CHARGE_PAST = 60.0
"""It means to stop this far past where its foe stood..."""
CHARGE_GROUP = 50.0
"""...running on through anyone within this of where it would have stopped..."""
CHARGE_EDGE = 14.0
"""...or this far short of the end of the surface."""
CHARGE_COOLDOWN = 3.5
WINDED_TIME = 0.6
TRAMPLE_DAMAGE = 3
TRAMPLE_FLING = 280.0
TRAMPLE_DOWN = 0.9
TRAMPLE_STUN = 0.4
TRAMPLE_FRONT = 16.0
TRAMPLE_BACK = 8.0
"""Its body runs this far ahead of and behind its feet, trampling whoever's there."""
LANE_HEIGHT = 8.0

STOMP_TIMES = (0.42, 0.1, 0.48)
STOMP_DAMAGE = 6
STOMP_PUSH = 160.0
STOMP_COOLDOWN = 1.4
STOMP_CLOSE = 18.0
"""He stomps only this close, the hoof coming down on them. Any farther, he smashes."""
STOMP_X = 42.0
"""Where the hoof comes down when a stomp has no one aimed."""
STOMP_HIT = 10.0
STOMP_RADIUS = 40.0
"""The stomp shakes the ground this far, and flattens whoever's standing there."""
STOMP_QUAKE = 1
STOMP_FLING = 170.0
STOMP_DOWN = 0.8
STOMP_STUN = 0.35

PUNCH_TIMES = (0.18, 0.09, 0.34)
PUNCH_DAMAGE = 4
PUNCH_PUSH = 280.0
PUNCH_COOLDOWN = 0.55
PUNCH_HIT = 12.0
"""How near the fist has to pass to land, up a wall."""
SMASH_TIMES = (0.34, 0.1, 0.4)
SMASH_DAMAGE = 5
SMASH_PUSH = 260.0
SMASH_COOLDOWN = 0.85
SMASH_HIT = 14.0
SMASH_X = 38.0
"""How far ahead of its feet the fists can slam the ground."""
THROW_TIMES = (0.22, 0.28, 0.16, 0.3)
"""Reach for him, hold him cocked, fling, recover."""
THROW_DAMAGE = 8
"""Its hardest blow: the adventurer it throws hits someone farther off for this."""
THROW_PUSH = 460.0
THROW_COOLDOWN = 1.0
THROW_HIT = 14.0
THROW_SELF = 10
"""What the hurled adventurer himself takes when he lands."""
GRAB_REACH = 30.0
THROW_MIN = 72.0
THROW_MAX = 500.0
HURL_GRAVITY = 980.0
PUNCH_SHOULDER = Vec2(10.0, -54.0)
"""The fist's shoulder while it climbs, in its own frame."""
GUARD_SHOULDER = Vec2(-4.0, -40.0)
"""The punching shoulder on the ground."""
GUARD_NEAR = Vec2(4.0, -36.0)
"""Its near fist, cocked in front of its chest."""
ARM_REACH = 25.0
"""How far that fist can strike from the shoulder, climbing..."""
GROUND_REACH = 34.0
"""...and on the ground."""
SWIPE_TIMES = (0.32, 0.12, 0.42)
"""Swing out off the wall cocking the free arm, lash out, swing back in to the wall."""
SWIPE_DAMAGE = 5
SWIPE_PUSH = 260.0
SWIPE_COOLDOWN = 0.9
SWIPE_HIT = 14.0
SWIPE_SHOULDER = Vec2(4.0, -55.0)
"""Up a wall, the striking (far) shoulder, squared up to the wall..."""
GRIP_SHOULDER = Vec2(10.0, -53.0)
"""...and the near one, whose hand keeps hold of the wall through the swipe."""
SWIPE_ARM = 26.0
"""How far the free fist reaches from its shoulder (a little short of the drawn arm)."""
LUNGE_OUT = 18.0
LUNGE_ALONG = 26.0
"""How far its body swings out from the wall, and up or down it, hanging off one hand:
with the arm and fist, a swipe reaches about 70 px from its shoulder, across a narrow
gap to someone on the facing wall."""
GRIP_ARM = 27.0
SWIPE_HOLD = (Vec2(WALL_GAP + 0.5, -61.0), 0.12)
"""Where the free hand leaves and rejoins the wall, and how long it takes its hands to
go from climbing into the swipe (and back)."""

STAND_OFF = 34.0
OVERLAP = 14.0
FOE_COMMIT = 1.5
FOE_SWITCH = 0.6
REPLAN_EVERY = 0.5
FOE_SHIFT = 30.0
GIVE_UP = 3.0
STAND_GIVE_UP = 1.5
"""Standing where its route ended without landing a blow, before it tries someone else."""
IGNORE_FOE = 5.0
REACH_CHECK = 0.5
"""How long a verdict on whether it can get at someone is kept."""
OUT_OF_REACH = 0.8
"""How long it sticks with a foe who has got out of its reach, when another is in reach."""
LOW_REACH = 92.0
"""How far above its feet a blow from the ground still lands on someone on a wall."""
PROWL = 150.0
PROWL_REST = (0.5, 1.1)
STALL_TIME = 1.8
STALL_MOVE = 6.0
"""Going for someone and not getting this far in `STALL_TIME` counts him out of reach..."""
STALL_FORGET = 3.0
"""...for this long."""
REST_TIME = (1.0, 3.0)
ESCAPE_REACH = 160.0
WALL_PATIENCE = 0.6
"""On a wall with nowhere to go for this long, it lets go."""
WALL_WHIFFS = 2
"""Wall punches that hit nothing, and then it drops and fights on the ground."""
GROUND_HUNT = 4.0
"""After that drop, it stays off the walls for this long."""

ZERO = Vec2(0.0, 0.0)

STANCES = ("windup", "skid", "stomp", "punch", "smash", "hurl")
"""Actions it plants its feet for."""
POSE_SPRING = 22.0
"""How stiffly (1/s) its posture and head follow from one move into the next."""


class Minotaur(Mortal):
    max_hp = MINOTAUR_HP
    linger = 3.5

    def __init__(self, world: SimWorld, anchor: Anchor, heading: int = 1) -> None:
        self.world = world
        self.surface: Surface | None = anchor.surface
        """What its feet are on (a walk or a wall); None in the air or over a lip."""
        self.position = anchor.point
        """Its feet."""
        self.velocity = ZERO
        self.speed = 0.0
        """Along a walk (+x right)."""
        self.facing = heading
        self.size = 1.0
        """Drawn and fought scale; Labyrinth King grows to `LABYRINTH_SIZE`."""
        self.legendary = False
        self._legendary_scaled = False
        self.turn_left = 0.0
        self.route: list[RouteStep] = []
        self.goal: Vec2 | None = None
        self.flight: Flight | None = None
        self.haul: Haul | None = None
        self.climb_speed = 0.0
        """Up a wall (px/s), eased."""
        self.climb_phase = 0.0
        self._climb_spare = 0.0
        """Through its hand-over-hand climb: a hand reaches up at every half."""
        self.sliding = False
        self.slide = 0.0
        """0 climbing to 1 sliding down a wall, eased (for drawing)."""
        self.land_left = 0.0
        self.land_time = 1.0
        self.impact = 0.0
        """How hard its last landing was (0..1)."""
        self.action: str | None = None
        """"crouch" (for a jump), "windup", "charge", "skid", "winded", "stomp",
        "punch", "smash" or "hurl"."""
        self.action_time = 0.0
        self._pending: RouteStep | None = None
        self._struck: set[Stickman] = set()
        self._shocked = False
        self.charge_stop = 0.0
        self.charge_wait = 1.0
        self.attack_wait = 0.0
        self.throw_wait = 0.0
        self.trampled = 0
        """Adventurers run down in the current charge."""
        self.rage_left = 0.0
        self.provoker: Stickman | None = None
        """Who shot it last, while it's enraged."""
        self.fury = 0.0
        """0 calm to 1 enraged (eased, for drawing)."""
        self.foe: Stickman | None = None
        self._foe_since = 0.0
        self._foe_stuck = 0.0
        self._unreached = 0.0
        """How long it's stood where its route ended without being able to reach its foe."""
        self._ignored: dict[Stickman, float] = {}
        self._reach: dict[Stickman, tuple[float, bool]] = {}
        """Whether it can get at each adventurer, and until when that holds."""
        self._out_of_reach = 0.0
        self._prowl_to: float | None = None
        self._prowl_rest = 0.0
        self._prowling = False
        self._stall_spot: tuple[float, Vec2] | None = None
        self._replan_wait = 0.0
        self._aimed: Vec2 | None = None
        self.rest = 0.5
        self._wall_idle = 0.0
        self._wall_whiff = 0
        self._ground_for = 0.0
        """Seconds left of staying off the walls, after a punch there fails."""
        self.kills = {
            "charge": 0,
            "punch": 0,
            "smash": 0,
            "stomp": 0,
            "quake": 0,
            "crush": 0,
            "throw": 0,
            "swipe": 0,
        }
        self._punch_at: Vec2 | None = None
        """Where the fist is thrown (its own frame), set as a punch starts."""
        self._smash_x = SMASH_X
        """How far ahead of its feet the fists slam, set as a smash starts."""
        self._stomp_x = STOMP_X
        """How far ahead of its feet the hoof comes down, set as a stomp starts."""
        self._caught: Stickman | None = None
        """Who it's holding, through a hurl."""
        self._hurl_at: Stickman | None = None
        """Who the held adventurer is being thrown at."""
        self._thrown: Thrown | None = None
        self._swipe_lunge = ZERO
        """How far (own frame) its body swings out for the swipe under way..."""
        self._swipe_at = SWIPE_HOLD[0]
        """...where the fist is aimed, from the swung-out body..."""
        self._swipe_grip = ZERO
        """...where (world) the other hand holds on..."""
        self._swipe_back: Vec2 | None = None
        """...and, if it was called off, where the fist turned back from."""
        self._swipe_live = False
        self.lunge = ZERO
        """How far (world) its body has swung out off the wall, eased."""
        self._lunge_rate = ZERO
        # Animation state (read by the renderer).
        self.time = 0.0
        self.phase = 0.0
        """Walk cycle: a footfall at every half."""
        self.gait = 0.0
        """How far into its stride it is (0 standing to 1 walking), eased."""
        self.gallop = 0.0
        """0 walking to 1 charging: its gait, eased by its speed."""
        self.stance = 0.0
        """0 walking to 1 planted for `stance_kind` (an action with its feet set), eased."""
        self.stance_kind = "stomp"
        self.stride_way = 1
        self.slung = 0.0
        """0 with its fists up to 1 gripping a wall, eased."""
        """+1 striding forward, -1 backing up (kept once it stops)."""
        self._pose: tuple[float, float, float] | None = None
        """Eased lean, crouch and head pitch."""
        self._pose_rate = (0.0, 0.0, 0.0)
        self.paw = 0.0
        self.slump = 0.0
        self.tilt = 0.0
        """Dead: how far it has toppled (0 upright to 1 on its back)."""

    # ----- where it is -----------------------------------------------------------

    @property
    def planner(self) -> Planner:
        return self.world.minotaur_planner

    @property
    def airborne(self) -> bool:
        return self.flight is not None

    @property
    def on_wall(self) -> bool:
        return self.surface is not None and self.surface.wall

    @property
    def grounded(self) -> bool:
        return self.surface is not None and self.surface.walkable

    @property
    def turning(self) -> bool:
        return self.turn_left > 0.0

    @property
    def turn(self) -> float:
        """-1..1: which way it faces, easing through a turnaround."""
        if self.turn_left <= 0.0:
            return float(self.facing)
        t = smoothstep(1.0 - self.turn_left / (TURN_TIME / self.pace))
        return self.facing * (2.0 * t - 1.0)

    @property
    def pace(self) -> float:
        return RAGE_PACE if self.rage_left > 0.0 else 1.0

    @property
    def enraged(self) -> bool:
        return self.rage_left > 0.0

    def root(self) -> Vec2:
        """Under its body: its feet, or (on a wall) out from the wall by `WALL_GAP`, and
        swung out further for a swipe."""
        return self.position - Vec2(self.facing * self._gap(), 0.0) + self.lunge

    def _gap(self) -> float:
        if self.on_wall:
            return WALL_GAP
        haul, flight = self.haul, self.flight
        if haul is not None:
            start, end = haul.from_wall, haul.target.surface.wall
            t = min(1.0, haul.age / haul.duration)
        elif flight is not None:
            start = flight.from_wall
            end = flight.target is not None and flight.target.surface.wall
            t = min(1.0, flight.age / flight.duration) if flight.target is not None else 1.0
        else:
            return 0.0
        return WALL_GAP * (start + (end - start) * smoothstep(t))

    def posture(self) -> tuple[float, float]:
        """How far its upper body leans forward (radians) and how low it crouches (px),
        eased from one move into the next."""
        if self._pose is None:
            return self._posture()
        return self._pose[0], self._pose[1]

    def _posture(self) -> tuple[float, float]:
        action, t = self.action, self.action_time
        if self.dead:
            return -0.1, 8.0 * self.slump
        if self.on_wall:
            return -0.05, 3.0
        if self.flight is not None:
            rising = self.velocity.y < 0.0
            return (0.25 if rising else 0.05), (2.0 if rising else 5.0)
        if self.land_left > 0.0:
            u = self.land_left / self.land_time
            dip = math.sin(math.pi * min(1.0, u * 1.3)) * (5.0 + 9.0 * self.impact)
            return 0.15 + 0.2 * self.impact * u, dip
        if action == "crouch":
            u = smoothstep(min(1.0, t / JUMP_CROUCH))
            return 0.3 * u, 12.0 * u
        if action == "windup":
            u = smoothstep(min(1.0, t / (CHARGE_WINDUP * 0.5)))
            return 0.4 * u, 5.0 * u
        if action == "charge":
            return 0.6, 6.0
        if action == "skid":
            return -0.15, 9.0
        if action == "winded":
            return 0.35, 3.0 + 1.5 * math.sin(self.time * 9.0)
        if action == "stomp":
            return self._stomp_posture()
        if action == "smash":
            return self._smash_posture()
        if action == "hurl":
            return self._hurl_posture()
        if action == "punch" and not self.on_wall:
            return 0.22, 3.0
        lean = 0.08 + 0.1 * clamp(abs(self.speed) / WALK_SPEED, 0.0, 1.5) * self._forward()
        return lean + 0.12 * self.fury, 0.0

    def _forward(self) -> float:
        """+1 walking forward, -1 backing up."""
        return 1.0 if self.speed * self.facing >= 0.0 else -1.0

    def _stomp_posture(self) -> tuple[float, float]:
        """Leans back as the hoof rises, then crashes forward onto it."""
        wind, strike, recover = STOMP_TIMES
        t = self.action_time
        start, top, hit = (0.05, 0.0), (-0.28, 2.0), (0.4, 10.0)
        if t < wind:
            u = smoothstep(t / wind)
            a, b = start, top
        elif t < wind + strike:
            u = ((t - wind) / strike) ** 2
            a, b = top, hit
        else:
            u = smoothstep(clamp((t - wind - strike) / recover, 0.0, 1.0))
            a, b = hit, start
        return a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u

    def _smash_posture(self) -> tuple[float, float]:
        """Rears up with both fists, then crashes them into the ground."""
        wind, strike, recover = SMASH_TIMES
        t = self.action_time
        start, top, hit = (0.08, 0.0), (-0.22, 1.0), (0.48, 9.0)
        if t < wind:
            u = smoothstep(t / wind)
            a, b = start, top
        elif t < wind + strike:
            u = ((t - wind) / strike) ** 2
            a, b = top, hit
        else:
            u = smoothstep(clamp((t - wind - strike) / recover, 0.0, 1.0))
            a, b = hit, start
        return a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u

    def _hurl_posture(self) -> tuple[float, float]:
        """Leans back with someone cocked in its fist, then snaps forward to throw."""
        reach, hold, fling, recover = THROW_TIMES
        t = self.action_time
        if t < reach + hold:
            u = smoothstep(min(1.0, t / (reach + hold)))
            return 0.05 - 0.3 * u, 2.0 * u
        if t < reach + hold + fling:
            u = ((t - reach - hold) / fling) ** 2
            return -0.3 + 0.7 * u, 2.0 - 1.0 * u
        u = smoothstep(clamp((t - reach - hold - fling) / recover, 0.0, 1.0))
        return 0.4 * (1.0 - u), 1.0 * (1.0 - u)

    def local(self, point: Vec2) -> Vec2:
        """A point of its upright body (own frame) placed for its lean and crouch."""
        lean, squat = self.posture()
        hip = Vec2(0.0, -HIP_HEIGHT + squat)
        if point.y >= -HIP_HEIGHT:
            scale = (HIP_HEIGHT - squat) / HIP_HEIGHT
            return Vec2(point.x, point.y * scale)
        return hip + (point - Vec2(0.0, -HIP_HEIGHT)).rotated(lean)

    def to_world(self, local: Vec2) -> Vec2:
        """Its own frame to the world (facing either way)."""
        root = self.root()
        if self.dead and self.tilt > 0.0:
            fallen = smoothstep(self.tilt)
            local = local.rotated(-0.5 * math.pi * fallen) - Vec2(0.0, 12.0 * fallen)
        return Vec2(root.x + local.x * self.facing, root.y + local.y)

    def center(self) -> Vec2:
        return self.to_world(self.local(CHEST))

    def head(self) -> Vec2:
        return self.to_world(self.local(HEAD))

    def parts(self) -> list[Vec2]:
        return [
            self.to_world(self.local(p))
            for p in (HEAD, CHEST, WAIST, Vec2(1.0, -HIP_HEIGHT), Vec2(2.0, -12.0))
        ]

    def hits(self, point: Vec2, margin: float = 0.0) -> bool:
        # Match the Labyrinth King's larger drawn silhouette.
        scale = self.size
        head = self.to_world(self.local(HEAD))
        if head.distance_to(point) <= HEAD_RADIUS * scale + margin:
            return True
        waist = self.to_world(self.local(WAIST))
        chest = self.to_world(self.local(SHOULDER))
        if (
            _segment_distance(point, self.to_world(self.local(NECK)), head)
            <= NECK_RADIUS * scale + margin
        ):
            return True
        if _segment_distance(point, waist, chest) <= TORSO_RADIUS * scale + margin:
            return True
        if self.to_world(self.local(BACK)).distance_to(point) <= BACK_RADIUS * scale + margin:
            return True
        hips = self.to_world(self.local(Vec2(0.0, -HIP_HEIGHT)))
        return any(
            _segment_distance(point, self.to_world(foot), hips) <= LEG_RADIUS * scale + margin
            for foot in STANCE
        )

    def hoof(self, t: float | None = None) -> Vec2:
        """The stomping hoof in its own frame (y = 0 on the ground)."""
        if t is None:
            t = self.action_time
        wind, strike, recover = STOMP_TIMES
        land = self._stomp_x
        planted, lifted, slammed = (
            Vec2(-12.0, 0.0),
            Vec2(max(2.0, land - 6.0), -26.0),
            Vec2(land, 0.0),
        )
        if t < wind:
            return planted.lerp(lifted, smoothstep(t / max(wind, 1e-3)))
        if t < wind + strike:
            return lifted.lerp(slammed, ((t - wind) / strike) ** 2)
        return slammed.lerp(planted, smoothstep(clamp((t - wind - strike) / recover, 0.0, 1.0)))

    def impact_point(self) -> Vec2:
        """Where the hoof comes down."""
        wind, strike, _ = STOMP_TIMES
        return self.to_world(Vec2(self.hoof(wind + strike).x, 0.0))

    # ----- update -------------------------------------------------------------------

    def update(self, dt: float) -> None:
        self._apply_legendary_size()
        self.time += dt
        self._timers(dt)
        if self.flight is not None:
            self._fly(dt)
        elif self.haul is not None:
            self._haul(dt)
        elif self.land_left > 0.0:
            self.land_left -= dt
            self._brake(dt)
        elif self.action is not None:
            self._act(dt)
        else:
            self._think(dt)
        self._fly_thrown(dt)
        self._escape()

    def _apply_legendary_size(self) -> None:
        """Legendary status is applied by spawning after construction."""
        if self._legendary_scaled or not self.legendary:
            return
        self._legendary_scaled = True
        self.size = LABYRINTH_SIZE

    def _timers(self, dt: float) -> None:
        rate = RAGE_COOLDOWN if self.enraged else 1.0
        self.charge_wait -= dt * rate
        self.attack_wait -= dt * rate
        self.throw_wait -= dt * rate
        self._ground_for = max(0.0, self._ground_for - dt)
        was_enraged = self.rage_left > 0.0
        self.rage_left = max(0.0, self.rage_left - dt)
        if self.rage_left <= 0.0:
            if was_enraged and getattr(self, "legendary", False):
                self.damage = max(0, self.damage - 3)
            self.provoker = None
        self.fury = _approach(self.fury, 1.0 if self.enraged else 0.0, dt * 3.0)
        if self.turn_left > 0.0:
            self.turn_left = max(0.0, self.turn_left - dt)
        self._ignored = {s: t - dt for s, t in self._ignored.items() if t > dt}
        if self.action == "windup":
            self.paw += dt
        self._ease_pose(dt)

    def _ease_pose(self, dt: float) -> None:
        """Ease the gait and posture the renderer reads, so nothing pops between moves."""
        speed = abs(self.speed)
        walking = self.grounded and self.land_left <= 0.0
        moving = clamp(speed / (WALK_SPEED * 0.6), 0.0, 1.0) if walking else 0.0
        self.gait = _approach(self.gait, moving, dt * (4.0 if moving > self.gait else 2.5))
        if speed > 0.5:
            self.stride_way = 1 if self.speed * self.facing > 0.0 else -1
        galloping = clamp((speed - WALK_SPEED) / (CHARGE_SPEED * 0.5 - WALK_SPEED), 0.0, 1.0)
        self.gallop = _approach(self.gallop, galloping, dt * 4.0)
        planted = self.action in STANCES
        if planted:
            self.stance_kind = self.action  # type: ignore[assignment]
        self.stance = _approach(self.stance, 1.0 if planted else 0.0, dt / 0.16)
        climbing = self.on_wall or (self.haul is not None and self.haul.kind != "grab")
        self.slung = _approach(self.slung, 1.0 if climbing and not self.dead else 0.0, dt / 0.3)
        self.slide = _approach(self.slide, 1.0 if self.sliding and self.on_wall else 0.0, dt / 0.12)
        self._ease_lunge(dt)
        target = (*self._posture(), self._head_pitch())
        if self._pose is None:
            self._pose, self._pose_rate = target, (0.0, 0.0, 0.0)
            return
        # A critically damped spring: eases off as smoothly as it eases in.
        pose, rate = [], []
        for x, v, goal in zip(self._pose, self._pose_rate, target, strict=True):
            v += (POSE_SPRING**2 * (goal - x) - 2.0 * POSE_SPRING * v) * dt
            pose.append(x + v * dt)
            rate.append(v)
        self._pose, self._pose_rate = tuple(pose), tuple(rate)  # type: ignore[assignment]

    def _ease_lunge(self, dt: float) -> None:
        """Swing its body out for a swipe and back in, on the same spring as its pose."""
        goal = self._swipe_lunge_target()
        lunge, rate = self.lunge, self._lunge_rate
        if goal == ZERO and lunge.length() < 0.05 and rate.length() < 0.5:
            self.lunge, self._lunge_rate = ZERO, ZERO
            return
        rate = rate + ((goal - lunge) * POSE_SPRING**2 - rate * (2.0 * POSE_SPRING)) * dt
        self.lunge, self._lunge_rate = lunge + rate * dt, rate

    @property
    def pitch(self) -> float:
        """How far its head is bowed (radians, + horns forward), eased."""
        return self._pose[2] if self._pose is not None else self._head_pitch()

    def _head_pitch(self) -> float:
        """Head down (horns forward) for the charge, up for the roar of a stomp."""
        action, t = self.action, self.action_time
        if self.dead:
            return -0.2
        if self.on_wall or (self.haul is not None and self.haul.kind != "grab"):
            return -1.25
        if action == "windup":
            return 0.4 * smoothstep(min(1.0, t / 0.35))
        if action in ("charge", "skid"):
            return 0.4
        if action == "winded":
            return 0.35
        if action == "stomp":
            wind, strike, recover = STOMP_TIMES
            if t < wind:
                return -0.25
            if t < wind + strike + recover * 0.4:
                return 0.4
        if action == "smash":
            wind, strike, _ = SMASH_TIMES
            return 0.35 if t < wind else -0.15
        if action == "hurl":
            reach, hold, fling, _ = THROW_TIMES
            return -0.2 if t < reach + hold else 0.35
        return 0.05 + 0.15 * self.fury

    def cycle(self) -> float:
        """How far it travels in one full walk (or gallop) cycle."""
        return STRIDE * (1.0 + 0.6 * self.gallop)

    def struck(self, ranged: bool, attacker: object = None) -> None:
        """Hit (by `attacker`, if known): from range, it flies into a rage at him."""
        if not ranged or self.dead:
            return
        self.rage_left = RAGE_TIME
        shooter = attacker if attacker in self.world.stickmen else self._guess_shooter()
        if shooter is not None and shooter.prey:  # type: ignore[union-attr]
            self.provoker = shooter  # type: ignore[assignment]

    def _guess_shooter(self) -> Stickman | None:
        center = self.center()
        shooters = [
            s
            for s in self.world.stickmen
            if s.prey and s.foe is self and s.calling.reach > 2.0 * STAND_OFF
        ]
        return min(shooters, key=lambda s: s.center().distance_to(center), default=None)

    # ----- deciding what to do ---------------------------------------------------------

    def _think(self, dt: float) -> None:
        if self.surface is None:
            return
        foe = self._choose_foe(dt)
        if foe is None:
            self.foe = None
            self._wander(dt)
        else:
            if foe is not self.foe:
                self.foe, self._foe_since, self._foe_stuck = foe, self.time, 0.0
                self._aimed, self._replan_wait = None, 0.0
            self._fight(dt, foe)
            self._watch_stall(foe)
        if self.on_wall and not self.route and not self._braced():
            self._wall_idle += dt
            if self._wall_idle >= WALL_PATIENCE:
                self._give_up_wall()
        else:
            self._wall_idle = 0.0

    def _watch_stall(self, foe: Stickman) -> None:
        """Stuck going for him (a climb it can't make, a route that gets it nowhere):
        drop the route and count him out of reach for a while."""
        spot = self._stall_spot
        if self._prowling or self._flat_with(foe) or spot is None:
            self._stall_spot = (self.time, self.position)
            return
        if self.position.distance_to(spot[1]) > STALL_MOVE:
            self._stall_spot = (self.time, self.position)
        elif self.time - spot[0] >= STALL_TIME:
            self._reach[foe] = (self.time + STALL_FORGET, False)
            self.route, self._aimed, self._unreached = [], None, 0.0
            self._stall_spot = (self.time, self.position)

    def _choose_foe(self, dt: float = 0.0) -> Stickman | None:
        """The nearest free adventurer it can get at, kept for at least `FOE_COMMIT`
        unless another is much nearer; enraged, whoever shot it, if it can get at him."""
        center = self.center()
        prey = [s for s in self.world.stickmen if s.prey and s not in self._ignored]
        self._reach = {s: kept for s, kept in self._reach.items() if s in prey}
        if not prey:
            return None
        # Only those it can get at, if anyone: whoever's out of reach (up a wall it can't
        # climb, hanging under a window) is dropped, the current foe after a moment.
        reachable = [s for s in prey if self._reachable(s)]
        guards = priority_prey([
            s for s in reachable if getattr(s, "target_priority", 0)
        ])
        if guards:
            self._out_of_reach = 0.0
            return min(guards, key=lambda s: s.center().distance_to(center))
        current = self.foe
        if current in prey and current not in reachable and reachable:
            self._out_of_reach += dt
            if self._out_of_reach < OUT_OF_REACH:
                return current
        else:
            self._out_of_reach = 0.0
        if reachable:
            prey = reachable
        provoker = self.provoker
        if provoker is not None and provoker in prey:
            # An archer shooting from off this wall beats whoever it's punching there.
            if self.on_wall and self._off_this_wall(provoker):
                return provoker
            close = [s for s in prey if s.center().distance_to(center) < STAND_OFF + 10.0]
            if not close or provoker in close:
                return provoker
        nearest = min(prey, key=lambda s: s.center().distance_to(center))
        current = self.foe
        if current is None or current not in prey:
            return nearest
        held = current.center().distance_to(center)
        near = nearest.center().distance_to(center)
        settled = self.time - self._foe_since >= FOE_COMMIT
        if near < FOE_SWITCH * held and (settled or near < OVERLAP * 3.0):
            return nearest
        return current

    def _fight(self, dt: float, foe: Stickman) -> None:
        if self.on_wall:
            if self.attack_wait <= 0.0 and (self._try_punch(foe) or self._try_swipe(foe)):
                return
            if self._swipe_lands(foe) is not None:
                # In reach: hold on here for the next blow, rather than climb off.
                self.route, self._aimed = [], None
                self.climb_speed = _approach(self.climb_speed, 0.0, CLIMB_ACCEL * dt)
                return
            self._pursue(dt, foe)
            return
        here = foe.contact()
        flat = self._flat_with(foe)
        if flat and self.throw_wait <= 0.0 and not self.turning and self._try_throw():
            return
        if flat and not self.turning and self._try_charge(foe, dt):
            return
        if self.attack_wait <= 0.0 and not self.turning and self._try_attack(foe):
            return
        if flat:
            self._unreached = 0.0
            self._prowling = False
            self._stand_off(dt, here.x)
            return
        if self.grounded and not self._reachable(foe):
            self._unreached = 0.0
            self._prowl(dt, foe)
            return
        if self._prowling:
            self._prowling, self.route, self._aimed = False, [], None
        self._pursue(dt, foe)
        if self.route or not self.grounded:
            self._unreached = 0.0
            return
        # There, but he's up a wall or hanging under a window out of its reach.
        self._unreached += dt
        if self._unreached >= STAND_GIVE_UP:
            self._ignored[foe] = IGNORE_FOE
            self.foe, self._unreached = None, 0.0
        elif abs(self.speed) < 2.0 and abs(here.x - self.position.x) > OVERLAP:
            self._turn_to(_sign(here.x - self.position.x))

    def _flat_with(self, stickman: Stickman) -> bool:
        """He's on the same flat surface (the same window top or the floor) as it."""
        surface = self.surface
        if surface is None or not surface.walkable or stickman.follower.in_transition:
            return False
        if not stickman.follower.current_anchor().surface.walkable:
            return False
        at = stickman.contact()
        return (
            abs(at.y - surface.start.y) <= 3.0 and surface.low - 4.0 <= at.x <= surface.high + 4.0
        )

    def _stand_off(self, dt: float, x: float) -> None:
        """Close in to `STAND_OFF` from him on its side of him (backing off if it's on
        top of him), then turn to face him."""
        surface = self.surface
        assert surface is not None
        self.route = []
        offset = x - self.position.x
        side = self.facing if abs(offset) < OVERLAP else _sign(offset)
        low, high = surface.low + 2.0, surface.high - 2.0
        spot = clamp(x - side * STAND_OFF, low, high)
        if abs(spot - x) < OVERLAP + 4.0:
            spot = clamp(x + side * STAND_OFF, low, high)
        if abs(spot - self.position.x) > 3.0:
            self._walk_to(spot, dt, backstep=STAND_OFF + OVERLAP + 4.0)
            return
        self._brake(dt)
        if side != self.facing and abs(self.speed) < 2.0:
            self._turn_to(side)

    def _pursue(self, dt: float, foe: Stickman) -> None:
        """Route over to him (replanning as he moves, `REPLAN_EVERY` at most)."""
        self._replan_wait -= dt
        idle = not self.route
        can_plan = (self.grounded and not self.turning) or (self.on_wall and idle)
        if can_plan and self._replan_wait <= 0.0:
            self._replan_wait = REPLAN_EVERY
            goal = self._closing_on(foe)
            aimed = self._aimed
            if goal is not None and (
                idle or aimed is None or goal.point.distance_to(aimed) > FOE_SHIFT
            ):
                if self._route_to(goal):
                    self._aimed, self._foe_stuck = goal.point, 0.0
                else:
                    self._foe_stuck += REPLAN_EVERY
                    if self._foe_stuck >= GIVE_UP:
                        self._ignored[foe] = IGNORE_FOE
                        self.foe = None
        self._follow(dt)

    def _braced(self) -> bool:
        """On a wall where a punch or a swipe would actually land, so it keeps its grip."""
        foe = self.foe
        return (
            foe is not None
            and self.on_wall
            and (self._punch_lands(foe) or self._swipe_lands(foe) is not None)
        )

    def _off_this_wall(self, foe: Stickman) -> bool:
        """He's not clinging to the wall it is on."""
        surface = self.surface
        if surface is None:
            return True
        theirs = foe.follower.current_anchor().surface
        same = theirs.wall and theirs.box == surface.box
        return not (same and abs(theirs.start.x - surface.start.x) <= 2.0)

    def _give_up_wall(self) -> None:
        """Let go and fight on the ground: this wall isn't getting it a punch."""
        self._wall_whiff = 0
        self._wall_idle = 0.0
        self._ground_for = GROUND_HUNT
        self._loose()

    def _reachable(self, foe: Stickman) -> bool:
        """Whether it has a way to land a blow on him (kept for `REACH_CHECK`)."""
        kept = self._reach.get(foe)
        if kept is not None and self.time < kept[0]:
            return kept[1]
        verdict = self._can_reach(foe)
        self._reach[foe] = (self.time + REACH_CHECK, verdict)
        return verdict

    def _can_reach(self, foe: Stickman) -> bool:
        """He's on a floor or window top it has a way to (or between surfaces), or it can climb
        to a spot on his wall a punch reaches him from, or he's low enough on a wall for a
        blow from the ground below him."""
        follower = foe.follower
        if follower.in_transition:
            return True
        theirs = follower.current_anchor().surface
        if theirs.walkable:
            return self._flat_with(foe) or self._route_exists(
                Anchor(theirs, theirs.closest_point(foe.contact()))
            )
        if self.on_wall and (self._punch_lands(foe) or self._swipe_lands(foe) is not None):
            return True
        if self._ground_for <= 0.0:
            if self._strike_spot(foe) is not None:
                return True
            wall = self._wall_spot(foe)
            if wall is not None and self._route_exists(wall):
                return True
        ground = self._ground_near(foe.contact())
        if ground is None:
            return False
        chest = foe.center()
        return (
            abs(ground.point.x - chest.x) <= STAND_OFF + OVERLAP
            and ground.point.y - chest.y <= LOW_REACH
        )

    def _prowl(self, dt: float, foe: Stickman) -> None:
        """He's out of its reach: pace to and fro out of his line, pausing to glare up at
        him, rather than stand under him taking arrows."""
        surface = self.surface
        assert surface is not None
        if not self._prowling:
            self._prowling, self.route, self._aimed = True, [], None
            self._prowl_to, self._prowl_rest = None, 0.0
        if self.route:
            self._follow(dt)
            return
        if not surface.walkable:
            self._wander(dt)
            return
        here = foe.center().x
        if self._prowl_to is None:
            if self._prowl_rest > 0.0:
                self._prowl_rest -= dt
                self._brake(dt)
                way = _sign(here - self.position.x, self.facing)
                if (
                    way != self.facing
                    and abs(self.speed) < 2.0
                    and abs(here - self.position.x) > OVERLAP
                ):
                    self._turn_to(way)
                return
            low, high = surface.low + 10.0, surface.high - 10.0
            spots = [clamp(here - PROWL, low, high), clamp(here + PROWL, low, high)]
            spots = [x for x in spots if abs(x - self.position.x) > 30.0]
            if not spots:
                self.rest = 0.0
                self._wander(dt)
                return
            self._prowl_to = max(
                spots, key=lambda x: abs(x - here) - 0.3 * abs(x - self.position.x)
            )
        if self._walk_to(self._prowl_to, dt):
            self._prowl_to = None
            self._prowl_rest = self.world.random.uniform(*PROWL_REST)

    def _closing_on(self, foe: Stickman) -> Anchor | None:
        """Where to go for `foe`: off the floor, the quickest spot on a wall (his, or one
        facing it, maybe the one it's on) a swipe from there reaches him; or up the wall
        he's clinging to, when a punch from there can reach him and it can get there;
        otherwise the nearest walkable spot level with or below him."""
        ground = self._ground_near(foe.contact())
        if self._ground_for > 0.0:
            return ground
        spot = self._strike_spot(foe)
        if spot is not None:
            return spot
        wall = self._wall_spot(foe)
        if wall is not None and self._route_exists(wall):
            return wall
        return ground

    def _route_exists(self, goal: Anchor) -> bool:
        surface = self.surface
        if surface is None:
            return False
        return self.planner.plan(Anchor(surface, self.position), goal) is not None

    def _strike_spot(self, foe: Stickman) -> Anchor | None:
        """He's off the floor (up a wall, under a window): the spot on a wall it can get to
        soonest that a swipe reaches him from. Where it clings now, if that will do;
        otherwise shoulder level with him on a wall near enough."""
        surface = self.surface
        if surface is None or foe.follower.current_anchor().surface.walkable:
            return None
        if self.on_wall and self._swipe_lands(foe) is not None:
            return Anchor(surface, self.position)
        chest = foe.center()
        reach = self.planner.reachable(surface)
        start = Anchor(surface, self.position)
        far = LUNGE_OUT + SWIPE_ARM + SWIPE_HIT + WALL_GAP + 12.0
        best, best_time = None, math.inf
        for wall in self.planner.surfaces:
            if not wall.wall or wall.id not in reach or abs(wall.start.x - chest.x) > far:
                continue
            feet = wall.point_at(clamp(chest.y - SWIPE_SHOULDER.y, wall.low, wall.high))
            root = feet - Vec2(wall.facing * WALL_GAP, 0.0)
            if self._swipe_from(root, wall.facing, foe) is None:
                continue
            spot = Anchor(wall, feet)
            route = self.planner.plan(start, spot)
            if route is not None and route.duration < best_time:
                best, best_time = spot, route.duration
        return best

    def _wall_spot(self, foe: Stickman) -> Anchor | None:
        """Feet on the wall he's climbing, shoulder lined up with his chest."""
        theirs = foe.follower.current_anchor().surface
        if not theirs.wall:
            return None
        chest = foe.center()
        walls = [
            s
            for s in self.planner.surfaces
            if s.wall
            and s.kind is theirs.kind
            and s.box == theirs.box
            and abs(s.start.x - theirs.start.x) <= 2.0
        ]
        if not walls:
            return None

        def gap(surface: Surface) -> float:
            if surface.low <= chest.y <= surface.high:
                return 0.0
            return min(abs(chest.y - surface.low), abs(chest.y - surface.high))

        wall = min(walls, key=gap)
        feet = chest.y - PUNCH_SHOULDER.y
        if wall.low <= feet <= wall.high:
            return Anchor(wall, wall.point_at(feet))
        reach = ARM_REACH + PUNCH_HIT
        beside = abs(wall.start.x - chest.x) <= 36.0
        for end in (wall.low, wall.high):
            shoulder_y = end + PUNCH_SHOULDER.y
            if beside and abs(shoulder_y - chest.y) <= reach:
                return Anchor(wall, wall.point_at(end))
        return None

    def _ground_near(self, point: Vec2) -> Anchor | None:
        """The nearest spot it could walk to level with or below `point` (so not the
        top of the window he's clinging to the side of), else the nearest at all."""
        best, best_distance = None, math.inf
        for surface in self.planner.surfaces:
            if not surface.walkable or surface.start.y < point.y - 8.0:
                continue
            closest = surface.closest_point(point)
            distance = closest.distance_to(point)
            if distance < best_distance:
                best, best_distance = Anchor(surface, closest), distance
        return best or self.planner.anchor_near(point, walk_only=True)

    def _route_to(self, goal: Anchor) -> bool:
        surface = self.surface
        if surface is None:
            return False
        route = self.planner.plan(Anchor(surface, self.position), goal)
        if route is None:
            return False
        self.route = list(route.steps)
        self.goal = goal.point
        return True

    def _wander(self, dt: float) -> None:
        if self.route:
            self._follow(dt)
            return
        self._brake(dt)
        self.rest -= dt
        if self.rest > 0.0 and not self.on_wall:
            return
        rng = self.world.random
        self.rest = rng.uniform(*REST_TIME)
        surface = self.surface
        assert surface is not None
        reachable = self.planner.reachable(surface)
        walks = [s for s in self.planner.surfaces if s.walkable and s.id in reachable]
        if not walks:
            return
        target = rng.choices(walks, weights=[s.length for s in walks])[0]
        point = target.point_at(rng.uniform(target.low, target.high))
        self._route_to(Anchor(target, point))

    # ----- the charge -------------------------------------------------------------------

    def _try_charge(self, foe: Stickman, dt: float) -> bool:
        if self.charge_wait > 0.0 or abs(self.speed) > WALK_SPEED * self.pace + 1.0:
            return False
        stop = self._charge_lane(foe)
        if stop is None:
            return False
        way = _sign(foe.contact().x - self.position.x)
        if way != self.facing:
            self._brake(dt)
            if abs(self.speed) < 2.0:
                self._turn_to(way)
            return True
        self.route = []
        self.charge_stop = stop
        self._start("windup")
        return True

    def _charge_lane(self, foe: Stickman) -> float | None:
        """Where a charge at `foe` would stop, if it's worth one: he's `CHARGE_MIN` to
        `CHARGE_MAX` along its surface (`CHARGE_SOLO` alone)."""
        surface = self.surface
        assert surface is not None
        x = self.position.x
        target = foe.contact().x
        distance = abs(target - x)
        if not CHARGE_MIN <= distance <= CHARGE_MAX:
            return None
        way = _sign(target - x)
        end = surface.high - CHARGE_EDGE if way > 0 else surface.low + CHARGE_EDGE
        if (end - x) * way < distance - TRAMPLE_FRONT:
            return None
        stop = self._charge_stop(target, way, end)
        if distance < CHARGE_SOLO and self._in_lane(x, stop) < 2:
            return None
        return stop

    def _in_lane(self, start: float, stop: float) -> int:
        low, high = min(start, stop) - TRAMPLE_BACK, max(start, stop) + TRAMPLE_FRONT
        return sum(1 for s in self.world.stickmen if s.prey and self._on_lane(s, low, high))

    def _on_lane(self, stickman: Stickman, low: float, high: float) -> bool:
        at = stickman.contact()
        return abs(at.y - self.position.y) <= LANE_HEIGHT and low <= at.x <= high

    def _start(self, action: str) -> None:
        self.action, self.action_time = action, 0.0
        if action == "windup":
            self.paw = 0.0
        self._struck = set()
        self._shocked = False
        self._unreached = 0.0
        self._stall_spot = None

    def _act(self, dt: float) -> None:
        self.action_time += dt
        action, t = self.action, self.action_time
        if action == "crouch":
            if t >= JUMP_CROUCH / self.pace:
                step, self._pending = self._pending, None
                self.action = None
                if step is not None:
                    self._launch(step, "jump")
        elif action == "windup":
            self._brake(dt)
            if t >= CHARGE_WINDUP / self.pace:
                self._aim_charge()
                self._start("charge")
                self.trampled = 0
            elif int((t - dt) / 0.22) != int(t / 0.22):
                self._dust(self.to_world(Vec2(10.0, 0.0)), -self.facing, 1, 0.35)
        elif action in ("charge", "skid"):
            self._charge(dt)
        elif action == "winded":
            self._brake(dt)
            if t >= WINDED_TIME:
                self.action = None
                self.charge_wait = CHARGE_COOLDOWN
        elif action == "stomp":
            self._brake(dt)
            self._stomp(dt)
        elif action == "smash":
            self._brake(dt)
            self._smash(dt)
        elif action == "hurl":
            self._brake(dt)
            self._hurl(dt)
        elif action == "punch":
            self.climb_speed = _approach(self.climb_speed, 0.0, CLIMB_ACCEL * dt)
            self._punch(dt)
        elif action == "swipe":
            self.climb_speed = _approach(self.climb_speed, 0.0, CLIMB_ACCEL * dt)
            self._swipe(dt)

    def _aim_charge(self) -> None:
        """Last look before it goes: aim past its foe if he's still ahead of it."""
        foe = self.foe
        if foe is None or not foe.prey or not self._flat_with(foe):
            return
        surface = self.surface
        assert surface is not None
        x, way = self.position.x, self.facing
        target = foe.contact().x
        if (target - x) * way < CHARGE_MIN * 0.5:
            return
        end = surface.high - CHARGE_EDGE if way > 0 else surface.low + CHARGE_EDGE
        self.charge_stop = self._charge_stop(target, way, end)

    def _charge_stop(self, target: float, way: int, end: float) -> float:
        """`CHARGE_PAST` beyond `target`, or beyond anyone bunched up just past him
        (within `CHARGE_MAX` of it), but short of `end`."""
        x = self.position.x
        ahead = sorted(
            (s.contact().x - x) * way
            for s in self.world.stickmen
            if s.prey and self._on_lane(s, -math.inf, math.inf)
        )
        run = (target - x) * way + CHARGE_PAST
        for along in ahead:
            if along > CHARGE_MAX or along > run - CHARGE_PAST + CHARGE_GROUP:
                break
            run = max(run, along + CHARGE_PAST)
        stop = x + way * run
        return min(stop, end) if way > 0 else max(stop, end)

    def _charge(self, dt: float) -> None:
        surface = self.surface
        if surface is None or not surface.walkable:
            self.action = None
            return
        way = self.facing
        end = surface.high - CHARGE_EDGE if way > 0 else surface.low + CHARGE_EDGE
        stop = min(self.charge_stop, end) if way > 0 else max(self.charge_stop, end)
        remaining = (stop - self.position.x) * way
        speed = abs(self.speed)
        top = CHARGE_SPEED * self.pace
        if self.action == "charge" and remaining <= speed * speed / (2.0 * CHARGE_SKID) + 1.0:
            self.action, self.action_time = "skid", 0.0
        if self.action == "skid":
            speed = max(0.0, speed - CHARGE_SKID * dt)
            if int((self.action_time - dt) / 0.07) != int(self.action_time / 0.07):
                self._dust(self.position, way, 1, 0.45)
        else:
            speed = min(top, speed + CHARGE_ACCEL * dt)
        before = self.phase
        step = min(speed * dt, max(0.0, remaining))
        self.position = Vec2(self.position.x + way * step, surface.start.y)
        self.speed = way * speed
        self.phase += step / self.cycle()
        if int(before * 2.0) != int(self.phase * 2.0) and self.action == "charge":
            self._dust(self.position, -way, 1, 0.4)
        self._trample()
        if remaining - step <= 0.5 or (self.action == "skid" and speed <= 1.0):
            self.speed = 0.0
            self._start("winded")

    def _trample(self) -> None:
        way = self.facing
        x = self.position.x
        low, high = sorted((x - way * TRAMPLE_BACK, x + way * TRAMPLE_FRONT))
        horns = self.to_world(self.local(HORNS))
        chest = self.center()
        for stickman in self.world.stickmen:
            if not stickman.prey or stickman in self._struck:
                continue
            if not (
                self._on_lane(stickman, low, high)
                or stickman.hits(horns, 3.0)
                or stickman.hits(chest, 6.0)
            ):
                continue
            self._struck.add(stickman)
            self.trampled += 1
            body = stickman.center()
            push = Vec2(way * TRAMPLE_FLING, -TRAMPLE_FLING * 0.5)
            death = "Gored and trampled by the minotaur!"
            if stickman.hurt_from(self, TRAMPLE_DAMAGE, body, push, "minotaur", death):
                self.kills["charge"] += 1
            elif stickman.animated:
                stickman.knock_down(
                    body - Vec2(way * 12.0, -4.0), TRAMPLE_FLING, TRAMPLE_DOWN, TRAMPLE_STUN
                )

    # ----- the fist and the stomp -----------------------------------------------------

    def _try_attack(self, foe: Stickman) -> bool:
        """A stomp if he's close enough to come down on, otherwise a ground smash."""
        if self.surface is None or not self.surface.walkable:
            return False
        ahead = (foe.contact().x - self.position.x) * self.facing
        if ahead < -2.0:
            return False
        if ahead <= STOMP_CLOSE and self._try_stomp(foe):
            return True
        return self._try_smash(foe)

    def _try_punch(self, foe: Stickman) -> bool:
        """A fist, up a wall, if it would reach him."""
        if not self._punch_lands(foe):
            return False
        self._punch_at = self._punch_aim(foe)
        self.route = []
        self._start("punch")
        return True

    def _punch_lands(self, foe: Stickman) -> bool:
        """Whether a punch from where it stands would reach him, without starting one."""
        if self.on_wall:
            spot = self._wall_spot(foe)
            if (
                spot is None
                or self.surface is None
                or spot.surface.id != self.surface.id
                or abs(spot.point.y - self.position.y) > 18.0
            ):
                return False
        elif not self.grounded:
            return False
        saved = self._punch_at
        self._punch_at = self._punch_aim(foe)
        wind, strike, _ = PUNCH_TIMES
        hit = any(
            foe.hits(self.to_world(self.fist(wind + strike * i / 4)), PUNCH_HIT) for i in range(5)
        )
        self._punch_at = saved
        return hit

    def _punch_aim(self, foe: Stickman) -> Vec2:
        """The fist at his chest, pulled in to an arm's length of the shoulder."""
        root = self.root()
        center = foe.center()
        shoulder = PUNCH_SHOULDER if self.on_wall else GUARD_SHOULDER
        reach = ARM_REACH if self.on_wall else GROUND_REACH
        aim = Vec2((center.x - root.x) * self.facing, center.y - root.y)
        offset = aim - shoulder
        distance = offset.length()
        if distance > reach:
            aim = shoulder + offset * (reach / max(distance, 1e-3))
        return aim

    def fist(self, t: float | None = None) -> Vec2:
        """The punching fist in its own frame, `t` seconds into the punch."""
        if t is None:
            t = self.action_time
        wind, strike, recover = PUNCH_TIMES
        aim = self._punch_at if self._punch_at is not None else GUARD_NEAR
        chamber, cocked = Vec2(-6.0, -38.0), Vec2(2.0, -52.0)
        if t < wind:
            return chamber.lerp(cocked, smoothstep(t / max(wind, 1e-3)))
        if t < wind + strike:
            return cocked.lerp(aim, ((t - wind) / strike) ** 2)
        back = smoothstep(clamp((t - wind - strike) / recover, 0.0, 1.0))
        rest = Vec2(WALL_GAP + 1.0, -64.0) if self.on_wall else GUARD_NEAR
        return aim.lerp(rest, back)

    def _punch(self, dt: float) -> None:
        wind, strike, recover = PUNCH_TIMES
        t = self.action_time
        start, end = max(t - dt, wind), min(t, wind + strike)
        if end > start:
            for i in range(1, 4):
                self._jab(start + (end - start) * i / 3)
        if t >= wind + strike + recover:
            missed = self.on_wall and not self._struck
            self.action = None
            self.attack_wait = PUNCH_COOLDOWN
            if missed:
                self._wall_whiff += 1
                if self._wall_whiff >= WALL_WHIFFS:
                    self._give_up_wall()
            else:
                self._wall_whiff = 0

    def _jab(self, t: float) -> None:
        fist = self.to_world(self.fist(t))
        for stickman in self.world.stickmen:
            if not stickman.prey or stickman in self._struck:
                continue
            if not stickman.hits(fist, PUNCH_HIT):
                continue
            self._struck.add(stickman)
            if self.on_wall:
                push = Vec2(-self.facing * PUNCH_PUSH, -90.0)
                death = "Punched off the wall by the minotaur!"
            else:
                push = Vec2(self.facing * PUNCH_PUSH, -PUNCH_PUSH * 0.35)
                death = "Laid out by the minotaur's fist!"
            if stickman.hurt_from(self, PUNCH_DAMAGE, fist, push, "minotaur", death):
                self.kills["punch"] += 1

    # ----- the swipe off a wall ---------------------------------------------------------

    def _try_swipe(self, foe: Stickman) -> bool:
        """Up a wall, a swipe at him wherever he is in reach: across a gap on the facing
        wall, above or below on this one."""
        plan = self._swipe_lands(foe)
        if plan is None:
            return False
        self.route = []
        self._start("swipe")
        self._swipe_live, self._swipe_back = True, None
        self._set_swipe(*plan)
        return True

    def _swipe_lands(self, foe: Stickman) -> tuple[Vec2, Vec2] | None:
        """The lunge and aim of a swipe from where it clings that would land on him."""
        if not self.on_wall:
            return None
        return self._swipe_from(self._wall_root(self.position), self.facing, foe)

    def _wall_root(self, feet: Vec2) -> Vec2:
        """Its body's root clinging to a wall with its feet at `feet`, not swung out."""
        return feet - Vec2(self.facing * WALL_GAP, 0.0)

    def _swipe_from(self, root: Vec2, facing: int, foe: Stickman) -> tuple[Vec2, Vec2] | None:
        """Hanging on a wall facing `facing` with its body at `root`: how far it would swing
        out and where it would aim to reach him, if the fist would land."""
        chest = foe.center()
        target = Vec2((chest.x - root.x) * facing, chest.y - root.y)
        offset = target - SWIPE_SHOULDER
        distance = offset.length()
        if distance > LUNGE_OUT + LUNGE_ALONG + SWIPE_ARM + SWIPE_HIT:
            return None
        lunge = offset * (max(0.0, distance - SWIPE_ARM) / max(distance, 1e-3))
        lunge = Vec2(clamp(lunge.x, -LUNGE_OUT, 4.0), clamp(lunge.y, -LUNGE_ALONG, LUNGE_ALONG))
        offset = target - lunge - SWIPE_SHOULDER
        distance = offset.length()
        if distance > SWIPE_ARM:
            offset = offset * (SWIPE_ARM / distance)
        aim = SWIPE_SHOULDER + offset

        def world(local: Vec2) -> Vec2:
            return Vec2(root.x + (lunge.x + local.x) * facing, root.y + lunge.y + local.y)

        if not self._clear_between(world(SWIPE_SHOULDER), chest):
            return None
        cocked = self._cocked(aim)
        for i in range(5):
            fist = cocked.lerp(aim, (i / 4) ** 2)
            if foe.hits(world(fist), SWIPE_HIT):
                return lunge, aim
        return None

    def _clear_between(self, a: Vec2, b: Vec2) -> bool:
        """No window in the way of a blow from `a` to `b` (its own end may be in one: in a
        narrow slot its bulk clips into the window beside)."""
        boxes = [box for box in self.world.boxes if not box.contains(a)]
        for i in range(2, 9):
            point = a.lerp(b, i / 10)
            if any(box.contains(point) for box in boxes):
                return False
        return True

    @staticmethod
    def _cocked(aim: Vec2) -> Vec2:
        """The free fist raised over its head, drawn back from the way it's about to lash
        out (so the swipe comes down at him)."""
        back = (SWIPE_SHOULDER - aim).normalized()
        return SWIPE_SHOULDER + back * 6.0 + Vec2(0.0, -20.0)

    def _set_swipe(self, lunge: Vec2, aim: Vec2) -> None:
        """Aim the swipe, and take hold of the wall with the other hand where it reaches
        from the swung-out body."""
        self._swipe_lunge, self._swipe_at = lunge, aim
        wall = WALL_GAP + 0.5 - lunge.x
        across = wall - GRIP_SHOULDER.x
        up = math.sqrt(max(0.0, GRIP_ARM * GRIP_ARM - across * across)) * 0.6
        grip = Vec2(wall, GRIP_SHOULDER.y - up)
        root = self._wall_root(self.position)
        self._swipe_grip = Vec2(
            root.x + (lunge.x + grip.x) * self.facing, root.y + lunge.y + grip.y
        )

    def swipe_fist(self, t: float | None = None) -> Vec2:
        """The free fist in its own frame (of its swung-out body), `t` seconds into the
        swipe."""
        if t is None:
            t = self.action_time
        wind, strike, recover = SWIPE_TIMES
        hold, aim = SWIPE_HOLD[0], self._swipe_at
        cocked = self._cocked(aim)
        if t < wind:
            return hold.lerp(cocked, smoothstep(t / wind))
        if t < wind + strike:
            return cocked.lerp(aim, ((t - wind) / strike) ** 2)
        back = self._swipe_back if self._swipe_back is not None else aim
        return back.lerp(hold, smoothstep(clamp((t - wind - strike) / recover, 0.0, 1.0)))

    def swipe_grip(self) -> Vec2:
        """The hand holding on to the wall through the swipe, in its own frame."""
        root = self.root()
        grip = self._swipe_grip
        return Vec2((grip.x - root.x) * self.facing, grip.y - root.y)

    def swipe_hold(self) -> float:
        """0..1: how far its hands have gone over from climbing to the swipe."""
        if self.action != "swipe":
            return 0.0
        blend = SWIPE_HOLD[1]
        left = sum(SWIPE_TIMES) - self.action_time
        return smoothstep(clamp(min(self.action_time, left) / blend, 0.0, 1.0))

    def _swipe_lunge_target(self) -> Vec2:
        """Where its body is swinging to (world offset): out for the swipe, then back in."""
        if self.action != "swipe" or not self._swipe_live or not self.on_wall:
            return ZERO
        wind, strike, recover = SWIPE_TIMES
        if self.action_time >= wind + strike + recover * 0.25:
            return ZERO
        lunge = self._swipe_lunge
        return Vec2(lunge.x * self.facing, lunge.y)

    def _swipe(self, dt: float) -> None:
        wind, strike, recover = SWIPE_TIMES
        t = self.action_time
        foe = self.foe
        if not self.on_wall:
            self.action = None
            return
        if self._swipe_live and t < wind:
            # Follow him as it winds up; called off (never thrown at air) if he gets away.
            plan = self._swipe_lands(foe) if foe is not None and foe.prey else None
            if plan is not None:
                self._set_swipe(*plan)
            else:
                self._swipe_back = self.swipe_fist(t)
                self._swipe_live = False
                self.action_time = t = wind + strike
        if self._swipe_live:
            start, end = max(t - dt, wind), min(t, wind + strike)
            if end > start:
                for i in range(1, 4):
                    self._lash(start + (end - start) * i / 3)
        if t >= wind + strike + recover:
            self.action = None
            self.attack_wait = SWIPE_COOLDOWN
            if self._swipe_live and not self._struck:
                self._wall_whiff += 1
                if self._wall_whiff >= WALL_WHIFFS:
                    self._give_up_wall()
            elif self._struck:
                self._wall_whiff = 0

    def _lash(self, t: float) -> None:
        fist = self.to_world(self.swipe_fist(t))
        shoulder = self.to_world(SWIPE_SHOULDER)
        for stickman in self.world.stickmen:
            if not stickman.prey or stickman in self._struck:
                continue
            if not stickman.hits(fist, SWIPE_HIT):
                continue
            self._struck.add(stickman)
            way = (fist - shoulder).normalized()
            push = way * SWIPE_PUSH + Vec2(0.0, -60.0)
            death = "Swatted off the wall by the minotaur!"
            if stickman.hurt_from(self, SWIPE_DAMAGE, fist, push, "minotaur", death):
                self.kills["swipe"] += 1

    def _try_smash(self, foe: Stickman) -> bool:
        """Both fists into the ground, if they'd come down on him."""
        if not self.grounded or self.on_wall:
            return False
        ahead = (foe.contact().x - self.position.x) * self.facing
        self._smash_x = clamp(ahead, 16.0, SMASH_X)
        wind, strike, _ = SMASH_TIMES
        for i in range(5):
            hands = self.smash_hands(wind + strike * i / 4)
            ground = Vec2(self.to_world(hands[0]).x, self.position.y)
            if any(foe.hits(self.to_world(hand), SMASH_HIT) for hand in hands) or foe.hits(
                ground, SMASH_HIT
            ):
                self.route = []
                self._start("smash")
                return True
        return False

    def smash_hands(self, t: float | None = None) -> tuple[Vec2, Vec2]:
        """Both fists in its own frame, `t` seconds into the ground smash."""
        if t is None:
            t = self.action_time
        wind, strike, recover = SMASH_TIMES
        land = self._smash_x
        raised = (Vec2(-4.0, -68.0), Vec2(2.0, -70.0))
        slammed = (Vec2(land, -2.0), Vec2(land - 7.0, -3.0))
        far_rest = Vec2(-10.0, -32.0)
        if t < wind:
            u = smoothstep(t / max(wind, 1e-3))
            return GUARD_NEAR.lerp(raised[0], u), far_rest.lerp(raised[1], u)
        if t < wind + strike:
            u = ((t - wind) / strike) ** 2
            return raised[0].lerp(slammed[0], u), raised[1].lerp(slammed[1], u)
        u = smoothstep(clamp((t - wind - strike) / recover, 0.0, 1.0))
        return slammed[0].lerp(GUARD_NEAR, u), slammed[1].lerp(far_rest, u)

    def _smash(self, dt: float) -> None:
        wind, strike, recover = SMASH_TIMES
        t = self.action_time
        start, end = max(t - dt, wind), min(t, wind + strike)
        if end > start:
            for i in range(1, 4):
                self._slam(start + (end - start) * i / 3)
        if not self._shocked and t >= wind + strike:
            self._shocked = True
            point = self.to_world(Vec2(self._smash_x, 0.0))
            self.world.debris.burst(
                point, Vec2(0.0, -1.0), 6, 120.0, ring_radius=8.0, cracks=3, puffs=2, scale=0.5
            )
            self._dust(point, 1, 2, 0.45)
            self._dust(point, -1, 2, 0.45)
        if t >= wind + strike + recover:
            self.action = None
            self.attack_wait = SMASH_COOLDOWN

    def _slam(self, t: float) -> None:
        hands = [self.to_world(hand) for hand in self.smash_hands(t)]
        ground = Vec2(hands[0].x, self.position.y)
        for stickman in self.world.stickmen:
            if not stickman.prey or stickman in self._struck:
                continue
            if not any(stickman.hits(hand, SMASH_HIT) for hand in hands) and not stickman.hits(
                ground, SMASH_HIT
            ):
                continue
            self._struck.add(stickman)
            push = Vec2(self.facing * SMASH_PUSH, 30.0)
            death = "Smashed into the ground by the minotaur!"
            if stickman.hurt_from(self, SMASH_DAMAGE, ground, push, "minotaur", death):
                self.kills["smash"] += 1
            elif stickman.animated:
                stickman.knock_down(ground, SMASH_PUSH * 0.6, 0.7, 0.3)

    def _try_throw(self) -> bool:
        """Grab someone in reach and hurl him at a foe farther off."""
        if self.throw_wait > 0.0 or not self.grounded or self.on_wall:
            return False
        if self.surface is None or not self.surface.walkable:
            return False
        victim = self._grab_victim()
        target = self._throw_target(victim) if victim is not None else None
        if victim is None or target is None:
            return False
        self._caught = victim
        self._hurl_at = target
        victim.paralyze(sum(THROW_TIMES) + 1.2)
        self.route = []
        self._start("hurl")
        self.throw_wait = THROW_COOLDOWN
        return True

    def _ahead(self, stickman: Stickman) -> float:
        return (stickman.contact().x - self.position.x) * self.facing

    def _grab_victim(self) -> Stickman | None:
        near = [
            man
            for man in self.world.stickmen
            if man.prey
            and -6.0 <= self._ahead(man) <= GRAB_REACH
            and abs(man.contact().y - self.position.y) <= 14.0
        ]
        if not near:
            return None
        return min(near, key=lambda man: abs(self._ahead(man)))

    def _throw_target(self, victim: Stickman) -> Stickman | None:
        if getattr(self, "legendary", False):
            far = [man for man in self.world.stickmen if man.prey and man is not victim]
        else:
            far = [
                man
                for man in self.world.stickmen
                if man.prey
                and man is not victim
                and THROW_MIN <= self._ahead(man) <= THROW_MAX
                and abs(man.contact().y - self.position.y) <= 80.0
            ]
        if not far:
            return None
        foe = self.foe
        if foe in far:
            return foe
        if getattr(self, "legendary", False):
            return min(far, key=lambda man: abs(self._ahead(man)))
        return min(far, key=self._ahead)

    def grip(self, t: float | None = None) -> Vec2:
        """The fist holding someone, in its own frame, `t` seconds into the hurl."""
        if t is None:
            t = self.action_time
        reach, hold, fling, recover = THROW_TIMES
        scooped, cocked, follow = Vec2(18.0, -24.0), Vec2(-8.0, -58.0), Vec2(32.0, -34.0)
        if t < reach:
            return scooped.lerp(Vec2(12.0, -36.0), smoothstep(t / max(reach, 1e-3)))
        if t < reach + hold:
            return Vec2(12.0, -36.0).lerp(cocked, smoothstep((t - reach) / max(hold, 1e-3)))
        if t < reach + hold + fling:
            return cocked.lerp(follow, ((t - reach - hold) / fling) ** 2)
        back = smoothstep(clamp((t - reach - hold - fling) / recover, 0.0, 1.0))
        return follow.lerp(GUARD_NEAR, back)

    def _hurl(self, dt: float) -> None:
        reach, hold, fling, recover = THROW_TIMES
        t = self.action_time
        caught = self._caught
        if caught is not None and not caught.animated:
            self._caught = caught = None
        if caught is not None and t < reach + hold:
            self._pin(caught, self.to_world(self.grip(t)))
        if self._thrown is None and caught is not None and t >= reach + hold:
            self._release_throw(caught)
        if t >= reach + hold + fling + recover:
            self.action = None

    def _pin(self, man: Stickman, point: Vec2) -> None:
        """Hold `man` so his chest sits at `point`. His ragdoll comes along too, or he'd
        drop back where he was grabbed the moment he goes limp."""
        if not man.animated:
            return
        man.locomotion.shift(point - man.center())
        man.ragdoll.drive(man.locomotion.pose, self.world.step, snap=True)

    def _release_throw(self, man: Stickman) -> None:
        origin = man.center()
        target = self._hurl_at
        aim = (
            target.center()
            if target is not None and target.prey
            else origin + Vec2(self.facing * 160.0, -30.0)
        )
        velocity = lob_velocity(
            origin, aim, ZERO, self.world.boxes, self.world.floor_y, HURL_GRAVITY, pace=0.55
        )
        ground = self.world.floor_y if getattr(self, "legendary", False) else self.position.y
        self._thrown = Thrown(man, origin, velocity, ground)
        self._caught = None
        man.paralyze(1.6)

    def _fly_thrown(self, dt: float) -> None:
        thrown = self._thrown
        if thrown is None:
            return
        man = thrown.victim
        if not man.animated:
            self._thrown = None
            return
        age = thrown.age
        thrown.age += dt
        legendary = getattr(self, "legendary", False)
        steps = 4
        for i in range(1, steps + 1):
            t = age + (thrown.age - age) * i / steps
            point = thrown.origin + thrown.velocity * t + Vec2(0.0, 0.5 * HURL_GRAVITY * t * t)
            self._pin(man, point)
            if self._thrown_hits(man, point, thrown):
                return
            # Labyrinth King throws sail through windows and ledges; only the floor stops them.
            hit_ground = point.y >= thrown.ground_y - 2.0
            hit_box = (not legendary) and any(
                box.contains(point) for box in self.world.boxes
            )
            if hit_ground or hit_box:
                self._drop_thrown(man, thrown.velocity + Vec2(0.0, HURL_GRAVITY * t))
                return
        if thrown.age > (2.4 if legendary else 1.5):
            velocity = thrown.velocity + Vec2(0.0, HURL_GRAVITY * thrown.age)
            self._drop_thrown(man, velocity)

    def _thrown_hits(self, man: Stickman, point: Vec2, thrown: Thrown) -> bool:
        for other in self.world.stickmen:
            if other is man or not other.prey:
                continue
            if not other.hits(point, THROW_HIT):
                continue
            velocity = thrown.velocity + Vec2(0.0, HURL_GRAVITY * thrown.age)
            push = (
                velocity.normalized() * THROW_PUSH
                if velocity.length() > 1.0
                else Vec2(self.facing * THROW_PUSH, -80.0)
            )
            death = "Blown apart by a hurled adventurer!"
            if other.hurt_from(self, THROW_DAMAGE, point, push, "minotaur", death):
                self.kills["throw"] += 1
            elif other.animated:
                other.knock_down(point, THROW_PUSH, 0.9, 0.45)
            self._drop_thrown(man, velocity)
            return True
        return False

    def _drop_thrown(self, man: Stickman, velocity: Vec2) -> None:
        self._thrown = None
        if not man.animated:
            return
        push = velocity if velocity.length() > 1.0 else Vec2(self.facing * 220.0, -80.0)
        death = "Hurled by the minotaur!"
        if not man.hurt_from(self, THROW_SELF, man.center(), push, "minotaur", death):
            man.knock_down(man.center(), push.length(), 1.0, 0.5)

    def _try_stomp(self, foe: Stickman) -> bool:
        ahead = (foe.contact().x - self.position.x) * self.facing
        self._stomp_x = clamp(ahead, 6.0, STOMP_CLOSE)
        wind, strike, _ = STOMP_TIMES
        for i in range(7):
            hoof = self.to_world(self.hoof(wind + strike * i / 6))
            if foe.hits(hoof, STOMP_HIT) or foe.hits(Vec2(hoof.x, self.position.y), STOMP_HIT):
                self.route = []
                self._start("stomp")
                return True
        return False

    def _stomp(self, dt: float) -> None:
        wind, strike, recover = STOMP_TIMES
        t = self.action_time
        start, end = max(t - dt, wind), min(t, wind + strike)
        if end > start:
            for i in range(1, 4):
                self._stamp(start + (end - start) * i / 3)
        if not self._shocked and t >= wind + strike:
            self._shocked = True
            self._quake()
        if t >= wind + strike + recover:
            self.action = None
            self.attack_wait = STOMP_COOLDOWN

    def _stamp(self, t: float) -> None:
        hoof = self.to_world(self.hoof(t))
        ground = Vec2(hoof.x, self.position.y)
        for stickman in self.world.stickmen:
            if not stickman.prey or stickman in self._struck:
                continue
            if not (stickman.hits(hoof, STOMP_HIT) or stickman.hits(ground, STOMP_HIT)):
                continue
            self._struck.add(stickman)
            push = Vec2(self.facing * STOMP_PUSH, 40.0)
            death = "Stomped flat by the minotaur!"
            if stickman.hurt_from(self, STOMP_DAMAGE, ground, push, "minotaur", death):
                self.kills["stomp"] += 1
            elif stickman.animated:
                stickman.knock_down(ground, STOMP_FLING, STOMP_DOWN, STOMP_STUN)

    def _quake(self) -> None:
        """The hoof comes down: the ground shakes, and anyone close by goes flat."""
        point = self.impact_point()
        self.world.debris.burst(
            point,
            Vec2(0.0, -1.0),
            8,
            140.0,
            ring_radius=12.0,
            cracks=4,
            spread=1.1,
            puffs=3,
            scale=0.6,
        )
        self._dust(point, 1, 2, 0.5)
        self._dust(point, -1, 2, 0.5)
        for stickman in self.world.stickmen:
            if not stickman.prey or stickman in self._struck:
                continue
            at = stickman.contact()
            if at.distance_to(point) > STOMP_RADIUS or abs(at.y - point.y) > 16.0:
                continue
            self._struck.add(stickman)
            body = stickman.center()
            push = (body - point).normalized() * STOMP_FLING
            death = "Flattened by the minotaur's stomp!"
            if stickman.hurt_from(
                self, STOMP_QUAKE, body, push, "minotaur", death, bleed=False
            ):
                self.kills["quake"] += 1
            elif stickman.animated:
                stickman.knock_down(point, STOMP_FLING, STOMP_DOWN, STOMP_STUN)

    # ----- getting about ------------------------------------------------------------------

    def _turn_to(self, way: int) -> None:
        if way != self.facing:
            self.facing = way
            self.turn_left = 0.0

    def _brake(self, dt: float) -> None:
        if self.speed == 0.0:
            return
        before = self.speed
        self.speed = _approach(self.speed, 0.0, BRAKING * dt)
        surface = self.surface
        if surface is not None and surface.walkable:
            self._step_along(surface, (before + self.speed) * 0.5 * dt)

    def _step_along(self, surface: Surface, move: float) -> None:
        x = self.position.x + move
        clamped = clamp(x, surface.low, surface.high)
        if clamped != x:
            self.speed = 0.0
        self.phase += abs(clamped - self.position.x) / self.cycle()
        self.position = Vec2(clamped, surface.start.y)

    def _walk_to(self, x: float, dt: float, backstep: float = BACKSTEP) -> bool:
        """Head for `x` along its walk, easing in and out; True once there. It turns
        round first, unless `x` is no more than `backstep` behind it."""
        surface = self.surface
        assert surface is not None and surface.walkable
        offset = x - self.position.x
        if abs(offset) <= 0.75:
            if abs(self.speed) < 25.0:
                self.speed = 0.0
                self.position = Vec2(clamp(x, surface.low, surface.high), surface.start.y)
                return True
        way = _sign(offset)
        backing = way != self.facing
        if backing and abs(offset) > backstep:
            if abs(self.speed) > 1.0:
                self._brake(dt)
                return False
            self._turn_to(way)
            return False
        if self.turning:
            return False
        top = (BACK_SPEED if backing else WALK_SPEED) * self.pace
        wanted = way * min(top, math.sqrt(2.0 * BRAKING * abs(offset)) + 4.0)
        rate = (
            ACCELERATION if abs(wanted) > abs(self.speed) and wanted * self.speed >= 0 else BRAKING
        )
        self.speed = _approach(self.speed, wanted, rate * self.pace * dt)
        move = self.speed * dt
        if (offset - move) * way < 0.0:
            move = offset
        self._step_along(surface, move)
        return False

    def _follow(self, dt: float) -> None:
        """Carry on along its route: walk, climb up or slide down walls, and start the
        jumps, drops and hauls between surfaces."""
        if not self.route:
            self._brake(dt)
            return
        step = self.route[0]
        move = step.move
        surface = self.surface
        if surface is None:
            return
        if move is Move.WALK:
            if not surface.walkable:
                self.route = []
                return
            if self._walk_to(step.end.x, dt):
                self.route.pop(0)
            return
        if move is Move.CLIMB:
            if not surface.wall:
                self.route = []
                return
            if self._climb(step, dt):
                self.route.pop(0)
                after = self.route[0] if self.route else None
                if after is not None and after.move is Move.MANTLE:
                    # Straight on over the lip, so the climb never stalls at the top.
                    self.route.pop(0)
                    self._start_haul(after)
                    self._haul(self._climb_spare)
            return
        if surface.walkable:
            if abs(self.speed) > 2.0:
                self._brake(dt)
                return
            dx = step.end.x - step.start.x
            if move in (Move.JUMP, Move.DROP) and abs(dx) > 2.0:
                way = _sign(dx)
                if way != self.facing or self.turning:
                    self._turn_to(way)
                    return
        self.route.pop(0)
        self.speed = 0.0
        if move is Move.JUMP:
            self._pending = step
            self._start("crouch")
        elif move is Move.DROP:
            self._launch(step, "drop")
        elif move in (Move.MANTLE, Move.GRAB):
            self._start_haul(step)
        else:
            self.route = []

    def _climb(self, step: RouteStep, dt: float) -> bool:
        """Up a wall hand over hand at a steady pace; down it in a slide. True once at
        the step's end."""
        x = self.position.x
        if step.end.y >= step.start.y - 0.5:
            self.sliding = True
            self.climb_speed = 0.0
            y = min(step.end.y, self.position.y + SLIDE_SPEED * self.pace * dt)
            self.position = Vec2(x, y)
            if y >= step.end.y - 0.01:
                self.sliding = False
                return True
            return False
        self.sliding = False
        left = self.position.y - step.end.y
        self._climb_spare = 0.0
        if left <= 0.5:
            self.position = Vec2(x, step.end.y)
            self._climb_spare = dt
            return True
        top = CLIMB_SPEED * self.pace
        if len(self.route) < 2 or self.route[1].move is not Move.MANTLE:
            top = min(top, math.sqrt(2.0 * CLIMB_ACCEL * left) + 10.0)
        self.climb_speed = _approach(self.climb_speed, top, CLIMB_ACCEL * self.pace * dt)
        rise = min(left, self.climb_speed * dt)
        self.position = Vec2(x, self.position.y - rise)
        self.climb_phase += rise / CLIMB_REACH
        if left - rise <= 0.5:
            self.position = Vec2(x, step.end.y)
            self._climb_spare = dt - rise / max(self.climb_speed, 1.0)
            return True
        return False

    def _launch(self, step: RouteStep, kind: str) -> None:
        start, end = self.position, step.end
        hop = JUMP_APEX if kind == "jump" else (6.0 if self.grounded else 0.0)
        apex = min(start.y, end.y) - hop
        rise = max(0.0, start.y - apex)
        vy = -math.sqrt(2.0 * GRAVITY * rise)
        duration = max(0.15, -vy / GRAVITY + math.sqrt(2.0 * max(0.0, end.y - apex) / GRAVITY))
        launch = Vec2((end.x - start.x) / duration, vy)
        target = Anchor(step.surface, end)
        self.flight = Flight(start, launch, duration, target, end, kind, self.on_wall)
        self.velocity = launch
        self.surface = None
        self.climb_speed = 0.0
        self.sliding = False

    def _loose(self) -> None:
        """Lost its footing: it falls."""
        velocity = Vec2(self.speed, 0.0) if self.grounded else self.velocity
        self.flight = Flight(
            self.position, velocity, math.inf, None, self.position, "fall", self.on_wall
        )
        self.velocity = velocity
        self.surface = None
        self.haul = None
        self.climb_speed = 0.0
        self.sliding = False
        self.route = []
        if self.action in ("charge", "skid", "windup", "crouch", "swipe"):
            self.action = None

    def _fly(self, dt: float) -> None:
        flight = self.flight
        assert flight is not None
        flight.age += dt
        if flight.target is not None:
            t = min(flight.age, flight.duration)
            arc = flight.start + flight.launch * t + Vec2(0.0, 0.5 * GRAVITY * t * t)
            drift = (flight.target.point - flight.aim) * smoothstep(t / flight.duration)
            self.position = arc + drift
            self.velocity = flight.launch + Vec2(0.0, GRAVITY * t)
            if flight.age >= flight.duration:
                self._land(flight.target, self.velocity.y)
            return
        velocity = self.velocity + Vec2(0.0, GRAVITY * dt)
        after = self.position + velocity * dt
        world = self.world
        after = Vec2(clamp(after.x, world.left + 4.0, world.width - 4.0), after.y)
        self.velocity = velocity
        landing = self._landing(self.position, after)
        if landing is not None:
            self._land(landing, velocity.y)
            return
        self.position = after

    def _landing(self, before: Vec2, after: Vec2) -> Anchor | None:
        """The walk it comes down on going from `before` to `after`, if any."""
        if after.y <= before.y:
            return None
        found = [
            s
            for s in self.planner.surfaces
            if s.walkable
            and before.y - 0.5 <= s.start.y <= after.y + 0.5
            and s.low - 2.0 <= after.x <= s.high + 2.0
        ]
        if not found and after.y >= self.world.floor_y:
            return self.planner.anchor_near(Vec2(after.x, self.world.floor_y), walk_only=True)
        if not found:
            return None
        surface = min(found, key=lambda s: s.start.y)
        return Anchor(surface, surface.closest_point(after))

    def _land(self, anchor: Anchor, impact: float) -> None:
        self.flight = None
        self.surface = anchor.surface
        self.position = anchor.point
        self.velocity = ZERO
        self.speed = 0.0
        if anchor.surface.wall:
            self.facing = anchor.surface.facing
            self.turn_left = 0.0
            return
        hard = clamp((impact - SOFT_LANDING) / (HARD_LANDING - SOFT_LANDING), 0.0, 1.0)
        self.impact = hard
        self._crush()
        if self.dead:
            return
        low, high = LAND_TIME
        self.land_time = self.land_left = low + (high - low) * hard
        puffs = 1 + round(3 * hard)
        self._dust(self.position, 1, puffs, 0.45 + 0.35 * hard)
        self._dust(self.position, -1, puffs, 0.45 + 0.35 * hard)

    def _crush(self) -> None:
        """It came down on them: they go flat under its weight."""
        if self.impact <= 0.0:
            return
        point = self.position
        for stickman in self.world.stickmen:
            if not stickman.prey:
                continue
            at = stickman.contact()
            if abs(at.y - point.y) > 16.0 or abs(at.x - point.x) > CRUSH_REACH:
                continue
            body = stickman.center()
            side = _sign(body.x - point.x, default=self.facing)
            push = Vec2(side * 60.0, 80.0)
            death = "Flattened under the falling minotaur!"
            if stickman.hurt_from(self, CRUSH_DAMAGE, body, push, "minotaur", death):
                self.kills["crush"] += 1
            elif stickman.animated:
                stickman.knock_down(point, CRUSH_FLING, CRUSH_DOWN, CRUSH_STUN)

    def _start_haul(self, step: RouteStep) -> None:
        if step.move is Move.GRAB:
            kind, duration = "grab", GRAB_TIME
        elif step.end.y < step.start.y:
            kind, duration = "mantle", MANTLE_TIME
        else:
            kind, duration = "unmantle", MANTLE_TIME
        if step.surface.wall:
            self.facing = step.surface.facing
        elif self.surface is not None and self.surface.wall:
            self.facing = self.surface.facing
        self.turn_left = 0.0
        duration /= self.pace
        target = Anchor(step.surface, step.end)
        self.haul = Haul(
            self.position, step.end, duration, target, kind, self.on_wall, speed=self.climb_speed
        )
        self.surface = None
        self.climb_speed = 0.0
        self.sliding = False

    def _haul(self, dt: float) -> None:
        haul = self.haul
        assert haul is not None
        haul.age += dt
        t = min(1.0, haul.age / haul.duration)
        start, end = haul.start, haul.end
        if haul.kind == "mantle":
            rise = _carry_on(min(1.0, t / 0.6), haul.speed * 0.6 * haul.duration, start.y - end.y)
            over = smoothstep(max(0.0, (t - 0.45) / 0.55))
        elif haul.kind == "unmantle":
            over, rise = smoothstep(min(1.0, t / 0.55)), smoothstep(max(0.0, (t - 0.4) / 0.6))
        else:
            rise = over = smoothstep(t)
        self.position = Vec2(start.x + (end.x - start.x) * over, start.y + (end.y - start.y) * rise)
        if t >= 1.0:
            self.haul = None
            self.surface = haul.target.surface
            self.position = haul.target.point
            if self.surface.walkable and haul.kind == "mantle":
                self.land_time = self.land_left = LAND_TIME[0]
                self.impact = 0.0

    def lip(self) -> float | None:
        """The top of the wall it's climbing (y), if it's going over it."""
        for step in self.route[:2]:
            if step.move is Move.MANTLE and step.end.y < step.start.y:
                return step.end.y
        return None

    def haul_progress(self) -> tuple[str, float] | None:
        haul = self.haul
        if haul is None:
            return None
        return haul.kind, min(1.0, haul.age / haul.duration)

    def _dust(self, point: Vec2, way: int, puffs: int, scale: float) -> None:
        self.world.debris.burst(
            point + Vec2(0.0, -1.0),
            Vec2(float(way), -0.25),
            0,
            70.0,
            spread=0.35,
            puffs=puffs,
            scale=scale,
        )

    # ----- the windows moving ---------------------------------------------------------------

    def terrain_changed(self, change: TerrainChange) -> None:
        """Ride the window it's on (or land where its jump was going); fall if it closes
        or moves out from under it."""
        self.route = []
        self._aimed = None
        self._replan_wait = 0.0
        flight = self.flight
        if flight is not None:
            if change.shift is not None:
                flight.start = flight.start + change.shift
                flight.aim = flight.aim + change.shift
                self.position = self.position + change.shift
            if flight.target is not None:
                target = self._moved(flight.target, change)
                if target is None:
                    self._loose()
                else:
                    flight.target = target
            return
        haul = self.haul
        if haul is not None:
            target = self._moved(haul.target, change)
            if target is None:
                self._loose()
                return
            delta = target.point - haul.target.point
            haul.start, haul.end, haul.target = haul.start + delta, target.point, target
            self.position = self.position + delta
            return
        surface = self.surface
        if surface is None:
            return
        moved = self._moved(Anchor(surface, self.position), change)
        if moved is None:
            carry = change.delta_for(surface.box)
            if carry is not None:
                self.position = self.position + carry
            self._loose()
            return
        self.surface, self.position = moved.surface, moved.point
        pending = self._pending
        if pending is not None:
            self._pending = None
            if self.action == "crouch":
                self.action = None

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

    def _escape(self) -> None:
        """Out of a window that opened over it, onto the nearest surface. A window
        hanging over the floor doesn't count: he walks through that overhang. Nor does one
        beside a wall he's on: he climbs a narrow slot with his bulk in the window next to
        it, or getting on or off one (a wall covered over is gone, and he falls off that)."""
        if self.on_wall:
            return
        haul = self.haul
        if haul is not None and (haul.from_wall or haul.target.surface.wall):
            return
        body = self.to_world(Vec2(0.0, -HIP_HEIGHT))
        if not self._solid(body, self.position.y):
            return
        if self.flight is not None and self.flight.target is not None:
            return
        best: Anchor | None = None
        best_distance = ESCAPE_REACH
        for surface in self.planner.surfaces:
            if not surface.walkable:
                continue
            point = surface.closest_point(self.position)
            hips = point - Vec2(0.0, HIP_HEIGHT)
            distance = point.distance_to(self.position)
            if distance < best_distance and not self._solid(hips, point.y):
                best, best_distance = Anchor(surface, point), distance
        if best is None:
            return
        self.flight = None
        self.haul = None
        self.climb_speed = 0.0
        self.route = []
        if self.action in ("charge", "skid", "windup", "crouch"):
            self.action = None
        self.surface, self.position, self.speed = best.surface, best.point, 0.0

    def _solid(self, point: Vec2, feet_y: float) -> bool:
        """Whether `point` is inside a window. Standing on the floor, a window that
        doesn't cover his feet is the overhang above the bottom edge, and he walks
        through it."""
        on_floor = abs(feet_y - self.world.floor_y) <= 2.0
        feet = Vec2(point.x, feet_y)
        for box in self.world.boxes:
            if not box.contains(point):
                continue
            if on_floor and not box.contains(feet):
                continue
            return True
        return False

    # ----- death -------------------------------------------------------------------------

    def die(self, point: Vec2, push: Vec2) -> None:
        self.dead = True
        self.down_time = 0.0
        self.action = None
        self.route = []
        self.rage_left = 0.0
        if not self.grounded:
            self._loose()
            self.velocity = self.velocity + push * 0.2

    def update_dead(self, dt: float) -> None:
        self.down_time += dt
        self.time += dt
        self.fury = _approach(self.fury, 0.0, dt * 3.0)
        self._ease_lunge(dt)
        if self.flight is not None:
            self._fly(dt)
            return
        if self.haul is not None or (self.surface is not None and not self.surface.walkable):
            self._loose()
            return
        self.speed = _approach(self.speed, 0.0, BRAKING * 2.0 * dt)
        self.slump = min(1.0, self.slump + dt / 0.35)
        if self.slump >= 1.0:
            before = self.tilt
            self.tilt = min(1.0, self.tilt + dt / 0.55)
            if before < 1.0 <= self.tilt:
                back = self.position - Vec2(self.facing * 40.0, 0.0)
                self._dust(back, -self.facing, 3, 0.6)
                self._dust(back, self.facing, 2, 0.5)
