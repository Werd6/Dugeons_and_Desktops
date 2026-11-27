"""Iggy chooses ready spells independently; his simulacra cannot create more copies."""

from __future__ import annotations

import math
from dataclasses import replace

from dungeons_desktops.core.geometry import Vec2, smoothstep
from dungeons_desktops.game.adventurers.actor import Stickman
from dungeons_desktops.game.defenders.lich.actor import (
    DOOR_EMERGE,
    DOOR_FADE,
    DOOR_FIRST,
    DOOR_STEP_OUT,
    DOOR_SWAP,
    DOOR_TIME,
    Door,
)
from dungeons_desktops.game.heroes.the_inquisitive.companion import CatCompanion
from dungeons_desktops.game.heroes.the_inquisitive.dimension_door import (
    carry_anchor,
    choose_door,
    door_spot,
    valid_landing,
)
from dungeons_desktops.game.heroes.the_inquisitive.model import build_gnome_wizard
from dungeons_desktops.game.heroes.the_inquisitive.spells import (
    CAST_RANGE,
    CAST_RECOVERY,
    CAST_RELEASE,
    CAST_TIME,
    COOLDOWNS,
    COPY_HP,
    COPY_LIMIT,
    MISSILE_COUNT,
    MISSILE_INTERVAL,
    RAY_CAST_TIME,
    RAY_REACH,
    VOLLEY_TIME,
    Ability,
    IggySpells,
    Sparkle,
)
from dungeons_desktops.game.heroes.the_inquisitive.weapon import IggyWand
from dungeons_desktops.game.unlocks import HERO_NAMES
from dungeons_desktops.game.world.api import World
from dungeons_desktops.navigation.planner import Anchor, Planner
from dungeons_desktops.navigation.terrain import TerrainChange
from dungeons_desktops.rig.equipment import Stroke, Weapon
from dungeons_desktops.rig.skeleton import BoneTransform


