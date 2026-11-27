"""Extracted world services mixed into :class:`SimWorld`."""

from __future__ import annotations

import math

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.game.actors.base import surface_below
from dungeons_desktops.game.adventurers import model as stick_figure
from dungeons_desktops.game.adventurers.actor import Stickman
from dungeons_desktops.game.defenders.aboleth.actor import Aboleth
from dungeons_desktops.game.defenders.chimera.actor import Chimera
from dungeons_desktops.game.defenders.displacer.actor import Displacer
from dungeons_desktops.game.defenders.dragon.actor import Dragon
from dungeons_desktops.game.defenders.drakes.drake import COLOURS, Drake
from dungeons_desktops.game.defenders.drakes.kobold import Kobold
from dungeons_desktops.game.defenders.drow.actor import Drow, Lizard
from dungeons_desktops.game.defenders.goblins.actor import PACK, Goblin
from dungeons_desktops.game.defenders.graveknights.actor import (
    GRAVEKNIGHT_PACK,
    GRAVEKNIGHT_ROSTER,
    Graveknight,
    GraveknightRole,
)
from dungeons_desktops.game.defenders.hydra import actor as serpent
from dungeons_desktops.game.defenders.hydra.actor import Hydra
from dungeons_desktops.game.defenders.legendary import apply_legendary
from dungeons_desktops.game.defenders.lich.actor import Lich
from dungeons_desktops.game.defenders.mimic import actor as chest
from dungeons_desktops.game.defenders.mimic.actor import Mimic
from dungeons_desktops.game.defenders.mindflayer.actor import MindFlayer
from dungeons_desktops.game.defenders.mindflayer.devourer import Devourer
from dungeons_desktops.game.defenders.minotaur.actor import Minotaur
from dungeons_desktops.game.defenders.worm.actor import DEVOURER_HP, Worm
from dungeons_desktops.game.defenders.zombies.actor import Zombie
from dungeons_desktops.game.effects.breath import VARIANTS
from dungeons_desktops.game.heroes.hero_alchemist.actor import HeroAlchemist
from dungeons_desktops.game.heroes.hero_cleric.actor import HeroCleric
from dungeons_desktops.game.heroes.hero_fighter.actor import HeroFighter
from dungeons_desktops.game.heroes.hero_paladin.actor import HeroPaladin
from dungeons_desktops.game.heroes.hero_sorcerer.actor import HeroSorcerer
from dungeons_desktops.game.heroes.natures_wrath.actor import NaturesWrath
from dungeons_desktops.game.heroes.the_hunter.actor import TheHunter
from dungeons_desktops.game.heroes.the_inquisitive.actor import Iggy
from dungeons_desktops.game.heroes.the_mighty.actor import TheMighty
from dungeons_desktops.game.heroes.the_slayer.actor import TheSlayer
from dungeons_desktops.navigation.planner import Anchor, Planner
from dungeons_desktops.navigation.terrain import Terrain

MISSILE_BOXES: tuple[Rect, ...] = ()
"""What arrows, bombs, spears and bullets collide with besides the floor: nothing, they
fly straight through windows."""
BLAST_REACH = 6.0
"""How far past a bomb blast's radius it still catches a monster's nearest part."""
KILL_MARK_TIME = 1.4
"""How long a "+skull" floats over a fallen adventurer."""




