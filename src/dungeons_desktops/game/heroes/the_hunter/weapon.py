"""A long scoped rifle held with both hands, using the shared rifle animation."""

import math

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.heroes.the_hunter.combat import Gun
from dungeons_desktops.rig.equipment import Rifle, Stroke
from dungeons_desktops.rig.locomotion import PoseMode


class SniperRifle(Rifle):
    name = "sniper rifle"
    two_handed = True
    held_modes = frozenset({PoseMode.WALK, PoseMode.AIR})
    duration = 1.0
    lower_from = 0.7
    shot_times = (0.45,)
    CARRY_GRIP = Vec2(0.12, 0.5)
    CARRY_ANGLE = -0.25
    AIM_GRIP = Vec2(0.05, 0.22)

    def __init__(self, layout) -> None:
        super().__init__(layout)
        self.length = 36.0 * self.scale
        self.stock = 10.0 * self.scale
        self.aim = 0.0

    def cancel(self) -> None:
        super().cancel()
        self._pending = 0
        self.since_shot = math.inf

    def _mirror_angles(self, amount: float) -> None:
        super()._mirror_angles(amount)
        self.aim_angle += (math.pi - 2 * self.aim_angle) * amount

    def _hold(self, pose, skip) -> None:
        amount = self._aim_amount()
        recoil = math.exp(-self.since_shot / 0.06) if self.busy else 0.0
        torso, head = self.layout.torso, self.layout.head
        pose.angles[torso] = pose.angles[torso] * (1 - amount) + 0.1 * amount - 0.08 * recoil
        pose.angles[head] = pose.angles[head] * (1 - amount) + 0.2 * amount
        shoulder = self._shoulder(pose)
        grip = shoulder + self.CARRY_GRIP.lerp(self.AIM_GRIP, amount) * self.arm_length
        grip -= Vec2(2.0 * recoil * self.scale, 0)
        self.aim_angle = self.CARRY_ANGLE * (1 - amount) + self.aim * amount
        self.angle = self.aim_angle - 0.12 * recoil
        self._solve(pose, {
            self.hand_chain.name: grip,
            self.support_chain.name: grip + Vec2.from_angle(self.angle) * self.support,
        }, skip)

    def _held(self, grip: Vec2, direction: Vec2, facing: int) -> list[Stroke]:
        s = self.scale
        down = direction.rotated(facing * math.pi / 2)

        def at(x, y):
            return grip + (direction * x + down * y) * s

        stock = tuple(at(x, y) for x, y in (
            (-10, -1.6), (-3, -1.1), (0.5, 0), (-1.8, 3.2), (-4, 2.7), (-10, 2.5),
        ))
        strokes = [
            Stroke(at(-10, 0), grip, 0.65 * s, "wood", stock),
            Stroke(at(-10, -1.5), at(-10, 2.5), 1.2 * s, "gunmetal"),
            Stroke(at(-2, 0), at(13, 0), 3.0 * s, "gunmetal"),
            Stroke(at(4, 1.1), at(14, 1.1), 2.0 * s, "wood"),
            Stroke(at(13, -0.4), at(36, -0.4), 1.4 * s, "metal"),
            Stroke(at(33, -0.4), at(36, -0.4), 2.3 * s, "gunmetal"),
            Stroke(at(2, 0.7), at(1, 4.0), 2.0 * s, "gunmetal"),
            Stroke(at(7, 1), at(7, 4.0), 2.5 * s, "gunmetal"),
            Stroke(at(2, -1.2), at(2, -3.4), 1.0 * s, "metal"),
            Stroke(at(9, -1.2), at(9, -3.4), 1.0 * s, "metal"),
            Stroke(at(-1, -3.8), at(12, -3.8), 2.2 * s, "gunmetal"),
            Stroke(at(10, -3.8), at(13, -3.8), 3.4 * s, "metal"),
            Stroke(at(13, -4.6), at(13, -3.0), 0.65 * s, "scope_glass"),
            Stroke(at(-1, -3.8), at(1, -3.8), 2.8 * s, "metal"),
        ]
        if self.since_shot < 0.06:
            strokes.append(Stroke(at(36, -0.4), at(43, -0.4), 2.5 * s, "flash"))
        return strokes

    def _slung(self, transforms, facing) -> list[Stroke]:
        low, high = self._back_line(transforms, facing, 2.0, 4.0)
        direction = (high - low).normalized().rotated(facing * 0.3)
        return self._held(low + direction * self.stock, direction, facing)


def shotgun_strokes(grip, direction, facing, scale, flash=False) -> list[Stroke]:
    side = direction.rotated(facing * math.pi / 2)

    def at(x, y):
        return grip + (direction * x + side * y) * scale

    stock = tuple(at(x, y) for x, y in ((-8, -2), (-8, 2), (-1, 1), (2, 0), (0, -1.4)))
    strokes = [
        Stroke(at(-8, 0), at(1, 0), 0.7 * scale, "wood", stock),
        Stroke(at(-8, -2), at(-8, 2), 1.0 * scale, "gunmetal"),
        Stroke(at(0, 0), at(8, 0), 3.0 * scale, "gunmetal"),
        Stroke(at(8, -0.8), at(23, -0.8), 1.5 * scale, "metal"),
        Stroke(at(8, 0.9), at(22, 0.9), 1.5 * scale, "gunmetal"),
        Stroke(at(8, 0.7), at(14, 0.7), 2.5 * scale, "wood"),
    ]
    if flash:
        for spread in (-4, 0, 4):
            strokes.append(Stroke(at(23, 0), at(34, spread), 2 * scale, "flash"))
    return strokes


