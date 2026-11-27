"""Hand-held weapons: an upper-body animation layer plus vector shapes to draw.

A weapon runs after the locomotion gait, in the canonical frame (facing +x),
and re-solves the arms so the hands hold the weapon. Actions (a sword swing,
firing a rifle) are timelines played on top of whatever the legs are doing.

The weapon's drawn shape hangs off the displayed (world) pose: the grip follows
the weapon hand, and the angle is the layer's canonical angle mirrored for
facing. That keeps it in hand through pose blends.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep
from dungeons_desktops.rig.biped import BipedLayout
from dungeons_desktops.rig.ik import solve_two_bone
from dungeons_desktops.rig.locomotion import PoseMode
from dungeons_desktops.rig.skeleton import BoneTransform, Pose, forward_kinematics


@dataclass(frozen=True)
class Stroke:
    """One line of a weapon drawing. `kind` picks the color: steel, hilt, wood, metal, flash.
    With a `shape`, it's that filled outline instead, edged `width` thick."""

    start: Vec2
    end: Vec2
    width: float
    kind: str
    shape: tuple[Vec2, ...] = ()


@dataclass(frozen=True)
class Key:
    """A pose for the weapon hand: offset from the shoulder in arm lengths, weapon angle,
    and spine/head angles."""

    time: float
    hand: Vec2
    angle: float
    torso: float = 0.0
    head: float = 0.0


def _world_angle(angle: float, facing: int) -> float:
    return angle if facing > 0 else math.pi - angle


def _sample(keys: tuple[Key, ...], time: float) -> Key:
    for a, b in zip(keys, keys[1:], strict=False):
        if time <= b.time:
            t = smoothstep(clamp((time - a.time) / (b.time - a.time), 0.0, 1.0))
            return Key(
                time,
                a.hand.lerp(b.hand, t),
                a.angle + (b.angle - a.angle) * t,
                a.torso + (b.torso - a.torso) * t,
                a.head + (b.head - a.head) * t,
            )
    return keys[-1]


CLINGING = frozenset({PoseMode.CLIMB, PoseMode.HANG})
"""Modes where the wearer holds on with one hand while the weapon hand acts."""
MIRROR_SWING = 0.12
"""Seconds a `reverse` action takes to swing across to the far side, and back."""


class Weapon:
    """Base: holds an angle, plays a timed action, and slings itself when not in use.

    On a wall or under a ceiling (`cling_modes`) a weapon comes out only for an action,
    and only the weapon hand moves (unless `two_handed`): the other keeps its grip.
    With `reverse` the action is mirrored about the shoulder, aimed away from the way
    the wearer faces (a climber facing his wall, striking at something behind him)."""

    name = "weapon"
    size = 1.0
    """Drawn size relative to the figure's scale."""
    duration = 1.0
    stops_movement = False
    held_modes = frozenset({PoseMode.WALK})
    cling_modes = CLINGING
    two_handed = False
    hit_time: float | None = None
    """For a melee weapon, when in the action the blow lands."""

    def __init__(self, layout: BipedLayout) -> None:
        self.layout = layout
        self.scale = layout.scale
        self.unit = layout.scale * self.size
        self.hand_chain, self.support_chain = layout.arms[1], layout.arms[0]
        self.arm_length = sum(layout.skeleton.bone(b).length for b in self.hand_chain.bones)
        self.time: float | None = None
        self.held = True
        self.hanging = False
        """The wearer hangs from a ceiling: a slung weapon goes on upside down, below
        the shoulders, instead of poking up through the ceiling."""
        self.angle = 0.0
        self.reverse = False
        self._clinging = False

    @property
    def busy(self) -> bool:
        return self.time is not None

    def start(self) -> bool:
        if self.busy:
            return False
        self.time = 0.0
        return True

    def cancel(self) -> None:
        self.time = None
        self.hanging = False
        self.reverse = False

    def apply(self, pose: Pose, mode: PoseMode, dt: float, skip: frozenset[str]) -> None:
        """Advance the action and re-pose the arms (canonical frame, in place)."""
        if self.time is not None:
            self.time += dt
            if self.time >= self.duration:
                self.time = None
                self.reverse = False
        self._clinging = mode in self.cling_modes and mode not in self.held_modes
        self.held = mode in self.held_modes or (self._clinging and self.time is not None)
        self.hanging = mode is PoseMode.HANG
        if self.held:
            self._hold(pose, skip)
            if self.reverse:
                self._mirror_angles(self._mirrored())

    def _mirrored(self) -> float:
        """How far a `reverse` action is mirrored, 0..1: it swings across from the
        unmirrored pose at the start and back at the end, so the hand doesn't jump."""
        if not self.reverse or self.time is None:
            return 0.0
        edge = min(self.time, self.duration - self.time) / MIRROR_SWING
        return smoothstep(clamp(edge, 0.0, 1.0))

    def _mirror_angles(self, amount: float) -> None:
        self.angle += (math.pi - 2.0 * self.angle) * amount

    @property
    def _frees_support(self) -> bool:
        """A two-handed action lets go of a wall (his feet are on it), never a ceiling."""
        return self.two_handed and not self.hanging

    def _hold(self, pose: Pose, skip: frozenset[str]) -> None:
        raise NotImplementedError

    def _shoulder(self, pose: Pose) -> Vec2:
        return forward_kinematics(self.layout.skeleton, pose)[self.layout.torso].end

    def _solve(self, pose: Pose, chain_name_target: dict[str, Vec2], skip: frozenset[str]):
        mirrored = self._mirrored()
        shoulder = self._shoulder(pose) if mirrored else None
        for chain in self.layout.arms:
            target = chain_name_target.get(chain.name)
            if target is None or chain.name in skip:
                continue
            if self._clinging and chain is self.support_chain and not self._frees_support:
                continue
            if shoulder is not None:
                target = Vec2(target.x + 2.0 * (shoulder.x - target.x) * mirrored, target.y)
            solve_two_bone(self.layout.skeleton, pose, chain, target)

    # ----- drawing (world frame) ---------------------------------------------

    def strokes(
        self, transforms: dict[str, BoneTransform], facing: int, slung: bool = False
    ) -> list[Stroke]:
        if slung or not self.held:
            return self._slung(transforms, facing)
        grip = transforms[self.hand_chain.bones[-1]].end
        direction = Vec2.from_angle(_world_angle(self.angle, facing))
        return self._held(grip, direction, self.swing_facing(facing))

    def swing_facing(self, facing: int) -> int:
        """The way the action points: away from `facing` while `reverse`."""
        return -facing if self._mirrored() > 0.5 else facing

    def _held(self, grip: Vec2, direction: Vec2, facing: int) -> list[Stroke]:
        raise NotImplementedError

    def _slung(self, transforms: dict[str, BoneTransform], facing: int) -> list[Stroke]:
        raise NotImplementedError

    def _back_line(
        self, transforms: dict[str, BoneTransform], facing: int, below: float, above: float
    ) -> tuple[Vec2, Vec2]:
        torso = transforms[self.layout.torso]
        along = (torso.end - torso.start).normalized()
        behind = Vec2(-facing * 2.5 * self.scale, 0.0)
        if self.hanging:
            return torso.end + behind + along * below, torso.start + behind - along * above
        return torso.start + behind - along * below, torso.end + behind + along * above


