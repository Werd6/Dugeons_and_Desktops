"""Legendary unlock progress, claim rules, summon flag and signature kit smoke."""

from __future__ import annotations

import pytest

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.desktop.session import DesktopSession
from dungeons_desktops.desktop.windows import FakeWindowSource
from dungeons_desktops.game.defenders.legendary import (
    LEGENDARY_DAMAGE_BONUS,
    LEGENDARY_HP,
    apply_legendary,
    legendary_damage,
    legendary_name,
)
from dungeons_desktops.game.defenders.lich.spells import CLOUD_DURATION, Cloudkill
from dungeons_desktops.game.defenders.minotaur.actor import THROW_MAX, Minotaur
from dungeons_desktops.game.progression import Progression
from dungeons_desktops.game.unlocks import (
    GOBLIN_DEATHS_REQUIRED,
    HERO_UNLOCK_COUNT,
    LEGENDARY_BY_DEFENDER,
    LEGENDARY_HERO_KILLS,
    LEGENDARY_NAMES,
    OTHER_LEGENDARY_COUNT,
    UNLOCKS,
    WORM_LEGENDARY_KILLS,
)
from dungeons_desktops.game.world.simulation import SimWorld

SCREEN = Rect(0, 0, 1400, 900)
USABLE = Rect(0, 30, 1400, 800)

PATHS = (
    ("barbarian", "minotaur", "hero_barbarian"),
    ("wizard", "lich", "hero_wizard"),
    ("rogue", "drakes", "hero_rogue"),
    ("paladin", "zombies", "hero_paladin"),
    ("ranger", "drow", "hero_ranger"),
    ("cleric", "graveknights", "hero_cleric"),
    ("alchemist", "displacer", "hero_alchemist"),
    ("druid", "chimera", "hero_druid"),
    ("sorcerer", "mindflayer", "hero_sorcerer"),
    ("fighter", "hydra", "hero_fighter"),
)


def session(**kwargs) -> DesktopSession:
    return DesktopSession(
        SCREEN,
        USABLE,
        FakeWindowSource(),
        seed=5,
        max_stickmen=0,
        enforce_unlocks=True,
        **kwargs,
    )


def test_catalog_lists_all_legendaries_without_pending_starters():
    legendaries = [unlock for unlock in UNLOCKS if unlock.kind == "legendary"]
    assert len(legendaries) == len(LEGENDARY_BY_DEFENDER) == 14
    assert not any(unlock.pending for unlock in legendaries)
    assert LEGENDARY_HERO_KILLS == 5
    assert GOBLIN_DEATHS_REQUIRED == 1000
    assert WORM_LEGENDARY_KILLS == 10_000
    assert HERO_UNLOCK_COUNT == OTHER_LEGENDARY_COUNT - 3 == 10
    assert legendary_name("minotaur") == LEGENDARY_NAMES["minotaur"] == "Labyrinth King"
    assert legendary_name("mindflayer") == LEGENDARY_NAMES["mindflayer"] == "Elder Thing Herald"
    assert legendary_name("worm") == LEGENDARY_NAMES["worm"] == "Devourer"


@pytest.mark.parametrize(("enemy", "defender", "hero"), PATHS)
def test_class_path_legendary_needs_monster_claim_and_hero_kills(enemy, defender, hero):
    key = f"legendary:{defender}"
    progress = Progression(claimed_unlocks={f"monster:{defender}"})
    for _ in range(LEGENDARY_HERO_KILLS - 1):
        progress.record_kill(hero, defender if defender != "drakes" else "drake")
    assert progress.unlock_progress(key) == LEGENDARY_HERO_KILLS - 1
    assert not progress.can_unlock(key)
    progress.record_kill(hero, defender if defender != "drakes" else "drake")
    assert progress.unlock_progress(key) == LEGENDARY_HERO_KILLS
    assert progress.can_unlock(key)
    assert progress.claim_unlock(key)
    assert progress.unlocked_legendaries == (defender,)
    assert not progress.claim_unlock(key)


def test_goblin_king_needs_five_hundred_individual_goblin_deaths():
    progress = Progression()
    key = "legendary:goblins"
    for _ in range(GOBLIN_DEATHS_REQUIRED - 1):
        progress.record_defender_death("goblin")
    assert progress.unlock_progress(key) == GOBLIN_DEATHS_REQUIRED - 1
    assert not progress.can_unlock(key)
    progress.record_defender_death("goblin")
    assert progress.can_unlock(key)
    assert progress.claim_unlock(key)
    assert "goblins" in progress.unlocked_legendaries


def test_killing_a_live_goblin_counts_toward_the_goblin_king():
    world = SimWorld([], 400, 800)
    goblin = world.add_goblin(Vec2(200, world.floor_y))
    hero = world.add_stickman(Vec2(220, world.floor_y), "fighter")
    assert world.hurt_monster(goblin, goblin.hp, goblin.center(), Vec2(10, -5), attacker=hero)
    assert world.progression.defenders_killed == {"goblin": 1}


def test_chest_of_holding_needs_every_hero_claimed():
    progress = Progression()
    key = "legendary:mimic"
    hero_keys = [f"hero:hero_{enemy}" for enemy, _, _ in PATHS]
    monster_keys = [f"monster:{defender}" for _, defender, _ in PATHS]
    progress.claimed_unlocks.update(monster_keys)
    for hero_key in hero_keys[:-1]:
        progress.claimed_unlocks.add(hero_key)
    assert progress.unlock_progress(key) == HERO_UNLOCK_COUNT - 1
    assert not progress.can_unlock(key)
    progress.claimed_unlocks.add(hero_keys[-1])
    assert progress.unlock_progress(key) == HERO_UNLOCK_COUNT
    assert progress.can_unlock(key)
    assert progress.claim_unlock(key)


