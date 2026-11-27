"""The Soulforger: a marked-target fighter using the shared adventurer AI."""

from __future__ import annotations

import math
from dataclasses import replace
from enum import Enum

from dungeons_desktops.core.geometry import Vec2, clamp
from dungeons_desktops.game.actors.base import surface_below
from dungeons_desktops.game.adventurers.actor import (
    GOAL_SNAP,
    MELEE_HEIGHT,
    MELEE_SLACK,
    SEEK_EVERY,
    SEEK_GIVE_UP,
    Stickman,
)
from dungeons_desktops.game.adventurers.combat import ADVENTURER_DAMAGE
from dungeons_desktops.game.heroes.hero_fighter.combat import (
    FLURRY_DAMAGE,
    FLURRY_HITS,
    FLURRY_REACH,
    FLURRY_SEQUENCE,
    FLURRY_TIME,
    LEAP_COOLDOWN,
    LEAP_OFFSET,
    LEAP_RANGE,
    LEAP_TIME,
    MARK_CAST_TIME,
    MARK_DAMAGE_BONUS,
    MARK_REACQUIRE,
    MARK_SPEED,
    SHIELD_COOLDOWN,
    SHIELD_RANGE,
    THROW_COOLDOWN,
    THROW_MIN_RANGE,
    THROW_RANGE,
    THROW_WINDUP,
    CombatLeap,
    SpectralShield,
    SpectralTrident,
    final_push,
)
from dungeons_desktops.game.heroes.hero_fighter.weapon import (
    SoulforgedTridentAndShield,
)
from dungeons_desktops.game.world.api import World
from dungeons_desktops.navigation.planner import Anchor
from dungeons_desktops.navigation.terrain import TerrainChange
from dungeons_desktops.rig.locomotion import LocomotionInput, PoseMode


class HeroAction(Enum):
    MARK = "mark"
    THROW = "throw"
    LEAP = "leap"
    FLURRY = "flurry"


