"""A skull-faced sorcerer hero with a repeating dark-magic rotation."""

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.adventurers.actor import Stickman
from dungeons_desktops.game.heroes.hero_sorcerer.blood_cloud import BloodCloud
from dungeons_desktops.game.heroes.hero_sorcerer.corpsenado import Corpsenado
from dungeons_desktops.game.heroes.hero_sorcerer.rotation import (
    CAST_RANGE,
    RAPID_BOLT_SLOTS,
    ROTATION,
    STEP_DELAYS,
    Ability,
)
from dungeons_desktops.game.heroes.hero_sorcerer.skeletal_grasp import SkeletalGrasp
from dungeons_desktops.game.heroes.hero_sorcerer.weapon import SkullFocus
from dungeons_desktops.game.unlocks import HERO_NAMES
from dungeons_desktops.game.world.api import World
from dungeons_desktops.navigation.planner import Anchor
from dungeons_desktops.navigation.terrain import TerrainChange


class HeroSorcerer(Stickman):
    display_name = HERO_NAMES["hero_sorcerer"]
    rotation = ROTATION

    def __init__(self, world: World, anchor: Anchor, wander: bool = False) -> None:
        self.corpsenado: Corpsenado | None = None
        self.blood_cloud: BloodCloud | None = None
        self.skeletal_grasp: SkeletalGrasp | None = None
        self.queue_index = 0
        self.casting: Ability | None = None
        self.cast_wait = 0.0
        self.cast_target: object | None = None
        self.cast_released = False
        super().__init__(world, anchor, "hero_sorcerer", wander)

    @property
    def current_ability(self) -> Ability:
        return self.rotation[self.queue_index]

    def update(self, dt: float) -> None:
        # Persistent spells keep resolving after their caster is interrupted or killed.
        self._update_spells(dt)
        self.cast_wait = max(0.0, self.cast_wait - dt)

        if not self._can_rotate():
            self._cancel_rotation_cast()
        elif self.casting is None:
            self._begin_rotation_cast()
        elif not self.cast_released:
            point = self._target_point()
            if point is None:
                self._cancel_rotation_cast()
            else:
                assert self.weapon is not None
                self._face(point, self.weapon)

        super().update(dt)

        if self.casting is not None and (self.weapon is None or not self.weapon.busy):
            if self.cast_released:
                self._finish_rotation_cast()
            else:
                self._clear_rotation_cast()

    def attack(self) -> None:
        """Manual attacks use the next slot in the same automatic rotation."""
        if not self._begin_rotation_cast():
            name = self.current_ability.value.replace("_", " ").title()
            self.say(f"{name} needs a target in range and a ready focus")

    def _engage(self) -> bool:
        # The base ranged AI would inject extra bolts between rotation slots.
        return False

    def _can_rotate(self) -> bool:
        return (
            self.animated
            and not self.thrall
            and not self.paralysed
            and self.lure is None
            and self.reeled is None
            and self.engulfed_by is None
            and self.dragging_limb is None
            and self._can_act()
        )

    def _begin_rotation_cast(self) -> bool:
        weapon = self.weapon
        if (
            self.casting is not None
            or self.cast_wait > 0.0
            or not self._can_rotate()
            or weapon is None
            or weapon.busy
        ):
            return False
        found = self.world.nearest_monster(self.center(), CAST_RANGE)
        if found is None:
            return False
        monster, point = found
        self.casting = self.current_ability
        self.cast_target = monster
        self.cast_released = False
        if isinstance(weapon, SkullFocus):
            weapon.set_rapid(self.queue_index in RAPID_BOLT_SLOTS)
        self._strike(monster, point)
        return True

    def _target_point(self) -> Vec2 | None:
        if self.cast_target is None:
            return None
        point = self.world.closest_part(self.cast_target, self.center())
        if point is None or point.distance_to(self.center()) > CAST_RANGE:
            return None
        return point

    def _release(self, weapon, transforms, facing: int) -> None:
        ability = self.casting
        if ability is None:
            super()._release(weapon, transforms, facing)
            return
        point = self._target_point()
        if point is None:
            return
        if ability is Ability.BOLT:
            super()._release(weapon, transforms, facing)
        elif ability is Ability.SKELETAL_ARMS:
            grasp = SkeletalGrasp.summon(self, point)
            if grasp is not None:
                self.skeletal_grasp = grasp
                self.say("Skeletal Grasp!")
        elif ability is Ability.CORPSENADO:
            self.corpsenado = Corpsenado.summon(self, point)
            self.say("Corpsenado!")
        elif ability is Ability.BLOOD_CLOUD:
            self.blood_cloud = BloodCloud(self, point)
            self.say("Cloud of Leeching Blood!")
        self.cast_released = True

    def _finish_rotation_cast(self) -> None:
        index = self.queue_index
        self.queue_index = (index + 1) % len(self.rotation)
        self.cast_wait = STEP_DELAYS[index]
        self._clear_rotation_cast()

    def _cancel_rotation_cast(self) -> None:
        if self.casting is None:
            return
        if self.cast_released:
            self._finish_rotation_cast()
            return
        if self.weapon is not None:
            self.weapon.cancel()
        self._clear_rotation_cast()

    def _clear_rotation_cast(self) -> None:
        self.casting = None
        self.cast_target = None
        self.cast_released = False
        if self.goal is not None:
            self.needs_replan = True

    def _update_spells(self, dt: float) -> None:
        for name in ("corpsenado", "blood_cloud", "skeletal_grasp"):
            spell = getattr(self, name)
            if spell is None:
                continue
            spell.update(dt)
            if spell.expired:
                setattr(self, name, None)

    def terrain_changed(self, change: TerrainChange) -> None:
        super().terrain_changed(change)
        if self.skeletal_grasp is not None:
            self.skeletal_grasp.terrain_changed(change)
