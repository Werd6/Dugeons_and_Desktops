"""Lifetime combat totals, independent of the desktop and its storage backend."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from dungeons_desktops.game.unlocks import BASE_DEFENDERS, UNLOCK_BY_KEY, UNLOCKS

SAVE_VERSION = 2

MONSTER_NAMES = {
    "aboleth": "Aboleth",
    "chimera": "Chimera",
    "drow": "Drow",
    "lizard": "Drow's lizard",
    "drake": "Drake",
    "kobold": "Kobold",
    "hydra": "Hydra",
    "mimic": "Mimic",
    "lich": "Lich",
    "minotaur": "Minotaur",
    "displacer": "Displacer beast",
    "mindflayer": "Mind flayer",
    "worm": "Worm",
    "zombie": "Zombie",
    "graveknight": "Graveknight",
    "goblin": "Goblin",
    "dragon": "Dragon",
}

# Effects keep their damage/grace labels; summons credit their summoner's type.
SOURCE_MONSTERS = {
    "chimera's fire": "chimera",
    "acid glob": "hydra",
    "kobold trap": "kobold",
    "mind flayer": "mindflayer",
    "skeleton": "lich",
    "thrall": "mindflayer",
    "devourer": "mindflayer",
}


def _count(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("Progress counts must be nonnegative integers")
    return value


def _counts(value: object) -> dict[str, int]:
    if not isinstance(value, dict) or any(not isinstance(key, str) or not key for key in value):
        raise ValueError("Progress breakdowns must map type names to counts")
    return {key: _count(count) for key, count in value.items()}


def _claims(value: object) -> set[str]:
    if not isinstance(value, list) or any(not isinstance(key, str) or not key for key in value):
        raise ValueError("Unlock claims must be a list of nonempty identifiers")
    claims = set(value)
    # Unknown identifiers remain inert, but survive round trips for future catalogs.
    # A malformed orphan hero claim must not bypass its prerequisite on a later load.
    return {
        key
        for key in claims
        if key not in UNLOCK_BY_KEY
        or UNLOCK_BY_KEY[key].prerequisite is None
        or UNLOCK_BY_KEY[key].prerequisite in claims
    }


@dataclass
class Progression:
    """One skull per enemy death, including the eventual death of a thrall.

    Monster totals are by type, across every appearance of that type. The source
    of the finishing hit gets credit, including lingering spells and traps, with
    summon kills rolled into the summoner's total.
    """

    skulls_earned: int = 0
    enemies_killed: dict[str, int] = field(default_factory=dict)
    monster_kills: dict[str, int] = field(default_factory=dict)
    defenders_killed: dict[str, int] = field(default_factory=dict)
    """How many times each defender body type has fallen (individual goblins, etc.)."""
    on_change: Callable[[], None] | None = field(default=None, repr=False, compare=False)
    claimed_unlocks: set[str] = field(default_factory=set, kw_only=True)

    @property
    def total_kills(self) -> int:
        return sum(self.enemies_killed.values())

    @property
    def unlocked_defenders(self) -> tuple[str, ...]:
        return (
            *BASE_DEFENDERS,
            *(
                unlock.target
                for unlock in UNLOCKS
                if unlock.kind == "monster" and unlock.key in self.claimed_unlocks
            ),
        )

    @property
    def unlocked_heroes(self) -> tuple[str, ...]:
        return tuple(
            unlock.target
            for unlock in UNLOCKS
            if unlock.kind == "hero"
            and unlock.key in self.claimed_unlocks
            and unlock.prerequisite in self.claimed_unlocks
        )

    @property
    def unlocked_legendaries(self) -> tuple[str, ...]:
        """Defender kinds whose legendary form has been claimed."""
        return tuple(
            unlock.target
            for unlock in UNLOCKS
            if unlock.kind == "legendary" and unlock.key in self.claimed_unlocks
        )

    def unlock_progress(self, key: str) -> int:
        """Lifetime credit for an achievement, without capping it at the target."""
        unlock = UNLOCK_BY_KEY[key]
        if unlock.pending:
            return 0
        if unlock.requires_kind is not None:
            return sum(
                1
                for other in UNLOCKS
                if other.kind == unlock.requires_kind
                and other.key != key
                and other.key in self.claimed_unlocks
            )
        if unlock.defender_deaths:
            return sum(self.defenders_killed.get(kind, 0) for kind in unlock.defender_deaths)
        if unlock.enemy_type is not None:
            return self.enemies_killed.get(unlock.enemy_type, 0)
        if unlock.monster_types:
            return sum(self.monster_kills.get(kind, 0) for kind in unlock.monster_types)
        return self.total_kills

    def can_unlock(self, key: str) -> bool:
        unlock = UNLOCK_BY_KEY.get(key)
        return (
            unlock is not None
            and not unlock.pending
            and key not in self.claimed_unlocks
            and (unlock.prerequisite is None or unlock.prerequisite in self.claimed_unlocks)
            and self.unlock_progress(key) >= unlock.threshold
        )

    def claim_unlock(self, key: str) -> bool:
        """Claim an earned unlock once, without spending skulls or resetting kills."""
        if not self.can_unlock(key):
            return False
        self.claimed_unlocks.add(key)
        if self.on_change is not None:
            self.on_change()
        return True

    def record_kill(self, enemy_type: str, source: str) -> None:
        monster_type = SOURCE_MONSTERS.get(source, source)
        self.skulls_earned += 1
        self.enemies_killed[enemy_type] = self.enemies_killed.get(enemy_type, 0) + 1
        self.monster_kills[monster_type] = self.monster_kills.get(monster_type, 0) + 1
        if self.on_change is not None:
            self.on_change()

    def record_defender_death(self, kind: str) -> None:
        """Count one fallen defender body toward death-based unlocks."""
        self.defenders_killed[kind] = self.defenders_killed.get(kind, 0) + 1
        if self.on_change is not None:
            self.on_change()

    def reset(self) -> None:
        """Wipe skulls, kill totals and claimed unlocks (for testing a fresh start)."""
        self.skulls_earned = 0
        self.enemies_killed.clear()
        self.monster_kills.clear()
        self.defenders_killed.clear()
        self.claimed_unlocks.clear()
        if self.on_change is not None:
            self.on_change()

    def to_dict(self) -> dict:
        return {
            "version": SAVE_VERSION,
            "skulls_earned": self.skulls_earned,
            "enemies_killed": dict(self.enemies_killed),
            "monster_kills": dict(self.monster_kills),
            "defenders_killed": dict(self.defenders_killed),
            "claimed_unlocks": sorted(self.claimed_unlocks),
        }

    @classmethod
    def from_dict(cls, data: object) -> Progression:
        if not isinstance(data, dict) or type(data.get("version")) is not int:
            raise ValueError("Invalid progress format")
        if data["version"] not in (1, SAVE_VERSION):
            raise ValueError("Unsupported progress version")
        # Merge older saves' separate summon totals without changing earned skulls
        # or enemy counts. Repeating this normalization never awards extra kills.
        monster_kills: dict[str, int] = {}
        for source, count in _counts(data.get("monster_kills", {})).items():
            monster = SOURCE_MONSTERS.get(source, source)
            monster_kills[monster] = monster_kills.get(monster, 0) + count
        return cls(
            skulls_earned=_count(data.get("skulls_earned", 0)),
            enemies_killed=_counts(data.get("enemies_killed", {})),
            monster_kills=monster_kills,
            defenders_killed=_counts(data.get("defenders_killed", {})),
            claimed_unlocks=(
                _claims(data.get("claimed_unlocks", [])) if data["version"] >= 2 else set()
            ),
        )
