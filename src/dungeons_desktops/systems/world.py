"""The shared simulation: stickmen and the monsters hunting them, on a set of boxes.

Both the preview (draggable fake windows) and the desktop overlay (real window
rectangles) run on this. It owns the terrain and planners built from the boxes,
the projectiles and vials in flight, and every actor; `advance` steps them all
on a fixed clock. Changing the boxes goes through `apply_terrain` so actors
standing on a box that moved are carried and the rest re-anchor.

Monsters have HP (see `mortal`). The adventurers' blows, arrows and missiles land
through `hurt_monster`; a monster brought to 0 HP leaves its live list for `fallen`
until its body has faded.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass

from dungeons_desktops.core.clock import FixedStepClock
from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.creatures import goblin, stick_figure
from dungeons_desktops.navigation.planner import Anchor, Planner
from dungeons_desktops.navigation.terrain import Terrain, TerrainChange
from dungeons_desktops.systems import chimera_lion as lion
from dungeons_desktops.systems import displacer as beast
from dungeons_desktops.systems import hydra as serpent
from dungeons_desktops.systems import lich as undead
from dungeons_desktops.systems import mimic as chest
from dungeons_desktops.systems import minotaur as bull
from dungeons_desktops.systems.actors import (
    GOBLIN_DAMAGE,
    THRALL_DAMAGE,
    Actor,
    Stickman,
    surface_below,
)
from dungeons_desktops.systems.breath import VARIANTS
from dungeons_desktops.systems.chimera import Chimera
from dungeons_desktops.systems.darkness import Darkness
from dungeons_desktops.systems.debris import Debris
from dungeons_desktops.systems.devourer import Devourer
from dungeons_desktops.systems.displacer import Displacer
from dungeons_desktops.systems.dragon import BODY_LENGTH, Dragon
from dungeons_desktops.systems.drakes import COLOURS, Drake
from dungeons_desktops.systems.drow import LIZARD_MOVES, Drow, DrowPack, Lizard
from dungeons_desktops.systems.elementals import KINDS as ELEMENT_FORMS
from dungeons_desktops.systems.elementals import Elemental
from dungeons_desktops.systems.goblins import PACK, SPEAR_PUSH, Goblin, GoblinPack
from dungeons_desktops.systems.gore import Gore
from dungeons_desktops.systems.heroes import Dio
from dungeons_desktops.systems.hydra import Hydra
from dungeons_desktops.systems.kobolds import Kobold, Traps
from dungeons_desktops.systems.lich import Lich
from dungeons_desktops.systems.mimic import Mimic
from dungeons_desktops.systems.mindflayer import MindFlayer
from dungeons_desktops.systems.minotaur import Minotaur
from dungeons_desktops.systems.mortal import ADVENTURER_DAMAGE
from dungeons_desktops.systems.necromancy import Necromancy
from dungeons_desktops.systems.ooze import MOVES as OOZE_MOVES
from dungeons_desktops.systems.ooze import Ooze
from dungeons_desktops.systems.projectiles import Projectiles
from dungeons_desktops.systems.skeletons import CRUMBLE_AFTER, SKELETON_CAP, Skeleton, SkeletonPack
from dungeons_desktops.systems.spears import Spears
from dungeons_desktops.systems.spells import Spells
from dungeons_desktops.systems.vials import Explosion, Vials
from dungeons_desktops.systems.worm import BORDER_DEPTH, Worm, WormMode

MISSILE_BOXES: tuple[Rect, ...] = ()
"""What arrows, bombs, spears and bullets collide with besides the floor: nothing, they
fly straight through windows."""
BLAST_REACH = 6.0
"""How far past a bomb blast's radius it still catches a monster's nearest part."""
KILL_MARK_TIME = 1.4
"""How long a "+skull" floats over a fallen adventurer."""


@dataclass
class KillMark:
    """A "+skull" popping up where an adventurer died."""

    point: Vec2
    age: float = 0.0


class SimWorld:
    def __init__(
        self,
        boxes: Sequence[Rect],
        floor_y: float,
        width: float,
        left: float = 0.0,
        ceiling: float | None = None,
        seed: int | None = 7,
    ) -> None:
        """`left`..`width` is the horizontal extent; a `ceiling` makes its sides climbable."""
        self.boxes = list(boxes)
        self.floor_y = floor_y
        self.left = left
        self.width = width
        self.ceiling = ceiling
        self.clock = FixedStepClock()
        self.random = random.Random(seed)
        self.projectiles = Projectiles()
        self.vials = Vials()
        self.debris = Debris(self.random)
        self.gore = Gore(self.random)
        self.spears = Spears()
        self.spells = Spells(self.random)
        self.necromancy = Necromancy(self)
        self.kills = 0
        """Stickmen killed by any monster so far."""
        self.kill_marks: list[KillMark] = []
        self.stickmen: list[Stickman] = []
        self.heroes: list[Dio] = []
        """Named heroes also remain in `stickmen` for shared prey and combat handling."""
        self.goblins: list[Goblin] = []
        self.goblin_pack = GoblinPack(self)
        self.skeletons: list[Skeleton] = []
        self.skeleton_pack = SkeletonPack(self)
        self.worms: list[Worm] = []
        self.dragons: list[Dragon] = []
        self.mindflayers: list[MindFlayer] = []
        self.devourers: list[Devourer] = []
        self.displacers: list[Displacer] = []
        self.minotaurs: list[Minotaur] = []
        self.liches: list[Lich] = []
        self.mimics: list[Mimic] = []
        self.hydras: list[Hydra] = []
        self.drakes: list[Drake] = []
        self.kobolds: list[Kobold] = []
        self.traps = Traps(self)
        self.lizards: list[Lizard] = []
        self.drow: list[Drow] = []
        self.drow_pack = DrowPack(self)
        self.darkness = Darkness(self)
        self.chimeras: list[Chimera] = []
        self.elementals: list[Elemental] = []
        self.oozes: list[Ooze] = []
        self.fallen: list[
            Goblin
            | Chimera
            | Elemental
            | Drake
            | Kobold
            | Dragon
            | Worm
            | MindFlayer
            | Devourer
            | Displacer
            | Minotaur
            | Ooze
            | Lich
            | Mimic
            | Hydra
        ] = []
        """Dead monsters, until their bodies fade."""
        self.monster_kills = 0
        self._detonations: list[Vec2] = []
        """Blasts set off this step outside the vials (an alchemist going off when eaten)."""
        self._rebuild()

    @property
    def bottom_border(self) -> Rect:
        """The band of ground below the screen's bottom edge."""
        return Rect(self.left, self.floor_y, self.width - self.left, BORDER_DEPTH)

    @property
    def step(self) -> float:
        return self.clock.step

    def say(self, actor: Actor, message: str) -> None:
        pass

    def mark_kill(self, point: Vec2) -> None:
        self.kill_marks.append(KillMark(point))

    @property
    def actors(self) -> list[Actor]:
        return [*self.stickmen, *self.goblins, *self.skeletons, *self.drow, *self.mindflayers]

    @property
    def thralls(self) -> list[Stickman]:
        """Adventurers under a mind flayer's control: monsters, to the others."""
        return [s for s in self.stickmen if s.thrall and s.animated]

    @property
    def surfaces(self):
        return self.terrain.surfaces

    # ----- population ----------------------------------------------------------

    def add_stickman(
        self, point: Vec2 | None = None, variant: str = "unarmed", wander: bool = False
    ) -> Stickman:
        if point is None:
            point = Vec2(self.random.uniform(self.left, self.width), self.floor_y)
        anchor = self.planner.anchor_near(point, walk_only=True)
        return self._add_stickman(anchor, variant, wander)

    def _add_stickman(self, anchor: Anchor, variant: str, wander: bool) -> Stickman:
        if variant == "hero_fighter":
            stickman = Dio(self, anchor, wander)
            self.heroes.append(stickman)
        else:
            stickman = Stickman(self, anchor, variant, wander)
        self.stickmen.append(stickman)
        return stickman

    def add_goblin(self, point: Vec2 | None = None, kind: str | None = None) -> Goblin:
        """`kind` is "sword", "spear" or "flag"; by default the next one in `PACK`."""
        if point is None:
            if self.boxes:
                box = self.random.choice(self.boxes)
                point = Vec2(box.x + box.width * self.random.uniform(0.2, 0.8), box.top - 5.0)
            else:
                point = Vec2(self.random.uniform(self.left, self.width), self.floor_y - 5.0)
        if kind is None:
            kind = PACK[len(self.goblins) % len(PACK)]
        goblin_ = Goblin(self, surface_below(self.goblin_planner, point), kind)
        self.goblins.append(goblin_)
        return goblin_

    def add_worm(self, head: Vec2 | None = None, heading: float | None = None) -> Worm:
        """Defaults to burrowing just below the floor at a random spot."""
        if head is None:
            head = Vec2(self.random.uniform(self.left + 40.0, self.width - 40.0), self.floor_y + 25)
        if heading is None:
            heading = self.random.choice((0.0, math.pi))
        worm = Worm(self, head, heading)
        self.worms.append(worm)
        return worm

    def add_dragon(
        self, body: Vec2 | None = None, facing: int | None = None, variant: str | None = None
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
        self.dragons.append(dragon)
        return dragon

    def add_drake(
        self, point: Vec2 | None = None, variant: str | None = None, facing: int | None = None
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
        self.drakes.append(drake)
        return drake

    def add_kobold(
        self,
        point: Vec2,
        variant: str = "red",
        facing: int = 1,
        velocity: Vec2 | None = None,
        aim: Vec2 | None = None,
    ) -> Kobold:
        """A kobold on foot: standing at `point` (snapped to the walkable spot below it),
        or with a `velocity` leaping from there - off a dying drake."""
        if velocity is None:
            point = surface_below(self.goblin_planner, point).point
        kobold = Kobold(self, point, variant, facing, velocity or Vec2(0.0, 0.0))
        if aim is not None:
            kobold.aim = aim
        self.kobolds.append(kobold)
        return kobold

    def add_lizard(self, point: Vec2 | None = None, heading: int | None = None) -> Lizard:
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

    def add_mindflayer(self, point: Vec2 | None = None) -> MindFlayer:
        """Floats in at `point` (snapped to the nearest walkable spot); by default on a
        random window top."""
        if point is None:
            if self.boxes:
                box = self.random.choice(self.boxes)
                point = Vec2(box.x + box.width * self.random.uniform(0.2, 0.8), box.top)
            else:
                point = Vec2(self.random.uniform(self.left, self.width), self.floor_y)
        flayer = MindFlayer(self, self.planner.anchor_near(point, walk_only=True))
        self.mindflayers.append(flayer)
        return flayer

    def add_displacer(self, point: Vec2 | None = None) -> Displacer:
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
        self.displacers.append(displacer)
        return displacer

    def add_minotaur(self, point: Vec2 | None = None) -> Minotaur:
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
        self.minotaurs.append(minotaur)
        return minotaur

    def add_ooze(self, point: Vec2 | None = None, facing: int | None = None) -> Ooze:
        """Place an ooze on the nearest walkable surface."""
        if point is None:
            point = Vec2(self.random.uniform(self.left, self.width), self.floor_y)
        anchor = self.ooze_planner.anchor_near(point, walk_only=True)
        if facing is None:
            facing = self.random.choice((-1, 1))
        ooze = Ooze(self, anchor, facing)
        self.oozes.append(ooze)
        return ooze

    def add_chimera(self, point: Vec2 | None = None, facing: int | None = None) -> Chimera:
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
        self.chimeras.append(chimera)
        return chimera

    def add_elemental(
        self, point: Vec2 | None = None, facing: int | None = None, kind: str = ELEMENT_FORMS[0]
    ) -> Elemental:
        """The elemental, in its first form (or `kind`), hovering at `point` (snapped to
        the window top or floor under it unless it's air); by default on a random window
        top."""
        if point is None:
            if self.boxes:
                box = self.random.choice(self.boxes)
                point = Vec2(box.x + box.width * self.random.uniform(0.2, 0.8), box.top)
            else:
                point = Vec2(self.random.uniform(self.left, self.width), self.floor_y)
        planner = self.hydra_planner if kind == "earth" else self.planner
        anchor = surface_below(planner, Vec2(point.x, point.y - 2.0))
        if kind == "air":
            anchor = Anchor(anchor.surface, point)
        if facing is None:
            facing = self.random.choice((-1, 1))
        elemental = Elemental(self, anchor, kind, facing)
        self.elementals.append(elemental)
        return elemental

    def add_lich(self, point: Vec2 | None = None) -> Lich:
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
        self.liches.append(lich)
        return lich

    def add_mimic(self, point: Vec2 | None = None) -> Mimic:
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
        self.mimics.append(mimic)
        return mimic

    def add_hydra(
        self, point: Vec2 | None = None, facing: int | None = None, emerge: bool = True
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

    def advance(self, real_dt: float) -> None:
        for _ in range(self.clock.advance(real_dt)):
            self._step(self.clock.step)

    def _step(self, dt: float) -> None:
        self.projectiles.update(dt, MISSILE_BOXES, self.floor_y, self.width)
        for stickman in self.stickmen:
            stickman.update(dt)
        self.goblin_pack.update(dt)
        for goblin_ in self.goblins:
            goblin_.update(dt)
        self.skeleton_pack.update(dt)
        for skeleton in self.skeletons:
            skeleton.update(dt)
        self._crumble_skeletons(dt)
        for spear, stickman in self.spears.update(
            dt, MISSILE_BOXES, self.floor_y, self.width, self._spear_hits
        ):
            push = spear.velocity.normalized() * SPEAR_PUSH + Vec2(0.0, -80.0)
            stickman.hurt(GOBLIN_DAMAGE, spear.position, push, "goblin", "Speared by a goblin!")
        for worm in self.worms:
            worm.update(dt)
        for dragon in self.dragons:
            dragon.update(dt)
        for flayer in self.mindflayers:
            flayer.update(dt)
        for devourer in self.devourers:
            devourer.update(dt)
        for displacer in self.displacers:
            displacer.update(dt)
        for minotaur in self.minotaurs:
            minotaur.update(dt)
        for ooze in self.oozes:
            ooze.update(dt)
        for chimera in self.chimeras:
            chimera.update(dt)
        for elemental in self.elementals:
            elemental.update(dt)
        for lich in self.liches:
            lich.update(dt)
        for mimic in self.mimics:
            mimic.update(dt)
        for hydra in self.hydras:
            hydra.update(dt)
        for drake in self.drakes:
            drake.update(dt)
        for kobold in self.kobolds:
            kobold.update(dt)
        self.traps.update(dt)
        for lizard in self.lizards:
            lizard.update(dt)
        self.drow_pack.update(dt)
        for drow in self.drow:
            drow.update(dt)
        self.darkness.update(dt)
        self.necromancy.update(dt)
        for hit in self.spells.update(
            dt,
            self.locate,
            self.monster_at,
            MISSILE_BOXES,
            self.floor_y,
            self._grip,
            self.locate_prey,
            self.prey_at,
        ):
            push = hit.velocity.normalized() * 140.0 + Vec2(0.0, -60.0)
            if hit.hostile:
                assert isinstance(hit.monster, Stickman)
                self._thrall_hit(hit.monster, hit.point, push)
            else:
                self.hurt_monster(
                    hit.monster, ADVENTURER_DAMAGE, hit.point, push, ranged=True, attacker=hit.owner
                )
        for body in self.fallen:
            body.update_dead(dt)
        self.debris.update(dt)
        for mark in self.kill_marks:
            mark.age += dt
        self.kill_marks = [m for m in self.kill_marks if m.age < KILL_MARK_TIME]
        self.gore.update(dt, self.boxes, self.floor_y)
        bursts = self.vials.update(dt, MISSILE_BOXES, self.floor_y, self.width, self._vial_hits)
        for center in self._detonations:
            burst = Explosion(center, self.vials.blast_radius)
            self.vials.explosions.append(burst)
            bursts.append(burst)
        self._detonations.clear()
        for burst in bursts:
            if burst.hostile:
                self._blast_prey(burst.center, burst.radius)
            else:
                self._blast_monsters(burst.center, burst.radius, burst.owner)
        self._despawn()

    def raise_skeleton(self, body: Stickman) -> Skeleton | None:
        """`body`, killed by the lich, rising as a skeleton where it fell (if a lich
        still stands, the corpse is still there, and there's room in his host)."""
        if not self.liches or len(self.skeletons) >= SKELETON_CAP:
            return None
        if body not in self.stickmen or body.animated or body.burn is not None:
            return None
        anchor = surface_below(self.planner, body.center())
        skeleton = Skeleton(self, anchor, body.variant)
        skeleton.follower.facing = body.facing
        self.stickmen.remove(body)
        self.skeletons.append(skeleton)
        return skeleton

    def _crumble_skeletons(self, dt: float) -> None:
        """With no lich left, his skeletons fall apart a moment later."""
        if not self.skeletons or self.liches:
            return
        for skeleton in list(self.skeletons):
            if skeleton.crumble is None:
                skeleton.crumble = CRUMBLE_AFTER + self.random.uniform(0.0, 0.4)
            skeleton.crumble -= dt
            if skeleton.crumble <= 0.0:
                self.skeletons.remove(skeleton)
                skeleton.die(skeleton.center(), Vec2(0.0, 20.0))
                self.fallen.append(skeleton)

    def _despawn(self) -> None:
        if any(s.gone for s in self.stickmen):
            self.stickmen = [s for s in self.stickmen if not s.gone]
        self.heroes = [hero for hero in self.heroes if hero in self.stickmen]
        if any(m.gone for m in self.fallen):
            self.fallen = [m for m in self.fallen if not m.gone]

    def _spear_hits(self, point: Vec2) -> Stickman | None:
        return next((s for s in self.stickmen if s.prey and s.hits(point, 1.0)), None)

    def _vial_hits(self, point: Vec2, hostile: bool) -> bool:
        if hostile:
            return self.prey_at(point) is not None
        return self.monster_at(point) is not None

    # ----- a thrall's spells, arrows and bombs, aimed at the free adventurers ----

    def locate_prey(self, stickman: object) -> Vec2 | None:
        if isinstance(stickman, Stickman) and stickman.prey and stickman in self.stickmen:
            return stickman.center()
        return None

    def prey_at(self, point: Vec2) -> Stickman | None:
        return next((s for s in self.stickmen if s.prey and s.hits(point, 1.5)), None)

    def _thrall_hit(self, stickman: Stickman, point: Vec2, push: Vec2) -> None:
        if stickman.prey:
            stickman.hurt(
                THRALL_DAMAGE, point, push, "thrall", "Struck down by a mind-controlled friend!"
            )

    def _blast_prey(self, center: Vec2, radius: float) -> None:
        """A thrall's bomb: every free adventurer caught in it takes one hit."""
        for stickman in self.stickmen:
            if not stickman.prey:
                continue
            body = stickman.center()
            if body.distance_to(center) > radius + BLAST_REACH:
                continue
            away = (body - center).normalized()
            self._thrall_hit(stickman, body, away * 200.0 + Vec2(0.0, -120.0))

    def detonate(self, center: Vec2) -> None:
        """A bomb blast at `center`, landing at the end of this step."""
        self._detonations.append(center)

    def _blast_monsters(self, center: Vec2, radius: float, owner: object = None) -> None:
        """Every monster with a part in the blast takes one hit; adventurers are spared."""
        for monster in self.monsters():
            part = self.closest_part(monster, center)
            if part is None or part.distance_to(center) > radius + BLAST_REACH:
                continue
            away = (part - center).normalized()
            push = away * 200.0 + Vec2(0.0, -120.0)
            self.hurt_monster(monster, ADVENTURER_DAMAGE, part, push, ranged=True, attacker=owner)

    # ----- monsters, as the adventurers see them -----------------------------------

    def monsters(self) -> list[object]:
        """Every monster that can be seen (a worm only while it's out of the ground)."""
        worms = [w for w in self.worms if w.mode is WormMode.LEAP]
        return [
            *self.goblins,
            *self.skeletons,
            *self.dragons,
            *worms,
            *self.mindflayers,
            *self.devourers,
            *self.displacers,
            *self.minotaurs,
            *self.oozes,
            *self.chimeras,
            *[e for e in self.elementals if e.visible],
            *[lich for lich in self.liches if not lich.phased],
            *[mimic for mimic in self.mimics if mimic.revealed],
            *[hydra for hydra in self.hydras if hydra.visible],
            *self.drakes,
            *self.kobolds,
            *self.lizards,
            *self.drow,
            *self.illusions(),
            *self.thralls,
        ]

    def illusions(self) -> list[Displacer]:
        """The displacer beasts' illusions that are out (to the adventurers, monsters)."""
        return [d.ghost for d in self.displacers if d.ghost is not None and d.ghost.feinting]

    def locate(self, monster: object) -> Vec2 | None:
        """Where to aim at `monster`, or None if it's gone (or back underground)."""
        if isinstance(monster, Lizard):
            return monster.center() if monster in self.lizards else None
        if isinstance(monster, Drow):
            return monster.center() if monster in self.drow else None
        if isinstance(monster, Goblin) and (monster in self.goblins or monster in self.skeletons):
            return monster.center()
        if isinstance(monster, Dragon) and monster in self.dragons:
            return monster.body
        if isinstance(monster, Worm) and monster in self.worms and monster.mode is WormMode.LEAP:
            return monster.head
        if isinstance(monster, MindFlayer) and monster in self.mindflayers:
            return monster.center()
        if isinstance(monster, Devourer) and monster in self.devourers:
            return monster.center()
        if isinstance(monster, Displacer) and (
            monster in self.displacers or monster in self.illusions()
        ):
            return monster.center()
        if isinstance(monster, Minotaur) and monster in self.minotaurs:
            return monster.center()
        if isinstance(monster, Ooze) and monster in self.oozes:
            return monster.center()
        if isinstance(monster, Chimera) and monster in self.chimeras:
            return monster.center()
        if isinstance(monster, Elemental) and monster in self.elementals and monster.visible:
            return monster.center()
        if isinstance(monster, Lich) and monster in self.liches and not monster.phased:
            return monster.center()
        if isinstance(monster, Mimic) and monster in self.mimics and monster.revealed:
            return monster.center()
        if isinstance(monster, Hydra) and monster in self.hydras and monster.visible:
            return monster.center()
        if isinstance(monster, Drake) and monster in self.drakes:
            return monster.center()
        if isinstance(monster, Kobold) and monster in self.kobolds:
            return monster.center()
        if isinstance(monster, Stickman) and monster in self.thralls:
            return monster.center()
        return None

    def nearest_monster(
        self, point: Vec2, reach: float, through_ground: bool = False
    ) -> tuple[object, Vec2] | None:
        """The closest monster with any part of it within `reach` of `point`, and
        that closest part. `through_ground` also finds a worm while it's burrowing."""
        near = self.monsters_near(point, reach, through_ground)
        return near[0] if near else None

    def monsters_near(
        self, point: Vec2, reach: float, through_ground: bool = False
    ) -> list[tuple[object, Vec2]]:
        """Every monster with a part within `reach` of `point`, with that part, nearest
        first (a displacer beast's illusion ahead of everything else: it's what draws
        the eye)."""
        candidates = self.monsters()
        if through_ground:
            candidates += [w for w in self.worms if w not in candidates]
        found = []
        for monster in candidates:
            at = self.closest_part(monster, point, through_ground)
            if at is not None and at.distance_to(point) <= reach:
                found.append((monster, at))
        illusions = self.illusions()
        found.sort(key=lambda pair: (pair[0] not in illusions, pair[1].distance_to(point)))
        return found

    def closest_part(
        self, monster: object, point: Vec2, through_ground: bool = False
    ) -> Vec2 | None:
        """The part of a live `monster` nearest `point`; None if it can't be hit. Only
        the parts of a worm out of the ground count, unless `through_ground`."""
        if isinstance(monster, Worm) and through_ground and monster in self.worms:
            return min(monster.points[::2], key=point.distance_to)
        if self.locate(monster) is None:
            return None
        if isinstance(monster, Dragon):
            parts = [monster.body, monster.shoulder, monster.hip, monster.neck_base, monster.head]
        elif isinstance(
            monster,
            (Displacer, Minotaur, Ooze, Chimera, Elemental, Lich, Mimic, Hydra, Drake, Kobold),
        ):
            parts = monster.parts()
        elif isinstance(monster, Worm):
            parts = [p for p in monster.points[::3] if not monster.buried(p)] or [monster.head]
        else:
            parts = [monster.center()]
        return min(parts, key=point.distance_to)

    def _grip(self, monster: object, point: Vec2) -> Vec2 | None:
        return self.closest_part(monster, point, through_ground=True)

    def monster_at(self, point: Vec2) -> object | None:
        """The live monster whose body covers `point`, if any."""
        for goblin_ in [*self.goblins, *self.skeletons, *self.drow]:
            if goblin_.hits(point, margin=1.5):
                return goblin_
        for lizard in self.lizards:
            if lizard.hits(point, margin=1.0):
                return lizard
        for dragon in self.dragons:
            if dragon.body.distance_to(point) < BODY_LENGTH * 0.5:
                return dragon
            if dragon.head.distance_to(point) < 8.0:
                return dragon
        for worm in self.worms:
            if worm.mode is WormMode.LEAP and any(
                p.distance_to(point) < worm.radius(i) + 1.0 for i, p in enumerate(worm.points)
            ):
                return worm
        for flayer in self.mindflayers:
            if flayer.hits(point, margin=1.5):
                return flayer
        for devourer in self.devourers:
            if devourer.center().distance_to(point) < 6.0:
                return devourer
        for displacer in self.displacers:
            if displacer.hits(point, margin=1.0):
                return displacer
        for minotaur in self.minotaurs:
            if minotaur.hits(point, margin=1.0):
                return minotaur
        for ooze in self.oozes:
            if ooze.hits(point, margin=1.0):
                return ooze
        for chimera in self.chimeras:
            if chimera.hits(point, margin=1.0):
                return chimera
        for elemental in self.elementals:
            if elemental.hits(point, margin=1.0):
                return elemental
        for lich in self.liches:
            if lich.hits(point, margin=1.0):
                return lich
        for mimic in self.mimics:
            if mimic.revealed and mimic.hits(point, margin=1.0):
                return mimic
        for hydra in self.hydras:
            if hydra.hits(point, margin=1.0):
                return hydra
        for drake in self.drakes:
            if drake.hits(point, margin=1.0):
                return drake
        for kobold in self.kobolds:
            if kobold.hits(point, margin=1.0):
                return kobold
        for ghost in self.illusions():
            if ghost.hits(point, margin=1.0):
                return ghost
        for thrall in self.thralls:
            if thrall.hits(point, margin=1.5):
                return thrall
        return None

    def hurt_monster(
        self,
        monster: object,
        amount: int,
        point: Vec2,
        push: Vec2,
        ranged: bool = False,
        attacker: object = None,
    ) -> bool:
        """`amount` damage to a live monster, landing at `point`. At 0 HP it dies,
        shoved along `push`, and joins `fallen`. True if this killed it. A thrall takes it
        as an ordinary hit (and goes down as a stickman does). `ranged` is an arrow,
        missile, vine or bomb rather than a blow, from `attacker` if known."""
        if isinstance(monster, Stickman):
            if monster not in self.thralls:
                return False
            self.spells.sparkle(point, "hit", 7, 120.0)
            return monster.hurt(amount, point, push, "adventurer", "Cut down by its friends!")
        if isinstance(monster, Displacer) and monster.illusion:
            if monster.feinting:
                monster.ripple(point)
                self.spells.sparkle(point, "magic", 5, 90.0)
            return False
        if isinstance(monster, Lich) and monster.phased:
            return False
        if isinstance(monster, Mimic) and not monster.revealed:
            return False
        if isinstance(monster, Hydra) and not monster.visible:
            return False
        if isinstance(monster, Elemental):
            if not monster.vulnerable:
                return False
            amount = min(amount, monster.form_hp)
        alive = self._live_list(monster)
        if alive is None:
            return False
        if isinstance(monster, Minotaur):
            monster.struck(ranged, attacker)
        monster.damage += amount
        self.spells.sparkle(point, "hit", 7, 120.0)
        if monster.hp > 0:
            if isinstance(monster, Elemental):
                monster.wounded()
            return False
        alive.remove(monster)
        monster.die(point, push)
        self.fallen.append(monster)
        self.monster_kills += 1
        return True

    def _live_list(self, monster: object) -> list | None:
        for alive in (
            self.goblins,
            self.skeletons,
            self.dragons,
            self.worms,
            self.mindflayers,
            self.devourers,
            self.displacers,
            self.minotaurs,
            self.oozes,
            self.chimeras,
            self.elementals,
            self.liches,
            self.mimics,
            self.hydras,
            self.drakes,
            self.kobolds,
            self.lizards,
            self.drow,
        ):
            if monster in alive:
                return alive
        return None

    # ----- terrain -------------------------------------------------------------

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
        self.ooze_planner = Planner(self.displacer_terrain, OOZE_MOVES)
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
        for elemental in self.elementals:
            elemental.move_goal_with_box(change)
        if boxes is not None:
            self.boxes = list(boxes)
        self._rebuild()
        for stickman in self.stickmen:
            stickman.ragdoll.obstacles = self.boxes
            stickman.ragdoll.ground_y = self.floor_y
            if stickman.animated:
                stickman.terrain_changed(change)
        for goblin_ in [*self.goblins, *self.skeletons, *self.drow]:
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
        for ooze in self.oozes:
            ooze.terrain_changed(change)
        for chimera in self.chimeras:
            chimera.terrain_changed(change)
        for elemental in self.elementals:
            elemental.terrain_changed(change)
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
                body, (Displacer, Minotaur, Ooze, Lich, Mimic, Hydra, Kobold, Elemental)
            ):
                body.terrain_changed(change)
        self.debris.terrain_changed(change)
