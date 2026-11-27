"""The desktop pet: a monster defending your real windows from a stream of stickmen.

World coordinates are global logical points (y down), the frame Quartz window
bounds and Qt screen geometry share on macOS. The usable screen area (inside the
menu bar and Dock) bounds the world: its bottom is the floor, its left and right
edges are climbable walls, and every app window is a solid box. Windows are trimmed
clear of a lane along the sides and bottom, so even a fullscreen window leaves the
screen edges climbable and the floor walkable. A window whose top is up against the
top of the screen (maximized or fullscreen) has its top lowered by `TITLE_BAR`, so
creatures stand on its title/tab bar rather than hugging the menu bar.

Every `spawn_interval` seconds a wandering stickman appears at a random screen
edge: clinging to the left or right wall, or falling in from the top.

One defender holds the screen at a time: the chimera (prowls in on the frontmost
window), the drow lizard riders (two of them, on
wall-climbing lizards from the frontmost window), the kobold drake riders (three of
them, each a different chromatic colour, arriving on the frontmost window; once the last
drake is dead the riders on foot vanish too), the hydra (bursts out of the frontmost
window), the mimic (sits disguised as a treasure chest
on the frontmost window), the lich (rises on the frontmost window),
the minotaur (stomps in on the frontmost window), the displacer beast (prowls in on
the frontmost window), the mind flayer
(appears on the frontmost window, and its thralls and intellect devourers fight on its
side), the burrow worm, a goblin war band (arriving together on the frontmost window),
or the dragon (flies in from a side).
The adventurers wear it down (see `mortal` for the HP); once every monster of it is
dead, the next defender in `defenders` takes over while the bodies fade. A dead mind
flayer's thralls and devourers stay and fight on alongside the next defender (they
don't count toward its health bar).
"""

from __future__ import annotations

from collections.abc import Sequence

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.desktop.windows import WindowRecord, WindowSource, WindowTracker
from dungeons_desktops.game.actors.base import surface_below
from dungeons_desktops.game.actors.mortal import Mortal
from dungeons_desktops.game.adventurers import model as stick_figure
from dungeons_desktops.game.adventurers.actor import Stickman
from dungeons_desktops.game.defenders.drakes.drake import COLOURS
from dungeons_desktops.game.defenders.drakes.kobold import KOBOLD_HP
from dungeons_desktops.game.defenders.drow.actor import DROW_HP
from dungeons_desktops.game.defenders.goblins.actor import PACK, Goblin
from dungeons_desktops.game.defenders.graveknights.actor import (
    GRAVEKNIGHT_PACK,
    GRAVEKNIGHT_ROSTER,
)
from dungeons_desktops.game.defenders.zombies.actor import ZOMBIE_PACK
from dungeons_desktops.game.progression import Progression
from dungeons_desktops.game.unlocks import HERO_NAMES, UNLOCK_BY_KEY
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.navigation.planner import Anchor
from dungeons_desktops.navigation.terrain import SurfaceKind

LEGENDARY_DRAKE_PACK = len(COLOURS)
LEGENDARY_ZOMBIE_PACK = ZOMBIE_PACK + 5
SPAWN_INTERVAL = 6.0
FIRST_SPAWN = 1.0
MAX_STICKMEN = 8
HERO_SPAWN_CHANCE = 0.01
"""Chance for a claimed hero to replace a regular invader, with no hero already alive."""
EDGES = ("left", "right", "top")
GOBLIN_SPACING = 12.0
GOBLIN_SQUAD = len(PACK)
GOBLIN_ELBOW_ROOM = 10.0
"""A window top must fit the whole line-up plus this much to muster on."""
LIZARDS = 2
DRAKE_PACK = 3
"""How many of the drake `COLOURS` ride in, picked at random, no two alike."""
DEFENDERS = (
    "dragon",
    "goblins",
    "mimic",
    "chimera",
    "drow",
    "drakes",
    "hydra",
    "lich",
    "minotaur",
    "displacer",
    "mindflayer",
    "worm",
    "zombies",
    "graveknights",
)
SUPPORTED_DEFENDERS = DEFENDERS
"""Every menu option in the Command Board roster (starters first)."""
EDGE_TOUCH = 1.0
SIDE_LANE = 18.0
BOTTOM_LANE = stick_figure.MOVES.max_jump - 1.0
"""Room kept free of windows along the screen sides and above the floor. The bottom
lane stays low enough for a stickman on the floor to jump up and grab a window's side."""
TITLE_BAR = 40.0
"""How far below a window's real top edge its walkable top sits, for windows near the
top of the screen: creatures stand on the title/tab bar row."""
NEAR_TOP = 30.0
"""A window whose top is within this of the screen's usable top gets `TITLE_BAR`."""


