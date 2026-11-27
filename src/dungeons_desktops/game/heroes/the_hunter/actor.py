"""Independent gun cooldowns, shotgun recoil rolls, and dual-pistol kiting."""

import math
from dataclasses import replace

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.adventurers.actor import Stickman
from dungeons_desktops.game.heroes.the_hunter.combat import (
    APPROACH_DISTANCE,
    HOLD_DISTANCE,
    PISTOL_DAMAGE,
    PISTOL_INTERVAL,
    PISTOL_RANGE,
    RETREAT_DISTANCE,
    SHOTGUN_BLAST_TIME,
    SHOTGUN_COOLDOWN,
    SHOTGUN_DAMAGE,
    SHOTGUN_RANGE,
    SHOTGUN_RECOVERY,
    SNIPER_COOLDOWN,
    SNIPER_DAMAGE,
    TRACER_TIME,
    Gun,
    ShotgunBlast,
    Tracer,
)
from dungeons_desktops.game.heroes.the_hunter.movement import (
    Roll,
    retreat_point,
    roll_pose,
    start_roll,
)
from dungeons_desktops.game.unlocks import HERO_NAMES
from dungeons_desktops.game.world.api import World
from dungeons_desktops.navigation.planner import Anchor
from dungeons_desktops.navigation.terrain import TerrainChange
from dungeons_desktops.rig.locomotion import PoseMode