class SpawningMixin:
    def capture_adventurer_soul(self, stickman: Stickman, point: Vec2) -> bool:
        """Send a regular, free adventurer's soul to the nearest living Hero Cleric."""
        if (
            stickman.variant not in stick_figure.CLASSES
            or stickman.thrall
            or getattr(stickman, "_soul_claimed", False)
        ):
            return False
        clerics = [
            hero
            for hero in self.heroes
            if isinstance(hero, HeroCleric) and hero.animated and hero is not stickman
        ]
        if not clerics:
            return False
        cleric = min(clerics, key=lambda hero: hero.center().distance_to(point))
        stickman._soul_claimed = True
        cleric.capture_soul(stickman.variant, point)
        return True

    def add_stickman(
        self, point: Vec2 | None = None, variant: str = "unarmed", wander: bool = False
    ) -> Stickman:
        if point is None:
            point = Vec2(self.random.uniform(self.left, self.width), self.floor_y)
        anchor = self.planner.anchor_near(point, walk_only=True)
        return self._add_stickman(anchor, variant, wander)

    def _add_stickman(self, anchor: Anchor, variant: str, wander: bool) -> Stickman:
        if variant == "hero_fighter":
            stickman = HeroFighter(self, anchor, wander)
            self.heroes.append(stickman)
        elif variant == "hero_alchemist":
            stickman = HeroAlchemist(self, anchor, wander)
            self.heroes.append(stickman)
        elif variant == "hero_sorcerer":
            stickman = HeroSorcerer(self, anchor, wander)
            self.heroes.append(stickman)
        elif variant == "hero_cleric":
            stickman = HeroCleric(self, anchor, wander)
            self.heroes.append(stickman)
        elif variant == "hero_druid":
            stickman = NaturesWrath(self, anchor, wander)
            self.heroes.append(stickman)
        elif variant == "hero_barbarian":
            stickman = TheMighty(self, anchor, wander)
            self.heroes.append(stickman)
        elif variant == "hero_wizard":
            stickman = Iggy(self, anchor, wander)
            self.heroes.append(stickman)
        elif variant == "hero_rogue":
            stickman = TheSlayer(self, anchor, wander)
            self.heroes.append(stickman)
        elif variant == "hero_paladin":
            stickman = HeroPaladin(self, anchor, wander)
            self.heroes.append(stickman)
        elif variant == "hero_ranger":
            stickman = TheHunter(self, anchor, wander)
            self.heroes.append(stickman)
        else:
            stickman = Stickman(self, anchor, variant, wander)
        self.stickmen.append(stickman)
        return stickman

    def add_goblin(
        self,
        point: Vec2 | None = None,
        kind: str | None = None,
        *,
        legendary: bool = False,
        crowned: bool = False,
    ) -> Goblin:
        """`kind` is "sword", "spear" or "flag"; by default the next one in `PACK`."""
        if point is None:
            if self.boxes:
                box = self.random.choice(self.boxes)
                point = Vec2(box.x + box.width * self.random.uniform(0.2, 0.8), box.top - 5.0)
            else:
                point = Vec2(self.random.uniform(self.left, self.width), self.floor_y - 5.0)
        if kind is None:
            kind = PACK[len(self.goblins) % len(PACK)]
        goblin_ = Goblin(
            self,
            surface_below(self.goblin_planner, point),
            kind,
            legendary=legendary,
            crowned=crowned and legendary,
        )
        if legendary and not goblin_.crowned:
            apply_legendary(goblin_)
        self.goblins.append(goblin_)
        return goblin_

    def add_zombie(self, point: Vec2 | None = None, *, legendary: bool = False) -> Zombie:
        """Place a zombie on the window top or floor below the requested point."""
        if point is None:
            if self.boxes:
                box = self.random.choice(self.boxes)
                point = Vec2(box.x + box.width * self.random.uniform(0.2, 0.8), box.top)
            else:
                point = Vec2(self.random.uniform(self.left, self.width), self.floor_y)
        zombie = Zombie(self, surface_below(self.zombie_planner, point), legendary=legendary)
        self.zombies.append(zombie)
        return zombie

    def add_graveknight(
        self,
        point: Vec2 | None = None,
        role: GraveknightRole | str | None = None,
        *,
        legendary: bool = False,
    ) -> Graveknight:
        """Place one fixed-role Graveknight; omitted roles cycle through the roster."""
        if point is None:
            if self.boxes:
                box = self.random.choice(self.boxes)
                point = Vec2(box.x + box.width * self.random.uniform(0.2, 0.8), box.top)
            else:
                point = Vec2(self.random.uniform(self.left, self.width), self.floor_y)
        if role is None:
            role = GRAVEKNIGHT_ROSTER[len(self.graveknights) % GRAVEKNIGHT_PACK]
        knight = Graveknight(self, surface_below(self.planner, point), role)
        if legendary:
            apply_legendary(knight)
        self.graveknights.append(knight)
        return knight

    def add_graveknights(self, point: Vec2 | None = None) -> list[Graveknight]:
        """Muster the complete four-knight squad around one requested point."""
        if point is None:
            if self.boxes:
                box = self.random.choice(self.boxes)
                point = Vec2(box.x + box.width * 0.5, box.top)
            else:
                point = Vec2((self.left + self.width) * 0.5, self.floor_y)
        anchor = surface_below(self.planner, point)
        surface = anchor.surface
        center = surface.coord(anchor.point)
        spacing = 12.0
        knights = []
        for index, role in enumerate(GRAVEKNIGHT_ROSTER):
            offset = (index - (GRAVEKNIGHT_PACK - 1) / 2) * spacing
            along = min(surface.high, max(surface.low, center + offset))
            knights.append(self.add_graveknight(surface.point_at(along), role))
        return knights

    def add_worm(
        self, head: Vec2 | None = None, heading: float | None = None, *, legendary: bool = False
    ) -> Worm:
        """Defaults to burrowing just below the floor at a random spot."""
        if head is None:
            head = Vec2(self.random.uniform(self.left + 40.0, self.width - 40.0), self.floor_y + 25)
        if heading is None:
            heading = self.random.choice((0.0, math.pi))
        worm = Worm(self, head, heading)
        if legendary:
            apply_legendary(worm)
            worm.max_hp = DEVOURER_HP
        self.worms.append(worm)
        return worm

    def add_dragon(
        self,
        body: Vec2 | None = None,
        facing: int | None = None,
        variant: str | None = None,
        *,
        legendary: bool = False,
    ) -> Dragon:
        """Flies in; defaults to entering from a random side just under the screen top,
        in a random colour (`breath.VARIANTS`)."""
        if variant is None:
            variant = self.random.choice(VARIANTS)
        if facing is None:
            facing = self.random.choice((-1, 1))
        if body is None:
            top = self.ceiling if self.ceiling is not None else 0.0
            x = self.left - 30.0 if facing > 0 else self.width + 30.0
            body = Vec2(x, top + self.random.uniform(70.0, 150.0))
        dragon = Dragon(self, body, facing, variant=variant)
        if legendary:
            apply_legendary(dragon)
        self.dragons.append(dragon)
        return dragon

    def add_drake(
        self,
        point: Vec2 | None = None,
        variant: str | None = None,
        facing: int | None = None,
        *,
        legendary: bool = False,
    ) -> Drake:
        """Stands at `point` (snapped to the walkable spot below it); by default on a random
        window top, in the next colour of the pack (`drakes.COLOURS`)."""
        if point is None:
            if self.boxes:
                box = self.random.choice(self.boxes)
                point = Vec2(box.x + box.width * self.random.uniform(0.2, 0.8), box.top - 5.0)
            else:
                point = Vec2(self.random.uniform(self.left, self.width), self.floor_y - 5.0)
        slot = len(self.drakes)
        if variant is None:
            variant = COLOURS[slot % len(COLOURS)]
        if facing is None:
            facing = self.random.choice((-1, 1))
        anchor = surface_below(self.goblin_planner, point)
        drake = Drake(self, anchor.point, facing, variant=variant, slot=slot)
        drake.support = anchor.surface
        drake.x = anchor.point.x
        drake.snap()
        if legendary:
            apply_legendary(drake)
            if variant == "red":
                from dungeons_desktops.game.defenders.drakes.drake import RED_ALPHA_SIZE

                drake.legendary_alpha = True
                drake.size = RED_ALPHA_SIZE
                drake.max_hp = max(1, int(round(drake.max_hp * 1.25)))
                drake.damage = 0
        self.drakes.append(drake)
        return drake

    def add_kobold(
        self,
        point: Vec2,
        variant: str = "red",
        facing: int = 1,
        velocity: Vec2 | None = None,
        aim: Vec2 | None = None,
        *,
        legendary: bool = False,
    ) -> Kobold:
        """A kobold on foot: standing at `point` (snapped to the walkable spot below it),
        or with a `velocity` leaping from there - off a dying drake."""
        if velocity is None:
            point = surface_below(self.goblin_planner, point).point
        kobold = Kobold(self, point, variant, facing, velocity or Vec2(0.0, 0.0))
        kobold.legendary = legendary
        if aim is not None:
            kobold.aim = aim
        self.kobolds.append(kobold)
        return kobold

    def add_lizard(
        self, point: Vec2 | None = None, heading: int | None = None, *, legendary: bool = False
    ) -> Lizard:
        """A drow on his lizard at `point` (snapped to the nearest window top or the floor);
        by default on a random window top."""
        if point is None:
            if self.boxes:
                box = self.random.choice(self.boxes)
                point = Vec2(box.x + box.width * self.random.uniform(0.2, 0.8), box.top)
            else:
                point = Vec2(self.random.uniform(self.left, self.width), self.floor_y)
        if heading is None:
            heading = self.random.choice((-1, 1))
        anchor = self.lizard_planner.anchor_near(point, walk_only=True)
        lizard = Lizard(self, anchor, heading=heading, slot=len(self.lizards))
        if legendary:
            apply_legendary(lizard)
        self.lizards.append(lizard)
        return lizard

    def add_drow(self, point: Vec2, facing: int = 1, leap: Vec2 | None = None) -> Drow:
        """A drow on foot at `point`, or (`leap`ing off his dying lizard) dropping from
        there onto whatever is below."""
        anchor = surface_below(self.planner, point)
        drow = Drow(self, anchor, facing)
        if leap is not None and anchor.point.y - point.y > 2.0:
            drow.drop_from(point)
            drow.locomotion.teleport(drow.follower.command())
            drow._last_contact = point
        self.drow.append(drow)
        return drow

    def add_mindflayer(self, point: Vec2 | None = None, *, legendary: bool = False) -> MindFlayer:
        """Floats in at `point` (snapped to the nearest walkable spot); by default on a
        random window top."""
        if point is None:
            if self.boxes:
                box = self.random.choice(self.boxes)
                point = Vec2(box.x + box.width * self.random.uniform(0.2, 0.8), box.top)
            else:
                point = Vec2(self.random.uniform(self.left, self.width), self.floor_y)
        flayer = MindFlayer(self, self.planner.anchor_near(point, walk_only=True))
        if legendary:
            apply_legendary(flayer)
        self.mindflayers.append(flayer)
        return flayer

    def add_displacer(self, point: Vec2 | None = None, *, legendary: bool = False) -> Displacer:
        """Prowls in at `point` (snapped to the nearest window top or the floor); by default
        on a random window top."""
        if point is None:
            if self.boxes:
                box = self.random.choice(self.boxes)
                point = Vec2(box.x + box.width * self.random.uniform(0.2, 0.8), box.top)
            else:
                point = Vec2(self.random.uniform(self.left, self.width), self.floor_y)
        anchor = self.displacer_planner.anchor_near(point, walk_only=True)
        displacer = Displacer(self, anchor, heading=self.random.choice((-1, 1)))
        if legendary:
            apply_legendary(displacer)
        self.displacers.append(displacer)
        return displacer

    def add_minotaur(self, point: Vec2 | None = None, *, legendary: bool = False) -> Minotaur:
        """Stomps in at `point` (snapped to the nearest window top or the floor); by
        default on a random window top."""
        if point is None:
            if self.boxes:
                box = self.random.choice(self.boxes)
                point = Vec2(box.x + box.width * self.random.uniform(0.2, 0.8), box.top)
            else:
                point = Vec2(self.random.uniform(self.left, self.width), self.floor_y)
        anchor = self.minotaur_planner.anchor_near(point, walk_only=True)
        minotaur = Minotaur(self, anchor, heading=self.random.choice((-1, 1)))
        if legendary:
            apply_legendary(minotaur)
            minotaur._apply_legendary_size()
        self.minotaurs.append(minotaur)
        return minotaur


    def add_aboleth(self, point: Vec2 | None = None, facing: int | None = None) -> Aboleth:
        """Place an aboleth swimming freely in the air."""
        top = self.ceiling if self.ceiling is not None else 0.0
        if point is None:
            point = Vec2(
                self.random.uniform(self.left + 80.0, self.width - 80.0),
                self.random.uniform(top + 80.0, max(top + 100.0, self.floor_y - 120.0)),
            )
        if facing is None:
            facing = self.random.choice((-1, 1))
        aboleth = Aboleth(self, point, facing)
        self.aboleths.append(aboleth)
        return aboleth

    def add_chimera(
        self, point: Vec2 | None = None, facing: int | None = None, *, legendary: bool = False
    ) -> Chimera:
        """Prowls in at `point` (snapped to the nearest window top or the floor); by
        default on a random window top."""
        if point is None:
            if self.boxes:
                box = self.random.choice(self.boxes)
                point = Vec2(box.x + box.width * self.random.uniform(0.2, 0.8), box.top)
            else:
                point = Vec2(self.random.uniform(self.left, self.width), self.floor_y)
        anchor = self.chimera_planner.anchor_near(point, walk_only=True)
        if facing is None:
            facing = self.random.choice((-1, 1))
        chimera = Chimera(self, anchor, facing)
        if legendary:
            apply_legendary(chimera)
        self.chimeras.append(chimera)
        return chimera


    def add_lich(self, point: Vec2 | None = None, *, legendary: bool = False) -> Lich:
        """Rises at `point` (snapped to the nearest window top or the floor he fits on);
        by default on a random window top."""
        if point is None:
            if self.boxes:
                box = self.random.choice(self.boxes)
                point = Vec2(box.x + box.width * self.random.uniform(0.2, 0.8), box.top)
            else:
                point = Vec2(self.random.uniform(self.left, self.width), self.floor_y)
        surfaces = [s for s in self.lich_terrain.surfaces if s.walkable]
        surface = min(surfaces, key=lambda s: s.closest_point(point).distance_to(point))
        low, high = Lich.span(surface)
        spot = Vec2(min(high, max(low, point.x)), surface.start.y)
        lich = Lich(self, surface, spot, heading=self.random.choice((-1, 1)))
        if legendary:
            apply_legendary(lich)
        self.liches.append(lich)
        return lich

    def add_mimic(self, point: Vec2 | None = None, *, legendary: bool = False) -> Mimic:
        """Sits down as a treasure chest at `point` (snapped to the nearest window top or
        floor spot an adventurer can walk up to); by default on a random window top."""
        if point is None:
            if self.boxes:
                box = self.random.choice(self.boxes)
                point = Vec2(box.x + box.width * self.random.uniform(0.2, 0.8), box.top)
            else:
                point = Vec2(self.random.uniform(self.left, self.width), self.floor_y)
        planner = self.mimic_planner
        anchor = planner.anchor_near(point, walk_only=True)
        assert anchor is not None
        spots = []
        for surface in planner.surfaces:
            if not surface.walkable:
                continue
            for inset in (0.0, chest.APPROACH + 2.0):
                if surface.low + inset > surface.high - inset:
                    continue
                spot = surface.point_at(
                    min(surface.high - inset, max(surface.low + inset, point.x))
                )
                if chest.roomy(self.planner, spot):
                    spots.append(spot)
                    break
        if spots:
            spot = min(spots, key=point.distance_to)
            anchor = planner.anchor_near(spot, walk_only=True) or anchor
        mimic = Mimic(self, anchor, heading=self.random.choice((-1, 1)))
        if legendary:
            apply_legendary(mimic)
        self.mimics.append(mimic)
        return mimic

    def add_hydra(
        self,
        point: Vec2 | None = None,
        facing: int | None = None,
        emerge: bool = True,
        *,
        legendary: bool = False,
    ) -> Hydra:
        """Breaks out of the ground at `point` (snapped to the nearest window top or floor
        spot it fits on), or with `emerge` False lies there already; by default on a
        random window top."""
        if point is None:
            if self.boxes:
                box = self.random.choice(self.boxes)
                point = Vec2(box.x + box.width * self.random.uniform(0.2, 0.8), box.top)
            else:
                point = Vec2(self.random.uniform(self.left, self.width), self.floor_y)
        if facing is None:
            facing = self.random.choice((-1, 1))
        anchor = self.hydra_planner.anchor_near(point, walk_only=True)
        assert anchor is not None
        hydra = Hydra(self, anchor, facing, emerge=emerge)
        if legendary:
            apply_legendary(hydra)
        self.hydras.append(hydra)
        return hydra

    @property
    def hydra_planner(self) -> Planner:
        """The hydra's terrain and planner, built the first time one is needed after a
        terrain change."""
        if self._hydra_planner is None:
            self._hydra_planner = serpent.build_planner(
                self.boxes, self.floor_y, self.left, self.width, self.ceiling
            )
        return self._hydra_planner

    @property
    def mimic_planner(self) -> Planner:
        """The mimic's terrain and planner, built the first time one is needed after a
        terrain change."""
        if self._mimic_planner is None:
            terrain = Terrain(
                self.boxes,
                self.floor_y,
                self.left,
                self.width,
                hang_reach=chest.HANG_REACH,
                mantle_depth=chest.MANTLE_DEPTH,
                ceiling=self.ceiling,
                hang_depth=chest.HANG_DEPTH,
                clearance=chest.CLEARANCE,
            )
            self._mimic_planner = Planner(terrain, chest.MOVES)
        return self._mimic_planner

    def spawn_devourer(self, point: Vec2) -> Devourer:
        """An intellect devourer leaping out of a skull at `point`."""
        hop = Vec2(self.random.uniform(-60.0, 60.0), -220.0)
        devourer = Devourer(self, point, hop, facing=1 if hop.x >= 0 else -1)
        self.devourers.append(devourer)
        self.gore.spray(point, Vec2(0.0, -150.0), 14, 200.0)
        return devourer

    # ----- simulation ----------------------------------------------------------
