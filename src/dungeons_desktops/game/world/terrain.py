"""Extracted world services mixed into :class:`SimWorld`."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from dungeons_desktops.core.geometry import Rect
from dungeons_desktops.game.adventurers import model as stick_figure
from dungeons_desktops.game.defenders.aboleth.actor import Aboleth
from dungeons_desktops.game.defenders.chimera import lion
from dungeons_desktops.game.defenders.displacer import actor as beast
from dungeons_desktops.game.defenders.displacer.actor import Displacer
from dungeons_desktops.game.defenders.drakes.kobold import Kobold
from dungeons_desktops.game.defenders.drow.actor import LIZARD_MOVES
from dungeons_desktops.game.defenders.goblins import model as goblin
from dungeons_desktops.game.defenders.hydra.actor import Hydra
from dungeons_desktops.game.defenders.lich import actor as undead
from dungeons_desktops.game.defenders.lich.actor import Lich
from dungeons_desktops.game.defenders.mimic.actor import Mimic
from dungeons_desktops.game.defenders.minotaur import actor as bull
from dungeons_desktops.game.defenders.minotaur.actor import Minotaur
from dungeons_desktops.game.defenders.zombies.model import MOVES as ZOMBIE_MOVES
from dungeons_desktops.game.heroes.hero_paladin import model as hero_paladin
from dungeons_desktops.game.heroes.natures_wrath import model as natures_wrath
from dungeons_desktops.game.heroes.the_inquisitive import model as iggy
from dungeons_desktops.game.heroes.the_mighty import model as mighty
from dungeons_desktops.navigation.planner import Planner
from dungeons_desktops.navigation.terrain import Terrain, TerrainChange

MISSILE_BOXES: tuple[Rect, ...] = ()
"""What arrows, bombs, spears and bullets collide with besides the floor: nothing, they
fly straight through windows."""
BLAST_REACH = 6.0
"""How far past a bomb blast's radius it still catches a monster's nearest part."""
KILL_MARK_TIME = 1.4
"""How long a "+skull" floats over a fallen adventurer."""




class TerrainMixin:
    def _rebuild(self) -> None:
        self.terrain = Terrain(
            self.boxes,
            self.floor_y,
            self.left,
            self.width,
            hang_reach=stick_figure.HANG_REACH,
            mantle_depth=stick_figure.MANTLE_DEPTH,
            ceiling=self.ceiling,
            hang_depth=stick_figure.HANG_DEPTH,
        )
        self.planner = Planner(self.terrain, stick_figure.MOVES)
        self.zombie_planner = Planner(self.terrain, ZOMBIE_MOVES)
        self.goblin_terrain = Terrain(
            self.boxes,
            self.floor_y,
            self.left,
            self.width,
            hang_reach=goblin.HANG_REACH,
            mantle_depth=goblin.MANTLE_DEPTH,
            ceiling=self.ceiling,
            hang_depth=goblin.HANG_DEPTH,
        )
        self.goblin_planner = Planner(self.goblin_terrain, goblin.MOVES)
        self.natures_wrath_planner = Planner(
            Terrain(
                self.boxes,
                self.floor_y,
                self.left,
                self.width,
                hang_reach=natures_wrath.HANG_REACH,
                mantle_depth=natures_wrath.MANTLE_DEPTH,
                ceiling=self.ceiling,
                hang_depth=natures_wrath.HANG_DEPTH,
            ),
            natures_wrath.MOVES,
        )
        self.mighty_planner = Planner(
            Terrain(
                self.boxes,
                self.floor_y,
                self.left,
                self.width,
                hang_reach=mighty.HANG_REACH,
                mantle_depth=mighty.MANTLE_DEPTH,
                ceiling=self.ceiling,
                hang_depth=mighty.HANG_DEPTH,
            ),
            mighty.MOVES,
        )
        self.mighty_rage_planner = Planner(
            Terrain(
                self.boxes, self.floor_y, self.left, self.width,
                hang_reach=mighty.HANG_REACH * 2,
                mantle_depth=mighty.MANTLE_DEPTH * 2,
                ceiling=self.ceiling,
                hang_depth=mighty.HANG_DEPTH * 2,
            ),
            replace(mighty.MOVES, edge_clearance=mighty.MOVES.edge_clearance * 2),
        )
        self.iggy_planner = Planner(
            Terrain(
                self.boxes, self.floor_y, self.left, self.width,
                hang_reach=iggy.HANG_REACH,
                mantle_depth=iggy.MANTLE_DEPTH,
                ceiling=self.ceiling,
                hang_depth=iggy.HANG_DEPTH,
            ),
            iggy.MOVES,
        )
        self.hero_paladin_planner = Planner(
            Terrain(
                self.boxes, self.floor_y, self.left, self.width,
                hang_reach=hero_paladin.HANG_REACH,
                mantle_depth=hero_paladin.MANTLE_DEPTH,
                ceiling=self.ceiling,
                hang_depth=hero_paladin.HANG_DEPTH,
            ),
            hero_paladin.MOVES,
        )
        self.displacer_terrain = Terrain(
            self.boxes,
            self.floor_y,
            self.left,
            self.width,
            hang_reach=beast.HANG_REACH,
            mantle_depth=beast.MANTLE_DEPTH,
            ceiling=self.ceiling,
            hang_depth=beast.HANG_DEPTH,
            clearance=beast.CLEARANCE,
        )
        self.displacer_planner = Planner(self.displacer_terrain, beast.MOVES)
        self.lizard_planner = Planner(self.displacer_terrain, LIZARD_MOVES)
        self.minotaur_terrain = Terrain(
            self.boxes,
            self.floor_y,
            self.left,
            self.width,
            hang_reach=bull.HANG_REACH,
            mantle_depth=bull.MANTLE_DEPTH,
            ceiling=self.ceiling,
            clearance=bull.CLEARANCE,
            headroom=bull.HEADROOM,
            wall_clearance=0.0,
        )
        self.minotaur_planner = Planner(self.minotaur_terrain, bull.MOVES)
        self.chimera_terrain = Terrain(
            self.boxes,
            self.floor_y,
            self.left,
            self.width,
            hang_reach=0.0,
            mantle_depth=lion.MANTLE_DEPTH,
            ceiling=self.ceiling,
            clearance=lion.CLEARANCE,
            # Keep full window sides in tight slots — the body may clip the neighbor
            # while climbing rather than belly-crawling a truncated wall.
            wall_clearance=0.0,
        )
        self.chimera_planner = Planner(self.chimera_terrain, lion.MOVES)
        self._mimic_planner: Planner | None = None
        self._hydra_planner: Planner | None = None
        self.lich_terrain = Terrain(
            self.boxes,
            self.floor_y,
            self.left,
            self.width,
            ceiling=self.ceiling,
            headroom=undead.HEADROOM,
        )

    def apply_terrain(self, change: TerrainChange, boxes: Sequence[Rect] | None = None) -> None:
        """Rebuild after the boxes changed (pass the new list, or mutate `boxes` first)."""
        for actor in self.actors:
            actor.move_goal_with_box(change)
        if boxes is not None:
            self.boxes = list(boxes)
        self._rebuild()
        for stickman in self.stickmen:
            stickman.ragdoll.obstacles = self.boxes
            stickman.ragdoll.ground_y = self.floor_y
            if stickman.animated:
                stickman.terrain_changed(change)
        for goblin_ in [
            *self.goblins,
            *self.zombies,
            *self.skeletons,
            *self.drow,
        ]:
            goblin_.terrain_changed(change)
        for worm in self.worms:
            worm.terrain_changed(change, self.boxes)
        for dragon in self.dragons:
            dragon.terrain_changed(change)
        for flayer in self.mindflayers:
            flayer.terrain_changed(change)
        for devourer in self.devourers:
            devourer.terrain_changed(change)
        for displacer in self.displacers:
            displacer.terrain_changed(change)
        for minotaur in self.minotaurs:
            minotaur.terrain_changed(change)
        for aboleth in self.aboleths:
            aboleth.terrain_changed(change)
        for chimera in self.chimeras:
            chimera.terrain_changed(change)
        for lich in self.liches:
            lich.terrain_changed(change)
        for mimic in self.mimics:
            mimic.terrain_changed(change)
        for hydra in self.hydras:
            hydra.terrain_changed(change)
        for drake in self.drakes:
            drake.terrain_changed(change)
        for kobold in self.kobolds:
            kobold.terrain_changed(change)
        self.traps.terrain_changed(change)
        for lizard in self.lizards:
            lizard.terrain_changed(change)
        self.necromancy.terrain_changed(change)
        for body in self.fallen:
            if isinstance(
                body, (Displacer, Minotaur, Aboleth, Lich, Mimic, Hydra, Kobold)
            ):
                body.terrain_changed(change)
        self.debris.terrain_changed(change)
