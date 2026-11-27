"""Earned thresholds make unlocks claimable without granting them automatically."""

import pytest

from dungeons_desktops.game.progression import SAVE_VERSION, Progression
from dungeons_desktops.game.unlocks import BASE_DEFENDERS, HERO_NAMES, UNLOCK_BY_KEY, UNLOCKS

PATHS = (
    ("barbarian", "minotaur", "minotaur", "The Mighty"),
    ("wizard", "lich", "lich", "The Inquisitive"),
    ("rogue", "drakes", "kobold", "The Slayer"),
    ("paladin", "zombies", "zombie", "The Indomitable"),
    ("ranger", "drow", "drow", "The Outlaw"),
    ("cleric", "graveknights", "graveknight", "The Burning Dawn"),
    ("alchemist", "displacer", "displacer", "The Biologist"),
    ("druid", "chimera", "chimera", "Natures Wrath"),
    ("sorcerer", "mindflayer", "mindflayer", "The Darkblood"),
    ("fighter", "hydra", "hydra", "The Soulforger"),
)


def test_new_game_has_only_three_base_monsters_and_no_heroes():
    progress = Progression()
    assert progress.unlocked_defenders == BASE_DEFENDERS == ("dragon", "goblins", "mimic")
    assert not progress.unlocked_heroes and not progress.claimed_unlocks
    assert len(UNLOCK_BY_KEY) == len(UNLOCKS) == 35
    assert not any(progress.can_unlock(unlock.key) for unlock in UNLOCKS)


@pytest.mark.parametrize(("enemy", "defender", "source", "hero_name"), PATHS)
def test_each_class_unlocks_its_monster_at_fifty_then_its_hero_at_one_hundred(
    enemy, defender, source, hero_name,
):
    progress = Progression()
    monster_key = f"monster:{defender}"
    hero_key = f"hero:hero_{enemy}"
    hero_variant = f"hero_{enemy}"
    assert HERO_NAMES[hero_variant] == hero_name

    for _ in range(49):
        progress.record_kill(enemy, "goblin")
    assert progress.unlock_progress(monster_key) == 49
    assert not progress.claim_unlock(monster_key)
    progress.record_kill(enemy, "goblin")
    assert progress.can_unlock(monster_key)
    assert defender not in progress.unlocked_defenders
    assert progress.claim_unlock(monster_key)
    assert defender in progress.unlocked_defenders
    assert not progress.claim_unlock(monster_key)

    for _ in range(99):
        progress.record_kill(enemy, source)
    assert progress.unlock_progress(hero_key) == 99
    assert not progress.claim_unlock(hero_key)
    progress.record_kill(enemy, source)
    assert progress.can_unlock(hero_key)
    assert hero_variant not in progress.unlocked_heroes
    assert progress.claim_unlock(hero_key)
    assert progress.unlocked_heroes == (hero_variant,)
    assert not progress.claim_unlock(hero_key)
    assert progress.skulls_earned == progress.total_kills == 150


def test_hero_needs_its_monster_claim_even_if_lifetime_kills_already_qualify():
    progress = Progression(enemies_killed={"barbarian": 50}, monster_kills={"minotaur": 100})
    assert progress.unlock_progress("hero:hero_barbarian") == 100
    assert not progress.can_unlock("hero:hero_barbarian")
    assert not progress.claim_unlock("hero:hero_barbarian")
    assert progress.claim_unlock("monster:minotaur")
    assert progress.claim_unlock("hero:hero_barbarian")


def test_hero_and_other_class_deaths_do_not_advance_an_ordinary_class_requirement():
    progress = Progression(enemies_killed={"hero_barbarian": 100, "fighter": 100})
    assert progress.unlock_progress("monster:minotaur") == 0
    assert not progress.can_unlock("monster:minotaur")
    assert progress.can_unlock("monster:hydra")


def test_worm_uses_total_enemy_kills_and_needs_an_explicit_claim():
    progress = Progression(skulls_earned=1000, enemies_killed={"wizard": 40, "fighter": 59})
    assert progress.unlock_progress("monster:worm") == 99
    assert not progress.claim_unlock("monster:worm")
    progress.record_kill("hero_barbarian", "dragon")
    assert progress.can_unlock("monster:worm")
    assert "worm" not in progress.unlocked_defenders
    assert progress.claim_unlock("monster:worm")
    assert "worm" in progress.unlocked_defenders
    assert progress.skulls_earned == 1001


@pytest.mark.parametrize(("hero", "first", "second", "prerequisite"), [
    ("hero_rogue", "drake", "kobold", "monster:drakes"),
    ("hero_ranger", "drow", "lizard", "monster:drow"),
])
def test_rider_and_mount_kills_combine_for_their_hero(hero, first, second, prerequisite):
    progress = Progression(
        monster_kills={first: 60, second: 39}, claimed_unlocks={prerequisite},
    )
    key = f"hero:{hero}"
    assert progress.unlock_progress(key) == 99
    assert not progress.can_unlock(key)
    progress.record_kill("wizard", second)
    assert progress.can_unlock(key)


@pytest.mark.parametrize(("hero", "prerequisite", "source"), [
    ("hero_wizard", "monster:lich", "skeleton"),
    ("hero_sorcerer", "monster:mindflayer", "thrall"),
    ("hero_sorcerer", "monster:mindflayer", "devourer"),
])
def test_summon_kills_help_unlock_the_summoners_hero(hero, prerequisite, source):
    progress = Progression(claimed_unlocks={prerequisite})
    for _ in range(100):
        progress.record_kill("fighter", source)
    assert progress.unlock_progress(f"hero:{hero}") == 100
    assert progress.can_unlock(f"hero:{hero}")


def test_claim_saves_once_without_spending_skulls_or_erasing_kills():
    saves = []
    progress = Progression(50, {"barbarian": 50}, {"goblin": 50})
    progress.on_change = lambda: saves.append(progress.to_dict())
    assert progress.claim_unlock("monster:minotaur")
    assert not progress.claim_unlock("monster:minotaur")
    assert not progress.claim_unlock("hero:hero_barbarian")
    assert not progress.claim_unlock("monster:unknown")
    assert len(saves) == 1
    assert saves[0]["claimed_unlocks"] == ["monster:minotaur"]
    assert progress.skulls_earned == 50
    assert progress.enemies_killed == {"barbarian": 50}
    assert progress.monster_kills == {"goblin": 50}


def test_unknown_claims_survive_but_do_not_grant_roster_entries():
    data = Progression().to_dict()
    data["claimed_unlocks"] = ["monster:future", "hero:future", "hero:hero_barbarian"]
    restored = Progression.from_dict(data)
    assert restored.claimed_unlocks == {"monster:future", "hero:future"}
    assert restored.unlocked_defenders == BASE_DEFENDERS
    assert not restored.unlocked_heroes
    assert Progression.from_dict(restored.to_dict()).claimed_unlocks == restored.claimed_unlocks


@pytest.mark.parametrize("claims", [None, {}, "monster:minotaur", [1], [""], [True]])
def test_invalid_claim_data_is_rejected(claims):
    with pytest.raises(ValueError):
        Progression.from_dict({"version": SAVE_VERSION, "claimed_unlocks": claims})