def pistol_strokes(grip, direction, facing, scale, flash=False) -> list[Stroke]:
    down = direction.rotated(facing * math.pi / 2)

    def at(x, y):
        return grip + (direction * x + down * y) * scale

    strokes = [
        Stroke(at(-1, 0), at(-3, 4), 2.4 * scale, "wood"),
        Stroke(at(-2, -1), at(4, -1), 2.7 * scale, "gunmetal"),
        Stroke(at(3, -1), at(11, -1), 1.8 * scale, "metal"),
        Stroke(at(0, 0), at(2, 2), 0.8 * scale, "metal"),
    ]
    if flash:
        strokes.append(Stroke(at(11, -1), at(17, -1), 2 * scale, "flash"))
    return strokes


class HunterArsenal(SniperRifle):
    """One active weapon animation; the other guns remain on the body."""

    def __init__(self, layout) -> None:
        super().__init__(layout)
        self.gun = Gun.SNIPER
        self.backpedalling = False

    def start_action(self, gun: Gun) -> bool:
        if self.busy:
            return False
        self.gun = gun
        self._pending = 0
        names = {Gun.SNIPER: "sniper rifle", Gun.SHOTGUN: "shotgun", Gun.PISTOLS: "twin pistols"}
        self.name = names[gun]
        self.duration = {Gun.SNIPER: 1.0, Gun.SHOTGUN: 0.45, Gun.PISTOLS: 0.4}[gun]
        self.shot_times = {Gun.SNIPER: (0.45,), Gun.SHOTGUN: (0.2,), Gun.PISTOLS: (0.1, 0.24)}[gun]
        self.raise_time = 0.3 if gun is Gun.SNIPER else 0.1
        self.lower_from = self.duration - 0.15
        self.stops_movement = gun is not Gun.PISTOLS
        self.length = {Gun.SNIPER: 36, Gun.SHOTGUN: 23, Gun.PISTOLS: 11}[gun] * self.scale
        return self.start()

    def take_releases(self) -> range:
        count = self.take_shots()
        return range(self._shots_taken - count, self._shots_taken)

    def _hold(self, pose, skip) -> None:
        if self.gun is not Gun.PISTOLS:
            super()._hold(pose, skip)
            return
        recoil = math.exp(-self.since_shot / 0.05)
        pose.angles[self.layout.torso] += -0.06 if self.backpedalling else 0.04
        shoulder = self._shoulder(pose)
        self.aim_angle = self.aim
        self.angle = self.aim - 0.08 * recoil
        forward = Vec2.from_angle(self.aim)
        down = forward.rotated(math.pi / 2)
        targets = {}
        for index, chain in enumerate((self.hand_chain, self.support_chain)):
            active = self._shots_taken > 0 and (self._shots_taken - 1) % 2 == index
            reach = (0.78 if index == 0 else 0.57) * self.arm_length - (recoil if active else 0)
            targets[chain.name] = shoulder + forward * reach + down * (1 if index == 0 else -1.5)
        self._solve(pose, targets, skip)

    def muzzle(self, transforms, facing, hand=0):
        if self.gun is not Gun.PISTOLS:
            return super().muzzle(transforms, facing)
        chain = self.hand_chain if hand == 0 else self.support_chain
        grip = transforms[chain.bones[-1]].end
        angle = self.angle if facing > 0 else math.pi - self.angle
        direction = Vec2.from_angle(angle)
        return grip + direction * self.length, direction

    def _held(self, grip, direction, facing):
        if self.gun is Gun.SHOTGUN:
            return shotgun_strokes(grip, direction, facing, self.scale, self.since_shot < 0.07)
        return super()._held(grip, direction, facing)

    def strokes(self, transforms, facing, slung=False):
        if self.gun is not Gun.PISTOLS:
            return super().strokes(transforms, facing, slung)
        if slung or not self.held:
            return []
        direction = Vec2.from_angle(self.angle if facing > 0 else math.pi - self.angle)
        strokes = []
        for index, chain in ((1, self.support_chain), (0, self.hand_chain)):
            flash = self.since_shot < 0.07 and (self._shots_taken - 1) % 2 == index
            strokes.extend(pistol_strokes(
                transforms[chain.bones[-1]].end, direction, facing, self.scale, flash,
            ))
        return strokes

    def slung_sniper(self, transforms, facing):
        low, high = self._back_line(transforms, facing, 2.0, 4.0)
        direction = (high - low).normalized().rotated(facing * 0.3)
        return [s for s in SniperRifle._held(self, low + direction * self.stock, direction, facing)
                if s.kind != "flash"]
