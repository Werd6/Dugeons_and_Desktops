"""Procedural hang from a ceiling for a biped, facing +x.

The figure hangs by its hands from a horizontal grip line (a window's underside or
the top of the screen), arms up, body below them and legs dangling. Going along,
it swings hand over hand: one hand holds while the body passes under it, then lets
go, dips and reaches ahead to a new hold, so one hand always grips. The body sways
like a pendulum with each reach and the legs trail and scissor.

All sizes come from the skeleton's bone lengths; `hang_depth` gives the matching
hands-to-feet distance the terrain should use.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from dungeons_desktops.core.geometry import Vec2, smoothstep
from dungeons_desktops.rig.biped import UP, BipedLayout
from dungeons_desktops.rig.ik import solve_two_bone
from dungeons_desktops.rig.skeleton import Pose, forward_kinematics

ARM_BEND = 0.9
"""Shoulder below the grip line, as a fraction of arm length (elbows slightly bent)."""
LEG_DROP = 0.92
"""Feet below the hip, as a fraction of leg length (knees slightly bent)."""
STRIDE = 0.95
"""Hand-over-hand stride as a fraction of arm length."""
STANCE = 0.62
"""Fraction of a cycle each hand holds on; above one half, so the hands overlap."""
REACH_DIP = 0.22
"""How far a reaching hand drops below the grip mid-swing, as a fraction of arm length."""
SWAY = 0.16
LEAN = 0.12
PIKE = -0.25
"""Resting body tilt: hips a little ahead of the shoulders."""
HEAD_BACK = 1.15
"""Head tipped back from upright (radians), looking up at the hands, so a big head
stays under the grip line instead of poking through it."""
HEAD_LIMIT = 0.8


def arm_length(layout: BipedLayout) -> float:
    return sum(layout.skeleton.bone(name).length for name in layout.arms[0].bones)


def hang_depth(layout: BipedLayout) -> float:
    """Grip line to feet when hanging still."""
    skeleton = layout.skeleton
    body = skeleton.bone(layout.pelvis).length + skeleton.bone(layout.torso).length
    return arm_length(layout) * ARM_BEND + body + layout.leg_length * LEG_DROP


@dataclass
class _Hold:
    x: float
    planted: float
    swing_from: float
    swinging: bool = False
    dip: float = 0.0


class HangDriver:
    def __init__(self, layout: BipedLayout) -> None:
        self.layout = layout
        self.arm = arm_length(layout)
        self.stride = STRIDE * self.arm
        self.phases = (0.0, 0.5)
        self.x = 0.0
        self.grip = 0.0
        self.cycle = 0.0
        self.time = 0.0
        self.motion = 0.0
        """Smoothed speed along the grip, -1..1 of full gait, for sway and lean."""
        self.holds = [_Hold(0.0, 0.0, 0.0) for _ in layout.arms]
        self.pose: Pose = layout.skeleton.rest_pose(Vec2(0.0, 0.0))

    def place(self, x: float, grip: float) -> None:
        self.x, self.grip = x, grip
        self.cycle = 0.0
        self.motion = 0.0
        quarter = self.stride * 0.25
        for i, hold in enumerate(self.holds):
            hx = x + (quarter if self.phases[i] == 0.0 else -quarter)
            hold.x = hold.planted = hold.swing_from = hx
            hold.swinging, hold.dip = False, 0.0
        self._solve(0.0)

    def shift(self, dx: float, dy: float) -> None:
        self.x += dx
        self.grip += dy
        for hold in self.holds:
            hold.x += dx
            hold.planted += dx
            hold.swing_from += dx

    def update(self, x: float, grip: float, dt: float) -> Pose:
        self.grip = grip
        delta = x - self.x
        self.x = x
        self.time += dt
        moving = abs(delta) > 1e-9
        if moving:
            direction = 1.0 if delta > 0 else -1.0
            self.cycle = (self.cycle + abs(delta) / self.stride) % 1.0
            for i, hold in enumerate(self.holds):
                self._step_hold(i, hold, direction)
        else:
            for i, hold in enumerate(self.holds):
                if hold.swinging or hold.dip > 0.0:
                    hold.x += (self._rest(i) - hold.x) * min(1.0, dt * 6.0)
                    hold.planted = hold.x
                    hold.dip *= max(0.0, 1.0 - dt * 8.0)
                    hold.swinging = False
        target = (1.0 if delta > 0 else -1.0) if moving else 0.0
        self.motion += (target - self.motion) * min(1.0, dt * 5.0)
        return self._solve(dt)

    def _rest(self, index: int) -> float:
        quarter = self.stride * 0.25
        return self.x + (quarter if self.phases[index] == 0.0 else -quarter)

    def _step_hold(self, index: int, hold: _Hold, direction: float) -> None:
        phase = (self.cycle + self.phases[index]) % 1.0
        swinging = phase >= STANCE
        if swinging and not hold.swinging:
            hold.swing_from = hold.x
        elif not swinging and hold.swinging:
            hold.planted = hold.x
        hold.swinging = swinging
        if not swinging:
            hold.x, hold.dip = hold.planted, 0.0
            return
        t = (phase - STANCE) / (1.0 - STANCE)
        remaining = (1.0 - t) * (1.0 - STANCE) * self.stride
        landing = self.x + direction * (remaining + STANCE * self.stride * 0.5)
        hold.x = hold.swing_from + (landing - hold.swing_from) * smoothstep(t)
        hold.dip = REACH_DIP * self.arm * math.sin(math.pi * t)

    def _solve(self, dt: float) -> Pose:
        layout = self.layout
        skeleton = layout.skeleton
        pelvis = skeleton.bone(layout.pelvis).length
        torso = skeleton.bone(layout.torso).length
        leg = layout.leg_length

        idle = 1.0 - min(1.0, abs(self.motion))
        swing = math.sin(math.tau * self.cycle * 2.0) * abs(self.motion)
        drift = math.sin(self.time * 1.9) * idle
        tilt = PIKE + SWAY * (0.6 * swing + 0.35 * drift) + LEAN * self.motion

        shoulder = Vec2(self.x, self.grip + ARM_BEND * self.arm)
        body_angle = UP + tilt
        bend = -0.04 * swing
        hip = (
            shoulder
            - Vec2.from_angle(body_angle + bend, torso)
            - Vec2.from_angle(body_angle, pelvis)
        )

        pose = self.pose
        pose.root = hip
        pose.angles[layout.pelvis] = body_angle
        pose.angles[layout.torso] = bend
        pose.angles[layout.head] = max(-HEAD_LIMIT, min(HEAD_LIMIT, -HEAD_BACK - tilt - bend))

        trail = -0.12 * self.motion
        for i, chain in enumerate(layout.legs):
            side = 1.0 if i == 0 else -1.0
            scissor = 0.14 * side * math.sin(math.tau * self.cycle) * abs(self.motion)
            kick = 0.08 * side * drift
            foot = hip + Vec2((trail + scissor + kick + 0.06) * leg, LEG_DROP * leg)
            solve_two_bone(skeleton, pose, chain, foot)
        for hold, chain in zip(self.holds, layout.arms, strict=True):
            solve_two_bone(skeleton, pose, chain, Vec2(hold.x, self.grip + hold.dip))
        return pose

    def hand_positions(self) -> list[Vec2]:
        transforms = forward_kinematics(self.layout.skeleton, self.pose)
        return [transforms[chain.bones[-1]].end for chain in self.layout.arms]