class Sword(Weapon):
    """One-handed sword. The swing is an overhead chop: wind up behind the head, cut
    forward and down, follow through, and come back to the carry."""

    name = "sword"
    duration = 0.6
    held_modes = frozenset({PoseMode.WALK, PoseMode.AIR})
    blade = 20.0
    handle = 4.0
    trail_window = (0.18, 0.44)
    hit_time = 0.32

    WINDUP = Key(0.22, Vec2(-0.45, -0.75), -2.5, torso=-0.3, head=-0.15)
    STRIKE = Key(0.34, Vec2(0.8, 0.35), 0.75, torso=0.35, head=0.2)
    FOLLOW = Key(0.42, Vec2(0.55, 0.7), 1.45, torso=0.3, head=0.15)

    def __init__(self, layout: BipedLayout) -> None:
        super().__init__(layout)
        self.blade = Sword.blade * self.unit
        self.handle = Sword.handle * self.unit
        self._from: Key | None = None
        self.angle = -1.1

    @property
    def trail_active(self) -> bool:
        return self.time is not None and self.trail_window[0] <= self.time <= self.trail_window[1]

    def start(self) -> bool:
        self._from = None
        return super().start()

    def _rest(self, pose: Pose) -> Key:
        transforms = forward_kinematics(self.layout.skeleton, pose)
        hand = transforms[self.hand_chain.bones[-1]].end
        forearm = transforms[self.hand_chain.bones[-1]].angle
        offset = (hand - transforms[self.layout.torso].end) / self.arm_length
        return Key(0.0, offset, clamp(forearm - 2.0, -1.9, -0.4))

    def _hold(self, pose: Pose, skip: frozenset[str]) -> None:
        rest = self._rest(pose)
        if self.time is None:
            self.angle = rest.angle
            return
        if self._from is None:
            self._from = rest
        keys = (
            self._from,
            self.WINDUP,
            self.STRIKE,
            self.FOLLOW,
            Key(self.duration, rest.hand, rest.angle),
        )
        key = _sample(keys, self.time)
        layout = self.layout
        pose.angles[layout.torso] = pose.angles[layout.torso] + key.torso
        pose.angles[layout.head] = pose.angles[layout.head] + key.head
        shoulder = self._shoulder(pose)
        self._solve(pose, {self.hand_chain.name: shoulder + key.hand * self.arm_length}, skip)
        self.angle = key.angle

    def tip(self, transforms: dict[str, BoneTransform], facing: int) -> Vec2:
        grip = transforms[self.hand_chain.bones[-1]].end
        reach = self.blade + 1.5 * self.unit
        return grip + Vec2.from_angle(_world_angle(self.angle, facing), reach)

    def _held(self, grip: Vec2, direction: Vec2, facing: int) -> list[Stroke]:
        s = self.unit
        across = direction.rotated(math.pi / 2) * (3.0 * s)
        guard = grip + direction * (1.5 * s)
        return [
            Stroke(grip - direction * self.handle, grip, 2.0 * s, "hilt"),
            Stroke(guard - across, guard + across, 2.0 * s, "hilt"),
            Stroke(guard, guard + direction * self.blade, 2.0 * s, "steel"),
        ]

    def _slung(self, transforms: dict[str, BoneTransform], facing: int) -> list[Stroke]:
        s = self.unit
        low, high = self._back_line(transforms, facing, 2.0 * s, 8.0 * s)
        along = (high - low).normalized()
        across = along.rotated(math.pi / 2) * (3.0 * s)
        guard = high - along * self.handle
        return [
            Stroke(low, guard, 2.0 * s, "steel"),
            Stroke(guard - across, guard + across, 2.0 * s, "hilt"),
            Stroke(guard, high, 2.0 * s, "hilt"),
        ]


class VialThrower(Weapon):
    """A goblin's posture and overhand lob. Always hunched; the throw winds the arm
    back over the head and whips it forward, letting go of the vial near the top."""

    name = "vials"
    duration = 0.75
    stops_movement = True
    release_time = 0.38
    hunch = 0.45

    WINDUP = Key(0.28, Vec2(-0.6, -0.7), 0.0, torso=-0.3, head=0.1)
    THROW = Key(0.4, Vec2(0.75, -0.45), 0.0, torso=0.25, head=0.0)
    FOLLOW = Key(0.5, Vec2(0.6, 0.35), 0.0, torso=0.3, head=0.0)

    def __init__(self, layout: BipedLayout) -> None:
        super().__init__(layout)
        self._from: Key | None = None
        self._released = False
        self._pending = False

    @property
    def holding(self) -> bool:
        return self.time is not None and self.time < self.release_time

    def start(self) -> bool:
        started = super().start()
        if started:
            self._from = None
            self._released = False
        return started

    def take_release(self) -> bool:
        """True once per throw, on the step the vial leaves the hand."""
        pending, self._pending = self._pending, False
        return pending

    def apply(self, pose: Pose, mode: PoseMode, dt: float, skip: frozenset[str]) -> None:
        if self.time is not None and not self._released and self.time + dt >= self.release_time:
            self._released = self._pending = True
        super().apply(pose, mode, dt, skip)

    def _hold(self, pose: Pose, skip: frozenset[str]) -> None:
        layout = self.layout
        pose.angles[layout.torso] += self.hunch
        pose.angles[layout.head] -= self.hunch * 0.8
        if self.time is None:
            return
        transforms = forward_kinematics(layout.skeleton, pose)
        shoulder = transforms[layout.torso].end
        hand = transforms[self.hand_chain.bones[-1]].end
        if self._from is None:
            self._from = Key(0.0, (hand - shoulder) / self.arm_length, 0.0)
        back = Key(self.duration, self._from.hand, 0.0)
        key = _sample((self._from, self.WINDUP, self.THROW, self.FOLLOW, back), self.time)
        pose.angles[layout.torso] += key.torso
        pose.angles[layout.head] += key.head
        shoulder = self._shoulder(pose)
        self._solve(pose, {self.hand_chain.name: shoulder + key.hand * self.arm_length}, skip)

    def hand(self, transforms: dict[str, BoneTransform]) -> Vec2:
        return transforms[self.hand_chain.bones[-1]].end

    def strokes(
        self, transforms: dict[str, BoneTransform], facing: int, slung: bool = False
    ) -> list[Stroke]:
        return []


