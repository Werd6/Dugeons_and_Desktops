"""Extracted world services mixed into :class:`SimWorld`."""

from __future__ import annotations

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.game.adventurers.actor import (
    THRALL_DAMAGE,
    Stickman,
)
from dungeons_desktops.game.adventurers.combat import ADVENTURER_DAMAGE
from dungeons_desktops.game.defenders.aboleth.actor import Aboleth
from dungeons_desktops.game.defenders.chimera.actor import Chimera
from dungeons_desktops.game.defenders.displacer.actor import Displacer
from dungeons_desktops.game.defenders.dragon.actor import BODY_LENGTH, Dragon
from dungeons_desktops.game.defenders.drakes.drake import Drake
from dungeons_desktops.game.defenders.drakes.kobold import Kobold
from dungeons_desktops.game.defenders.drow.actor import Drow, Lizard
from dungeons_desktops.game.defenders.goblins.actor import Goblin
from dungeons_desktops.game.defenders.hydra.actor import Hydra
from dungeons_desktops.game.defenders.lich.actor import Lich
from dungeons_desktops.game.defenders.mimic.actor import Mimic
from dungeons_desktops.game.defenders.mindflayer.actor import MindFlayer
from dungeons_desktops.game.defenders.mindflayer.devourer import Devourer
from dungeons_desktops.game.defenders.minotaur.actor import Minotaur
from dungeons_desktops.game.defenders.worm.actor import Worm, WormMode

MISSILE_BOXES: tuple[Rect, ...] = ()
"""What arrows, bombs, spears and bullets collide with besides the floor: nothing, they
fly straight through windows."""
BLAST_REACH = 6.0
"""How far past a bomb blast's radius it still catches a monster's nearest part."""
KILL_MARK_TIME = 1.4
"""How long a "+skull" floats over a fallen adventurer."""




class CombatMixin:
    def _spear_hits(self, point: Vec2) -> Stickman | None:
        return next((s for s in self.stickmen if s.prey and s.hits(point, 1.0)), None)

    def _vial_hits(self, point: Vec2, hostile: bool) -> object | None:
        if hostile:
            return self.prey_at(point)
        return self.monster_at(point)

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
            *self.graveknights,
            *self.zombies,
            *self.skeletons,
            *self.dragons,
            *worms,
            *self.mindflayers,
            *self.devourers,
            *self.displacers,
            *self.minotaurs,
            *self.aboleths,
            *self.chimeras,
            *[lich for lich in self.liches if not lich.phased],
            *[mimic for mimic in self.mimics if mimic.revealed],
            *[hydra for hydra in self.hydras if hydra.visible],
            *self.drakes,
            *self.kobolds,
            *self.lizards,
            *[drow for drow in self.drow if not getattr(drow, "cloaked", False)],
            *self.illusions(),
            *self.thralls,
        ]

    def illusions(self) -> list[Displacer]:
        """The displacer beasts' illusions that are out (to the adventurers, monsters)."""
        return [
            ghost
            for displacer in self.displacers
            for ghost in (displacer.ghost, getattr(displacer, "ghost2", None))
            if ghost is not None and ghost.feinting
        ]

    def locate(self, monster: object) -> Vec2 | None:
        """Where to aim at `monster`, or None if it's gone (or back underground)."""
        if isinstance(monster, Lizard):
            return monster.center() if monster in self.lizards else None
        if isinstance(monster, Drow):
            if monster not in self.drow or getattr(monster, "cloaked", False):
                return None
            return monster.center()
        if isinstance(monster, Goblin) and monster in (
            *self.goblins,
            *self.graveknights,
            *self.skeletons,
            *self.zombies,
        ):
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
        if isinstance(monster, Aboleth) and monster in self.aboleths:
            return monster.center()
        if isinstance(monster, Chimera) and monster in self.chimeras:
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
            (
                Displacer,
                Minotaur,
                Chimera,
                Aboleth,
                Lich,
                Mimic,
                Hydra,
                Drake,
                Kobold,
            ),
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
        for goblin_ in [
            *self.goblins,
            *self.graveknights,
            *self.zombies,
            *self.skeletons,
            *self.drow,
        ]:
            if getattr(goblin_, "cloaked", False):
                continue
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
        for aboleth in self.aboleths:
            if aboleth.hits(point, margin=1.0):
                return aboleth
        for chimera in self.chimeras:
            if chimera.hits(point, margin=1.0):
                return chimera
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
        amount: float,
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
            killed = monster.hurt(amount, point, push, "adventurer", "Cut down by its friends!")
            if killed:
                self.chromatic.shatter(monster, point, push)
                self._credit_kill(attacker, monster)
            return killed
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
        alive = self._live_list(monster)
        if alive is None:
            return False
        if isinstance(monster, Minotaur):
            monster.struck(ranged, attacker)
        monster.damage += amount
        self.spells.sparkle(point, "hit", 7, 120.0)
        if monster.hp > 0:
            return False
        alive.remove(monster)
        monster.die(point, push)
        # Aboleths slip into a deep portal — no corpse shatter.
        if not isinstance(monster, Aboleth):
            self.chromatic.shatter(monster, point, push)
        self.fallen.append(monster)
        self.monster_kills += 1
        if isinstance(monster, Goblin):
            # Individual bodies, including king recruits — not whole pack dismissals.
            self.progression.record_defender_death("goblin")
        self._credit_kill(attacker, monster)
        if (on_killed_by := getattr(monster, "on_killed_by", None)) is not None:
            on_killed_by(attacker)
        return True

    @staticmethod
    def _credit_kill(attacker: object, victim: object) -> None:
        """Notify the owner of a confirmed kill, including hits from their projectiles."""
        if (on_kill := getattr(attacker, "on_kill", None)) is not None:
            on_kill(victim)

    def _live_list(self, monster: object) -> list | None:
        for alive in (
            self.goblins,
            self.graveknights,
            self.zombies,
            self.skeletons,
            self.dragons,
            self.worms,
            self.mindflayers,
            self.devourers,
            self.displacers,
            self.minotaurs,
            self.aboleths,
            self.chimeras,
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
