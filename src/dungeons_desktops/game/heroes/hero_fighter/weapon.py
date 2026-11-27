"""The Soulforger's divine trident and shield."""

import math

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep
from dungeons_desktops.rig.biped import BipedLayout
from dungeons_desktops.rig.equipment import HammerAndShield, Key, Stroke
from dungeons_desktops.rig.skeleton import BoneTransform, Pose


class SoulforgedTridentAndShield(HammerAndShield):
    """A silver trident alternating broad cuts with direct thrusts."""

    name = "soulforged trident and shield"
    size = 1.75
    duration = 0.58
    hit_time = 0.27
    haft = 24.0
    GUARD = Vec2(0.58, 0.58)
    REST_ANGLE = -1.12
    SLASH_WINDUP = Key(0.16, Vec2(-0.35, -0.62), -2.35, torso=-0.24, head=-0.08)
    SLASH_STRIKE = Key(0.29, Vec2(0.88, 0.24), 0.62, torso=0.32, head=0.1)
    SLASH_FOLLOW = Key(0.41, Vec2(0.52, 0.62), 1.32, torso=0.24, head=0.06)
    STAB_WINDUP = Key(0.15, Vec2(-0.28, 0.02), -0.06, torso=-0.2, head=-0.04)
    STAB_STRIKE = Key(0.27, Vec2(1.0, 0.02), 0.0, torso=0.28, head=0.08)
    STAB_FOLLOW = Key(0.38, Vec2(0.76, 0.08), 0.06, torso=0.16)
    WINDUP = SLASH_WINDUP
    STRIKE = SLASH_STRIKE
    FOLLOW = SLASH_FOLLOW
    trail_window = (0.16, 0.36)

    def __init__(self, layout: BipedLayout) -> None:
        super().__init__(layout)
        self.haft = type(self).haft * self.unit
        self.blade = self.haft + 2.5 * self.unit
        self.hero_action: str | None = None
        self.hero_progress = 0.0
        self.hero_aim = 0.0
        self.melee_style = "slash"
        self._stab_next = False

    def start(self) -> bool:
        started = super().start()
        if not started:
            return False
        self.melee_style = "stab" if self._stab_next else "slash"
        self._stab_next = not self._stab_next
        if self.melee_style == "stab":
            self.WINDUP = self.STAB_WINDUP
            self.STRIKE = self.STAB_STRIKE
            self.FOLLOW = self.STAB_FOLLOW
            self.trail_window = (0.17, 0.31)
        else:
            self.WINDUP = self.SLASH_WINDUP
            self.STRIKE = self.SLASH_STRIKE
            self.FOLLOW = self.SLASH_FOLLOW
            self.trail_window = (0.17, 0.41)
        return True

    def set_hero_action(self, action: str, progress: float, aim: float = 0.0) -> None:
        self.hero_action = action
        self.hero_progress = clamp(progress, 0.0, 1.0)
        self.hero_aim = aim

    def clear_hero_action(self) -> None:
        self.hero_action = None
        self.hero_progress = 0.0
        self.hero_aim = 0.0

    def _hold(self, pose: Pose, skip: frozenset[str]) -> None:
        if self.hero_action is not None:
            self._hero_hold(pose, skip)
            return
        if self.time is not None:
            super()._hold(pose, skip)
            return
        self.angle = -0.25
        shoulder = self._shoulder(pose)
        self._solve(
            pose,
            {self.support_chain.name: shoulder + self.GUARD * self.arm_length},
            skip,
        )

    def _hero_hold(self, pose: Pose, skip: frozenset[str]) -> None:
        action = self.hero_action
        t = smoothstep(self.hero_progress)
        main = Vec2(0.35, 0.18)
        support = self.GUARD
        angle = self.REST_ANGLE
        torso = 0.0
        if action == "throw":
            main = Vec2(-0.42, -0.58).lerp(Vec2(0.88, -0.18), t)
            angle = -2.25 + (self.hero_aim + 2.25) * t
            torso = -0.22 + 0.5 * t
        elif action == "mark":
            main = Vec2(0.08, -0.88)
            support = Vec2(-0.18, -0.72)
            angle = -math.pi / 2
            torso = -0.12 * math.sin(math.pi * t)
        elif action == "leap":
            main = Vec2(-0.24, -0.78)
            support = Vec2(0.48, 0.42)
            angle = -2.15
            torso = -0.18
        elif action == "trident_slice":
            swing = math.sin(math.pi * t)
            main = Vec2(-0.20 + 0.98 * t, -0.62 + 0.92 * t)
            angle = -2.35 + 3.25 * t
            torso = 0.28 * swing
        elif action == "trident_stab":
            thrust = smoothstep(clamp(t / 0.72, 0.0, 1.0))
            main = Vec2(-0.3, 0.0).lerp(Vec2(1.0, 0.02), thrust)
            support = Vec2(0.46, 0.34)
            angle = -0.06 + 0.06 * thrust
            torso = -0.18 + 0.46 * thrust
        elif action == "shield_slice":
            swing = math.sin(math.pi * t)
            main = Vec2(0.18, -0.35)
            support = Vec2(0.42, 0.30).lerp(Vec2(1.0, 0.02), swing)
            angle = -1.35
            torso = 0.22 * swing
        pose.angles[self.layout.torso] += torso
        shoulder = self._shoulder(pose)
        self._solve(
            pose,
            {
                self.hand_chain.name: shoulder + main * self.arm_length,
                self.support_chain.name: shoulder + support * self.arm_length,
            },
            skip,
        )
        self.angle = angle

    def _hammer(
        self, butt: Vec2, direction: Vec2, scale: float = 1.0
    ) -> list[Stroke]:
        """Draw the trident through the hook used by the shared shield rig."""
        s = self.unit * scale
        crown = butt + direction * (self.haft * scale)
        across = direction.rotated(math.pi / 2)
        side_root = crown - direction * (1.5 * s)
        left = crown + direction * (4.0 * s) + across * (3.2 * s)
        right = crown + direction * (4.0 * s) - across * (3.2 * s)
        center = crown + direction * (6.0 * s)
        lines = (
            (butt, crown),
            (side_root, crown + across * (3.2 * s)),
            (side_root, crown - across * (3.2 * s)),
            (crown + across * (3.2 * s), left),
            (crown - across * (3.2 * s), right),
            (crown, center),
        )
        return [
            *[Stroke(a, b, 2.3 * s, "divine_glow") for a, b in lines],
            *[Stroke(a, b, 1.0 * s, "divine") for a, b in lines],
            *[Stroke(a, b, 0.25 * s, "divine_core") for a, b in lines],
        ]

    def trident_center(self, transforms: dict[str, BoneTransform], facing: int) -> Vec2:
        return transforms[self.hand_chain.bones[-1]].end

    def trident_strokes(
        self, center: Vec2, direction: Vec2, scale: float = 1.0
    ) -> list[Stroke]:
        butt = center - direction * (self.haft * scale * 0.5)
        return self._hammer(butt, direction, scale)

    def strokes(
        self, transforms: dict[str, BoneTransform], facing: int, slung: bool = False
    ) -> list[Stroke]:
        if slung or not self.held:
            return super().strokes(transforms, facing, slung)
        s = self.unit
        grip = transforms[self.hand_chain.bones[-1]].end
        angle = self.angle if facing > 0 else math.pi - self.angle
        direction = Vec2.from_angle(angle)
        shield_hand = transforms[self.support_chain.bones[-1]].end
        shield_center = shield_hand + Vec2(facing * 5.4 * s, -3.2 * s)
        return [
            *self._shield(shield_center),
            *self.trident_strokes(grip, direction),
        ]

    def _shield(self, center: Vec2) -> list[Stroke]:
        s = self.unit
        outline = (
            Vec2(-5.3 * s, -5.2 * s),
            Vec2(5.3 * s, -5.2 * s),
            Vec2(5.0 * s, 1.7 * s),
            Vec2(0.0, 8.1 * s),
            Vec2(-5.0 * s, 1.7 * s),
        )
        rim = tuple(center + point for point in outline)
        face = tuple(center + point * 0.78 + Vec2(0.0, -0.2 * s) for point in outline)
        return [
            Stroke(center, center, 0.8 * s, "hero_shield_trim", rim),
            Stroke(center, center, 0.2 * s, "hero_shield", face),
            Stroke(
                center + Vec2(-2.7 * s, -1.8 * s),
                center + Vec2(2.7 * s, -1.8 * s),
                1.3 * s,
                "hero_shield_strap",
            ),
            Stroke(
                center + Vec2(-2.4 * s, 1.4 * s),
                center + Vec2(2.4 * s, 1.4 * s),
                1.3 * s,
                "hero_shield_strap",
            ),
            Stroke(center, center, 2.1 * s, "hero_shield_trim"),
        ]