class TheHunter(Stickman):
    display_name = HERO_NAMES["hero_ranger"]

    def __init__(self, world: World, anchor: Anchor, wander: bool = False) -> None:
        self.roll: Roll | None = None
        self._roll_after: float | None = None
        super().__init__(world, anchor, "hero_ranger", wander)
        self.sniper_cooldown = 0.0
        self.shotgun_cooldown = 0.0
        self.tracers: list[Tracer] = []
        self.shotgun_blast: ShotgunBlast | None = None
        self._run_settings = self.locomotion.walk.settings
        self._backstep_settings = replace(
            self._run_settings, stride=self.layout.leg_length * 1.2,
            stance_fraction=0.58, step_height=self.layout.leg_length * 0.14,
            hip_bob=0.35, lean=0.08, crouch=0.04, heel_kick=0.0,
        )
        self._target_wait = 0.0
        self._move_wait = 0.0
        self._retreating = False
        self._combat_route = False

    @property
    def _shoots(self) -> bool:
        return True

    @property
    def shot(self):
        return (self.tracers[-1].start, self.tracers[-1].end) if self.tracers else None

    @property
    def shot_left(self):
        return TRACER_TIME - self.tracers[-1].age if self.tracers else 0.0

    def _combat_allowed(self) -> bool:
        return (
            self.animated and not self.paralysed and self.blind <= 0
            and self.lure is None and self.reeled is None and self.engulfed_by is None
            and self.dragging_limb is None
        )

    def _point(self, target):
        if target is None:
            return None
        if self.thrall:
            return self.world.locate_prey(target)
        return self.world.closest_part(target, self.center())

    def _enemies(self):
        if self.thrall:
            return [(s, s.center()) for s in self.world.stickmen if s is not self and s.prey]
        return self.world.monsters_near(self.center(), math.inf)

    def _refresh_target(self, force=False):
        if not force and self._target_wait > 0 and self._point(self.quarry) is not None:
            return
        # Do not rescan the entire screen every frame, even with no enemies present.
        if not force and self._target_wait > 0 and self.quarry is None:
            return
        self._target_wait = 0.25
        found = self._enemies()
        nearest = min(found, key=lambda pair: pair[1].distance_to(self.center()), default=None)
        self.quarry = nearest[0] if nearest else None

    def _tick_status(self, dt):
        self.faerie = max(0.0, self.faerie - dt)
        self.cooldown = max(0.0, self.cooldown - dt)
        for source in self._grace:
            self._grace[source] -= dt

    def update(self, dt: float) -> None:
        self.sniper_cooldown = max(0.0, self.sniper_cooldown - dt)
        self.shotgun_cooldown = max(0.0, self.shotgun_cooldown - dt)
        self._target_wait -= dt
        self._move_wait -= dt
        for tracer in self.tracers:
            tracer.age += dt
        self.tracers = [t for t in self.tracers if t.age < TRACER_TIME]
        if self.shotgun_blast is not None:
            self.shotgun_blast.age += dt
            if self.shotgun_blast.age >= SHOTGUN_BLAST_TIME:
                self.shotgun_blast = None
        if not self._combat_allowed():
            self.roll = None
            self._roll_after = None
            self.weapon.backpedalling = False
            if self.weapon.busy:
                self.weapon.cancel()
            super().update(dt)
            return
        self._replan_if_needed()
        if not self.animated:
            return
        if self._roll_after is not None:
            self._tick_status(dt)
            self._shotgun_recovery(dt)
            return
        if self.roll is not None:
            self._tick_status(dt)
            self._update_roll(dt)
            return
        if not self.follower.in_transition:
            self._refresh_target()
            if self.weapon.busy or self.quarry is not None:
                self._tick_status(dt)
                self._combat_update(dt)
                return
        if self.quarry is None and self._combat_route and not self.follower.in_transition:
            self.goal = None
            self.halt()
            self._combat_route = False
        self.weapon.backpedalling = False
        self._set_backstep(False)
        super().update(dt)

    def attack(self) -> None:
        if (
            self._combat_allowed() and self.roll is None and self._roll_after is None
            and self._can_act()
        ):
            self._refresh_target(force=True)
            if not self.weapon.busy:
                self._engage()

    def _engage(self) -> bool:
        if (
            not self._combat_allowed() or self.weapon.busy or self.roll is not None
            or self._roll_after is not None
        ):
            return False
        self._refresh_target()
        point = self._point(self.quarry)
        if point is None:
            return False
        distance = point.distance_to(self.center())
        if (
            not self.thrall and distance <= SHOTGUN_RANGE and self.shotgun_cooldown <= 0
            and self.follower.current_anchor().surface.horizontal
        ):
            gun = Gun.SHOTGUN
        elif not self.thrall and self.sniper_cooldown <= 0:
            gun = Gun.SNIPER
        elif distance <= PISTOL_RANGE and self.cooldown <= 0:
            gun = Gun.PISTOLS
        else:
            return False
        self._start_attack(gun, self.quarry, point)
        return True

    def _start_attack(self, gun, target, point):
        self.foe, self._foe_point = target, point
        self._face(point, self.weapon)
        offset = point - self.center()
        self.weapon.aim = math.atan2(offset.y, max(1.0, abs(offset.x)))
        if gun is not Gun.PISTOLS:
            self.halt()
        else:
            self.cooldown = PISTOL_INTERVAL
        self.weapon.start_action(gun)
        self._move_wait = 0.0

    def _seek(self, dt: float) -> bool:
        # Combat movement is handled even while the pistols are firing.
        return self.quarry is not None

    def _combat_update(self, dt):
        if not self.weapon.busy and self._can_act():
            self._engage()
        point = self._point(self.foe if self.weapon.busy else self.quarry)
        if point is not None:
            self._face(point, self.weapon)
            offset = point - self.center()
            self.weapon.aim = math.atan2(offset.y, max(1.0, abs(offset.x)))
        if self.weapon.busy and self.weapon.gun is not Gun.PISTOLS:
            self.halt()
        else:
            self._position_for_pistols(self._point(self.quarry))
        before = self.contact()
        command = self.follower.update(dt * self.calling.speed)
        if point is not None and command.mode in (PoseMode.WALK, PoseMode.HANG):
            facing = 1 if point.x >= command.contact.x else -1
            self.follower.facing = facing
            command = replace(command, facing=facing)
            self.weapon.backpedalling = (command.contact.x - before.x) * facing < -1e-6
        else:
            self.weapon.backpedalling = False
        self._set_backstep(self.weapon.backpedalling and command.mode is PoseMode.WALK)
        self.locomotion.update(dt, command)
        self._update_weapon()
        self.ragdoll.facing = self.locomotion.facing
        self.ragdoll.drive(self.locomotion.pose, dt)
        self._track_velocity(dt)

    def _set_backstep(self, active):
        settings = self._backstep_settings if active else self._run_settings
        walk = self.locomotion.walk
        if walk.settings is not settings:
            walk.settings = settings
            walk.place(walk.hip_x, walk.ground_y)
            self.locomotion.blend_from(self.locomotion.pose, 0.1)

    def _position_for_pistols(self, point):
        if point is None or self.follower.in_transition:
            return
        distance = point.distance_to(self.center())
        if distance < RETREAT_DISTANCE:
            self._retreating = True
        elif distance >= HOLD_DISTANCE:
            self._retreating = False
        if not self._retreating and distance <= APPROACH_DISTANCE:
            self.halt()
            if self._combat_route:
                self.goal = None
            self._combat_route = False
            return
        if self._move_wait > 0:
            return
        self._move_wait = 0.2
        start = self.follower.current_anchor()
        if self._retreating:
            facing = 1 if point.x >= start.point.x else -1
            dy = point.y - self.center().y
            horizontal = math.sqrt(max(0.0, HOLD_DISTANCE ** 2 - dy ** 2))
            amount = max(0.0, horizontal - abs(point.x - self.center().x))
            goal = retreat_point(self, amount, facing)
        else:
            goal = self.planner.anchor_near(point, 80)
        route = self.planner.plan(start, goal) if goal is not None else None
        self.follower.reset(start)
        self.follower.set_route(route)
        self.goal = goal.point if route is not None else None
        self.goal_reachable = route is not None
        self._combat_route = True

    def _damage(self, target, point, amount, direction):
        if self.thrall:
            target.hurt(amount, point, direction * 35, "thrall", "Shot by a thrall!", attacker=self)
        else:
            self.world.hurt_monster(
                target, amount, point, direction * 35, ranged=True, attacker=self,
            )

    def _update_weapon(self) -> None:
        for index in self.weapon.take_releases():
            if not self._combat_allowed() or self.roll is not None:
                continue
            gun = self.weapon.gun
            origin, direction = self.weapon.muzzle(self.transforms(), self.facing, index % 2)
            point = self._point(self.foe)
            if point is not None:
                direction = (point - self.center()).normalized()
            if gun is Gun.SHOTGUN:
                self.shotgun_cooldown = SHOTGUN_COOLDOWN
                if point is not None:
                    direction = (point - origin).normalized()
                self.shotgun_blast = ShotgunBlast(origin, direction)
                for target, hit in self._enemies():
                    if self.shotgun_blast.contains(hit):
                        self._damage(target, hit, SHOTGUN_DAMAGE, direction)
                self._roll_after = SHOTGUN_RECOVERY
                self.goal = None
                self.halt()
            else:
                reach = math.inf if gun is Gun.SNIPER else PISTOL_RANGE
                valid = point is not None and point.distance_to(self.center()) <= reach
                if gun is Gun.SNIPER:
                    self.sniper_cooldown = SNIPER_COOLDOWN
                end = point if valid else origin + direction * PISTOL_RANGE
                self.tracers.append(Tracer(origin, end, gun))
                if valid:
                    damage = SNIPER_DAMAGE if gun is Gun.SNIPER else PISTOL_DAMAGE
                    self._damage(self.foe, point, damage, direction)
        self.tracers = self.tracers[-16:]

    def _shotgun_recovery(self, dt):
        # Let the muzzle flash and recoil read before tucking into the backward roll.
        self.halt()
        self.locomotion.update(dt, self.follower.command())
        self._roll_after -= dt
        if self._roll_after <= 0:
            self._roll_after = None
            self.roll = start_roll(self)
            self.weapon.cancel()
            self.weapon.held = False
        self.ragdoll.drive(self.locomotion.pose, dt)
        self._track_velocity(dt)

    def _update_roll(self, dt):
        roll = self.roll
        roll.age += dt
        self.follower.reset(Anchor(roll.landing.surface, roll.point()))
        self.follower.facing = roll.facing
        self.locomotion.facing = roll.facing
        self.locomotion.pose = roll_pose(self, roll)
        self.weapon.held = False
        self.weapon.hanging = roll.landing.surface.hanging
        if roll.progress >= 1:
            pose = self.locomotion.pose.copy()
            self.follower.reset(roll.landing)
            self.locomotion.teleport(self.follower.command())
            self.locomotion.blend_from(pose, 0.12)
            self.roll = None
            self._move_wait = 0
        self.ragdoll.facing = self.locomotion.facing
        self.ragdoll.drive(self.locomotion.pose, dt)
        self._track_velocity(dt)

    def terrain_changed(self, change: TerrainChange) -> None:
        rolling = self.roll
        old = self.follower.current_anchor()
        super().terrain_changed(change)
        if rolling is not None and self.roll is not None:
            surface = self.follower.current_anchor().surface
            if not surface.horizontal:
                self.roll = None
                return
            delta = change.delta_for(old.surface.box) or Vec2(0, 0)
            rolling.start += delta
            rolling.landing = Anchor(surface, surface.closest_point(rolling.landing.point + delta))

    def go_ragdoll(self) -> None:
        self.roll = None
        self._roll_after = None
        super().go_ragdoll()