def test_ancient_wyrm_needs_every_other_legendary_claimed():
    progress = Progression()
    key = "legendary:dragon"
    others = [
        unlock.key
        for unlock in UNLOCKS
        if unlock.kind == "legendary" and unlock.key != key
    ]
    assert len(others) == OTHER_LEGENDARY_COUNT
    # Class-path legendaries also need their monster prerequisite present in claims.
    for unlock in UNLOCKS:
        if unlock.kind == "legendary" and unlock.key != key and unlock.prerequisite:
            progress.claimed_unlocks.add(unlock.prerequisite)
    for other in others[:-1]:
        progress.claimed_unlocks.add(other)
    assert progress.unlock_progress(key) == OTHER_LEGENDARY_COUNT - 1
    assert not progress.can_unlock(key)
    progress.claimed_unlocks.add(others[-1])
    assert progress.can_unlock(key)
    assert progress.claim_unlock(key)


def test_devourer_needs_ten_thousand_kills_and_the_worm_monster():
    progress = Progression(enemies_killed={"fighter": WORM_LEGENDARY_KILLS})
    key = "legendary:worm"
    assert progress.unlock_progress(key) == WORM_LEGENDARY_KILLS
    assert not progress.can_unlock(key)
    assert progress.claim_unlock("monster:worm")
    assert progress.can_unlock(key)
    assert progress.claim_unlock(key)


def test_apply_legendary_raises_hp_and_damage_helper_adds_bonus():
    world = SimWorld([], 300, 800)
    bull = world.add_minotaur(Vec2(150, world.floor_y))
    base = type(bull).max_hp
    apply_legendary(bull)
    assert bull.legendary is True
    assert bull.max_hp == max(1, int(round(base * LEGENDARY_HP)))
    assert bull.hp == bull.max_hp
    assert legendary_damage(4, True) == 4 + LEGENDARY_DAMAGE_BONUS
    assert legendary_damage(4, False) == 4


def test_session_summon_passes_legendary_flag_after_claim():
    progress = Progression(
        claimed_unlocks={"monster:minotaur", "legendary:minotaur"},
    )
    world = session(progression=progress, defenders=("minotaur",))
    assert world.is_legendary("minotaur")
    assert world.minotaurs and world.minotaurs[0].legendary
    assert world.minotaurs[0].max_hp > Minotaur.max_hp


def test_session_without_legendary_claim_summons_base_form():
    progress = Progression(claimed_unlocks={"monster:minotaur"})
    world = session(progression=progress, defenders=("minotaur",))
    assert not world.is_legendary("minotaur")
    assert world.minotaurs and not getattr(world.minotaurs[0], "legendary", False)


def test_minotaur_legendary_throw_is_global_and_rage_clear_heals():
    world = SimWorld([], 400, 800)
    bull = world.add_minotaur(Vec2(200, world.floor_y), legendary=True)
    far = world.add_stickman(Vec2(200 + THROW_MAX + 120.0, world.floor_y))
    victim = world.add_stickman(Vec2(220, world.floor_y))
    assert bull._throw_target(victim) is far
    bull.damage = 5
    bull.rage_left = 0.01
    bull._timers(0.02)
    assert bull.damage == 2


def test_lich_cloudkill_and_legendary_spell_queue():
    world = SimWorld([], 400, 800)
    lich = world.add_lich(Vec2(200, world.floor_y), legendary=True)
    assert lich.legendary
    lich.next_spell()
    assert "cloudkill" in lich.spells
    foe = world.add_stickman(Vec2(260, world.floor_y))
    world.necromancy.cast("cloudkill", lich, lich.position, foe)
    assert world.necromancy.cloudkills
    cloud = world.necromancy.cloudkills[0]
    assert isinstance(cloud, Cloudkill)
    assert cloud.age < CLOUD_DURATION


def test_legendary_drake_pack_and_zombie_pack_sizes():
    progress = Progression(
        claimed_unlocks={
            "monster:drakes",
            "legendary:drakes",
            "monster:zombies",
            "legendary:zombies",
        },
    )
    drakes = session(progression=progress, defenders=("drakes",))
    assert len(drakes.drakes) == 5
    assert any(getattr(drake, "legendary_alpha", False) for drake in drakes.drakes)
    zombies = session(progression=progress, defenders=("zombies",))
    assert len(zombies.zombies) == 15
    assert all(getattr(zombie, "legendary", False) for zombie in zombies.zombies)


def test_goblin_crowned_leader_on_legendary_summon():
    from dungeons_desktops.game.defenders.goblins.actor import (
        GOBLIN_HP,
        KING_HP,
        KING_SIZE,
        KING_SPAWN_INTERVAL,
    )
    from dungeons_desktops.game.defenders.goblins import model as goblin_model

    progress = Progression()
    progress.claimed_unlocks.add("legendary:goblins")
    world = session(progression=progress, defenders=("goblins",))
    world._dismiss()
    world._summon("goblins")
    crowned = [goblin for goblin in world.goblins if getattr(goblin, "crowned", False)]
    assert len(crowned) == 1
    king = crowned[0]
    assert king.legendary and king.max_hp == KING_HP == GOBLIN_HP * 4
    assert king.layout.scale == pytest.approx(goblin_model.SCALE * KING_SIZE)
    before = len(world.goblins)
    king.king_spawn_wait = 0.0
    king.update(1 / 60)
    assert len(world.goblins) == before + 1
    recruit = world.goblins[-1]
    assert recruit.kind in ("sword", "spear")
    assert recruit.max_hp == max(1, int(round(king.hp / 4.0)))
    assert recruit.legendary and not recruit.crowned
    assert king.king_spawn_wait == pytest.approx(KING_SPAWN_INTERVAL)
