"""The permanent monster, hero and legendary unlock paths."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

BASE_DEFENDERS = ("goblins", "mimic", "dragon")
CLASS_KILLS_REQUIRED = 50
MONSTER_KILLS_REQUIRED = 100
WORM_KILLS_REQUIRED = 100
LEGENDARY_HERO_KILLS = 5
"""How many times a class-path monster's named hero must die before its legendary unlocks."""
GOBLIN_DEATHS_REQUIRED = 1000
"""Individual goblin bodies that must fall for the Goblin King."""
WORM_LEGENDARY_KILLS = 10_000
"""Adventurer kills required for the Devourer after the worm itself is unlocked."""

DEFENDER_NAMES = {
    "goblins": "Goblins",
    "mimic": "Mimic",
    "dragon": "Dragon",
    "worm": "Worm",
    "minotaur": "Minotaur",
    "lich": "Lich",
    "drakes": "Kobolds",
    "zombies": "Zombies",
    "drow": "Drow",
    "graveknights": "Graveknights",
    "displacer": "Displacer beast",
    "chimera": "Chimera",
    "mindflayer": "Mind flayer",
    "hydra": "Hydra",
    "aboleth": "Aboleth",
}

LEGENDARY_NAMES = {
    "goblins": "Goblin King",
    "mimic": "Chest of Holding",
    "dragon": "Ancient Wyrm",
    "worm": "Devourer",
    "minotaur": "Labyrinth King",
    "lich": "Archlich",
    "drakes": "Drake Tyrant",
    "zombies": "Plague Horde",
    "drow": "House Assassins",
    "graveknights": "Ashen Court",
    "displacer": "Warp Stalker",
    "chimera": "Primal Chimera",
    "mindflayer": "Elder Thing Herald",
    "hydra": "World Serpent",
}


@dataclass(frozen=True)
class Unlock:
    key: str
    name: str
    kind: Literal["monster", "hero", "legendary"]
    target: str
    threshold: int
    enemy_type: str | None = None
    monster_types: tuple[str, ...] = ()
    defender_deaths: tuple[str, ...] = ()
    """Count deaths of these defender bodies (e.g. individual goblins)."""
    requires_kind: Literal["hero", "legendary"] | None = None
    """Progress is how many unlocks of this kind (excluding self) are already claimed."""
    prerequisite: str | None = None
    pending: bool = False
    """True while a custom unlock path is still TBD."""


# Roster identifiers stay stable while names can change without invalidating saves.
_PATHS = (
    ("barbarian", "minotaur", ("minotaur",), "The Mighty"),
    ("wizard", "lich", ("lich",), "The Inquisitive"),
    ("rogue", "drakes", ("drake", "kobold"), "The Slayer"),
    ("paladin", "zombies", ("zombie",), "The Indomitable"),
    ("ranger", "drow", ("drow", "lizard"), "The Outlaw"),
    ("cleric", "graveknights", ("graveknight",), "The Burning Dawn"),
    ("alchemist", "displacer", ("displacer",), "The Biologist"),
    ("druid", "chimera", ("chimera",), "Natures Wrath"),
    ("sorcerer", "mindflayer", ("mindflayer",), "The Darkblood"),
    ("fighter", "hydra", ("hydra",), "The Soulforger"),
)

HERO_UNLOCK_COUNT = len(_PATHS)
"""Named heroes that must all be claimed for the Chest of Holding."""
# Class-path legendaries plus the other three starter legendaries (not the Ancient Wyrm).
OTHER_LEGENDARY_COUNT = HERO_UNLOCK_COUNT + 3
"""Other legendary claims required before the Ancient Wyrm unlocks."""

_STARTER_LEGENDARIES = (
    Unlock(
        "legendary:goblins",
        LEGENDARY_NAMES["goblins"],
        "legendary",
        "goblins",
        GOBLIN_DEATHS_REQUIRED,
        defender_deaths=("goblin",),
    ),
    Unlock(
        "legendary:mimic",
        LEGENDARY_NAMES["mimic"],
        "legendary",
        "mimic",
        HERO_UNLOCK_COUNT,
        requires_kind="hero",
    ),
    Unlock(
        "legendary:dragon",
        LEGENDARY_NAMES["dragon"],
        "legendary",
        "dragon",
        OTHER_LEGENDARY_COUNT,
        requires_kind="legendary",
    ),
    Unlock(
        "legendary:worm",
        LEGENDARY_NAMES["worm"],
        "legendary",
        "worm",
        WORM_LEGENDARY_KILLS,
        prerequisite="monster:worm",
    ),
)

UNLOCKS: tuple[Unlock, ...] = (
    Unlock("monster:worm", "Worm", "monster", "worm", WORM_KILLS_REQUIRED),
    *(
        unlock
        for enemy, defender, sources, hero_name in _PATHS
        for unlock in (
            Unlock(
                f"monster:{defender}",
                DEFENDER_NAMES[defender],
                "monster",
                defender,
                CLASS_KILLS_REQUIRED,
                enemy_type=enemy,
            ),
            Unlock(
                f"hero:hero_{enemy}",
                hero_name,
                "hero",
                f"hero_{enemy}",
                MONSTER_KILLS_REQUIRED,
                monster_types=sources,
                prerequisite=f"monster:{defender}",
            ),
            Unlock(
                f"legendary:{defender}",
                LEGENDARY_NAMES[defender],
                "legendary",
                defender,
                LEGENDARY_HERO_KILLS,
                enemy_type=f"hero_{enemy}",
                prerequisite=f"monster:{defender}",
            ),
        )
    ),
    *_STARTER_LEGENDARIES,
)
UNLOCK_BY_KEY = {unlock.key: unlock for unlock in UNLOCKS}
HERO_NAMES = {unlock.target: unlock.name for unlock in UNLOCKS if unlock.kind == "hero"}
LEGENDARY_BY_DEFENDER = {
    unlock.target: unlock for unlock in UNLOCKS if unlock.kind == "legendary"
}
