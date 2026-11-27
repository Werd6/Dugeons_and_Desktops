"""The mind flayer: a robed psionic that floats after the adventurers and makes them
its own.

It routes exactly like a stickman (the same planner: across window tops, up and down
window sides, along undersides, jumps and drops) but never climbs or walks: it poses
itself (`_float`), an upright robed body that hovers a fixed height over a top, floats
`WALL_GAP` out from a side, hangs just under an underside, and glides smoothly from one
to the next, leaning into the way it's going. It hunts the nearest free adventurer and
has three powers, one at a time, standing still for each:

- Mind blast: from range, a slow purple bolt that homes in on him, does
  `BLAST_DAMAGE` (none, by default) and paralyses him for `BLAST_STUN` seconds.
  As the Elder Thing Herald (legendary), it then blinks onto the victim and starts a
  tentacle grab immediately.
- Tentacle grab: on a paralysed adventurer within reach, its face tentacles seize his
  head for `GRAB_TIME`; if he's still there at the end it plants an intellect
  devourer in his skull and he becomes its thrall (`Stickman.enthrall`).
- Psychic pulse: when anyone free gets close, a ring bursts out of it that flings
  everyone nearby flat and leaves them paralysed when they get up.

With three living thralls, the legendary flayer binds them into a ritual: they gather
at one spot, erupt in a psychic pulse, and tear open a rift. The rift is a sentry:
when prey (or a thrall) strays near, a tentacle lashes out, seizes them, and hauls
them through. After five meals an aboleth swims out and the tear closes. Thralls do
not open another rift until that aboleth is banished back through a deep portal.

With `MIND_FLAYER_HP` gone it collapses as a ragdoll.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from dungeons_desktops.core.geometry import Vec2, clamp
from dungeons_desktops.game.actors.floating import Floater
from dungeons_desktops.game.actors.hunting import nearest
from dungeons_desktops.game.actors.mortal import Mortal
from dungeons_desktops.game.adventurers import model as stick_figure
from dungeons_desktops.game.adventurers.actor import Stickman
from dungeons_desktops.game.defenders.mindflayer.rift import Rift, update_rift
from dungeons_desktops.game.world.api import World
from dungeons_desktops.navigation.planner import Anchor
from dungeons_desktops.rig.biped import UP
from dungeons_desktops.rig.ragdoll import Ragdoll
from dungeons_desktops.rig.skeleton import Pose, mirror_pose

MIND_FLAYER_HP = 9

FLOAT_PACE = 0.7
"""How fast it gets through its routes, relative to a stickman walking."""
HOVER = 4.0
"""How high the hem of its robe floats over a top or the floor."""
WALL_GAP = 12.0
"""How far out from a window side its body floats."""
CEILING_GAP = 5.0
"""How far below an underside the top of its head floats (room for its collar)."""
SETTLE_RATE = 14.0
"""How quickly its body eases onto the spot its route puts it at."""
MAX_LEAN = 0.32
LEAN_RATE = 6.0
TURN_SPEED = 6.0
"""Sideways speed above which it faces the way it's going."""
REPLAN_EVERY = 0.5
WANDER_WAIT = (2.0, 4.0)
BLAST_RANGE = 240.0
BLAST_WINDUP = 0.45
BLAST_COOLDOWN = 4
BLAST_DAMAGE = 0
BLAST_STUN = 7
BOLT_SPEED = 230.0
BOLT_LIFE = 2.5
BOLT_HIT = 2.0
"""How close to his body the bolt must get to land."""
PULSE_RADIUS = 60.0
PULSE_WINDUP = 0.5
PULSE_COOLDOWN = 7.0
PULSE_SPEED = 300.0
PULSE_DOWN = 1.0
PULSE_STUN = 3
WAVE_TIME = 0.5
GRAB_REACH = 22.0
GRAB_HEIGHT = 24.0
GRAB_TIME = 1.1
GRAB_SLACK = 1.5
"""How far past `GRAB_REACH` a victim may drift before the grab breaks."""
BLINK_OFFSET = 14.0
"""How far beside a stunned victim the legendary flayer blinks in."""
RITUAL_THRALLS = 3
RITUAL_ARRIVE = 28.0
"""How close each thrall must be to the gathering point before the pulse."""
RITUAL_PULSE_TIME = 0.7
RITUAL_PULSE_RADIUS = 110.0
class Power(Enum):
    BLAST = "blast"
    PULSE = "pulse"
    GRAB = "grab"


