"""Natures Wrath: an empty-handed hero with a repeating ability rotation."""

from dungeons_desktops.core.geometry import Vec2, clamp
from dungeons_desktops.game.actors.base import surface_below
from dungeons_desktops.game.adventurers.actor import Stickman
from dungeons_desktops.game.heroes.natures_wrath.bear import GiantBear
from dungeons_desktops.game.heroes.natures_wrath.casting import CastingPose
from dungeons_desktops.game.heroes.natures_wrath.dragon import MagmaDragon
from dungeons_desktops.game.heroes.natures_wrath.model import build_natures_wrath
from dungeons_desktops.game.heroes.natures_wrath.spells import (
    ABILITY_DELAYS,
    CAST_RANGE,
    CAST_RELEASE,
    CAST_TIME,
    ROTATION,
    Ability,
    NatureSpells,
)
from dungeons_desktops.game.world.api import World
from dungeons_desktops.navigation.planner import Anchor, Planner
from dungeons_desktops.navigation.terrain import TerrainChange
from dungeons_desktops.rig.locomotion import LocomotionInput, PoseMode


class NaturesWrath(Stickman):
    display_name = "Natures Wrath"
    rotation = ROTATION

    def __init__(self, world: World, anchor: Anchor, wander: bool = False) -> None:
        self.dragon: MagmaDragon | None = None
        self.bear: GiantBear | None = None
        # Desktop entry points supply an adventurer anchor; use this rig's terrain.
        anchor = world.natures_wrath_planner.anchor_near(anchor.point)
        super().__init__(world, anchor, "hero_druid", wander, layout=build_natures_wrath())
        self.nature_time = anchor.point.x * 0.017
        self.spells = NatureSpells(world, self)
        self.casting_pose = CastingPose(self.layout)
        self.locomotion.upper = self.casting_pose
        self.queue_index = 0
        self.casting: Ability | None = None
        self.cast_time = 0.0
        self.cast_wait = 0.0
        self.cast_target: object | None = None
        self.cast_released = False

    def update(self, dt: float) -> None:
        # Released spells finish even if their caster is stunned or killed.
        self.spells.update(dt)
        if self.animated:
            self.nature_time += dt
        if self.form is not None:
            if (
                not self.animated
                or self.thrall
                or self.lure is not None
                or self.reeled is not None
                or self.engulfed_by is not None
                or self.swallowed
            ):
                self._end_form()
            else:
                self._update_form(dt)
                return
        self.cast_wait = max(0.0, self.cast_wait - dt)
        if not self._can_cast():
            self._cancel_cast()
        elif self.casting is None:
            self._begin_cast()
        else:
            self.cast_time += dt
            point = self._target_point()
            if point is None and not self.cast_released:
                self._cancel_cast()
            elif point is not None:
                self._aim_cast(point)
        self.casting_pose.progress = self.cast_progress if self.casting is not None else None
        super().update(dt)
        if self.casting is None:
            return
        if not self.cast_released and self.cast_time >= CAST_RELEASE:
            point = self._target_point()
            if point is None:
                self._cancel_cast()
                return
            if self.casting is Ability.MAGMA_DRAGON:
                self._start_dragon()
                return
            if self.casting is Ability.BEAR:
                self._start_bear()
                return
            velocity = getattr(self.cast_target, "velocity", Vec2(0, 0))
            self.spells.cast(
                self.casting, self.flame_point(), point + velocity * 0.3, self.cast_target
            )
            self.cast_released = True
        if self.cast_time >= CAST_TIME:
            self.queue_index = (self.queue_index + 1) % len(self.rotation)
            self.cast_wait = ABILITY_DELAYS[self.casting]
            self._clear_cast()

    @property
    def planner(self) -> Planner:
        return self.world.natures_wrath_planner

    def attack(self) -> None:
        """Manual attacks use the same queue, windup, and cooldown as automatic casts."""
        if not self._begin_cast():
            name = self.current_ability.value.replace("_", " ").title()
            self.say(f"{name} needs a target in range and a ready casting hand")

    @property
    def current_ability(self) -> Ability:
        return self.rotation[self.queue_index]

    @property
    def cast_progress(self) -> float:
        return clamp(self.cast_time / CAST_TIME, 0.0, 1.0)

    @property
    def movement_paused(self) -> bool:
        return self.casting is not None or super().movement_paused

    def flame_point(self) -> Vec2:
        hand = self.transforms()[self.layout.arms[1].bones[-1]].end
        return hand + Vec2(self.facing * 1.5, -2.0)

    def _can_cast(self) -> bool:
        return (
            self.animated
            and self.form is None
            and self.stun <= 0
            and not self.thrall
            and self.lure is None
            and self.reeled is None
            and not self.swallowed
            and self.dragging_limb is None
            and self._can_act()
        )

    def _target_point(self) -> Vec2 | None:
        if self.cast_target is None:
            return None
        point = self.world.closest_part(self.cast_target, self.center())
        return (
            point if point is not None and point.distance_to(self.center()) <= CAST_RANGE else None
        )

    def _begin_cast(self) -> bool:
        if self.casting is not None or self.cast_wait > 0 or not self._can_cast():
            return False
        found = self.world.nearest_monster(self.center(), CAST_RANGE)
        if found is None:
            return False
        self.cast_target, point = found
        self.casting = self.current_ability
        self.cast_time = 0.0
        self.cast_released = False
        self.halt()
        self._aim_cast(point)
        return True

    def _aim_cast(self, point: Vec2) -> None:
        direction = point - self.center()
        if self.locomotion.mode is PoseMode.WALK and abs(direction.x) > 1:
            self.follower.facing = 1 if direction.x > 0 else -1
        self.casting_pose.direction = Vec2(
            direction.x * self.follower.facing, direction.y
        ).normalized()

    def _clear_cast(self) -> None:
        self.casting = None
        self.cast_target = None
        self.cast_time = 0.0
        self.cast_released = False
        self.casting_pose.progress = None
        if self.goal is not None:
            self.needs_replan = True

    def _cancel_cast(self) -> None:
        if self.casting is not None:
            # An interrupted windup keeps its slot; a released spell consumes it.
            if self.cast_released:
                self.queue_index = (self.queue_index + 1) % len(self.rotation)
                self.cast_wait = ABILITY_DELAYS[self.casting]
            self._clear_cast()

    def _seek(self, dt: float) -> bool:
        # Stay in casting range between spells; otherwise use normal wandering.
        if self._can_cast() and self.world.nearest_monster(self.center(), CAST_RANGE) is not None:
            self.goal = None
            self.halt()
            return True
        return super()._seek(dt)

    def _start_dragon(self) -> None:
        self._clear_cast()
        self.goal = None
        self.halt()
        self.dragon = MagmaDragon(self)
        self._sync_form_pose()

    @property
    def form(self) -> MagmaDragon | GiantBear | None:
        return self.dragon if self.dragon is not None else self.bear

    def _start_bear(self) -> None:
        self._clear_cast()
        self.goal = None
        self.halt()
        self.bear = GiantBear(self)
        self._sync_form_pose()

    def _update_form(self, dt: float) -> None:
        form = self.form
        assert form is not None
        paused = self.stun > 0
        self.stun = max(0.0, self.stun - dt)
        self.blind = max(0.0, self.blind - dt)
        self.faerie = max(0.0, self.faerie - dt)
        self.cooldown -= dt
        for source in self._grace:
            self._grace[source] -= dt
        form.update(dt, paused=paused)
        if self.form is not form:
            return
        self._sync_form_pose()
        if form.finished:
            self._end_form()

    def _sync_form_pose(self) -> None:
        form = self.form
        assert form is not None
        # Keep the humanoid proxy at the form's position for grips, effects and ragdolls.
        self.locomotion.teleport(
            LocomotionInput(
                PoseMode.AIR if form.flying else PoseMode.WALK,
                self.contact(),
                form.facing,
                "nature_form",
            )
        )
        self.follower.facing = form.facing
        self.ragdoll.facing = form.facing
        self.ragdoll.engage(self.locomotion.pose, self.world.step)
        self.velocity = form.velocity
        self._last_contact = self.contact()

    def _end_form(self) -> None:
        if self.form is None:
            return
        contact = self.contact()
        facing = self.form.facing
        ability = Ability.MAGMA_DRAGON if self.dragon is not None else Ability.BEAR
        self.dragon = None
        self.bear = None
        self.queue_index = (self.queue_index + 1) % len(self.rotation)
        self.cast_wait = ABILITY_DELAYS[ability]
        self.goal = None
        self.needs_replan = False
        self._pending_changes.clear()
        anchor = surface_below(self.planner, contact - Vec2(0, 2))
        self.follower.reset(anchor)
        self.follower.facing = facing
        if contact.distance_to(anchor.point) > 2:
            self.fall_in(contact)
        else:
            self.locomotion.teleport(self.follower.command())
            self.ragdoll.engage(self.locomotion.pose, self.world.step)
        self._last_contact = self.contact()

    @property
    def facing(self) -> int:
        return self.form.facing if self.form is not None else super().facing

    def center(self) -> Vec2:
        return self.form.body if self.form is not None else super().center()

    def contact(self) -> Vec2:
        if self.form is not None:
            return self.form.contact()
        return super().contact()

    def hits(self, point: Vec2, margin: float = 0.0) -> bool:
        if self.form is not None:
            return self.form.hits(point, margin)
        return super().hits(point, margin)

    @property
    def limbs_draggable(self) -> bool:
        return self.form is None and super().limbs_draggable

    def terrain_changed(self, change: TerrainChange) -> None:
        if self.form is not None:
            self.form.terrain_changed(change)
            self._sync_form_pose()
        else:
            super().terrain_changed(change)

    def go_ragdoll(self) -> None:
        self._end_form()
        self._cancel_cast()
        super().go_ragdoll()