class Bombs(VialThrower):
    """An alchemist's red bombs, lobbed overhand like the goblins' old vials but standing
    tall. One is in hand, ready (a fresh one comes out just after each throw), and two
    more hang at the belt."""

    name = "bombs"
    size = 2.2
    hunch = 0.0
    restock = 0.2
    """Seconds after a throw before the next bomb is in hand."""

    def strokes(
        self, transforms: dict[str, BoneTransform], facing: int, slung: bool = False
    ) -> list[Stroke]:
        hip = transforms[self.layout.torso].start
        s = self.unit
        strokes = [
            *self._bomb(hip + Vec2(facing * 1.6 * s, -1.0 * s), 0.7),
            *self._bomb(hip + Vec2(-facing * 1.2 * s, -0.6 * s), 0.7),
        ]
        thrown = self.time is not None and (
            self.release_time <= self.time < self.release_time + self.restock
        )
        if self.held and not slung and not thrown:
            strokes += self._bomb(self.hand(transforms) + Vec2(0.0, -1.0 * s))
        return strokes

    def _bomb(self, center: Vec2, scale: float = 1.0) -> list[Stroke]:
        s = self.unit * scale
        neck = center + Vec2(0.0, -2.2 * s)
        ball = tuple(center + Vec2.from_angle(k * math.tau / 12, 2.2 * s) for k in range(12))
        return [
            Stroke(center, center, 0.3 * s, "bomb", ball),
            Stroke(neck, neck + Vec2(0.0, -1.4 * s), 1.4 * s, "glass"),
            Stroke(neck + Vec2(0.0, -1.4 * s), neck + Vec2(0.0, -2.4 * s), 1.6 * s, "cork"),
        ]


class Rifle(Weapon):
    """Two-handed rifle. Carried across the chest at port arms; the action stops,
    shoulders the rifle, fires three shots with recoil, and lowers it again."""

    name = "rifle"
    duration = 1.4
    stops_movement = True
    raise_time = 0.3
    lower_from = 1.15
    shot_times = (0.45, 0.7, 0.95)
    stock = 6.0
    support = 9.0
    length = 20.0

    CARRY_GRIP = Vec2(0.2, 0.5)
    CARRY_ANGLE = -0.8
    AIM_GRIP = Vec2(0.3, 0.12)

    def __init__(self, layout: BipedLayout) -> None:
        super().__init__(layout)
        self.stock = Rifle.stock * self.scale
        self.support = Rifle.support * self.scale
        self.length = Rifle.length * self.scale
        self.angle = self.aim_angle = self.CARRY_ANGLE
        self._shots_taken = 0
        self._pending = 0
        self.since_shot = math.inf

    def start(self) -> bool:
        started = super().start()
        if started:
            self._shots_taken = 0
            self.since_shot = math.inf
        return started

    def take_shots(self) -> int:
        """Shots fired since the last call; the caller spawns the bullets."""
        count, self._pending = self._pending, 0
        return count

    def apply(self, pose: Pose, mode: PoseMode, dt: float, skip: frozenset[str]) -> None:
        self.since_shot += dt
        if self.time is not None:
            upcoming = self.time + dt
            while (
                self._shots_taken < len(self.shot_times)
                and upcoming >= self.shot_times[self._shots_taken]
            ):
                self._shots_taken += 1
                self._pending += 1
                self.since_shot = upcoming - self.shot_times[self._shots_taken - 1]
        super().apply(pose, mode, dt, skip)

    def _aim_amount(self) -> float:
        if self.time is None:
            return 0.0
        if self.time < self.raise_time:
            return smoothstep(self.time / self.raise_time)
        if self.time > self.lower_from:
            return 1.0 - smoothstep(
                (self.time - self.lower_from) / (self.duration - self.lower_from)
            )
        return 1.0

    def _hold(self, pose: Pose, skip: frozenset[str]) -> None:
        layout = self.layout
        aim = self._aim_amount()
        recoil = math.exp(-self.since_shot / 0.06) if self.busy else 0.0
        pose.angles[layout.torso] = pose.angles[layout.torso] * (1 - aim) + 0.1 * aim
        pose.angles[layout.torso] -= 0.08 * recoil
        pose.angles[layout.head] = pose.angles[layout.head] * (1 - aim) + 0.25 * aim

        shoulder = self._shoulder(pose)
        grip = shoulder + self.CARRY_GRIP.lerp(self.AIM_GRIP, aim) * self.arm_length
        grip -= Vec2(2.0 * recoil * self.scale, 0.0)
        self.aim_angle = self.CARRY_ANGLE * (1 - aim)
        self.angle = self.aim_angle - 0.2 * recoil
        direction = Vec2.from_angle(self.angle)
        self._solve(
            pose,
            {
                self.hand_chain.name: grip,
                self.support_chain.name: grip + direction * self.support,
            },
            skip,
        )

    def muzzle(self, transforms: dict[str, BoneTransform], facing: int) -> tuple[Vec2, Vec2]:
        """Muzzle point as drawn, and the direction a bullet leaves (the aim, before recoil)."""
        grip = transforms[self.hand_chain.bones[-1]].end
        drawn = Vec2.from_angle(_world_angle(self.angle, facing))
        return grip + drawn * self.length, Vec2.from_angle(_world_angle(self.aim_angle, facing))

    def _held(self, grip: Vec2, direction: Vec2, facing: int) -> list[Stroke]:
        s = self.scale
        forward = direction * s
        down = direction.rotated(facing * math.pi / 2) * s
        body_end = grip + forward * 10.0
        muzzle = grip + direction * self.length
        strokes = [
            Stroke(grip - direction * self.stock + down, grip, 3.5 * s, "wood"),
            Stroke(grip, body_end, 3.0 * s, "metal"),
            Stroke(grip + forward * 5.0, grip + forward * 5.5 + down * 4.0, 2.0 * s, "metal"),
            Stroke(body_end, muzzle, 1.6 * s, "metal"),
        ]
        if self.since_shot < 0.06:
            strokes += [
                Stroke(muzzle, muzzle + forward * 7.0, 3.5 * s, "flash"),
                Stroke(
                    muzzle + forward * 2.0 - down * 3.0,
                    muzzle + forward * 3.0 + down * 3.0,
                    1.5 * s,
                    "flash",
                ),
            ]
        return strokes

    def _slung(self, transforms: dict[str, BoneTransform], facing: int) -> list[Stroke]:
        s = self.scale
        low, high = self._back_line(transforms, facing, 4.0 * s, 6.0 * s)
        along = (high - low).normalized()
        return [
            Stroke(low, low + along * self.stock, 3.5 * s, "wood"),
            Stroke(low + along * self.stock, high, 2.0 * s, "metal"),
        ]


# ----- adventurer classes ----------------------------------------------------------


class FighterSword(Sword):
    """The existing sword chop played twice as fast, including its hit and trail."""

    duration = Sword.duration / 2
    hit_time = Sword.hit_time / 2
    trail_window = tuple(t / 2 for t in Sword.trail_window)
    WINDUP = replace(Sword.WINDUP, time=Sword.WINDUP.time / 2)
    STRIKE = replace(Sword.STRIKE, time=Sword.STRIKE.time / 2)
    FOLLOW = replace(Sword.FOLLOW, time=Sword.FOLLOW.time / 2)


