"""Dio, the named fighter hero: autonomous combat, winged travel, and divine counters."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import Enum
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep
from dungeons_desktops.game.adventurers import model as stick_figure
from dungeons_desktops.game.adventurers.actor import MELEE_PUSH, Stickman
from dungeons_desktops.game.heroes.dio.weapon import HeroTridentAndShield
from dungeons_desktops.navigation.planner import Anchor
from dungeons_desktops.rig.locomotion import LocomotionInput, PoseMode

if TYPE_CHECKING:
    from dungeons_desktops.game.world.api import World
    from dungeons_desktops.navigation.terrain import TerrainChange


MOVE_PAUSE = 0.3
DIO_AWARENESS_RANGE = 300.0
THROW_CHARGE = 0.35
TRIDENT_SPEED = 560.0
TRIDENT_DAMAGE = 4
TRIDENT_SCALE = 1.65
TRIDENT_HIT_RADIUS = 16.0
TRIDENT_MARGIN = 45.0
SLICE_APPROACH = 160.0
SLICE_LEAP = 0.28
SLICE_OFFSET = 30.0
SLICE_TIME = 0.8
SLICE_HITS = 6
SLICE_DAMAGE = 1
MARK_CAST = 0.25
MARK_TIME = 8.0
MARK_STRIKE_EVERY = 0.5
MARK_DAMAGE = 3
MARK_SPEED = 2.0
FLIGHT_SPEED = 180.0
HOVER_REACH = 30.0
MELEE_REACH = 58.0
SHIELD_DAMAGE = 2
SHIELD_RANGE = 50.0
SHIELD_COOLDOWN = 2.0
SHIELD_TRAVEL = 0.2
SHIELD_PUSH = 240.0
WALK_SPEED = stick_figure.MOVES.walk_speed


HERO_FIGHTER_GAIT = replace(
    stick_figure.RUN,
    stride=34.0 * stick_figure.SCALE,
    stance_fraction=0.55,
    step_height=5.0 * stick_figure.SCALE,
    hip_bob=1.0 * stick_figure.SCALE,
    lean=0.1,
    arm_swing=0.72,
    arm_reach=0.82,
    crouch=0.03,
)
"""A planted armored march with enough arm travel to carry both pieces visibly."""


class DioMove(Enum):
    TRIDENT_THROW = "trident_throw"
    DOUBLE_SLICE = "double_slice"
    DEATH_MARK = "death_mark"


MOVE_QUEUE = (DioMove.TRIDENT_THROW, DioMove.DOUBLE_SLICE, DioMove.DEATH_MARK)


class DioPhase(Enum):
    IDLE = "idle"
    THROW_CHARGE = "throw_charge"
    THROW_FLIGHT = "throw_flight"
    SLICE_APPROACH = "slice_approach"
    SLICE_LEAP = "slice_leap"
    SLICE_FLURRY = "slice_flurry"
    MARK_CAST = "mark_cast"
    MARK_HUNT = "mark_hunt"


@dataclass
class ThrownTrident:
    position: Vec2
    direction: Vec2
    hit: set[object]


@dataclass
class SpectralShield:
    target: object
    origin: Vec2
    position: Vec2
    age: float = 0.0


class Dio(Stickman):
    """An autonomous hero who cycles a throw, a six-hit leap, and a marked hunt."""

    display_name = "Dio"
    mindflayer_stun_immune = True

    def __init__(self, world: World, anchor: Anchor, wander: bool = False) -> None:
        layout = replace(stick_figure.build_stick_figure(), walk=HERO_FIGHTER_GAIT)
        super().__init__(world, anchor, "hero_fighter", wander, layout=layout)
        self.queue_index = 0
        self.phase = DioPhase.IDLE
        self.move_time = 0.0
        self.move_pause = 0.0
        self.target: object | None = None
        self.marked: object | None = None
        self.mark_time = 0.0
        self.mark_strike_wait = 0.0
        self.flurry_hits = 0
        self._flurry_offset: Vec2 | None = None
        self.attack_flash: str | None = None
        self.attack_flash_time = 0.0
        self.thrown_trident: ThrownTrident | None = None
        self.spectral_shield: SpectralShield | None = None
        self.shield_cooldown = 0.0
        self._air_feet: Vec2 | None = None
        self._wings = False
        self.wing_open = 0.0
        self.wing_retract = 0.0
        self.flight_clock = 0.0
        self._leap_start = anchor.point
        self._leap_end = anchor.point
        self._leap_anchor: Anchor | None = None

    @property
    def dio_weapon(self) -> HeroTridentAndShield:
        assert isinstance(self.weapon, HeroTridentAndShield)
        return self.weapon

    @property
    def current_move(self) -> DioMove:
        return MOVE_QUEUE[self.queue_index]

    @property
    def wings(self) -> bool:
        return (self._wings or self.wing_retract > 0.0) and self.animated

    @property
    def flying(self) -> bool:
        return self._air_feet is not None and self._wings

    @property
    def trident_charge(self) -> float:
        if self.phase is not DioPhase.THROW_CHARGE:
            return 0.0
        return clamp(self.move_time / THROW_CHARGE, 0.0, 1.0)

    def contact(self) -> Vec2:
        return self._air_feet if self._air_feet is not None else super().contact()

    def attack(self) -> None:
        """Preview/manual attack starts the queued move if Dio is otherwise idle."""
        if self.animated and self.phase is DioPhase.IDLE and self.move_pause <= 0.0:
            self._start_queued_move()

    # ----- simulation ---------------------------------------------------------

    def update(self, dt: float) -> None:
        if not self.animated:
            self._clear_combat()
            super().update(dt)
            return

        self.faerie = max(0.0, self.faerie - dt)
        for source in self._grace:
            self._grace[source] -= dt
        self.shield_cooldown = max(0.0, self.shield_cooldown - dt)
        self.wing_retract = max(0.0, self.wing_retract - dt)
        if self.wing_retract > 0.0:
            self.wing_open = min(1.0, self.wing_retract / 0.25)
        self.attack_flash_time = max(0.0, self.attack_flash_time - dt)
        if self.attack_flash_time <= 0.0:
            self.attack_flash = None
        self._update_thrown_trident(dt)
        self._update_spectral_shield(dt)

        if self.reeled is not None:
            self._leave_flight()
            self._reeling(dt)
            return
        if self.stun > 0.0:
            self.stun -= dt
            if self._air_feet is not None:
                self._drive_air(dt, self._air_feet)
                self._finish_frame(dt)
            else:
                self._hold_still(dt)
            return
        if self.thrall:
            self._land_immediately()
            self._thrall_update(dt)
            return
        if self.lure is not None:
            self._land_immediately()
            self._lured(dt)
            return
        if self.blind > 0.0:
            self._land_immediately()
            self._grope(dt)
            return

        if self.engulfed_by is None:
            self._replan_if_needed()
        self.move_pause = max(0.0, self.move_pause - dt)
        self._advance_combat(dt)
        self._finish_frame(dt)

    def _advance_combat(self, dt: float) -> None:
        if self.phase is DioPhase.IDLE:
            if self.move_pause > 0.0:
                self._idle_motion(dt)
                return
            if not self._start_queued_move():
                self._idle_motion(dt)
            return

        self.move_time += dt
        if self.phase is DioPhase.THROW_CHARGE:
            self._throw_charge(dt)
        elif self.phase is DioPhase.THROW_FLIGHT:
            self._stationary(dt)
            if self.thrown_trident is None:
                self._complete_move()
        elif self.phase is DioPhase.SLICE_APPROACH:
            self._slice_approach(dt)
        elif self.phase is DioPhase.SLICE_LEAP:
            self._slice_leap(dt)
        elif self.phase is DioPhase.SLICE_FLURRY:
            self._slice_flurry(dt)
        elif self.phase is DioPhase.MARK_CAST:
            self._mark_cast(dt)
        elif self.phase is DioPhase.MARK_HUNT:
            self._mark_hunt(dt)

    def _start_queued_move(self) -> bool:
        found = self.world.nearest_monster(self.center(), DIO_AWARENESS_RANGE)
        if found is None:
            self.target = None
            return False
        self.target = found[0]
        self.move_time = 0.0
        if self.current_move is DioMove.TRIDENT_THROW:
            self.phase = DioPhase.THROW_CHARGE
        elif self.current_move is DioMove.DOUBLE_SLICE:
            self.phase = DioPhase.SLICE_APPROACH
        else:
            self.phase = DioPhase.MARK_CAST
        return True

    def _target_part(self, target: object | None = None) -> Vec2 | None:
        target = self.target if target is None else target
        if target is None or self.world.locate(target) is None:
            return None
        return self.world.closest_part(target, self.center())

    def _face_target(self, point: Vec2) -> None:
        if abs(point.x - self.center().x) > 1.0:
            self.follower.facing = 1 if point.x > self.center().x else -1

    # ----- queued moves -------------------------------------------------------

    def _throw_charge(self, dt: float) -> None:
        point = self._target_part()
        if point is None:
            self._cancel_move()
            self._idle_motion(dt)
            return
        self._face_target(point)
        progress = clamp(self.move_time / THROW_CHARGE, 0.0, 1.0)
        aim = math.atan2(point.y - self.center().y, abs(point.x - self.center().x))
        self.dio_weapon.set_dio_action("throw", progress, aim)
        self._stationary(dt)
        if self.move_time < THROW_CHARGE:
            return
        origin = self.dio_weapon.trident_center(self.transforms(), self.facing)
        direction = (point - origin).normalized()
        if direction.length() == 0.0:
            direction = Vec2(float(self.facing), 0.0)
        self.thrown_trident = ThrownTrident(origin, direction, set())
        self.dio_weapon.trident_visible = False
        self.dio_weapon.clear_dio_action()
        self.phase = DioPhase.THROW_FLIGHT
        self.move_time = 0.0

    def _slice_approach(self, dt: float) -> None:
        point = self._target_part()
        if point is None:
            self._complete_move()
            self._idle_motion(dt)
            return
        if self.center().distance_to(point) <= SLICE_APPROACH:
            self._begin_leap(point)
            self._slice_leap(dt)
            return
        self._pursue(dt, self.target, SLICE_APPROACH * 0.85)

    def _begin_leap(self, point: Vec2) -> None:
        self.phase = DioPhase.SLICE_LEAP
        self.move_time = 0.0
        self._leap_start = self.contact()
        flat = self._flat_anchor(self.target)
        if self.engulfed_by is not None:
            self.phase = DioPhase.SLICE_FLURRY
            self._leap_end = self.contact()
            self._leap_anchor = None
            self._lock_flurry_distance()
            return
        if flat is not None:
            self._leap_anchor = self._offset_anchor(flat, point)
            self._leap_end = self._leap_anchor.point
        else:
            self._leap_anchor = None
            self._leap_end = self._hover_feet(point)
        self._air_feet = self._leap_start

    def _slice_leap(self, dt: float) -> None:
        progress = clamp(self.move_time / SLICE_LEAP, 0.0, 1.0)
        eased = smoothstep(progress)
        feet = self._leap_start.lerp(self._leap_end, eased)
        feet -= Vec2(0.0, math.sin(math.pi * progress) * 18.0)
        self._air_feet = feet
        point = self._target_part() or self._leap_end
        self._face_target(point)
        self._drive_air(dt, feet)
        if progress < 1.0:
            return
        if self._leap_anchor is not None:
            self._land(self._leap_anchor)
        self.phase = DioPhase.SLICE_FLURRY
        self.move_time = 0.0
        self.flurry_hits = 0
        self._lock_flurry_distance()

    def _slice_flurry(self, dt: float) -> None:
        slot = min(SLICE_HITS - 1, int(self.move_time / (SLICE_TIME / SLICE_HITS)))
        local = (self.move_time - slot * SLICE_TIME / SLICE_HITS) / (SLICE_TIME / SLICE_HITS)
        kind = "trident_slice" if slot % 2 == 0 else "shield_slice"
        self.dio_weapon.set_dio_action(kind, clamp(local, 0.0, 1.0))
        if not self._follow_flurry_target(dt):
            self._stationary(dt)
        should_have_hit = min(SLICE_HITS, int(self.move_time / SLICE_TIME * SLICE_HITS))
        while self.flurry_hits < should_have_hit:
            self._land_slice(self.flurry_hits)
            self.flurry_hits += 1
        if self.move_time >= SLICE_TIME:
            self._complete_move()

    def _lock_flurry_distance(self) -> None:
        """Keep Dio at the landing offset from this move's original target."""
        reference = self.world.locate(self.target) if self.target is not None else None
        self._flurry_offset = self.contact() - reference if reference is not None else None

    def _follow_flurry_target(self, dt: float) -> bool:
        """Carry the six-hit pose with a moving target without changing targets."""
        if self.engulfed_by is not None or self.target is None or self._flurry_offset is None:
            return False
        reference = self.world.locate(self.target)
        if reference is None:
            return False
        desired = reference + self._flurry_offset
        self._face_target(reference)
        flat = self._flat_anchor(self.target)
        if flat is None:
            self._take_flight()
            self._air_feet = desired
            self._drive_air(dt, desired)
            return True
        x = clamp(desired.x, flat.surface.low + 2.0, flat.surface.high - 2.0)
        anchor = Anchor(flat.surface, Vec2(x, flat.point.y))
        if self._air_feet is not None:
            self._land(anchor)
        else:
            self.follower.reset(anchor)
        self.locomotion.update(dt, self.follower.command())
        return True

    def _land_slice(self, index: int) -> None:
        self.attack_flash = "trident" if index % 2 == 0 else "shield"
        self.attack_flash_time = 0.13
        center = self.center()
        for monster, part in self.world.monsters_near(center, MELEE_REACH):
            push = Vec2(0.0, 0.0)
            if index == SLICE_HITS - 1:
                direction = 1 if part.x >= center.x else -1
                push = Vec2(direction * MELEE_PUSH, -MELEE_PUSH * 0.4)
            self.world.hurt_monster(monster, SLICE_DAMAGE, part, push, attacker=self)

    def _mark_cast(self, dt: float) -> None:
        point = self._target_part()
        if point is None:
            self._complete_move()
            self._idle_motion(dt)
            return
        self._face_target(point)
        self.dio_weapon.set_dio_action("mark", clamp(self.move_time / MARK_CAST, 0.0, 1.0))
        self._stationary(dt)
        if self.move_time < MARK_CAST:
            return
        self.marked = self.target
        self.mark_time = 0.0
        self.mark_strike_wait = 0.0
        self.phase = DioPhase.MARK_HUNT
        self.move_time = 0.0

    def _mark_hunt(self, dt: float) -> None:
        target = self.marked
        part = self._target_part(target)
        if part is None:
            self._complete_move()
            return
        self.target = target
        self.mark_time += dt
        if self.mark_time >= MARK_TIME:
            self._complete_move()
            return
        self.mark_strike_wait -= dt
        if part.distance_to(self.center()) > MELEE_REACH:
            self.dio_weapon.clear_dio_action()
            self._pursue(dt, target, HOVER_REACH, MARK_SPEED)
            return
        self._face_target(part)
        progress = 1.0 - clamp(self.mark_strike_wait / MARK_STRIKE_EVERY, 0.0, 1.0)
        self.dio_weapon.set_dio_action("marked", progress)
        self._stationary(dt)
        if self.mark_strike_wait > 0.0:
            return
        center = self.center()
        for monster, hit_part in self.world.monsters_near(center, MELEE_REACH):
            direction = 1 if hit_part.x >= center.x else -1
            push = Vec2(direction * MELEE_PUSH, -MELEE_PUSH * 0.4)
            self.world.hurt_monster(monster, MARK_DAMAGE, hit_part, push, attacker=self)
        self.attack_flash = "marked"
        self.attack_flash_time = 0.16
        self.mark_strike_wait = MARK_STRIKE_EVERY

    def _complete_move(self) -> None:
        self.queue_index = (self.queue_index + 1) % len(MOVE_QUEUE)
        self.phase = DioPhase.IDLE
        self.move_time = 0.0
        self.move_pause = MOVE_PAUSE
        self.target = None
        self.marked = None
        self.mark_time = 0.0
        self.flurry_hits = 0
        self._flurry_offset = None
        self.dio_weapon.trident_visible = True
        self.dio_weapon.clear_dio_action()

    def _cancel_move(self) -> None:
        """Drop an uncommitted action without consuming its queue position."""
        self.phase = DioPhase.IDLE
        self.move_time = 0.0
        self.target = None
        self.marked = None
        self._flurry_offset = None
        self.dio_weapon.trident_visible = True
        self.dio_weapon.clear_dio_action()

    # ----- movement -----------------------------------------------------------

    def _pursue(self, dt: float, target: object | None, stand: float, speed: float = 1.0) -> None:
        point = self._target_part(target)
        if point is None:
            self._stationary(dt)
            return
        if self.engulfed_by is not None:
            self._stationary(dt)
            return
        flat = self._flat_anchor(target)
        if self._air_feet is not None:
            if flat is not None:
                landing = self._offset_anchor(flat, point, stand)
                if self._fly_toward(dt, landing.point, speed):
                    self._land(landing)
            else:
                self._fly_toward(dt, self._hover_feet(point, stand), speed)
            return
        here = self.follower.current_anchor()
        if flat is None or flat.surface is not here.surface:
            self._take_flight()
            self._fly_toward(dt, self._hover_feet(point, stand), speed)
            return
        landing = self._offset_anchor(flat, point, stand)
        distance = abs(landing.point.x - here.point.x)
        if distance <= 1.0:
            self._stationary(dt)
            return
        step = min(distance, WALK_SPEED * self.calling.speed * speed * dt)
        direction = 1 if landing.point.x > here.point.x else -1
        self.follower.facing = direction
        point_on_surface = Vec2(here.point.x + direction * step, here.point.y)
        self.follower.reset(Anchor(here.surface, point_on_surface))
        self.locomotion.update(dt, self.follower.command())

    def _flat_anchor(self, target: object | None) -> Anchor | None:
        if target is None or self.world.locate(target) is None:
            return None
        airborne = getattr(target, "airborne", False)
        flying = getattr(target, "flying", False)
        if (airborne() if callable(airborne) else airborne) or (
            flying() if callable(flying) else flying
        ):
            return None
        surface = getattr(target, "support", None) or getattr(target, "surface", None)
        if surface is not None:
            if not surface.walkable:
                return None
            point = surface.closest_point(self.world.locate(target))
            return self.planner.anchor_near(point, 2.0, walk_only=True)
        contact = getattr(target, "contact", None)
        candidates = [contact()] if callable(contact) else []
        position = getattr(target, "position", None)
        if isinstance(position, Vec2):
            candidates.append(position)
        root = getattr(target, "root", None)
        if callable(root):
            candidates.append(root())
        parts = getattr(target, "parts", None)
        if callable(parts):
            candidates.extend(parts())
        for point in candidates:
            anchor = self.planner.anchor_near(point, 22.0, walk_only=True)
            if anchor is not None:
                return anchor
        return None

    def _offset_anchor(self, anchor: Anchor, target: Vec2, stand: float = SLICE_OFFSET) -> Anchor:
        side = 1 if target.x >= self.center().x else -1
        x = target.x - side * stand
        x = clamp(x, anchor.surface.low + 2.0, anchor.surface.high - 2.0)
        return Anchor(anchor.surface, Vec2(x, anchor.point.y))

    def _hover_feet(self, point: Vec2, stand: float = HOVER_REACH) -> Vec2:
        side = 1 if point.x >= self.center().x else -1
        return point + Vec2(-side * stand, self.layout.leg_length * 0.8)

    def _take_flight(self, point: Vec2 | None = None) -> None:
        if self._air_feet is None:
            self._air_feet = point or super().contact()
        self._wings = True
        self.goal = None
        self.halt()

    def _fly_toward(self, dt: float, destination: Vec2, speed: float = 1.0) -> bool:
        self._take_flight()
        assert self._air_feet is not None
        delta = destination - self._air_feet
        distance = delta.length()
        step = FLIGHT_SPEED * speed * dt
        if abs(delta.x) > 1.0:
            self.follower.facing = 1 if delta.x > 0.0 else -1
        self._air_feet = (
            destination if distance <= step else self._air_feet + delta.normalized() * step
        )
        self._drive_air(dt, self._air_feet)
        return distance <= step

    def _drive_air(self, dt: float, feet: Vec2) -> None:
        self.flight_clock += dt
        self.wing_open = min(1.0, self.wing_open + dt * 5.0)
        command = LocomotionInput(
            PoseMode.AIR,
            feet,
            self.follower.facing,
            ("dio-flight",),
            blend=0.15,
            rising=False,
        )
        self.locomotion.update(dt, command)

    def _land(self, anchor: Anchor) -> None:
        self.follower.reset(anchor)
        self._air_feet = None
        self._wings = False
        self.wing_retract = 0.25
        self.locomotion.update(0.0, self.follower.command())

    def _leave_flight(self) -> None:
        self._air_feet = None
        self._wings = False
        self.wing_open = 0.0
        self.wing_retract = 0.0

    def _land_immediately(self) -> None:
        if self._air_feet is None:
            return
        anchor = self.planner.anchor_near(self._air_feet, walk_only=True)
        if anchor is not None:
            self._land(anchor)

    def _idle_motion(self, dt: float) -> None:
        if self._air_feet is None:
            self._stationary(dt)
            return
        anchor = self.planner.anchor_near(self._air_feet, walk_only=True)
        if anchor is None:
            self._drive_air(dt, self._air_feet)
        elif self._fly_toward(dt, anchor.point):
            self._land(anchor)

    def _stationary(self, dt: float) -> None:
        if self.engulfed_by is not None:
            ooze = self.engulfed_by
            feet = ooze.engulfed_feet(self)  # type: ignore[attr-defined]
            facing = 1 if ooze.center().x >= self.center().x else -1  # type: ignore[attr-defined]
            self.follower.facing = facing
            command = LocomotionInput(PoseMode.AIR, feet, facing, ("engulfed", id(ooze)), blend=0.1)
            self.locomotion.update(dt, command)
        elif self._air_feet is not None:
            self._drive_air(dt, self._air_feet)
        else:
            self.halt()
            self.locomotion.update(dt, self.follower.command())

    def _finish_frame(self, dt: float) -> None:
        self.ragdoll.facing = self.locomotion.facing
        self.ragdoll.drive(self.locomotion.pose, dt)
        self._track_velocity(dt)

    # ----- projectiles and passive counter -----------------------------------

    def _update_thrown_trident(self, dt: float) -> None:
        trident = self.thrown_trident
        if trident is None:
            return
        travel = trident.direction * (TRIDENT_SPEED * dt)
        steps = max(1, int(travel.length() / 2.5) + 1)
        step = travel / steps
        for _ in range(steps):
            trident.position += step
            for monster, part in self.world.monsters_near(trident.position, TRIDENT_HIT_RADIUS):
                if monster in trident.hit:
                    continue
                trident.hit.add(monster)
                push = trident.direction * 180.0 + Vec2(0.0, -50.0)
                self.world.hurt_monster(
                    monster, TRIDENT_DAMAGE, part, push, ranged=True, attacker=self
                )
        left = getattr(self.world, "left", 0.0)
        ceiling = getattr(self.world, "ceiling", None)
        top = -200.0 if ceiling is None else ceiling
        point = trident.position
        gone = (
            point.x < left - TRIDENT_MARGIN
            or point.x > self.world.width + TRIDENT_MARGIN
            or point.y < top - TRIDENT_MARGIN
            or point.y > self.world.floor_y + TRIDENT_MARGIN
        )
        if gone:
            self.thrown_trident = None
            self.dio_weapon.trident_visible = True

    def _update_spectral_shield(self, dt: float) -> None:
        shield = self.spectral_shield
        if shield is None:
            return
        shield.age += dt
        part = self.world.closest_part(shield.target, shield.position)
        if part is None:
            self.spectral_shield = None
            return
        progress = clamp(shield.age / SHIELD_TRAVEL, 0.0, 1.0)
        shield.position = shield.origin.lerp(part, smoothstep(progress))
        if progress < 1.0:
            return
        for monster, hit_part in self.world.monsters_near(part, SHIELD_RANGE):
            away = (hit_part - self.center()).normalized()
            if away.length() == 0.0:
                away = Vec2(float(self.facing), 0.0)
            self.world.hurt_monster(
                monster,
                SHIELD_DAMAGE,
                hit_part,
                away * SHIELD_PUSH + Vec2(0.0, -80.0),
                attacker=self,
            )
        self.world.spells.sparkle(part, "holy", 10, 120.0)
        self.spectral_shield = None

    def hurt(
        self,
        amount: int,
        point: Vec2,
        push: Vec2,
        source: str,
        death: str,
        bleed: bool = True,
        attacker: object | None = None,
    ) -> bool:
        attacker = attacker or self._incoming_attacker
        before = self.damage
        killed = super().hurt(amount, point, push, source, death, bleed, attacker=attacker)
        if killed or self.damage == before or attacker is None or self.shield_cooldown > 0.0:
            return killed
        part = self.world.closest_part(attacker, self.center())
        if part is None or part.distance_to(self.center()) > SHIELD_RANGE:
            return killed
        self.shield_cooldown = SHIELD_COOLDOWN
        self.spectral_shield = SpectralShield(attacker, self.center(), self.center())
        return killed

    # ----- terrain and lifecycle ---------------------------------------------

    def terrain_changed(self, change: TerrainChange) -> None:
        if self._air_feet is None:
            super().terrain_changed(change)
            return
        anchor = self.planner.anchor_near(self._air_feet, walk_only=True)
        if anchor is not None:
            self.follower.reset(anchor)

    def lost_support(self, contact: Vec2) -> None:
        anchor = self.planner.anchor_near(contact, walk_only=True)
        if anchor is not None:
            self.follower.reset(anchor)
        self._take_flight(contact)

    def go_ragdoll(self) -> None:
        super().go_ragdoll()
        self._clear_combat()

    def _clear_combat(self) -> None:
        self.phase = DioPhase.IDLE
        self.target = None
        self.marked = None
        self.thrown_trident = None
        self.spectral_shield = None
        self._flurry_offset = None
        self._air_feet = None
        self._wings = False
        self.wing_open = 0.0
        self.wing_retract = 0.0
        if isinstance(self.weapon, HeroTridentAndShield):
            self.weapon.trident_visible = True
            self.weapon.clear_dio_action()


# Compatibility for existing spawn code, tests, and imports.
HeroFighter = Dio
