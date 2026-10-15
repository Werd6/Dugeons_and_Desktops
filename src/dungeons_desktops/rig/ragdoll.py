"""2D ragdoll built from the same bones as the animated skeleton.

Each bone is a rigid segment made of two Verlet points, which gives it mass,
velocity, and spin. Pins join each child's start to the parent point it hangs
from, joint limits keep elbows and knees from folding backwards, and a ground
line and solid boxes stop points. While the motors are on, the segments copy an
animated pose each step (kinematic), so releasing them carries the animation's
momentum.

Joint limits are defined for a figure facing +x. Set `facing = -1` for a figure
that was animated mirrored, so its knees and elbows bend the mirrored way.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from dungeons_desktops.core.geometry import Rect, Vec2, wrap_angle
from dungeons_desktops.rig.skeleton import Pose, Skeleton, forward_kinematics


@dataclass(frozen=True)
class RagdollSettings:
    gravity: float = 700.0
    iterations: int = 12
    damping: float = 0.998
    ground_friction: float = 0.5
    limit_stiffness: float = 1.0
    max_speed: float = 1200.0
    rigid_passes: int = 6


def _angle_gradient(v: Vec2) -> Vec2:
    """Gradient of atan2(v) with respect to the vector's end point."""
    length_sq = v.length_sq()
    if length_sq < 1e-12:
        return Vec2(0.0, 0.0)
    return Vec2(-v.y / length_sq, v.x / length_sq)