class Axe(Sword):
    """A barbarian's war axe: the sword's overhead chop with a long haft and a heavy
    bit on its leading edge."""

    name = "axe"
    size = 1.8
    haft = 18.0

    def __init__(self, layout: BipedLayout) -> None:
        super().__init__(layout)
        self.haft = Axe.haft * self.unit
        self.blade = self.haft

    def _head(self, top: Vec2, along: Vec2, out: Vec2) -> list[Stroke]:
        """A bearded crescent bit off the leading side of the haft's top, a short
        spike behind, and an iron collar where it's socketed on."""
        s = self.unit
        socket = top - along * (2.5 * s)
        edge = []
        for degrees in range(-75, 76, 15):
            a = math.radians(degrees)
            span = 7.5 if a < 0 else 5.0
            edge.append(
                socket + out * (3.0 * s + 5.0 * s * math.cos(a)) + along * (span * s * math.sin(a))
            )
        bit = (
            socket + out * (0.8 * s) - along * (1.8 * s),
            socket + out * (3.2 * s) - along * (1.6 * s),
            *edge,
            socket + out * (3.2 * s) + along * (1.4 * s),
            socket + out * (0.8 * s) + along * (1.6 * s),
        )
        return [
            Stroke(socket, socket, 0.6 * s, "steel", bit),
            Stroke(socket, socket - out * (3.5 * s), 1.6 * s, "steel"),
            Stroke(socket - along * (2.6 * s), socket + along * (2.6 * s), 3.0 * s, "metal"),
        ]

    def _held(self, grip: Vec2, direction: Vec2, facing: int) -> list[Stroke]:
        s = self.unit
        top = grip + direction * self.haft
        leading = direction.rotated(facing * math.pi / 2)
        return [
            Stroke(grip - direction * (4.0 * s), top, 2.0 * s, "wood"),
            *self._head(top, direction, leading),
        ]

    def _slung(self, transforms: dict[str, BoneTransform], facing: int) -> list[Stroke]:
        s = self.unit
        low, high = self._back_line(transforms, facing, 4.0 * s, 8.0 * s)
        along = (high - low).normalized()
        return [Stroke(low, high, 2.0 * s, "wood"), *self._head(high, along, Vec2(-facing, 0.0))]


class HammerAndShield(Sword):
    """A paladin's war hammer and heater shield. The hammer comes down in the sword's
    overhead chop; the shield stays up in front of the chest."""

    name = "warhammer and shield"
    size = 1.7
    duration = 0.7
    haft = 14.0
    GUARD = Vec2(0.5, 0.3)
    """Where the shield hand holds, from the shoulder, in arm lengths."""
    REST_ANGLE = -1.75
    """Hammer carried nearly upright, its head showing above the shield."""

    def __init__(self, layout: BipedLayout) -> None:
        super().__init__(layout)
        self.haft = HammerAndShield.haft * self.unit
        self.blade = self.haft

    def _rest(self, pose: Pose) -> Key:
        rest = super()._rest(pose)
        return Key(0.0, rest.hand, self.REST_ANGLE)

    def _hold(self, pose: Pose, skip: frozenset[str]) -> None:
        super()._hold(pose, skip)
        shoulder = self._shoulder(pose)
        self._solve(pose, {self.support_chain.name: shoulder + self.GUARD * self.arm_length}, skip)

    def strokes(
        self, transforms: dict[str, BoneTransform], facing: int, slung: bool = False
    ) -> list[Stroke]:
        s = self.unit
        if slung or not self.held:
            low, high = self._back_line(transforms, facing, 2.0 * s, 4.0 * s)
            along = (high - low).normalized()
            shield = self._shield(low.lerp(high, 0.45) + Vec2(-facing * 1.5 * s, 0.0))
            return [*self._hammer(low, along), *shield]
        grip = transforms[self.hand_chain.bones[-1]].end
        direction = Vec2.from_angle(_world_angle(self.angle, facing))
        hand = transforms[self.support_chain.bones[-1]].end
        return [
            *self._hammer(grip - direction * (2.0 * s), direction),
            *self._shield(hand + Vec2(self.swing_facing(facing) * 1.0 * s, 0.0)),
        ]

    def _hammer(self, butt: Vec2, direction: Vec2) -> list[Stroke]:
        s = self.unit
        top = butt + direction * self.haft
        across = direction.rotated(math.pi / 2)
        a, b = top - direction * (2.0 * s), top + direction * (2.0 * s)
        head = (
            a - across * (3.5 * s),
            a + across * (3.5 * s),
            b + across * (3.5 * s),
            b - across * (3.5 * s),
        )
        return [
            Stroke(butt, top, 1.8 * s, "wood"),
            Stroke(top, top, 0.8 * s, "metal", head),
            Stroke(b, b + direction * (2.5 * s), 1.4 * s, "metal"),
        ]

    def _shield(self, center: Vec2) -> list[Stroke]:
        """An upright heater shield: flat top, straight sides, curving to a point."""
        s = self.unit
        w, top, side, bottom = 4.2 * s, 4.5 * s, 1.0 * s, 6.8 * s
        outline = [
            Vec2(-w, -top),
            Vec2(w, -top),
            Vec2(w, side),
            Vec2(0.7 * w, side + 0.55 * (bottom - side)),
            Vec2(0.0, bottom),
            Vec2(-0.7 * w, side + 0.55 * (bottom - side)),
            Vec2(-w, side),
        ]
        rim = tuple(center + p for p in outline)
        face = tuple(center + p * 0.78 + Vec2(0.0, -0.3 * s) for p in outline)
        return [
            Stroke(center, center, 0.6 * s, "hilt", rim),
            Stroke(center, center, 0.2 * s, "shield", face),
            Stroke(center + Vec2(0.0, -3.0 * s), center + Vec2(0.0, 3.8 * s), 1.0 * s, "hilt"),
            Stroke(
                center + Vec2(-2.2 * s, -1.0 * s), center + Vec2(2.2 * s, -1.0 * s), 1.0 * s, "hilt"
            ),
        ]


class Daggers(Weapon):
    """A rogue's pair of daggers, held low and forward in a knife-fighter's guard; the
    attack is a quick stab with the right and then the left."""

    name = "daggers"
    size = 1.9
    duration = 0.5
    held_modes = frozenset({PoseMode.WALK, PoseMode.AIR})
    blade = 7.0
    hit_time = 0.16
    second = 0.17
    """Seconds after the right-hand stab that the left one starts."""
    GUARD = 0.15
    STAB = (
        Key(0.0, Vec2(0.45, 0.45), -0.5),
        Key(0.08, Vec2(0.1, 0.3), -0.3, torso=-0.1),
        Key(0.16, Vec2(1.0, 0.2), 0.05, torso=0.25),
        Key(0.3, Vec2(0.45, 0.45), -0.5),
    )

    def __init__(self, layout: BipedLayout) -> None:
        super().__init__(layout)
        self.blade = Daggers.blade * self.unit
        self.angle = self.off_angle = -0.5

    def _mirror_angles(self, amount: float) -> None:
        super()._mirror_angles(amount)
        self.off_angle += (math.pi - 2.0 * self.off_angle) * amount

    def _key(self, time: float | None) -> Key:
        if time is None or time < 0.0 or time >= self.STAB[-1].time:
            return self.STAB[0]
        return _sample(self.STAB, time)

    def _hold(self, pose: Pose, skip: frozenset[str]) -> None:
        main = self._key(self.time)
        off = self._key(None if self.time is None else self.time - self.second)
        torso = self.layout.torso
        pose.angles[torso] += self.GUARD + main.torso + 0.5 * off.torso
        shoulder = self._shoulder(pose)
        targets = {
            self.hand_chain.name: shoulder + main.hand * self.arm_length,
            self.support_chain.name: shoulder + (off.hand + Vec2(-0.12, 0.05)) * self.arm_length,
        }
        self._solve(pose, targets, skip)
        self.angle, self.off_angle = main.angle, off.angle

    def strokes(
        self, transforms: dict[str, BoneTransform], facing: int, slung: bool = False
    ) -> list[Stroke]:
        if slung or not self.held:
            hip = transforms[self.layout.torso].start
            down = Vec2(-facing * 0.35, 1.0).normalized()
            behind = Vec2(-facing * 2.0 * self.unit, 0.0)
            return [*self._dagger(hip + behind, down), *self._dagger(hip - behind, down)]
        strokes = []
        for chain, angle in ((self.support_chain, self.off_angle), (self.hand_chain, self.angle)):
            grip = transforms[chain.bones[-1]].end
            strokes += self._dagger(grip, Vec2.from_angle(_world_angle(angle, facing)))
        return strokes

    def _dagger(self, grip: Vec2, direction: Vec2) -> list[Stroke]:
        s = self.unit
        across = direction.rotated(math.pi / 2) * (1.8 * s)
        guard = grip + direction * (1.0 * s)
        return [
            Stroke(grip - direction * (2.5 * s), grip, 1.6 * s, "hilt"),
            Stroke(guard - across, guard + across, 1.4 * s, "hilt"),
            Stroke(guard, grip + direction * self.blade, 1.6 * s, "steel"),
        ]


