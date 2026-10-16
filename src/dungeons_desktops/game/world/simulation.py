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

import random
from collections.abc import Sequence
from dataclasses import dataclass

from dungeons_desktops.core.clock import FixedStepClock
from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.game.actors.base import Actor, surface_below
from dungeons_desktops.game.adventurers.actor import GOBLIN_DAMAGE, Stickman
from dungeons_desktops.game.adventurers.alchemy import Explosion, Vials
from dungeons_desktops.game.adventurers.combat import ADVENTURER_DAMAGE
from dungeons_desktops.game.adventurers.spells import Spells
from dungeons_desktops.game.defenders.chimera.actor import Chimera
from dungeons_desktops.game.defenders.displacer.actor import Displacer
from dungeons_desktops.game.defenders.dragon.actor import Dragon
from dungeons_desktops.game.defenders.drakes.drake import Drake
from dungeons_desktops.game.defenders.drakes.kobold import Kobold, Traps
from dungeons_desktops.game.defenders.drow.actor import Drow, DrowPack, Lizard
from dungeons_desktops.game.defenders.drow.darkness import Darkness
from dungeons_desktops.game.defenders.elementals.actor import Elemental
from dungeons_desktops.game.defenders.goblins.actor import SPEAR_PUSH, Goblin, GoblinPack
from dungeons_desktops.game.defenders.goblins.spears import Spears
from dungeons_desktops.game.defenders.hydra.actor import Hydra
from dungeons_desktops.game.defenders.lich.actor import Lich
from dungeons_desktops.game.defenders.lich.skeletons import (
    CRUMBLE_AFTER,
    SKELETON_CAP,
    Skeleton,
    SkeletonPack,
)
from dungeons_desktops.game.defenders.lich.spells import Necromancy
from dungeons_desktops.game.defenders.mimic.actor import Mimic
from dungeons_desktops.game.defenders.mindflayer.actor import MindFlayer
from dungeons_desktops.game.defenders.mindflayer.devourer import Devourer
from dungeons_desktops.game.defenders.minotaur.actor import Minotaur
from dungeons_desktops.game.defenders.ooze.actor import Ooze
from dungeons_desktops.game.defenders.worm.actor import BORDER_DEPTH, Worm
from dungeons_desktops.game.effects.debris import Debris
from dungeons_desktops.game.effects.gore import Gore
from dungeons_desktops.game.effects.projectiles import Projectiles
from dungeons_desktops.game.heroes.dio.actor import Dio
from dungeons_desktops.game.world.combat import CombatMixin
from dungeons_desktops.game.world.spawning import SpawningMixin
from dungeons_desktops.game.world.terrain import TerrainMixin

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


class SimWorld(SpawningMixin, CombatMixin, TerrainMixin):
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