class Ragdoll:
    def __init__(
        self,
        skeleton: Skeleton,
        ground_y: float,
        settings: RagdollSettings | None = None,
        end_radius: Mapping[str, float] | None = None,
    ) -> None:
        """`end_radius` keeps a bone's end point that far above the ground (e.g. a head)."""
        self.skeleton = skeleton
        self.ground_y = ground_y
        self.settings = settings or RagdollSettings()
        self.motors_on = True
        self.facing = 1
        self.obstacles: Sequence[Rect] = ()
        self._supported: set[int] = set()
        self._last_dt = 1.0 / 60.0

        self._pos: list[Vec2] = []
        self._prev: list[Vec2] = []
        self._inv_mass: list[float] = []
        self._radius: list[float] = []
        self._segment: dict[str, tuple[int, int]] = {}
        radii = end_radius or {}
        for bone in skeleton.bones:
            start = len(self._pos)
            for radius in (0.0, radii.get(bone.name, 0.0)):
                self._pos.append(Vec2(0.0, 0.0))
                self._prev.append(Vec2(0.0, 0.0))
                self._inv_mass.append(2.0 / bone.mass)
                self._radius.append(radius)
            self._segment[bone.name] = (start, start + 1)

        self._pins: list[tuple[int, int]] = []
        root_start: int | None = None
        for bone in skeleton.bones:
            start, _ = self._segment[bone.name]
            if bone.parent is None:
                if root_start is None:
                    root_start = start
                else:
                    self._pins.append((start, root_start))
            else:
                parent_start, parent_end = self._segment[bone.parent]
                self._pins.append((start, parent_start if bone.from_parent_start else parent_end))
        self._initialized = False

    def drive(self, pose: Pose, dt: float, snap: bool = False) -> None:
        """Copy an animated pose into the bodies. `snap` discards the implied velocity."""
        self._last_dt = dt
        transforms = forward_kinematics(self.skeleton, pose)
        for name, (a, b) in self._segment.items():
            t = transforms[name]
            for index, point in ((a, t.start), (b, t.end)):
                self._prev[index] = point if snap or not self._initialized else self._pos[index]
                self._pos[index] = point
        self._initialized = True

    def release(self) -> None:
        self.motors_on = False

    def engage(self, pose: Pose, dt: float) -> None:
        self.motors_on = True
        self.drive(pose, dt, snap=True)

    def apply_impulse(self, point: Vec2, velocity: Vec2, radius: float = 45.0) -> None:
        """Add `velocity` (units/second) to points near `point`, fading with distance."""
        for i, pos in enumerate(self._pos):
            falloff = 1.0 - pos.distance_to(point) / radius
            if falloff > 0.0:
                self._prev[i] -= velocity * (self._last_dt * falloff)

    def step(self, dt: float) -> None:
        if self.motors_on:
            return
        self._last_dt = dt
        s = self.settings
        gravity = Vec2(0.0, s.gravity * dt * dt)
        max_step = s.max_speed * dt
        for i, pos in enumerate(self._pos):
            velocity = (pos - self._prev[i]) * s.damping
            if velocity.length() > max_step:
                velocity = velocity.normalized() * max_step
            self._prev[i] = pos
            self._pos[i] = pos + velocity + gravity

        self._supported.clear()
        for _ in range(s.iterations):
            self._solve_limits()
            self._solve_rigid()
        # When a limit and the ground disagree, leave the joint slightly over its
        # limit rather than letting bones stretch or come apart.
        for _ in range(s.rigid_passes):
            self._solve_rigid()
        self._apply_friction()

    def _solve_rigid(self) -> None:
        for bone in self.skeleton.bones:
            a, b = self._segment[bone.name]
            self._solve_distance(a, b, bone.length)
        for a, b in self._pins:
            self._solve_distance(a, b, 0.0)
        self._solve_ground()

    def segment(self, name: str) -> tuple[Vec2, Vec2]:
        a, b = self._segment[name]
        return self._pos[a], self._pos[b]

    def pin_gaps(self) -> list[float]:
        return [self._pos[a].distance_to(self._pos[b]) for a, b in self._pins]

    def pose(self) -> Pose:
        """Read the bodies back as root position plus local angles."""
        world: dict[str, float] = {}
        angles: dict[str, float] = {}
        root = None
        for bone in self.skeleton.bones:
            start, end = self.segment(bone.name)
            world[bone.name] = (end - start).angle()
            if bone.parent is None:
                angles[bone.name] = world[bone.name]
                root = root or start
            else:
                angles[bone.name] = wrap_angle(world[bone.name] - world[bone.parent])
        return Pose(root=root or Vec2(0.0, 0.0), angles=angles)

    def _solve_distance(self, a: int, b: int, rest: float) -> None:
        wa, wb = self._inv_mass[a], self._inv_mass[b]
        total = wa + wb
        if total == 0.0:
            return
        pa, pb = self._pos[a], self._pos[b]
        delta = pb - pa
        distance = delta.length()
        if distance < 1e-9:
            return
        correction = delta * ((distance - rest) / (distance * total))
        self._pos[a] = pa + correction * wa
        self._pos[b] = pb - correction * wb

    def _solve_limits(self) -> None:
        """Position-based angle constraint on each limited joint.

        The relative angle depends on four points (both ends of parent and child).
        Each point moves along that angle's gradient, weighted by inverse mass; the
        gradients sum to zero, so a correction cannot add net linear or angular momentum.
        """
        stiffness = self.settings.limit_stiffness
        for bone in self.skeleton.bones:
            if bone.parent is None or not bone.limited:
                continue
            parent_start, parent_end = self._segment[bone.parent]
            child_start, child_end = self._segment[bone.name]
            parent_vec = self._pos[parent_end] - self._pos[parent_start]
            child_vec = self._pos[child_end] - self._pos[child_start]

            local = wrap_angle(child_vec.angle() - parent_vec.angle()) * self.facing
            violation = wrap_angle(local - bone.clamp_local(local)) * self.facing
            if abs(violation) < 1e-6:
                continue

            g_child = _angle_gradient(child_vec)
            g_parent = _angle_gradient(parent_vec)
            gradients = (
                (child_end, g_child),
                (child_start, -g_child),
                (parent_end, -g_parent),
                (parent_start, g_parent),
            )
            denominator = sum(self._inv_mass[i] * g.length_sq() for i, g in gradients)
            if denominator < 1e-12:
                continue
            scale = stiffness * violation / denominator
            for index, gradient in gradients:
                self._pos[index] -= gradient * (scale * self._inv_mass[index])

    def _solve_ground(self) -> None:
        for i, pos in enumerate(self._pos):
            radius = self._radius[i]
            floor = self.ground_y - radius
            if pos.y > floor:
                self._land(i, Vec2(pos.x, floor))
                pos = self._pos[i]
            for box in self.obstacles:
                pos = self._push_out(i, pos, box, radius)

    def _push_out(self, index: int, pos: Vec2, box: Rect, radius: float) -> Vec2:
        """Move a point that is inside a box to the box's nearest face."""
        left, right = box.left - radius, box.right + radius
        top, bottom = box.top - radius, box.bottom + radius
        if not (left < pos.x < right and top < pos.y < bottom):
            return pos
        exits = (
            (pos.y - top, Vec2(pos.x, top)),
            (bottom - pos.y, Vec2(pos.x, bottom)),
            (pos.x - left, Vec2(left, pos.y)),
            (right - pos.x, Vec2(right, pos.y)),
        )
        depth, exit_point = min(exits, key=lambda item: item[0])
        if exit_point.y == top and depth == exits[0][0]:
            self._land(index, exit_point)
        else:
            self._pos[index] = exit_point
        return self._pos[index]

    def _land(self, index: int, point: Vec2) -> None:
        self._pos[index] = point
        self._prev[index] = Vec2(self._prev[index].x, min(self._prev[index].y, point.y))
        self._supported.add(index)

    def _apply_friction(self) -> None:
        keep = 1.0 - self.settings.ground_friction
        for i in self._supported:
            pos, prev = self._pos[i], self._prev[i]
            self._prev[i] = Vec2(pos.x - (pos.x - prev.x) * keep, pos.y)