class _Released(Weapon):
    """An action that lets something go once, `release_time` into it (a spell, an
    arrow, a blessing); the wielder collects it with `take_release`."""

    release_time = 0.3
    stops_movement = True

    def __init__(self, layout: BipedLayout) -> None:
        super().__init__(layout)
        self.aim = 0.0
        """Canonical angle (facing +x) the action is aimed along."""
        self._released = False
        self._pending = False

    def start(self) -> bool:
        started = super().start()
        if started:
            self._released = False
        return started

    def take_release(self) -> bool:
        """True once per action, on the step it lets go."""
        pending, self._pending = self._pending, False
        return pending

    def apply(self, pose: Pose, mode: PoseMode, dt: float, skip: frozenset[str]) -> None:
        if self.time is not None and not self._released and self.time + dt >= self.release_time:
            self._released = self._pending = True
        super().apply(pose, mode, dt, skip)

    def _rest(self, pose: Pose, chain_bone: str) -> Vec2:
        transforms = forward_kinematics(self.layout.skeleton, pose)
        return (transforms[chain_bone].end - transforms[self.layout.torso].end) / self.arm_length


class Wand(_Released):
    """A wizard's wand: carried point-up at the side; casting draws it up and back,
    then thrusts it along `aim` and looses the spell at full stretch."""

    name = "wand"
    missile_kind = "magic"
    size = 1.9
    duration = 0.7
    release_time = 0.3
    length = 9.0
    REST_ANGLE = -0.9

    def __init__(self, layout: BipedLayout) -> None:
        super().__init__(layout)
        self.length = Wand.length * self.unit
        self.angle = self.REST_ANGLE
        self._from: Key | None = None

    def start(self) -> bool:
        self._from = None
        return super().start()

    def _hold(self, pose: Pose, skip: frozenset[str]) -> None:
        if self.time is None:
            self.angle = self.REST_ANGLE
            return
        if self._from is None:
            self._from = Key(0.0, self._rest(pose, self.hand_chain.bones[-1]), self.angle)
        aim = Vec2.from_angle(self.aim)
        keys = (
            self._from,
            Key(0.15, Vec2(-0.2, -0.75), -2.0, torso=-0.15, head=-0.1),
            Key(self.release_time, aim * 0.95, self.aim, torso=0.15, head=0.05),
            Key(0.5, aim * 0.9, self.aim, torso=0.1),
            Key(self.duration, self._from.hand, self.REST_ANGLE),
        )
        key = _sample(keys, self.time)
        layout = self.layout
        pose.angles[layout.torso] += key.torso
        pose.angles[layout.head] += key.head
        shoulder = self._shoulder(pose)
        self._solve(pose, {self.hand_chain.name: shoulder + key.hand * self.arm_length}, skip)
        self.angle = key.angle

    def tip(self, transforms: dict[str, BoneTransform], facing: int) -> Vec2:
        grip = transforms[self.hand_chain.bones[-1]].end
        return grip + Vec2.from_angle(_world_angle(self.angle, facing), self.length)

    def _held(self, grip: Vec2, direction: Vec2, facing: int) -> list[Stroke]:
        s = self.unit
        tip = grip + direction * self.length
        return [
            Stroke(grip - direction * (1.5 * s), tip, 1.3 * s, "wood"),
            Stroke(tip, tip + direction * (0.5 * s), 2.8 * s, "magic"),
        ]

    def _slung(self, transforms: dict[str, BoneTransform], facing: int) -> list[Stroke]:
        s = self.unit
        low, high = self._back_line(transforms, facing, 2.0 * s, 0.0)
        along = (high - low).normalized()
        return [Stroke(low, low + along * self.length, 1.3 * s, "wood")]


class FireOrb(Wand):
    """A sorcerer's floating focus, using the wand's aiming and release timeline."""

    name = "fire orb"
    missile_kind = "fire"
    hover = 12.0
    radius = 5.0

    def __init__(self, layout: BipedLayout) -> None:
        super().__init__(layout)
        self.clock = 0.0

    def apply(self, pose: Pose, mode: PoseMode, dt: float, skip: frozenset[str]) -> None:
        self.clock += dt
        super().apply(pose, mode, dt, skip)

    def _hold(self, pose: Pose, skip: frozenset[str]) -> None:
        if self.time is not None:
            super()._hold(pose, skip)
            return
        shoulder = self._shoulder(pose)
        palm = shoulder + Vec2(0.8, 0.3) * self.arm_length
        self._solve(pose, {self.hand_chain.name: palm}, skip)

    def _center(self, grip: Vec2) -> Vec2:
        bob = math.sin(self.clock * 3.0) * 1.5
        return grip + Vec2(0.0, (-self.hover + bob) * self.scale)

    def tip(self, transforms: dict[str, BoneTransform], facing: int) -> Vec2:
        return self._center(transforms[self.hand_chain.bones[-1]].end)

    def _held(self, grip: Vec2, direction: Vec2, facing: int) -> list[Stroke]:
        center = self._center(grip)
        radius = self.radius * self.scale
        strokes = []
        for size, kind in ((1.0, "orb"), (0.55, "flash")):
            ring = tuple(
                center + Vec2.from_angle(math.tau * k / 16, radius * size) for k in range(16)
            )
            strokes.append(Stroke(center, center, 0.5 * self.scale, kind, ring))
        return strokes

    def _slung(self, transforms: dict[str, BoneTransform], facing: int) -> list[Stroke]:
        return []


