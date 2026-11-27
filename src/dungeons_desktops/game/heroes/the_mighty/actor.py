"""The Mighty chooses attacks by distance and grows when damage enrages him."""

from dataclasses import dataclass, replace

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep
from dungeons_desktops.game.actors.base import surface_below
from dungeons_desktops.game.adventurers.actor import Stickman
from dungeons_desktops.game.heroes.the_mighty.combat import (
    BOULDER_COOLDOWN,
    BOULDER_RANGE,
    LEAP_DAMAGE,
    LEAP_RADIUS,
    LEAP_RANGE,
    LEAP_RECOVER,
    LEAP_WINDUP,
    MELEE_DAMAGE,
    MELEE_RANGE,
    RAGE_DAMAGE,
    RAGE_SIZE,
    RAGE_TIME,
    SWING_DAMAGE,
    SWING_RADIUS,
    Attack,
    MightyCombat,
)
from dungeons_desktops.game.heroes.the_mighty.model import build_mighty
from dungeons_desktops.game.heroes.the_mighty.weapon import HeavyAxe
from dungeons_desktops.game.world.api import World
from dungeons_desktops.navigation.planner import Anchor, Planner
from dungeons_desktops.navigation.terrain import TerrainChange
from dungeons_desktops.rig.locomotion import LocomotionDriver, LocomotionInput, PoseMode
from dungeons_desktops.rig.ragdoll import Ragdoll


@dataclass
class Leap:
    start: Vec2
    landing: Anchor
    duration: float
    height: float
    horizontal_delay: float = 0.0
    age: float = 0.0
    cancelled: bool = False

    def feet(self, progress: float) -> Vec2:
        along = smoothstep(
            clamp((progress - self.horizontal_delay) / (1 - self.horizontal_delay), 0, 1)
        )
        return Vec2(
            self.start.x + (self.landing.point.x - self.start.x) * along,
            self.start.y
            + (self.landing.point.y - self.start.y) * smoothstep(progress)
            - 4 * self.height * progress * (1 - progress),
        )