class Iggy(Stickman):
    display_name = HERO_NAMES["hero_wizard"]
    is_simulacrum = False
    mindflayer_stun_immune = True

    def __init__(self, world: World, anchor: Anchor, wander: bool = False) -> None:
        self.door: Door | None = None
        self.casting: Ability | None = None
        anchor = world.iggy_planner.anchor_near(anchor.point)
        super().__init__(world, anchor, "hero_wizard", wander, layout=build_gnome_wizard())
        self.weapon = IggyWand(self.layout)
        self.locomotion.upper = self.weapon
        self.cat = CatCompanion(self)
        self.spells = IggySpells(world, self)
        self.cooldowns = {
            ability: (DOOR_FIRST if ability is Ability.DIMENSION_DOOR else 0.0)
            for ability in Ability
            if not (self.is_simulacrum and ability is Ability.SIMULACRUM)
        }
        self.cast_time = 0.0
        self.cast_target: object | None = None
        self.cast_point = self.center()
        self.cast_released = False
        self.missiles_fired = 0
        self.recovery = 0.0

    @property
    def planner(self) -> Planner:
        return self.world.iggy_planner

    def update(self, dt: float) -> None:
        self.spells.update(dt)
        for ability in self.cooldowns:
            self.cooldowns[ability] = max(0.0, self.cooldowns[ability] - dt)
        self.recovery = max(0.0, self.recovery - dt)
        if not self._casting_allowed():
            self._clear_cast()
            self.door = None
        elif self.door is not None:
            self._step_door(dt)
        elif self.casting is not None:
            self.cast_time += dt
            if self.casting is Ability.CHROMATIC_RAY and self.cast_released:
                direction = self.spells.advance_ray(dt)
                if direction is not None:
                    self._aim(self.center() + direction * RAY_REACH)
                    self.weapon.beam_aim = self.weapon.aim
            else:
                point = self.world.closest_part(self.cast_target, self.center())
                if point is not None:
                    self.cast_point = point
                    self._aim(point)
                elif not self.cast_released and self.casting is not Ability.SIMULACRUM:
                    self._clear_cast()
        else:
            self._begin_cast()
        super().update(dt)
        if self.casting is Ability.CHROMATIC_RAY and self.cast_released:
            self.spells.resolve_ray(self.wand_tip())
        if self.casting is not None:
            self._cast_step()
        self.cat.update(dt)

    def _casting_allowed(self) -> bool:
        return (
            self.animated and not self.thrall and self.stun <= 0 and self.blind <= 0
            and self.lure is None and self.reeled is None and not self.swallowed
            and self.engulfed_by is None and self.dragging_limb is None
            and self._can_act()
        )

    @property
    def copies(self) -> list[Simulacrum]:
        return [
            actor for actor in self.world.stickmen
            if isinstance(actor, Simulacrum) and actor.summoner is self
            and actor.hp > 0 and not actor.gone
        ]

    def attack(self) -> None:
        if not self._begin_cast():
            self.say("Iggy needs a ready spell and a valid target")

    def cast_spell(self, ability: Ability) -> bool:
        """Explicit casts share the same eligibility and cooldowns as autonomous casts."""
        return self._begin_cast(ability)

    def _begin_cast(self, ability: Ability | None = None) -> bool:
        if (
            not self._casting_allowed() or self.casting is not None
            or self.door is not None or self.recovery > 0
        ):
            return False
        found = self.world.nearest_monster(self.center(), CAST_RANGE)
        ready = [spell for spell, wait in self.cooldowns.items() if wait <= 0]
        door = None
        if Ability.DIMENSION_DOOR in ready and ability in (None, Ability.DIMENSION_DOOR):
            door = choose_door(self)
        eligible = []
        for spell in ready:
            if spell is Ability.DIMENSION_DOOR:
                if door is not None:
                    eligible.append(spell)
            elif spell is Ability.SIMULACRUM:
                if len(self.copies) < COPY_LIMIT:
                    eligible.append(spell)
            elif found is not None:
                eligible.append(spell)
        if ability is not None:
            if ability not in eligible:
                return False
        elif Ability.SIMULACRUM in eligible:
            ability = Ability.SIMULACRUM
        elif door is not None:
            ability = Ability.DIMENSION_DOOR
        elif eligible:
            ability = self.world.random.choice(eligible)
        else:
            return False
        self.halt()
        if ability is Ability.DIMENSION_DOOR:
            target, landing = door
            self.cast_target = target
            origin = self.follower.current_anchor()
            self.door = Door(origin.point, origin.surface, landing.point, landing.surface)
            self.cooldowns[ability] = COOLDOWNS[ability]
            self.weapon.duration = CAST_TIME
            self.weapon.start()
            return True
        self.casting = ability
        self.cast_time = 0.0
        self.cast_released = False
        self.missiles_fired = 0
        self.cast_target, self.cast_point = found or (
            None, self.center() + Vec2(self.facing * 30, 0)
        )
        self._aim(self.cast_point)
        self.weapon.duration = self._cast_duration(ability)
        self.weapon.start()
        return True

    def _aim(self, point: Vec2) -> None:
        self._face(point, self.weapon)
        direction = point - self.center()
        self.weapon.aim = math.atan2(direction.y, abs(direction.x))

    def wand_tip(self) -> Vec2:
        return self.weapon.tip(self.transforms(), self.facing)

    def _cast_step(self) -> None:
        spell = self.casting
        if self.cast_time < CAST_RELEASE:
            return
        if not self.cast_released:
            if spell is Ability.SIMULACRUM:
                if self._summon() is None:
                    self._clear_cast()
                    return
            elif spell is Ability.CHROMATIC_RAY:
                if not self.spells.ray(self.wand_tip(), self.cast_target):
                    self._clear_cast()
                    return
            self.cast_released = True
            self.cooldowns[spell] = COOLDOWNS[spell]
        if spell is Ability.MAGIC_MISSILE:
            while (
                self.missiles_fired < MISSILE_COUNT
                and self.cast_time + 1e-9 >= CAST_RELEASE + self.missiles_fired * MISSILE_INTERVAL
            ):
                point = self.world.closest_part(self.cast_target, self.wand_tip())
                if point is None:
                    found = self.world.nearest_monster(self.center(), CAST_RANGE)
                    self.cast_target, point = found or (None, self.cast_point)
                self.spells.missile(self.wand_tip(), self.cast_target, point)
                self.missiles_fired += 1
        duration = self._cast_duration(spell)
        if self.cast_time >= duration:
            self.recovery = CAST_RECOVERY
            self._clear_cast()

    @staticmethod
    def _cast_duration(ability: Ability) -> float:
        if ability is Ability.MAGIC_MISSILE:
            return VOLLEY_TIME
        if ability is Ability.CHROMATIC_RAY:
            return RAY_CAST_TIME
        return CAST_TIME

    def _summon(self) -> Simulacrum | None:
        if self.is_simulacrum or len(self.copies) >= COPY_LIMIT:
            return None
        here = self.follower.current_anchor()
        surface = here.surface
        direction = 1 if len(self.copies) % 2 else -1
        offset = direction * (18 + 10 * (len(self.copies) // 2))
        coordinate = max(surface.low, min(surface.high, surface.coord(here.point) + offset))
        point = surface.point_at(coordinate)
        copy = Simulacrum(self.world, Anchor(surface, point), self)
        self.world.stickmen.append(copy)
        self.spells.sparks.append(Sparkle(copy.center(), (100, 195, 255), 18))
        return copy

    def _clear_cast(self) -> None:
        if self.casting is Ability.CHROMATIC_RAY:
            self.spells.stop_ray()
        if self.casting is not None or self.door is not None:
            self.weapon.cancel()
            if self.goal is not None:
                self.needs_replan = True
        self.casting = None

    def _engage(self) -> bool:
        return False  # Only this spellbook starts attacks; the ordinary wand is its animation.

    def _release(self, weapon: Weapon, transforms: dict[str, BoneTransform], facing: int) -> None:
        pass  # Release timing and individual volley shots are handled by _cast_step.

    @property
    def movement_paused(self) -> bool:
        return self.casting is not None or self.door is not None or super().movement_paused

    def _seek(self, dt: float) -> bool:
        if self.casting is not None or self.door is not None:
            return True
        return super()._seek(dt)

    @property
    def visibility(self) -> float:
        door = self.door
        if door is None or door.time < DOOR_FADE:
            return 1.0
        if door.time < DOOR_SWAP:
            return 1 - smoothstep((door.time - DOOR_FADE) / (DOOR_SWAP - DOOR_FADE))
        if door.time < DOOR_EMERGE:
            return 0.0
        return smoothstep((door.time - DOOR_EMERGE) / DOOR_STEP_OUT)

    @property
    def phased(self) -> bool:
        return self.door is not None and self.visibility < 0.5

    @property
    def prey(self) -> bool:
        return super().prey and not self.phased

    def hits(self, point: Vec2, margin: float = 0) -> bool:
        return not self.phased and super().hits(point, margin)

    def hurt(self, amount, point, push, source, death, bleed=True, attacker=None) -> bool:
        if self.phased:
            return False
        return super().hurt(amount, point, push, source, death, bleed, attacker)

    def _teleport(self, anchor: Anchor) -> None:
        self.follower.reset(anchor)
        if self.cast_target is not None:
            point = self.world.locate(self.cast_target)
            if point is not None:
                self.follower.facing = 1 if point.x > anchor.point.x else -1
        self.goal = None
        self.needs_replan = False
        self._pending_changes.clear()
        self.locomotion.teleport(self.follower.command())
        self.ragdoll.engage(self.locomotion.pose, self.world.step)
        self._last_contact = anchor.point
        self.velocity = Vec2(0, 0)
        self.cat._recall()

    def _step_door(self, dt: float) -> None:
        door = self.door
        door.time += dt
        if not door.moved and door.time >= DOOR_SWAP:
            landing = Anchor(door.surface, door.target)
            if not valid_landing(self, landing):
                landing = door_spot(self, self.cast_target)
                if landing is None and door.origin_surface is not None:
                    origin = Anchor(door.origin_surface, door.origin)
                    landing = origin if valid_landing(self, origin) else None
                if landing is None:
                    self.door = None
                    return
            door.surface, door.target = landing.surface, landing.point
            door.moved = True
            self._teleport(landing)
        if door.time >= DOOR_TIME:
            self.door = None
            self.recovery = CAST_RECOVERY

    def terrain_changed(self, change: TerrainChange) -> None:
        door = self.door
        if door is not None:
            origin = (
                carry_anchor(self, Anchor(door.origin_surface, door.origin), change)
                if door.origin_surface is not None else None
            )
            target = carry_anchor(self, Anchor(door.surface, door.target), change)
            door.origin_surface = origin.surface if origin is not None else None
            if origin is not None:
                door.origin = origin.point
            target = target or door_spot(self, self.cast_target) or origin
            if target is None:
                self.door = None
            else:
                door.surface, door.target = target.surface, target.point
        super().terrain_changed(change)
        self.cat.terrain_changed(change)
        self.spells.move_ray(self.wand_tip())


class Simulacrum(Iggy):
    display_name = "Iggy's Simulacrum"
    is_simulacrum = True

    def __init__(self, world: World, anchor: Anchor, summoner: Iggy) -> None:
        self.summoner = summoner
        super().__init__(world, anchor, wander=True)
        self.calling = replace(self.calling, hp=COPY_HP)
        # Each copy gets independent clocks and a short entrance before its first cast.
        self.recovery = 0.5

    def weapon_strokes(self) -> list[Stroke]:
        return [replace(stroke, kind="simulacrum") for stroke in super().weapon_strokes()]
