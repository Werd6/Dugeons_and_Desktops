"""Protocol exposed to actors without coupling them to :class:`SimWorld`."""

from __future__ import annotations

from random import Random
from typing import TYPE_CHECKING, Protocol

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.navigation.planner import Planner

if TYPE_CHECKING:
    from dungeons_desktops.game.actors.base import Actor
    from dungeons_desktops.game.adventurers.actor import Stickman
    from dungeons_desktops.game.adventurers.alchemy import Vials
    from dungeons_desktops.game.adventurers.spells import Spells
    from dungeons_desktops.game.defenders.graveknights.actor import (
        Graveknight,
        GraveknightPack,
        GraveknightRole,
    )
    from dungeons_desktops.game.defenders.zombies.actor import Zombie, ZombiePack
    from dungeons_desktops.game.effects.chromatic import ChromaticEffects
    from dungeons_desktops.game.effects.gore import Gore
    from dungeons_desktops.game.effects.projectiles import Projectiles


class World(Protocol):
    """The simulation services used by actors and feature systems."""

    boxes: list[Rect]
    floor_y: float
    left: float
    ceiling: float | None
    width: float
    planner: Planner
    zombie_planner: Planner
    zombies: list[Zombie]
    zombie_pack: ZombiePack
    graveknights: list[Graveknight]
    graveknight_pack: GraveknightPack
    goblin_planner: Planner
    natures_wrath_planner: Planner
    mighty_planner: Planner
    mighty_rage_planner: Planner
    iggy_planner: Planner
    hero_paladin_planner: Planner
    projectiles: Projectiles
    vials: Vials
    spells: Spells
    random: Random
    stickmen: list[Stickman]
    step: float
    gore: Gore
    chromatic: ChromaticEffects
    kills: int

    def say(self, actor: Actor, message: str) -> None: ...

    def nearest_monster(
        self, point: Vec2, reach: float, through_ground: bool = False
    ) -> tuple[object, Vec2] | None: ...

    def monsters_near(
        self, point: Vec2, reach: float, through_ground: bool = False
    ) -> list[tuple[object, Vec2]]: ...

    def monsters(self) -> list[object]: ...

    def locate(self, monster: object) -> Vec2 | None: ...

    def monster_at(self, point: Vec2) -> object | None: ...

    def illusions(self) -> list: ...

    def locate_prey(self, stickman: object) -> Vec2 | None: ...

    def closest_part(
        self, monster: object, point: Vec2, through_ground: bool = False
    ) -> Vec2 | None: ...

    def hurt_monster(
        self,
        monster: object,
        amount: float,
        point: Vec2,
        push: Vec2,
        ranged: bool = False,
        attacker: object = None,
    ) -> bool: ...

    def detonate(self, center: Vec2) -> None: ...

    def mark_kill(self, point: Vec2) -> None: ...

    def record_enemy_kill(self, victim: Stickman, source: str, point: Vec2) -> None: ...

    def spawn_devourer(self, point: Vec2) -> None: ...

    def add_zombie(self, point: Vec2 | None = None, *, legendary: bool = False) -> Zombie: ...

    def add_graveknight(
        self,
        point: Vec2 | None = None,
        role: GraveknightRole | str | None = None,
    ) -> Graveknight: ...

    def add_graveknights(self, point: Vec2 | None = None) -> list[Graveknight]: ...

    def add_stickman(
        self, point: Vec2 | None = None, variant: str = "unarmed", wander: bool = False
    ) -> Stickman: ...

    def capture_adventurer_soul(self, stickman: Stickman, point: Vec2) -> bool: ...