class TheMighty(Stickman):
    display_name = "The Mighty"

    def __init__(self, world: World, anchor: Anchor, wander: bool = False) -> None:
        self.size_multiplier = 1.0
        self.rage_left = 0.0
        self.fury = 0.0
        self.time = 0.0
        self.leap: Leap | None = None
        self._air_feet: Vec2 | None = None
        anchor = world.mighty_planner.anchor_near(anchor.point)
        super().__init__(world, anchor, "hero_barbarian", wander, layout=build_mighty())
        self.combat = MightyCombat(self)
        self.melee_count = 0
        self.boulder_cooldown = 0.0
        self._approach_wait = 0.0

    @property
    def planner(self) -> Planner:
        return (
            self.world.mighty_rage_planner
            if self.size_multiplier > 1
            else self.world.mighty_planner
        )

    @property
    def enraged(self) -> bool:
        return self.rage_left > 0 and self.animated

    @property
    def damage_bonus(self) -> int:
        return RAGE_DAMAGE if self.enraged else 0

    def contact(self) -> Vec2:
        return self._air_feet if self._air_feet is not None else super().contact()

    def attack(self) -> None:
        if (
            self.animated
            and not self.paralysed
            and not self.thrall
            and self.lure is None
            and self.reeled is None
            and not self.weapon.busy
            and self._can_act()
        ):
            if not self._engage():
                if self.boulder_cooldown > 0 and self._approach_for_leap():
                    self.say("Boulder Throw is cooling down; closing in for Leap Smash")
                else:
                    self.say("The Mighty needs a target in range")

    def _engage(self) -> bool:
        found = self.world.nearest_monster(self.center(), BOULDER_RANGE)
        if found is None or self.leap is not None:
            return False
        target, point = found
        distance = point.distance_to(self.center())
        ground = (
            self.locomotion.mode is PoseMode.WALK
            and not self.follower.in_transition
            and self.engulfed_by is None
        )
        reach = MELEE_RANGE * self.size_multiplier
        if distance <= reach and abs(point.y - self.center().y) <= 40 * self.size_multiplier:
            action = Attack.SWING if self.melee_count % 3 == 2 and ground else Attack.MELEE
        elif distance <= LEAP_RANGE and (leap := self._plan_leap(point)) is not None:
            action = Attack.LEAP
            self.leap = leap
        else:
            # An airborne foe or an obstructed landing gets a throw instead of an unsafe leap.
            if self.boulder_cooldown > 0:
                return False
            action = Attack.BOULDER
        self._resume_route = not self.wander and self.goal is not None and self.follower.moving
        self.halt()
        self._face(point, self.weapon)
        self.foe, self._foe_point = target, point
        self._struck = False
        duration = (
            LEAP_WINDUP + self.leap.duration + LEAP_RECOVER if action is Attack.LEAP else None
        )
        self.weapon.start_action(action, duration)
        cooldown = 1.8 if action in (Attack.LEAP, Attack.BOULDER) else 0.9
        self.calling = replace(self.calling, cooldown=cooldown)
        self.cooldown = cooldown
        return True

    def _land_blow(self) -> None:
        if self.thrall or self.paralysed or self.blind > 0:
            return
        action = self.weapon.action
        if action is Attack.BOULDER:
            point = self.world.closest_part(self.foe, self.center()) if self.foe else None
            if point is not None:
                hand = self.transforms()[self.weapon.hand_chain.bones[-1]].end
                self.combat.throw(hand, point, getattr(self.foe, "velocity", Vec2(0, 0)))
                self.boulder_cooldown = BOULDER_COOLDOWN
                self._approach_wait = 0.0
            return
        if action is Attack.LEAP:
            return
        self.melee_count += 1
        if action is Attack.SWING:
            point = self.contact() + Vec2(self.facing * 25 * self.size_multiplier, 0)
            self.combat.impact(
                point, SWING_RADIUS * self.size_multiplier, SWING_DAMAGE + self.damage_bonus
            )
            return
        center = self.center()
        reach = MELEE_RANGE * self.size_multiplier + 8
        point = self.world.closest_part(self.foe, center) if self.foe else None
        target = self.foe
        if point is None or point.distance_to(center) > reach:
            found = self.world.nearest_monster(center, reach)
            if found is None:
                return
            target, point = found
        if abs(point.y - center.y) <= 40 * self.size_multiplier:
            self.world.hurt_monster(
                target,
                MELEE_DAMAGE + self.damage_bonus,
                point,
                Vec2(self.facing * 150, -60),
                attacker=self,
            )

    def _seek(self, dt: float) -> bool:
        if self.boulder_cooldown > 0:
            return self._approach_for_leap()
        return super()._seek(dt)

    def _approach_for_leap(self) -> bool:
        """Close the gap over terrain while the throw recovers, up to its full range."""
        if self.follower.in_transition or self._approach_wait > 0:
            return self.quarry is not None
        self._approach_wait = 0.35
        found = self.world.nearest_monster(self.center(), BOULDER_RANGE)
        if found is None:
            if self.quarry is not None:
                self.goal = None
                self.halt()
            self.quarry = None
            return False
        self.quarry, point = found
        distance = point.distance_to(self.center())
        melee = (
            distance <= MELEE_RANGE * self.size_multiplier
            and abs(point.y - self.center().y) <= 40 * self.size_multiplier
        )
        leap = distance <= LEAP_RANGE and self._plan_leap(point) is not None
        if melee or leap:
            self.goal = None
            self.halt()
            return True
        start = self.follower.current_anchor()
        goal = surface_below(self.planner, point)
        route = self.planner.plan(start, goal)
        self.goal = goal.point
        self.goal_reachable = route is not None
        self.follower.reset(start)
        self.follower.set_route(route)
        return True

    def _plan_leap(self, point: Vec2) -> Leap | None:
        if not self._can_act() or self.engulfed_by is not None:
            return None
        surface = self.follower.current_anchor().surface
        start = self.contact()
        if surface.wall:
            # The contact is a foot grip on the wall; the body launches from outside it.
            start += surface.normal * (self.layout.climb.hip_offset + 2 * self.size_multiplier)
        elif surface.hanging:
            # Release below the underside instead of trying to jump upward into it.
            start += Vec2(0, 7 * self.size_multiplier)
        facing = 1 if point.x >= start.x else -1
        ideal = point - Vec2(facing * 20, 0)
        radius = LEAP_RADIUS * self.size_multiplier
        margin = 7 * self.size_multiplier
        candidates = []
        for landing in self.planner.surfaces:
            if not landing.walkable or landing.length < margin * 2:
                continue
            # A body part can overhang a window edge. Search nearby solid tops, too,
            # and keep the landing footprint inside the ledge.
            for x in (ideal.x, point.x, point.x + facing * 20):
                end = landing.point_at(clamp(x, landing.low + margin, landing.high - margin))
                if end.distance_to(point) <= radius:
                    anchor = Anchor(landing, end)
                    if anchor not in candidates:
                        candidates.append(anchor)
        candidates.sort(
            key=lambda anchor: (
                anchor.surface.closest_point(point).distance_to(point),
                anchor.point.distance_to(ideal),
            )
        )
        for anchor in candidates:
            distance = anchor.point.distance_to(start)
            height = max(45, distance * 0.35)
            heights = (
                (0.0,)
                if surface.hanging
                else (height, height * 1.6, height * 2.4, height * 0.5, 12.0)
            )
            for arc in heights:
                leap = Leap(
                    start,
                    anchor,
                    clamp(distance / 260, 0.5, 0.95),
                    arc,
                    horizontal_delay=0.2 if surface.wall else 0.0,
                )
                if self._clear_leap(leap):
                    return leap
        return None

    def _clear_leap(self, leap: Leap) -> bool:
        height = 44 * self.size_multiplier
        half_width = 6 * self.size_multiplier
        for index in range(61):
            feet = leap.feet(index / 60)
            if self.world.ceiling is not None and feet.y - height < self.world.ceiling:
                return False
            for box in self.world.boxes:
                if (
                    feet.x + half_width > box.left
                    and feet.x - half_width < box.right
                    and feet.y - 1 > box.top
                    and feet.y - height < box.bottom
                ):
                    return False
        return True

    def update(self, dt: float) -> None:
        self.time += dt
        self.combat.update(dt)
        self.boulder_cooldown = max(0.0, self.boulder_cooldown - dt)
        self._approach_wait = max(0.0, self._approach_wait - dt)
        self.rage_left = max(0.0, self.rage_left - dt)
        self.fury += ((1.0 if self.enraged else 0.0) - self.fury) * min(1, dt * 10)
        if self.animated:
            desired = RAGE_SIZE if self.enraged else 1.0
            if desired != self.size_multiplier and not self.follower.in_transition:
                self._resize(desired)
        if self.leap is not None and self.animated:
            self._update_leap(dt)
            return
        if (
            self.paralysed
            or self.thrall
            or self.lure is not None
            or self.reeled is not None
            or self.blind > 0
            or not self.animated
        ):
            self.weapon.cancel()
        elif (
            not self.wander
            and self.boulder_cooldown > 0
            and not self.weapon.busy
            and self.dragging_limb is None
            and self.engulfed_by is None
        ):
            self._approach_for_leap()
        super().update(dt)

    def _update_leap(self, dt: float) -> None:
        leap = self.leap
        assert leap is not None
        if (
            self.paralysed
            or self.blind > 0
            or self.thrall
            or self.lure is not None
            or self.reeled is not None
            or self.engulfed_by is not None
        ):
            leap.cancelled = True
        if self.reeled is not None or self.engulfed_by is not None:
            self.leap = None
            self._air_feet = None
            self.weapon.cancel()
            super().update(dt)
            return
        self.faerie = max(0, self.faerie - dt)
        self.stun = max(0, self.stun - dt)
        self.blind = max(0, self.blind - dt)
        self.cooldown -= dt
        for source in self._grace:
            self._grace[source] -= dt
        leap.age += dt
        progress = clamp((leap.age - LEAP_WINDUP) / leap.duration, 0, 1)
        if leap.age < LEAP_WINDUP:
            command = self.follower.command()
        else:
            self._air_feet = leap.feet(progress)
            if abs(leap.landing.point.x - leap.start.x) > 1:
                self.follower.facing = 1 if leap.landing.point.x > leap.start.x else -1
            self.weapon.reverse = False
            command = LocomotionInput(
                PoseMode.AIR,
                self._air_feet,
                self.follower.facing,
                ("mighty-leap",),
                blend=0.04,
                rising=progress < 0.5,
            )
        self.locomotion.update(dt, command)
        if progress >= 1:
            self.follower.reset(leap.landing)
            self._air_feet = None
            self.leap = None
            self.locomotion.update(0, self.follower.command())
            if not leap.cancelled:
                self.combat.impact(
                    leap.landing.point,
                    LEAP_RADIUS * self.size_multiplier,
                    LEAP_DAMAGE + self.damage_bonus,
                )
            else:
                self.weapon.cancel()
        self.ragdoll.facing = self.locomotion.facing
        self.ragdoll.drive(self.locomotion.pose, dt)
        self._track_velocity(dt)

    def hurt(self, amount, point, push, source, death, bleed=True, attacker=None) -> bool:
        before = self.damage
        killed = super().hurt(amount, point, push, source, death, bleed, attacker)
        if self.animated and self.damage > before:
            self.rage_left = RAGE_TIME
            if self.size_multiplier != RAGE_SIZE and not self.follower.in_transition:
                self._resize(RAGE_SIZE)
        return killed

    def _resize(self, multiplier: float) -> None:
        old = self.follower.current_anchor()
        facing = self.follower.facing
        self.size_multiplier = multiplier
        anchor = self.planner.anchor_near(old.point)
        if self.leap is not None:
            self.leap.landing = self.planner.anchor_near(self.leap.landing.point, walk_only=True)
        self.follower.reset(anchor)
        self.follower.facing = facing
        previous = self.weapon
        self.layout = build_mighty(multiplier)
        self.weapon = HeavyAxe(self.layout)
        if previous.busy:
            self.weapon.start_action(previous.action, previous.duration)
            self.weapon.time = previous.time
            self.weapon._from = previous._from
            self.weapon.angle = previous.angle
            self.weapon.reverse = previous.reverse
        command = self.follower.command()
        if self._air_feet is not None:
            command = LocomotionInput(PoseMode.AIR, self._air_feet, facing, ("mighty-leap",))
        self.locomotion = LocomotionDriver(self.layout, command, upper=self.weapon)
        self.ragdoll = Ragdoll(
            self.layout.skeleton,
            ground_y=self.world.floor_y,
            end_radius={self.layout.head: self.layout.head_radius},
        )
        self.ragdoll.obstacles = self.world.boxes
        self.ragdoll.facing = facing
        self.ragdoll.engage(self.locomotion.pose, self.world.step)
        self.trail.clear()
        if self.goal is not None and not self.weapon.busy and self.leap is None:
            self.replan()

    def terrain_changed(self, change: TerrainChange) -> None:
        if self.leap is None:
            super().terrain_changed(change)
            return
        if self.leap.age < LEAP_WINDUP:
            source = self.follower.current_anchor().surface.box
            self.leap.start += change.delta_for(source) or Vec2(0, 0)
            super().terrain_changed(change)
            if self.leap is None:
                return
            self.halt()
        old = self.leap.landing
        if change.removed(old.surface.box):
            self.lost_support(self.contact())
            return
        point = old.point + (change.delta_for(old.surface.box) or Vec2(0, 0))
        anchor = self.planner.anchor_near(point, 2, walk_only=True)
        if anchor is None:
            self.lost_support(self.contact())
        else:
            self.leap.landing = anchor

    def go_ragdoll(self) -> None:
        super().go_ragdoll()
        self.leap = None
        self._air_feet = None
        self.rage_left = 0