class HeroFighter(Stickman):
    display_name = "The Soulforger"
    mindflayer_stun_immune = True

    def __init__(self, world: World, anchor: Anchor, wander: bool = False) -> None:
        super().__init__(world, anchor, "hero_fighter", wander)
        self._base_calling = self.calling
        self._marked_calling = replace(
            self.calling, speed=self.calling.speed * MARK_SPEED
        )
        self.marked: object | None = None
        self.mark_wait = 0.0
        self.action: HeroAction | None = None
        self.action_time = 0.0
        self.action_target: object | None = None
        self.throw_cooldown = 0.0
        self.leap_cooldown = 0.0
        self.shield_cooldown = 0.0
        self.leap: CombatLeap | None = None
        self._air_feet: Vec2 | None = None
        self.flurry_hits = 0
        self.spectral_tridents: list[SpectralTrident] = []
        self.spectral_shield: SpectralShield | None = None
        self.attack_flash: str | None = None
        self.attack_flash_time = 0.0
        self.effect_time = 0.0

    @property
    def hero_weapon(self) -> SoulforgedTridentAndShield:
        assert isinstance(self.weapon, SoulforgedTridentAndShield)
        return self.weapon

    @property
    def movement_paused(self) -> bool:
        return self.action is not None or super().movement_paused

    def contact(self) -> Vec2:
        return self._air_feet if self._air_feet is not None else super().contact()

    def damage_against(self, target: object, base: int) -> int:
        return base + (MARK_DAMAGE_BONUS if target is self.marked else 0)

    def update(self, dt: float) -> None:
        self.effect_time += dt
        self._update_released_effects(dt)
        self.throw_cooldown = max(0.0, self.throw_cooldown - dt)
        self.leap_cooldown = max(0.0, self.leap_cooldown - dt)
        self.shield_cooldown = max(0.0, self.shield_cooldown - dt)
        self.mark_wait = max(0.0, self.mark_wait - dt)
        self.attack_flash_time = max(0.0, self.attack_flash_time - dt)
        if self.attack_flash_time <= 0.0:
            self.attack_flash = None

        if self.marked is not None and self.world.locate(self.marked) is None:
            lost = self.marked
            self.marked = None
            self.mark_wait = MARK_REACQUIRE
            if self.quarry is lost:
                self.quarry = None

        pursuing = (
            self.marked is not None
            and self.quarry is self.marked
            and not self.thrall
            and self.lure is None
            and self.reeled is None
            and self.engulfed_by is None
        )
        self.calling = self._marked_calling if pursuing else self._base_calling

        if not self.animated:
            self._clear_action()
            super().update(dt)
            return
        if self.action is not None and self._action_interrupted():
            self._abort_action()
            super().update(dt)
            return
        if self.action is HeroAction.LEAP:
            self._update_leap(dt)
            return
        if self.action is HeroAction.FLURRY:
            self._update_flurry(dt)
            return
        if self.action in (HeroAction.MARK, HeroAction.THROW):
            self._update_windup(dt)
        super().update(dt)

    def attack(self) -> None:
        if not self.animated or self.action is not None or self.weapon.busy:
            return
        if self.marked is None and self.mark_wait <= 0.0:
            found = self.world.nearest_monster(self.center(), self.seek_radius)
            if found is not None:
                self._start_mark(found[0], found[1])
                return
        if not self._engage():
            self.say("The Soulforger needs a marked target in range")

    def _action_interrupted(self) -> bool:
        return (
            self.paralysed
            or self.thrall
            or self.lure is not None
            or self.reeled is not None
            or self.engulfed_by is not None
            or self.blind > 0.0
            or self.divine_prayer > 0.0
            or self.dragging_limb is not None
        )

    def _update_windup(self, dt: float) -> None:
        action = self.action
        target = self.action_target
        point = self._target_point(target)
        if point is None:
            self._clear_action()
            return
        self._face(point, self.hero_weapon)
        self.action_time += dt
        if action is HeroAction.MARK:
            self.hero_weapon.set_hero_action(
                "mark", clamp(self.action_time / MARK_CAST_TIME, 0.0, 1.0)
            )
            if self.action_time >= MARK_CAST_TIME:
                self.marked = target
                self.quarry = target
                self._clear_action()
            return
        if point.distance_to(self.center()) > THROW_RANGE:
            self._clear_action()
            return
        aim = math.atan2(point.y - self.center().y, abs(point.x - self.center().x))
        self.hero_weapon.set_hero_action(
            "throw", clamp(self.action_time / THROW_WINDUP, 0.0, 1.0), aim
        )
        if self.action_time < THROW_WINDUP:
            return
        origin = self.hero_weapon.trident_center(self.transforms(), self.facing)
        direction = (point - origin).normalized()
        if direction.length() == 0.0:
            direction = Vec2(float(self.facing), 0.0)
        self.spectral_tridents.append(SpectralTrident(origin, direction))
        self.throw_cooldown = THROW_COOLDOWN
        self._clear_action()

    def _engage(self) -> bool:
        if self.action is not None or self.weapon is None or self.weapon.busy:
            return False
        if self.marked is None:
            if self.mark_wait > 0.0 or self.engulfed_by is not None:
                return False
            found = self.world.nearest_monster(self.center(), self.seek_radius)
            if found is None:
                return False
            self._start_mark(found[0], found[1])
            return True
        point = self._target_point(self.marked)
        if point is None:
            return False
        distance = point.distance_to(self.center())
        if (
            self.engulfed_by is None
            and self.leap_cooldown <= 0.0
            and distance <= LEAP_RANGE
        ):
            leap = self._plan_leap(point)
            if leap is not None:
                self._start_leap(leap)
                return True
        if (
            self.engulfed_by is None
            and self.throw_cooldown <= 0.0
            and THROW_MIN_RANGE <= distance <= THROW_RANGE
        ):
            self._start_throw(point)
            return True
        if distance > self.calling.reach or abs(point.y - self.center().y) > MELEE_HEIGHT:
            return False
        self._strike(self.marked, point)
        return True

    def _start_mark(self, target: object, point: Vec2) -> None:
        self.action = HeroAction.MARK
        self.action_target = target
        self.action_time = 0.0
        self._resume_route = not self.wander and self.goal is not None and self.follower.moving
        self.halt()
        self._face(point, self.hero_weapon)
        self.hero_weapon.set_hero_action("mark", 0.0)

    def _start_throw(self, point: Vec2) -> None:
        self.action = HeroAction.THROW
        self.action_target = self.marked
        self.action_time = 0.0
        self._resume_route = not self.wander and self.goal is not None and self.follower.moving
        self.halt()
        self._face(point, self.hero_weapon)
        self.hero_weapon.set_hero_action("throw", 0.0)

    def _start_leap(self, leap: CombatLeap) -> None:
        self.action = HeroAction.LEAP
        self.action_target = self.marked
        self.action_time = 0.0
        self.leap = leap
        self.leap_cooldown = LEAP_COOLDOWN
        self.goal = None
        self.halt()
        self.hero_weapon.set_hero_action("leap", 0.0)

    def _plan_leap(self, point: Vec2) -> CombatLeap | None:
        if (
            self.locomotion.mode is not PoseMode.WALK
            or self.follower.in_transition
            or self.engulfed_by is not None
        ):
            return None
        start_anchor = self.follower.current_anchor()
        landing = self.planner.anchor_near(point, 26.0, walk_only=True)
        if landing is None or landing.surface is not start_anchor.surface:
            return None
        direction = 1 if point.x >= self.center().x else -1
        margin = 4.0
        x = clamp(
            point.x - direction * LEAP_OFFSET,
            landing.surface.low + margin,
            landing.surface.high - margin,
        )
        leap = CombatLeap(self.contact(), Anchor(landing.surface, Vec2(x, landing.point.y)))
        return leap if self._clear_leap(leap) else None

    def _clear_leap(self, leap: CombatLeap) -> bool:
        half_width = 6.0
        torso_length = self.layout.skeleton.bone(self.layout.torso).length
        body_height = self.layout.leg_length + torso_length + 8.0
        for index in range(31):
            leap.age = LEAP_TIME * index / 30
            feet = leap.feet()
            for box in self.world.boxes:
                if (
                    feet.x + half_width > box.left
                    and feet.x - half_width < box.right
                    and feet.y - 1.0 > box.top
                    and feet.y - body_height < box.bottom
                ):
                    leap.age = 0.0
                    return False
        leap.age = 0.0
        return True

    def _update_leap(self, dt: float) -> None:
        leap = self.leap
        assert leap is not None
        self._tick_custom_frame(dt)
        leap.age += dt
        progress = clamp(leap.age / LEAP_TIME, 0.0, 1.0)
        self._air_feet = leap.feet()
        if abs(leap.landing.point.x - leap.start.x) > 1.0:
            self.follower.facing = 1 if leap.landing.point.x > leap.start.x else -1
        self.hero_weapon.set_hero_action("leap", progress)
        self.locomotion.update(
            dt,
            LocomotionInput(
                PoseMode.AIR,
                self._air_feet,
                self.follower.facing,
                ("soulforger-leap",),
                blend=0.04,
                rising=progress < 0.5,
            ),
        )
        if progress >= 1.0:
            self.follower.reset(leap.landing)
            self._air_feet = None
            self.leap = None
            self.action = HeroAction.FLURRY
            self.action_time = 0.0
            self.flurry_hits = 0
            self.locomotion.update(0.0, self.follower.command())
        self._finish_custom_frame(dt)

    def _update_flurry(self, dt: float) -> None:
        self._tick_custom_frame(dt)
        self.action_time += dt
        slot_time = FLURRY_TIME / FLURRY_HITS
        slot = min(FLURRY_HITS - 1, int(self.action_time / slot_time))
        local = (self.action_time - slot * slot_time) / slot_time
        action = FLURRY_SEQUENCE[slot]
        self.hero_weapon.set_hero_action(action, clamp(local, 0.0, 1.0))
        self.halt()
        self.locomotion.update(dt, self.follower.command())
        should_have_hit = min(
            FLURRY_HITS, int(self.action_time / FLURRY_TIME * FLURRY_HITS)
        )
        while self.flurry_hits < should_have_hit:
            self._land_flurry_hit(self.flurry_hits)
            self.flurry_hits += 1
        if self.action_time >= FLURRY_TIME:
            self._clear_action()
            self.needs_replan = True
        self._finish_custom_frame(dt)

    def _land_flurry_hit(self, index: int) -> None:
        target = self.action_target
        point = self._target_point(target)
        self.attack_flash = "trident" if index % 2 == 0 else "shield"
        self.attack_flash_time = 0.13
        if point is None or point.distance_to(self.center()) > FLURRY_REACH:
            return
        push = final_push(self.facing) if index == FLURRY_HITS - 1 else Vec2(0.0, 0.0)
        self.world.hurt_monster(
            target,
            self.damage_against(target, FLURRY_DAMAGE),
            point,
            push,
            attacker=self,
        )

    def _land_blow(self) -> None:
        if self.thrall:
            super()._land_blow()
            return
        target = self.marked
        point = self._target_point(target)
        center = self.center()
        if (
            point is None
            or point.distance_to(center) > self.calling.reach + MELEE_SLACK
            or abs(point.y - center.y) > MELEE_HEIGHT
        ):
            return
        self.world.hurt_monster(
            target,
            self.damage_against(target, ADVENTURER_DAMAGE),
            point,
            final_push(self.facing),
            attacker=self,
        )

    def _target_point(self, target: object | None) -> Vec2 | None:
        if target is None or self.world.locate(target) is None:
            return None
        return self.world.closest_part(target, self.center())

    def _seek(self, dt: float) -> bool:
        if self.action is not None:
            self.halt()
            return True
        if self.marked is None:
            if self.mark_wait <= 0.0:
                found = self.world.nearest_monster(self.center(), self.seek_radius)
                if found is not None:
                    self._start_mark(found[0], found[1])
                    return True
            return super()._seek(dt)

        self._shunned = {m: t - dt for m, t in self._shunned.items() if t > dt}
        if self.marked in self._shunned:
            self.quarry = None
            return False
        self._seek_wait -= dt
        if self._seek_wait > 0.0 or self.follower.in_transition:
            return self.quarry is self.marked
        self._seek_wait = SEEK_EVERY
        point = self._target_point(self.marked)
        if point is None:
            self.quarry = None
            return False
        self.quarry = self.marked
        center = self.center()
        level = abs(point.y - center.y) <= MELEE_HEIGHT
        if point.distance_to(center) <= self._stand_off() and level:
            if self.follower.moving:
                self.goal = None
                self.halt()
            return True
        start = self.follower.current_anchor()
        anchor = self.planner.anchor_near(point, GOAL_SNAP)
        route = None
        if anchor is not None and anchor.point.distance_to(start.point) >= 2.0:
            route = self.planner.plan(start, anchor)
        if route is None or not route.steps:
            self._shunned[self.marked] = SEEK_GIVE_UP
            self.quarry = None
            return False
        self.goal = anchor.point
        self.goal_reachable = True
        self.follower.reset(start)
        self.follower.set_route(route)
        return True

    def _face_nearest_monster(self) -> None:
        point = self._target_point(self.marked)
        if point is None:
            super()._face_nearest_monster()
        elif abs(point.x - self.center().x) > 1.0:
            self.follower.facing = 1 if point.x > self.center().x else -1

    def _tick_custom_frame(self, dt: float) -> None:
        self.faerie = max(0.0, self.faerie - dt)
        for source in self._grace:
            self._grace[source] -= dt
        self.cooldown -= dt

    def _finish_custom_frame(self, dt: float) -> None:
        self.ragdoll.facing = self.locomotion.facing
        self.ragdoll.drive(self.locomotion.pose, dt)
        self._track_velocity(dt)

    def _update_released_effects(self, dt: float) -> None:
        self.spectral_tridents = [
            trident
            for trident in self.spectral_tridents
            if trident.update(self, dt)
        ]
        if self.spectral_shield is not None and not self.spectral_shield.update(self, dt):
            self.spectral_shield = None

    def _clear_action(self) -> None:
        self.action = None
        self.action_time = 0.0
        self.action_target = None
        self.leap = None
        self._air_feet = None
        self.flurry_hits = 0
        if isinstance(self.weapon, SoulforgedTridentAndShield):
            self.weapon.clear_hero_action()

    def _abort_action(self) -> None:
        if self._air_feet is not None:
            self.follower.reset(surface_below(self.planner, self._air_feet))
        self._clear_action()
        self.needs_replan = True

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
        before = self.damage
        killed = super().hurt(amount, point, push, source, death, bleed, attacker)
        target_point = self._target_point(self.marked)
        if (
            not killed
            and self.damage > before
            and self.shield_cooldown <= 0.0
            and self.marked is not None
            and target_point is not None
            and target_point.distance_to(self.center()) <= SHIELD_RANGE
        ):
            self.shield_cooldown = SHIELD_COOLDOWN
            center = self.center()
            self.spectral_shield = SpectralShield(self.marked, center, center)
        return killed

    def terrain_changed(self, change: TerrainChange) -> None:
        if self._air_feet is None:
            super().terrain_changed(change)
            return
        self.follower.reset(surface_below(self.planner, self._air_feet))
        self._clear_action()
        self.needs_replan = True

    def go_ragdoll(self) -> None:
        super().go_ragdoll()
        self.marked = None
        self._clear_action()