class Bow(_Released):
    """A ranger's longbow in the left hand. Shooting raises it at arm's length along
    `aim`, nocks an arrow, draws the string back to the cheek and looses."""

    name = "bow"
    two_handed = True
    size = 1.6
    duration = 1.0
    release_time = 0.6
    raise_time = 0.22
    limb = 14.0
    arrow = 16.0
    REST_AIM = 1.0
    HANG_DRAW = 0.5
    """Hanging, the bow stays in the hand on the ceiling; the string is drawn this
    many arm lengths back from it."""

    def __init__(self, layout: BipedLayout) -> None:
        super().__init__(layout)
        self.limb = Bow.limb * self.unit
        self.arrow = Bow.arrow * self.unit
        self.angle = self.REST_AIM
        self.nocked = False

    def _amounts(self) -> tuple[float, float]:
        """How far the bow is raised and the string drawn, each 0..1."""
        time = self.time
        if time is None:
            return 0.0, 0.0
        lower_from = self.release_time + 0.15
        if time < lower_from:
            raised = smoothstep(clamp(time / self.raise_time, 0.0, 1.0))
        else:
            raised = 1.0 - smoothstep((time - lower_from) / (self.duration - lower_from))
        drawn = 0.0
        if self.raise_time <= time < self.release_time:
            span = self.release_time - self.raise_time
            drawn = smoothstep((time - self.raise_time) / span)
        return raised, drawn

    def _hold(self, pose: Pose, skip: frozenset[str]) -> None:
        raised, drawn = self._amounts()
        self.angle = self.REST_AIM + (self.aim - self.REST_AIM) * raised
        self.nocked = self.time is not None and 0.5 * self.raise_time <= self.time
        self.nocked = self.nocked and self.time < self.release_time
        if self.time is None:
            return
        arm = self.arm_length
        aim = Vec2.from_angle(self.aim)
        shoulder = self._shoulder(pose)
        bow_rest = shoulder + self._rest(pose, self.support_chain.bones[-1]) * arm
        hand_rest = shoulder + self._rest(pose, self.hand_chain.bones[-1]) * arm
        bow_hand = bow_rest.lerp(shoulder + aim * (0.95 * arm), raised)
        at_string = bow_hand - aim * (2.0 * self.unit)
        full_draw = shoulder + aim * (0.1 * arm) + Vec2(0.0, -0.05 * arm)
        if self._clinging and not self._frees_support:
            bow_hand = bow_rest
            at_string = bow_hand - aim * (2.0 * self.unit)
            full_draw = bow_hand - aim * (self.HANG_DRAW * arm)
        string_hand = hand_rest.lerp(at_string, raised).lerp(full_draw, drawn)
        targets = {self.support_chain.name: bow_hand, self.hand_chain.name: string_hand}
        self._solve(pose, targets, skip)

    def nock(self, transforms: dict[str, BoneTransform], facing: int) -> tuple[Vec2, Vec2]:
        """Where the arrow sits on the string, and the way it points."""
        return (
            transforms[self.hand_chain.bones[-1]].end,
            Vec2.from_angle(_world_angle(self.angle, facing)),
        )

    def strokes(
        self, transforms: dict[str, BoneTransform], facing: int, slung: bool = False
    ) -> list[Stroke]:
        if slung or not self.held:
            low, high = self._back_line(transforms, facing, 4.0 * self.unit, 6.0 * self.unit)
            middle = low.lerp(high, 0.5)
            up = (high - low).normalized()
            return self._bow(middle, up.rotated(facing * math.pi / 2), up, None)
        grip = transforms[self.support_chain.bones[-1]].end
        aim = Vec2.from_angle(_world_angle(self.angle, facing))
        up = aim.rotated(-facing * math.pi / 2)
        nock = transforms[self.hand_chain.bones[-1]].end if self.nocked else None
        return self._bow(grip, aim, up, nock)

    def _bow(self, grip: Vec2, aim: Vec2, up: Vec2, nock: Vec2 | None) -> list[Stroke]:
        s, limb = self.unit, self.limb
        tips = [grip + up * (side * limb) - aim * (3.0 * s) for side in (1, -1)]
        bends = [grip + up * (side * 0.55 * limb) - aim * (0.6 * s) for side in (1, -1)]
        string_mid = nock if nock is not None else tips[0].lerp(tips[1], 0.5)
        strokes = [
            Stroke(tips[0], bends[0], 1.5 * s, "wood"),
            Stroke(bends[0], grip, 1.7 * s, "wood"),
            Stroke(grip, bends[1], 1.7 * s, "wood"),
            Stroke(bends[1], tips[1], 1.5 * s, "wood"),
            Stroke(tips[0], string_mid, 0.5 * s, "string"),
            Stroke(string_mid, tips[1], 0.5 * s, "string"),
        ]
        if nock is not None:
            point = nock + aim * self.arrow
            strokes += [
                Stroke(nock, point, 0.9 * s, "wood"),
                Stroke(point - aim * (2.0 * s), point, 1.8 * s, "steel"),
            ]
        return strokes


class HolyStaff(_Released):
    """A cleric's staff topped with a white orb, planted upright in front; a blessing
    lifts it high overhead and lets the healing pulse go at the top."""

    name = "holy staff"
    size = 1.5
    duration = 0.9
    release_time = 0.35
    length = 26.0
    REST = Key(0.0, Vec2(0.35, 0.5), -math.pi / 2 + 0.1)
    RAISED = Key(0.3, Vec2(0.15, -0.95), -math.pi / 2, torso=-0.15, head=-0.25)

    def __init__(self, layout: BipedLayout) -> None:
        super().__init__(layout)
        self.length = HolyStaff.length * self.unit
        self.angle = self.REST.angle

    def _hold(self, pose: Pose, skip: frozenset[str]) -> None:
        key = self.REST
        if self.time is not None:
            held = Key(0.55, self.RAISED.hand, self.RAISED.angle, self.RAISED.torso, -0.2)
            back = Key(self.duration, self.REST.hand, self.REST.angle)
            key = _sample((self.REST, self.RAISED, held, back), self.time)
        layout = self.layout
        pose.angles[layout.torso] += key.torso
        pose.angles[layout.head] += key.head
        shoulder = self._shoulder(pose)
        self._solve(pose, {self.hand_chain.name: shoulder + key.hand * self.arm_length}, skip)
        self.angle = key.angle

    def top(self, transforms: dict[str, BoneTransform], facing: int) -> Vec2:
        grip = transforms[self.hand_chain.bones[-1]].end
        return grip + Vec2.from_angle(_world_angle(self.angle, facing), 0.6 * self.length)

    def _held(self, grip: Vec2, direction: Vec2, facing: int) -> list[Stroke]:
        return self._staff(grip - direction * (0.4 * self.length), direction)

    def _slung(self, transforms: dict[str, BoneTransform], facing: int) -> list[Stroke]:
        low, high = self._back_line(transforms, facing, 6.0 * self.unit, 0.0)
        return self._staff(low, (high - low).normalized())

    def _staff(self, butt: Vec2, direction: Vec2) -> list[Stroke]:
        s = self.unit
        top = butt + direction * self.length
        return [
            Stroke(butt, top, 1.6 * s, "wood"),
            Stroke(top, top + direction * (0.1 * s), 5.0 * s, "holy"),
        ]