@dataclass(eq=False)
class Bolt:
    position: Vec2
    target: Stickman
    age: float = 0.0


@dataclass
class Wave:
    center: Vec2
    age: float = 0.0


class MindFlayer(Floater, Mortal):
    max_hp = MIND_FLAYER_HP
    linger = 3.0
    pace = FLOAT_PACE
    hover = HOVER
    wall_gap = WALL_GAP
    ceiling_gap = CEILING_GAP
    settle_rate = SETTLE_RATE
    max_lean = MAX_LEAN
    lean_rate = LEAN_RATE
    turn_speed = TURN_SPEED
    replan_every = REPLAN_EVERY
    wander_wait = WANDER_WAIT

    def __init__(self, world: World, anchor: Anchor) -> None:
        layout = stick_figure.build_stick_figure()
        bones = layout.skeleton
        self._legs = layout.leg_length
        height = (
            self._legs
            + sum(bones.bone(name).length for name in (layout.pelvis, layout.torso, layout.head))
            + layout.head_radius
        )
        super().__init__(world, layout, anchor, height)
        self.hunt = nearest()
        self.target: Stickman | None = None
        self.power: Power | None = None
        self.power_time = 0.0
        self.victim: Stickman | None = None
        """Who the power under way is aimed at."""
        self.blast_cooldown = 1.0
        self.pulse_cooldown = 2.0
        self.bolts: list[Bolt] = []
        self.waves: list[Wave] = []
        self.thralls = 0
        self.ritual_point: Vec2 | None = None
        self.ritual_thralls: list[Stickman] = []
        self.ritual_pulse_age: float | None = None
        self.rifts: list[Rift] = []
        self.herald_aboleth = None
        """Living or banishing aboleth delivered by this flayer's rift, if any."""
        self.float_time = world.random.uniform(0.0, math.tau)
        self.ragdoll: Ragdoll | None = None
        self._pose = self._float_pose()

    @property
    def rift(self) -> Rift | None:
        """Newest open rift (for render/tests that expect a single tear)."""
        return self.rifts[-1] if self.rifts else None

    # Back-compat for anything still poking at the old Herald summon.
    @property
    def herald(self):
        return None

    @property
    def elder_brain(self):
        return None

    def pose(self) -> Pose:
        return self.ragdoll.pose() if self.ragdoll is not None else self._pose

    @property
    def facing(self) -> int:
        return self.ragdoll.facing if self.ragdoll is not None else self._facing

    @property
    def grab_reach(self) -> float:
        """0..1: how far the tentacles are out toward the victim's head."""
        if self.power is not Power.GRAB:
            return 0.0
        return min(1.0, self.power_time / (GRAB_TIME * 0.35))

    # ----- simulation ----------------------------------------------------------

    def update(self, dt: float) -> None:
        self.float_time += dt
        self._update_ritual(dt)
        self._replan_if_needed()
        self.blast_cooldown -= dt
        self.pulse_cooldown -= dt
        self.target = self.hunt.update(dt, self.contact(), self.world.stickmen)
        if self.power is not None:
            self._use_power(dt)
        elif not self.follower.in_transition:
            self._choose_power()
        rooted = self.power is not None
        if not rooted:
            self._replan_wait -= dt
            if self._replan_wait <= 0.0 and not self.follower.in_transition:
                self._replan_wait = REPLAN_EVERY
                self._head_out()
        if not rooted:
            self.follower.update(dt * self._pace())
        self._float(dt)
        self._track_velocity(dt)
        self._update_bolts(dt)
        self._update_waves(dt)

    # ----- thrall ritual → Elder Thing Herald ---------------------------------

    def _update_ritual(self, dt: float) -> None:
        """Legendary: one thrall triad opens a sentry rift; after it delivers an aboleth,
        further rituals wait until that aboleth is banished."""
        if not getattr(self, "legendary", False):
            return
        self.rifts = [rift for rift in self.rifts if update_rift(rift, dt, self.world, self)]

        if self.ritual_pulse_age is not None:
            self.ritual_pulse_age += dt
            if self.ritual_pulse_age >= RITUAL_PULSE_TIME:
                self._detonate_ritual()
            return

        if self.ritual_point is None:
            self._try_start_ritual()
            return

        living = [
            thrall
            for thrall in self.ritual_thralls
            if thrall.thrall and thrall.animated and thrall in self.world.stickmen
        ]
        self.ritual_thralls = living
        if len(living) < RITUAL_THRALLS:
            # Need a full triad again.
            for thrall in living:
                thrall.ritual_bound = False
                thrall.ritual_goal = None
            self.ritual_point = None
            self.ritual_thralls = []
            return

        for thrall in living:
            thrall.ritual_bound = True
            thrall.ritual_goal = self.ritual_point
            if thrall.goal != self.ritual_point:
                thrall.goal = self.ritual_point
                if not thrall.follower.in_transition:
                    thrall.replan()

        arrived = all(
            thrall.contact().distance_to(self.ritual_point) <= RITUAL_ARRIVE for thrall in living
        )
        if arrived:
            self.ritual_pulse_age = 0.0
            self.waves.append(Wave(self.ritual_point))
            self.world.spells.pulse(self.ritual_point, RITUAL_PULSE_RADIUS)
            self.world.spells.sparkle(self.ritual_point, "magic", 28, 220.0)

    def _try_start_ritual(self) -> None:
        # One rift / one aboleth at a time: no further tears until the aboleth is banished.
        if self.rifts or self.herald_aboleth is not None:
            return
        # Skip thralls already bound to a gathering so leftovers can form the next triad.
        thralls = [t for t in self.world.thralls if not t.ritual_bound][:RITUAL_THRALLS]
        if len(thralls) < RITUAL_THRALLS:
            return
        point = self._pick_ritual_point(thralls)
        self.ritual_point = point
        self.ritual_thralls = thralls
        for thrall in thralls:
            thrall.ritual_bound = True
            thrall.ritual_goal = point
            thrall.goal = point
            thrall.halt()
            if thrall.weapon is not None:
                thrall.weapon.cancel()
            thrall.replan()

    def spawn_aboleth_from_rift(self, rift: Rift) -> None:
        """Fifth meal: an aboleth swims through the tear into the world."""
        if self.herald_aboleth is not None:
            return
        facing = 1 if rift.center.x < self.world.width * 0.5 else -1
        aboleth = self.world.add_aboleth(rift.center + Vec2(0.0, -18.0), facing=facing)
        aboleth.begin_emergence(rift.center)
        aboleth.herald_flayer = self
        self.herald_aboleth = aboleth

    def release_aboleth(self, aboleth) -> None:
        """Called once the herald aboleth finishes banishing through a deep portal."""
        if self.herald_aboleth is aboleth:
            self.herald_aboleth = None

    def _pick_ritual_point(self, thralls: list[Stickman]) -> Vec2:
        mid = sum((thrall.contact() for thrall in thralls), Vec2(0.0, 0.0)) / len(thralls)
        world = self.world
        x = clamp(mid.x, world.left + 80.0, world.width - 80.0)
        # Prefer a clear floor gathering for the rift's entrance.
        floor = Vec2(x, world.floor_y)
        anchor = self.planner.anchor_near(floor, walk_only=True)
        if anchor is not None:
            return anchor.point
        fallback = self.planner.anchor_near(mid, walk_only=True)
        return fallback.point if fallback is not None else mid

    def _detonate_ritual(self) -> None:
        point = self.ritual_point
        assert point is not None
        for thrall in list(self.ritual_thralls):
            thrall.ritual_bound = False
            thrall.ritual_goal = None
            if thrall.weapon is not None:
                thrall.weapon.cancel()
            thrall.release_limb()
            self.world.spells.sparkle(thrall.center(), "magic", 18, 180.0)
            if thrall in self.world.stickmen:
                self.world.stickmen.remove(thrall)
        self.world.spells.pulse(point, RITUAL_PULSE_RADIUS * 1.15)
        self.world.spells.sparkle(point, "magic", 40, 280.0)
        self.waves.append(Wave(point))
        self.ritual_point = None
        self.ritual_thralls = []
        self.ritual_pulse_age = None
        self.rifts.append(Rift(point))

    # ----- floating ------------------------------------------------------------

    def _float(self, dt: float) -> None:
        target = self.target
        self._glide(dt, self.power is None, target.center() if target is not None else None)
        self._pose = self._float_pose()

    def _float_pose(self) -> Pose:
        """Upright over `feet`, tilted by `lean`, legs hanging inside the robe, arms
        folded in front, or raised for the power under way."""
        facing = self._facing
        lean = self.lean * facing
        tilt = UP + lean
        charge = 1.0
        if self.power is Power.BLAST:
            charge = min(1.0, self.power_time / BLAST_WINDUP)
        elif self.power is Power.PULSE:
            charge = min(1.0, self.power_time / PULSE_WINDUP)
        near, far, bend = math.pi / 2 - 0.35, math.pi / 2 - 0.2, -1.0
        if self.power is Power.BLAST and self.victim is not None:
            aim = self.victim.center() - self.center()
            point = math.atan2(aim.y, max(1.0, abs(aim.x)))
            near, bend = near + (point - near) * charge, bend * (1.0 - charge)
        elif self.power is Power.PULSE:
            near = near + (-0.6 - near) * charge
            far = far + (-2.5 - far) * charge
            bend = bend * (1.0 - charge)
        elif self.power is Power.GRAB:
            near, far, bend = 0.15, 0.35, -0.4
        hip = self.feet - Vec2(0.0, self._legs)
        angles = {
            "pelvis": tilt,
            "torso": 0.0,
            "head": 0.15,
            "upper_leg_l": math.pi / 2 + lean * 0.5 - tilt,
            "upper_leg_r": math.pi / 2 + lean * 0.5 - tilt,
            "lower_leg_l": 0.0,
            "lower_leg_r": 0.0,
            "upper_arm_r": near - tilt,
            "upper_arm_l": far - tilt,
            "lower_arm_r": bend,
            "lower_arm_l": bend if self.power is not Power.BLAST else -1.0,
        }
        pose = Pose(Vec2(hip.x, hip.y), angles)
        if facing < 0:
            pose = mirror_pose(self.layout.skeleton, pose, hip.x)
        return pose

    def reanchor(self, delta: Vec2, carried: bool, box: int | None = None) -> None:
        super().reanchor(delta, carried, box)
        if carried:
            self._pose = self._float_pose()

    def _head_out(self) -> None:
        self._seek(self.target, self.hunt)

    # ----- powers ----------------------------------------------------------------

    def _within(self, stickman: Stickman, reach: float, height: float) -> bool:
        center, theirs = self.center(), stickman.center()
        return abs(theirs.y - center.y) <= height and theirs.distance_to(center) <= reach

    def _choose_power(self) -> None:
        target = self.target
        center = self.center()
        close = [
            s
            for s in self.world.stickmen
            if (
                s.prey
                and not s.paralysed
                and not getattr(s, "mindflayer_stun_immune", False)
                and s.center().distance_to(center) <= PULSE_RADIUS
            )
        ]
        if target is not None and target.paralysed and target.animated:
            if self._within(target, GRAB_REACH, GRAB_HEIGHT):
                target.paralyze(GRAB_TIME + 0.3)
                self._start(Power.GRAB, target)
                return
        if close and self.pulse_cooldown <= 0.0:
            self._start(Power.PULSE, None)
            return
        if (
            target is not None
            and not target.paralysed
            and not getattr(target, "mindflayer_stun_immune", False)
            and self.blast_cooldown <= 0.0
            and target.center().distance_to(center) <= BLAST_RANGE
        ):
            self._start(Power.BLAST, target)

    def _start(self, power: Power, victim: Stickman | None) -> None:
        self.power, self.power_time, self.victim = power, 0.0, victim
        self.halt()
        if victim is not None:
            self._face(victim.center())

    def _use_power(self, dt: float) -> None:
        self.power_time += dt
        victim = self.victim
        if self.power is Power.BLAST:
            if self.power_time >= BLAST_WINDUP:
                if victim is not None and victim.prey:
                    self.bolts.append(Bolt(self.mouth(), victim))
                self.blast_cooldown = BLAST_COOLDOWN
                self.power = None
        elif self.power is Power.PULSE:
            if self.power_time >= PULSE_WINDUP:
                center = self.center()
                self.waves.append(Wave(center))
                for stickman in self.world.stickmen:
                    if (
                        stickman.prey
                        and not getattr(stickman, "mindflayer_stun_immune", False)
                        and stickman.center().distance_to(center) <= PULSE_RADIUS
                    ):
                        stickman.knock_down(center, PULSE_SPEED, PULSE_DOWN, PULSE_STUN)
                self.pulse_cooldown = PULSE_COOLDOWN
                self.power = None
        elif self.power is Power.GRAB:
            assert victim is not None
            held = victim.prey and self._within(
                victim, GRAB_REACH * GRAB_SLACK, GRAB_HEIGHT * GRAB_SLACK
            )
            if not held:
                self.power = None
                return
            self._face(victim.center())
            victim.paralyze(0.3)
            if self.power_time >= GRAB_TIME:
                victim.enthrall()
                self.thralls += 1
                self.world.spells.sparkle(victim.center(), "magic", 12, 90.0)
                self.power = None

    def mouth(self) -> Vec2:
        head = self.transforms()[self.layout.head].end
        return head + Vec2(self.facing * self.layout.head_radius * 0.6, 0.0)

    def _update_bolts(self, dt: float) -> None:
        flying = []
        for bolt in self.bolts:
            bolt.age += dt
            target = bolt.target
            if bolt.age >= BOLT_LIFE or not target.prey:
                continue
            to = target.center() - bolt.position
            step = BOLT_SPEED * dt
            if to.length() <= step or target.hits(bolt.position, BOLT_HIT):
                self._blast(target, bolt.position)
                continue
            bolt.position += to.normalized() * step
            flying.append(bolt)
        self.bolts = flying

    def _blast(self, target: Stickman, point: Vec2) -> None:
        self.world.spells.sparkle(point, "magic", 10, 110.0)
        if BLAST_DAMAGE:
            push = (target.center() - point).normalized() * 60.0
            killed = target.hurt_from(
                self,
                BLAST_DAMAGE,
                point,
                push,
                "mind flayer",
                "Mind-blasted by the mind flayer!",
                False,
            )
            if killed:
                return
        if getattr(target, "mindflayer_stun_immune", False):
            return
        target.paralyze(BLAST_STUN)
        if getattr(self, "legendary", False) and target.paralysed and target.animated:
            self._blink_and_grab(target)

    def _blink_and_grab(self, target: Stickman) -> None:
        """Legendary stun: vanish, reappear beside the victim, and begin the grab."""
        origin = self.center()
        self.world.spells.sparkle(origin, "magic", 16, 170.0)
        self.world.spells.pulse(origin, 22.0)
        contact = target.contact()
        side = -1 if target.center().x >= origin.x else 1
        aim = contact + Vec2(side * BLINK_OFFSET, 0.0)
        anchor = self.planner.anchor_near(aim) or self.planner.anchor_near(contact)
        if anchor is None:
            return
        self.follower.reset(anchor)
        self.halt()
        self.goal = None
        self.feet = self._place(anchor.surface, anchor.point)
        self._face(target.center())
        self._pose = self._float_pose()
        self.world.spells.sparkle(self.center(), "magic", 16, 170.0)
        self.world.spells.pulse(self.center(), 22.0)
        target.paralyze(GRAB_TIME + 0.3)
        self._start(Power.GRAB, target)

    def _update_waves(self, dt: float) -> None:
        for wave in self.waves:
            wave.age += dt
        self.waves = [w for w in self.waves if w.age < WAVE_TIME]

    # ----- death ---------------------------------------------------------------

    def die(self, point: Vec2, push: Vec2) -> None:
        """The robe crumples where it floated, shoved along `push` from `point`."""
        self.dead = True
        self.down_time = 0.0
        self.power = None
        world = self.world
        ragdoll = Ragdoll(
            self.layout.skeleton,
            ground_y=world.floor_y,
            end_radius={self.layout.head: self.layout.head_radius},
        )
        ragdoll.obstacles = world.boxes
        ragdoll.facing = self._facing
        ragdoll.engage(self._pose, world.step)
        ragdoll.release()
        ragdoll.apply_impulse(point, push, radius=25.0)
        self.ragdoll = ragdoll

    def update_dead(self, dt: float) -> None:
        assert self.ragdoll is not None
        self.ragdoll.obstacles = self.world.boxes
        self.ragdoll.step(dt)
        self.down_time += dt
        self._update_bolts(dt)
        self._update_waves(dt)