def to_local(point: Vec2, origin: Vec2) -> Vec2:
    """World point to a window whose top-left corner sits at `origin`."""
    return point - origin


def to_world(point: Vec2, origin: Vec2) -> Vec2:
    return point + origin


def below_title_bar(rect: Rect, usable: Rect) -> Rect:
    """`rect` with its top lowered to the title/tab bar row, if it's up against the top
    of `usable`; otherwise unchanged."""
    if rect.top > usable.top + NEAR_TOP:
        return rect
    return Rect(rect.x, rect.y + TITLE_BAR, rect.width, max(0.0, rect.height - TITLE_BAR))


def window_area(usable: Rect) -> Rect:
    """Where windows count as terrain: the usable screen minus the side and bottom lanes."""
    return Rect(
        usable.left + SIDE_LANE,
        usable.top,
        usable.width - 2 * SIDE_LANE,
        usable.height - BOTTOM_LANE,
    )


class DesktopSession(SimWorld):
    def __init__(
        self,
        screen: Rect,
        usable: Rect,
        source: WindowSource,
        seed: int | None = None,
        spawn_interval: float = SPAWN_INTERVAL,
        max_stickmen: int = MAX_STICKMEN,
        defenders: Sequence[str] | None = None,
        legendary_prefs: Sequence[str] | None = None,
        goblin_squad: int = GOBLIN_SQUAD,
        progression: Progression | None = None,
        enforce_unlocks: bool = False,
    ) -> None:
        """`screen` is the whole display; `usable` the part outside the menu bar and Dock.
        `defenders` is the rotation (starters first: dragon, goblins, mimic, then
        the unlockable roster), starting with the first. The desktop app enables
        `enforce_unlocks`; isolated simulations may use the full roster for combat testing."""
        self.screen = screen
        self.usable = usable
        self.source = source
        self.tracker = WindowTracker(window_area(usable))
        self.front_to_back: list[int] = []
        self.source_error: str | None = None
        self.spawn_interval = spawn_interval
        self.max_stickmen = max_stickmen
        self.spawn_timer = min(FIRST_SPAWN, spawn_interval)
        super().__init__(
            [],
            usable.bottom,
            usable.right,
            left=usable.left,
            ceiling=usable.top,
            seed=seed,
            progression=progression,
        )
        self.poll()
        self.enforce_unlocks = enforce_unlocks
        if defenders is None:
            defenders = self.available_defenders if enforce_unlocks else DEFENDERS
        self.defenders = tuple(kind for kind in defenders if kind in self.available_defenders)
        # Which unlocked legendaries should actually summon; defaults to all claimed.
        claimed = set(self.progression.unlocked_legendaries)
        if legendary_prefs is None:
            self.legendary_prefs = set(claimed)
        else:
            self.legendary_prefs = {kind for kind in legendary_prefs if kind in claimed}
        self.goblin_squad = goblin_squad
        self.defender_index = 0
        self.defender_max_hp = 0
        """Total HP the current defender arrived with (the whole pack, for goblins)."""
        if self.defenders:
            self._summon(self.defender)

    @property
    def goblin(self) -> Goblin | None:
        return self.goblins[0] if self.goblins else None

    # ----- defenders -----------------------------------------------------------

    @property
    def available_defenders(self) -> tuple[str, ...]:
        return self.progression.unlocked_defenders if self.enforce_unlocks else SUPPORTED_DEFENDERS

    def can_spawn_hero(self, variant: str) -> bool:
        return variant in HERO_NAMES and (
            not self.enforce_unlocks or variant in self.progression.unlocked_heroes
        )

    def prefers_legendary(self, kind: str) -> bool:
        """Whether the play menu has this monster set to its legendary form."""
        return kind in self.legendary_prefs

    def is_legendary(self, kind: str | None) -> bool:
        """Whether this defender summons in its claimed legendary form."""
        return (
            kind is not None
            and kind in self.progression.unlocked_legendaries
            and kind in self.legendary_prefs
        )

    def set_legendary_pref(self, kind: str, prefer: bool) -> None:
        """Prefer (or clear) the legendary form; re-summons if that defender is live."""
        if prefer:
            if kind in self.progression.unlocked_legendaries or not self.enforce_unlocks:
                self.legendary_prefs.add(kind)
        else:
            self.legendary_prefs.discard(kind)
        if self.defender == kind and kind in self.defenders:
            self._dismiss()
            self._summon(kind)

    def claim_unlock(self, key: str) -> bool:
        if not self.progression.claim_unlock(key):
            return False
        unlock = UNLOCK_BY_KEY[key]
        if unlock.kind == "monster" and unlock.target not in self.defenders:
            self.set_defenders((*self.defenders, unlock.target))
        if unlock.kind == "legendary":
            self.legendary_prefs.add(unlock.target)
            if self.defender == unlock.target:
                self._dismiss()
                self._summon(unlock.target)
        return True

    @property
    def defender(self) -> str | None:
        return self.defenders[self.defender_index] if self.defenders else None

    @property
    def live_monsters(self) -> list[Mortal]:
        """The defender itself: a mind flayer's devourers and thralls don't count."""
        return [
            *self.zombies,
            *self.graveknights,
            *self.goblins,
            *self.worms,
            *self.dragons,
            *self.mindflayers,
            *self.displacers,
            *self.minotaurs,
            *self.aboleths,
            *self.chimeras,
            *self.liches,
            *self.mimics,
            *self.hydras,
            *self.drakes,
            *self.kobolds,
            *self.lizards,
            *self.drow,
        ]

    @property
    def defender_health(self) -> float | None:
        """The current defender's HP left as a fraction (summed over a goblin pack, and
        over the drakes and lizards and their riders still to dismount), or None with no
        defender."""
        if self.defender is None or not self.defender_max_hp:
            return None
        riders = self._riders()
        left = sum(m.hp for m in self.live_monsters) + riders
        return min(1.0, left / self.defender_max_hp)

    @property
    def hero_health(self) -> float | None:
        """The first living hero's health, retained for existing callers."""
        bars = self.hero_health_bars
        return bars[0][1] if bars else None

    @property
    def hero_health_bars(self) -> list[tuple[str, float]]:
        """Display name and health fraction for every living hero in play."""
        return [
            (
                getattr(hero, "display_name", hero.variant.replace("_", " ").title()),
                hero.hp / hero.max_hp,
            )
            for hero in self.heroes
            if hero in self.stickmen and hero.animated
        ]

    def rotate(self) -> None:
        """The current defender leaves (any of it still alive vanishes, devourers and
        thralls too) and the next one in the rotation takes over."""
        if not self.defenders:
            return
        self._dismiss()
        self._next_defender()

    def set_defenders(self, defenders: Sequence[str]) -> None:
        """Replace the enabled rotation and immediately leave a disabled defender.

        The supplied order becomes the rotation order. If the current defender remains
        enabled, it stays in place; otherwise the next enabled defender in the full roster
        takes over. An empty sequence dismisses the current defender.
        """
        selected = tuple(dict.fromkeys(defenders))
        unknown = set(selected) - set(SUPPORTED_DEFENDERS)
        if unknown:
            names = ", ".join(sorted(unknown))
            raise ValueError(f"Unknown defender type: {names}")
        locked = set(selected) - set(self.available_defenders)
        if locked:
            raise ValueError(f"Defender not unlocked: {', '.join(sorted(locked))}")
        if selected == self.defenders:
            return

        current = self.defender
        if current in selected:
            self.defenders = selected
            self.defender_index = selected.index(current)
            return

        self._dismiss()
        self.defenders = selected
        self.defender_max_hp = 0
        if not selected:
            self.defender_index = 0
            return

        roster = SUPPORTED_DEFENDERS
        start = roster.index(current) if current in roster else -1
        following = (*roster[start + 1 :], *roster[: start + 1])
        next_defender = next(kind for kind in following if kind in selected)
        self.defender_index = selected.index(next_defender)
        self._summon(next_defender)

    def _next_defender(self) -> None:
        self.defender_index = (self.defender_index + 1) % len(self.defenders)
        self._summon(self.defender)

    def _dismiss(self) -> None:
        """Poof the live monsters and free any thralls; the dead ones in `fallen` are
        left to fade."""
        for worm in self.worms:
            self.debris.burst(worm.head, Vec2(0.0, -1.0), 16, 220.0, spread=1.4, puffs=6)
        for goblin_ in self.goblins:
            self._poof(goblin_.center())
        for knight in self.graveknights:
            self._poof(knight.center())
        for dragon in self.dragons:
            self.debris.burst(dragon.body, Vec2(0.0, -1.0), 10, 160.0, spread=3.0, puffs=14)
        for hydra in self.hydras:
            if not hydra.underground:
                self._poof(hydra.center())
        for monster in [
            *self.zombies,
            *self.mindflayers,
            *self.devourers,
            *self.displacers,
            *self.minotaurs,
            *self.aboleths,
            *self.chimeras,
            *self.liches,
            *self.mimics,
            *self.drakes,
            *self.kobolds,
            *self.lizards,
            *self.drow,
        ]:
            self._poof(monster.center())
        for mimic in self.mimics:
            mimic.let_go()
        for thrall in self.thralls:
            thrall.release()
        self.worms.clear()
        self.zombies.clear()
        self.graveknights.clear()
        self.goblins.clear()
        self.dragons.clear()
        self.mindflayers.clear()
        self.devourers.clear()
        self.displacers.clear()
        self.minotaurs.clear()
        self.aboleths.clear()
        self.chimeras.clear()
        self.liches.clear()
        self.mimics.clear()
        self.hydras.clear()
        self.drakes.clear()
        self.kobolds.clear()
        self.traps.clear()
        self.lizards.clear()
        self.drow.clear()
        self.darkness.clear()

    def _summon(self, kind: str | None) -> None:
        legendary = self.is_legendary(kind)
        if kind == "chimera":
            chimera = self.add_chimera(self._goblin_muster(1)[0], legendary=legendary)
            self._poof(chimera.center())
        elif kind == "drow":
            muster = self._goblin_muster(GOBLIN_SQUAD)
            for i, point in enumerate((muster[0], muster[-1])[:LIZARDS]):
                lizard = self.add_lizard(point, heading=-1 if i == 0 else 1, legendary=legendary)
                self._poof(lizard.center())
        elif kind == "drakes":
            pack = LEGENDARY_DRAKE_PACK if legendary else DRAKE_PACK
            colours = list(COLOURS) if legendary else self.random.sample(COLOURS, DRAKE_PACK)
            for point, colour in zip(self._goblin_muster(pack), colours, strict=True):
                drake = self.add_drake(point, colour, legendary=legendary)
                self._poof(drake.center())
        elif kind == "hydra":
            self.add_hydra(self._goblin_muster(1)[0], legendary=legendary)
        elif kind == "worm":
            self.add_worm(legendary=legendary)
        elif kind == "dragon":
            self.add_dragon(legendary=legendary)
        elif kind == "mimic":
            mimic = self.add_mimic(self._goblin_muster(1)[0], legendary=legendary)
            self._poof(mimic.center())
        elif kind == "lich":
            lich = self.add_lich(self._goblin_muster(1)[0], legendary=legendary)
            self._poof(lich.center())
        elif kind == "minotaur":
            bull = self.add_minotaur(self._goblin_muster(1)[0], legendary=legendary)
            self._poof(bull.center())
        elif kind == "displacer":
            beast = self.add_displacer(self._goblin_muster(1)[0], legendary=legendary)
            self._poof(beast.center())
        elif kind == "mindflayer":
            flayer = self.add_mindflayer(self._goblin_muster(1)[0], legendary=legendary)
            self._poof(flayer.center())
        elif kind == "zombies":
            pack = LEGENDARY_ZOMBIE_PACK if legendary else ZOMBIE_PACK
            for point in self._goblin_muster(pack):
                zombie = self.add_zombie(point, legendary=legendary)
                self._poof(zombie.center())
        elif kind == "graveknights":
            points = self._goblin_muster(GRAVEKNIGHT_PACK)
            for point, role in zip(points, GRAVEKNIGHT_ROSTER, strict=True):
                knight = self.add_graveknight(point, role, legendary=legendary)
                self._poof(knight.center())
        elif kind == "goblins":
            for i, point in enumerate(self._goblin_muster(self.goblin_squad)):
                goblin_ = self.add_goblin(point, legendary=legendary, crowned=legendary and i == 0)
                self._poof(goblin_.center())
        self.defender_max_hp = sum(m.max_hp for m in self.live_monsters)
        self.defender_max_hp += self._riders()

    def _riders(self) -> int:
        """HP of the riders still in the saddle, who come down fighting."""
        return KOBOLD_HP * len(self.drakes) + DROW_HP * sum(z.mounted for z in self.lizards)

    def _poof(self, point: Vec2) -> None:
        self.debris.burst(point, Vec2(0.0, -1.0), 6, 120.0, spread=3.0, puffs=8, scale=0.6)

    # ----- windows -------------------------------------------------------------

    def poll(self) -> bool:
        """Read the windows again; True if the terrain changed."""
        try:
            records = self.source.snapshot()
        except Exception as error:  # keep the last good terrain if the OS call fails
            self.source_error = str(error)
            return False
        self.source_error = None
        records = [WindowRecord(r.id, below_title_bar(r.rect, self.usable)) for r in records]
        update = self.tracker.update(records)
        if update is None:
            return False
        self.front_to_back = update.front_to_back
        self.apply_terrain(update.change, update.boxes)
        return True

    def _goblin_muster(self, count: int) -> list[Vec2]:
        """Where the war band appears, side by side: the widest exposed top of the
        frontmost window that has room, else the middle of the floor."""
        planner = self.goblin_planner
        room = GOBLIN_SPACING * (count - 1) + GOBLIN_ELBOW_ROOM
        spot: tuple[float, float, float] | None = None
        for index in self.front_to_back:
            tops = [
                s
                for s in planner.surfaces
                if s.kind is SurfaceKind.TOP and s.box == index and s.length >= room
            ]
            if tops:
                top = max(tops, key=lambda s: s.length)
                spot = (top.low, top.high, top.start.y)
                break
        if spot is None:
            spot = (self.left, self.width, self.floor_y)
        low, high, y = spot
        middle = (low + high) / 2
        half = (high - low) / 2
        points = []
        for i in range(count):
            offset = (i - (count - 1) / 2) * GOBLIN_SPACING
            points.append(Vec2(middle + max(-half, min(half, offset)), y - 2.0))
        return points

    # ----- spawning ------------------------------------------------------------

    def _step(self, dt: float) -> None:
        super()._step(dt)
        if self.defender == "drakes" and self.kobolds and not self.drakes:
            for kobold in self.kobolds:
                self._poof(kobold.center())
            self.kobolds.clear()
        if self.defender_max_hp and not self.live_monsters:
            self._next_defender()
        self.spawn_timer -= dt
        if self.spawn_timer <= 0.0:
            self.spawn_timer += self.spawn_interval
            if len(self.stickmen) < self.max_stickmen:
                self.spawn_at_edge()

    def spawn_at_edge(self, edge: str | None = None, variant: str | None = None) -> Stickman:
        random = self.random
        edge = edge or random.choice(EDGES)
        if variant in HERO_NAMES and not self.can_spawn_hero(variant):
            raise ValueError(f"Hero not unlocked: {variant}")
        if variant is None:
            heroes = self.progression.unlocked_heroes if self.enforce_unlocks else ()
            hero_alive = any(hero.animated for hero in self.heroes)
            if heroes and not hero_alive and random.random() < HERO_SPAWN_CHANCE:
                variant = random.choice(heroes)
            else:
                variant = random.choice(list(stick_figure.CLASSES))
        if edge != "top":
            anchor = self._side_anchor(edge)
            if anchor is not None:
                return self._add_stickman(anchor, variant, wander=True)
        return self._fall_in(variant)

    def _side_anchor(self, edge: str) -> Anchor | None:
        """A random spot on the screen-edge wall, or the end of a surface touching that edge."""
        random = self.random
        x = self.left if edge == "left" else self.width
        walls = [
            s
            for s in self.planner.surfaces
            if s.wall and s.box is None and s.start.x == x and s.length > 1.0
        ]
        if walls:
            wall = random.choices(walls, weights=[s.length for s in walls])[0]
            return Anchor(wall, wall.point_at(random.uniform(wall.low, wall.high)))

        def end(s) -> float:
            return s.low if edge == "left" else s.high

        touching = [
            s for s in self.planner.surfaces if s.walkable and abs(end(s) - x) <= EDGE_TOUCH
        ]
        if touching:
            surface = random.choice(touching)
            return Anchor(surface, surface.point_at(end(surface)))
        return None

    def _fall_in(self, variant: str) -> Stickman:
        x = self.random.uniform(self.left + 20.0, self.width - 20.0)
        landing = surface_below(self.planner, Vec2(x, self.usable.top))
        stickman = self._add_stickman(landing, variant, wander=True)
        stickman.fall_in(Vec2(landing.point.x, self.screen.top))
        return stickman