class DruidStaff(_Released):
    """A druid's gnarled staff, forked and leafing at the top, planted upright in front.
    The attack lifts it and drives the butt down into the ground, which sends the vine
    up at the moment of impact."""

    name = "druid staff"
    size = 1.5
    duration = 0.8
    release_time = 0.32
    length = 26.0
    REST = Key(0.0, Vec2(0.35, 0.5), -math.pi / 2 + 0.1)
    LIFTED = Key(0.2, Vec2(0.3, -0.35), -math.pi / 2, torso=-0.15, head=-0.1)
    DRIVEN = Key(0.32, Vec2(0.5, 0.85), -math.pi / 2 + 0.15, torso=0.35, head=0.2)

    def __init__(self, layout: BipedLayout) -> None:
        super().__init__(layout)
        self.length = DruidStaff.length * self.unit
        self.angle = self.REST.angle

    def _hold(self, pose: Pose, skip: frozenset[str]) -> None:
        key = self.REST
        if self.time is not None:
            held = Key(0.5, self.DRIVEN.hand, self.DRIVEN.angle, self.DRIVEN.torso, 0.1)
            back = Key(self.duration, self.REST.hand, self.REST.angle)
            key = _sample((self.REST, self.LIFTED, self.DRIVEN, held, back), self.time)
        layout = self.layout
        pose.angles[layout.torso] += key.torso
        pose.angles[layout.head] += key.head
        shoulder = self._shoulder(pose)
        self._solve(pose, {self.hand_chain.name: shoulder + key.hand * self.arm_length}, skip)
        self.angle = key.angle

    def _held(self, grip: Vec2, direction: Vec2, facing: int) -> list[Stroke]:
        return self._staff(grip - direction * (0.4 * self.length), direction, facing)

    def _slung(self, transforms: dict[str, BoneTransform], facing: int) -> list[Stroke]:
        low, high = self._back_line(transforms, facing, 6.0 * self.unit, 0.0)
        return self._staff(low, (high - low).normalized(), -facing)

    def _staff(self, butt: Vec2, direction: Vec2, facing: int) -> list[Stroke]:
        s = self.unit
        top = butt + direction * self.length
        side = direction.rotated(facing * math.pi / 2)
        knot = butt + direction * (0.55 * self.length) + side * (0.6 * s)
        fork = top - direction * (3.0 * s)
        prong = top + side * (2.6 * s) + direction * (1.0 * s)
        curl = top - side * (1.8 * s) + direction * (1.6 * s)
        strokes = [
            Stroke(butt, knot, 1.8 * s, "wood"),
            Stroke(knot, fork, 1.8 * s, "wood"),
            Stroke(fork, prong, 1.3 * s, "wood"),
            Stroke(fork, curl, 1.3 * s, "wood"),
        ]
        for base, angle, length in ((prong, 0.6, 3.2), (curl, -0.7, 2.8), (fork, 1.4, 2.6)):
            along = Vec2.from_angle(direction.angle() + angle * facing)
            tip = base + along * (length * s)
            across = along.rotated(math.pi / 2) * (0.9 * s)
            middle = base.lerp(tip, 0.5)
            leaf = (base, middle + across, tip, middle - across)
            strokes.append(Stroke(base, tip, 0.3 * s, "leaf", leaf))
        return strokes


GOBLIN_HUNCH = 0.45


def _hunch(layout: BipedLayout, pose: Pose) -> None:
    pose.angles[layout.torso] += GOBLIN_HUNCH
    pose.angles[layout.head] -= GOBLIN_HUNCH * 0.8


class GoblinSword(Sword):
    """A hunched goblin's short sword: the same overhead chop, reporting the moment
    the blade lands so the wielder can deal the hit."""

    strike_time = Sword.STRIKE.time
    held_modes = frozenset({PoseMode.WALK, PoseMode.AIR, PoseMode.CLIMB})
    cling_modes = frozenset()

    def __init__(self, layout: BipedLayout) -> None:
        super().__init__(layout)
        self._struck = False
        self._pending = False

    def start(self) -> bool:
        started = super().start()
        if started:
            self._struck = False
        return started

    def take_strike(self) -> bool:
        """True once per swing, on the step the blade comes down."""
        pending, self._pending = self._pending, False
        return pending

    def apply(self, pose: Pose, mode: PoseMode, dt: float, skip: frozenset[str]) -> None:
        if self.time is not None and not self._struck and self.time + dt >= self.strike_time:
            self._struck = self._pending = True
        super().apply(pose, mode, dt, skip)

    def _hold(self, pose: Pose, skip: frozenset[str]) -> None:
        _hunch(self.layout, pose)
        super()._hold(pose, skip)


class SpearThrower(VialThrower):
    """The same hunched overhand throw as the vial lob, with a spear: carried point-up
    over the shoulder, levelled during the wind-up, gone once thrown until the arm
    comes back round with the next one."""

    name = "spears"
    held_modes = frozenset({PoseMode.WALK, PoseMode.CLIMB})
    cling_modes = frozenset()
    length = 40.0

    def __init__(self, layout: BipedLayout) -> None:
        super().__init__(layout)
        self.length = SpearThrower.length * self.scale

    @property
    def in_hand(self) -> bool:
        return self.time is None or self.time < self.release_time or self.time > self.duration - 0.1

    def spear_angle(self) -> float:
        """Canonical angle of the spear in hand (facing +x)."""
        if self.time is None:
            return -1.25
        level = smoothstep(clamp(self.time / self.release_time, 0.0, 1.0))
        return -1.25 + (1.25 - 0.35) * level

    def strokes(
        self, transforms: dict[str, BoneTransform], facing: int, slung: bool = False
    ) -> list[Stroke]:
        s = self.scale
        if slung or not self.held:
            low, high = self._back_line(transforms, facing, 6.0 * s, 14.0 * s)
            along = (high - low).normalized()
            return self._spear(low, along, self.length)
        if not self.in_hand:
            return []
        grip = transforms[self.hand_chain.bones[-1]].end
        direction = Vec2.from_angle(_world_angle(self.spear_angle(), facing))
        return self._spear(grip - direction * (self.length * 0.4), direction, self.length)

    def _spear(self, butt: Vec2, direction: Vec2, length: float) -> list[Stroke]:
        s = self.scale
        tip = butt + direction * length
        return [
            Stroke(butt, tip - direction * (5.0 * s), 3.0 * s, "wood"),
            Stroke(tip - direction * (6.0 * s), tip, 4.5 * s, "steel"),
        ]


class Banner(Weapon):
    """A goblin standard: a tall pole held upright in front, never used to fight.
    The cloth is drawn separately (see `cloth`), streaming back as the bearer runs."""

    name = "banner"
    held_modes = frozenset({PoseMode.WALK})
    cling_modes = frozenset()
    pole = 42.0

    def __init__(self, layout: BipedLayout) -> None:
        super().__init__(layout)
        self.pole = Banner.pole * self.scale
        self.clock = 0.0
        self.angle = -math.pi / 2 + 0.12

    def apply(self, pose: Pose, mode: PoseMode, dt: float, skip: frozenset[str]) -> None:
        self.clock += dt
        super().apply(pose, mode, dt, skip)

    def _hold(self, pose: Pose, skip: frozenset[str]) -> None:
        _hunch(self.layout, pose)
        shoulder = self._shoulder(pose)
        sway = 0.04 * math.sin(self.clock * 7.0)
        self.angle = -math.pi / 2 + 0.12 + sway
        self._solve(
            pose, {self.hand_chain.name: shoulder + Vec2(0.45, 0.35) * self.arm_length}, skip
        )

    def top(self, transforms: dict[str, BoneTransform], facing: int) -> tuple[Vec2, Vec2]:
        """The pole's top and its upward direction, as drawn."""
        if not self.held:
            low, high = self._back_line(transforms, facing, 6.0 * self.scale, 0.0)
            along = (high - low).normalized()
            return low + along * self.pole, along
        grip = transforms[self.hand_chain.bones[-1]].end
        direction = Vec2.from_angle(_world_angle(self.angle, facing))
        return grip + direction * (self.pole * 0.75), direction

    def _held(self, grip: Vec2, direction: Vec2, facing: int) -> list[Stroke]:
        s = self.scale
        return [
            Stroke(
                grip - direction * (self.pole * 0.25),
                grip + direction * (self.pole * 0.75),
                1.6 * s,
                "wood",
            )
        ]

    def _slung(self, transforms: dict[str, BoneTransform], facing: int) -> list[Stroke]:
        s = self.scale
        low, high = self._back_line(transforms, facing, 6.0 * s, 0.0)
        along = (high - low).normalized()
        return [Stroke(low, low + along * self.pole, 1.6 * s, "wood")]


class TwinScimitars(Weapon):
    """A drow's pair of curved scimitars, carried low and crossed in front; the attack
    is a high cut with the right blade and, a beat later, one with the left. Each cut
    reports the moment it lands (`take_strike`) so the wielder can deal the hit."""

    name = "scimitars"
    size = 1.0
    duration = 0.56
    held_modes = frozenset({PoseMode.WALK, PoseMode.AIR, PoseMode.CLIMB})
    cling_modes = frozenset()
    blade = 13.0
    curve = 2.6
    """How far the blade bows back off the straight line from hilt to tip."""
    second = 0.18
    """Seconds after the right-hand cut that the left one starts."""
    strike_time = 0.17
    trail_window = (0.11, 0.24)
    GUARD = 0.05
    """A light ready lean: enough to show the blades, not a hunched scramble."""
    CUT = (
        Key(0.0, Vec2(0.5, 0.55), -0.75),
        Key(0.09, Vec2(-0.05, -0.65), -2.5, torso=-0.2, head=-0.08),
        Key(0.17, Vec2(1.0, 0.25), 0.55, torso=0.22, head=0.1),
        Key(0.3, Vec2(0.5, 0.55), -0.75),
    )

    def __init__(self, layout: BipedLayout) -> None:
        super().__init__(layout)
        self.blade = TwinScimitars.blade * self.unit
        self.curve = TwinScimitars.curve * self.unit
        self.angle = self.off_angle = -0.75
        self._pending = 0
        self._struck = 0

    @property
    def trail_active(self) -> bool:
        if self.time is None:
            return False
        low, high = self.trail_window
        return low <= self.time <= high or low <= self.time - self.second <= high

    def start(self) -> bool:
        started = super().start()
        if started:
            self._struck = 0
        return started

    def cancel(self) -> None:
        super().cancel()
        self._pending = 0

    def take_strike(self) -> bool:
        """True once for each cut, on the step its blade comes down."""
        if self._pending <= 0:
            return False
        self._pending -= 1
        return True

    def apply(self, pose: Pose, mode: PoseMode, dt: float, skip: frozenset[str]) -> None:
        if self.time is not None:
            for k, at in enumerate((self.strike_time, self.strike_time + self.second)):
                if self._struck == k and self.time + dt >= at:
                    self._struck += 1
                    self._pending += 1
        super().apply(pose, mode, dt, skip)

    def _mirror_angles(self, amount: float) -> None:
        super()._mirror_angles(amount)
        self.off_angle += (math.pi - 2.0 * self.off_angle) * amount

    def _key(self, time: float | None) -> Key:
        if time is None or time < 0.0 or time >= self.CUT[-1].time:
            return self.CUT[0]
        return _sample(self.CUT, time)

    def _hold(self, pose: Pose, skip: frozenset[str]) -> None:
        main = self._key(self.time)
        off = self._key(None if self.time is None else self.time - self.second)
        torso = self.layout.torso
        pose.angles[torso] += self.GUARD + main.torso + 0.6 * off.torso
        pose.angles[self.layout.head] += main.head
        shoulder = self._shoulder(pose)
        targets = {
            self.hand_chain.name: shoulder + main.hand * self.arm_length,
            self.support_chain.name: shoulder + (off.hand + Vec2(-0.15, 0.08)) * self.arm_length,
        }
        self._solve(pose, targets, skip)
        self.angle, self.off_angle = main.angle, off.angle

    def tips(self, transforms: dict[str, BoneTransform], facing: int) -> list[Vec2]:
        """Both blade tips, as drawn (off hand first)."""
        tips = []
        for chain, angle in ((self.support_chain, self.off_angle), (self.hand_chain, self.angle)):
            grip = transforms[chain.bones[-1]].end
            tips.append(self._shape(grip, Vec2.from_angle(_world_angle(angle, facing)), facing)[1])
        return tips

    def strokes(
        self, transforms: dict[str, BoneTransform], facing: int, slung: bool = False
    ) -> list[Stroke]:
        if slung or not self.held:
            hip = transforms[self.layout.torso].start
            down = Vec2(-facing * 0.5, 1.0).normalized()
            behind = Vec2(-facing * 1.5 * self.unit, 0.0)
            return [
                *self._scimitar(hip + behind, down, -facing),
                *self._scimitar(hip - behind, down.rotated(facing * 0.25), -facing),
            ]
        strokes = []
        for chain, angle in ((self.support_chain, self.off_angle), (self.hand_chain, self.angle)):
            grip = transforms[chain.bones[-1]].end
            strokes += self._scimitar(grip, Vec2.from_angle(_world_angle(angle, facing)), facing)
        return strokes

    def _shape(self, grip: Vec2, direction: Vec2, facing: int) -> tuple[list[Vec2], Vec2]:
        """The blade's outline (back edge out to the tip, then the cutting edge back) and
        its tip: it bows away from the edge, widening toward the point like a falchion."""
        s = self.unit
        back = direction.rotated(-facing * math.pi / 2)
        guard = grip + direction * (1.2 * s)
        spine, edge = [], []
        count = 8
        for i in range(count + 1):
            t = i / count
            bow = self.curve * (t * t)
            middle = guard + direction * (self.blade * t) + back * bow
            width = (0.9 + 0.8 * math.sin(math.pi * min(1.0, t * 1.15))) * s
            spine.append(middle + back * (0.35 * width))
            edge.append(middle - back * (0.65 * width))
        tip = guard + direction * (self.blade * 1.04) + back * (self.curve * 1.15)
        return [*spine, tip, *reversed(edge)], tip

    def _scimitar(self, grip: Vec2, direction: Vec2, facing: int) -> list[Stroke]:
        s = self.unit
        across = direction.rotated(math.pi / 2) * (2.0 * s)
        guard = grip + direction * (1.0 * s)
        outline, _ = self._shape(grip, direction, facing)
        return [
            Stroke(grip - direction * (2.6 * s), grip, 1.5 * s, "hilt"),
            Stroke(guard - across, guard + across, 1.3 * s, "hilt"),
            Stroke(guard, guard, 0.5 * s, "steel", tuple(outline)),
        ]
