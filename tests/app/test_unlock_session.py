"""Progression sessions enforce claims across roster selection and hero spawning."""

import pytest
from PySide6.QtCore import QSettings

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.desktop.menu import load_defenders, save_defenders
from dungeons_desktops.desktop.session import DEFENDERS, DesktopSession
from dungeons_desktops.desktop.windows import FakeWindowSource
from dungeons_desktops.game.adventurers.actor import Stickman
from dungeons_desktops.game.adventurers.model import CLASSES
from dungeons_desktops.game.progression import Progression
from dungeons_desktops.game.unlocks import BASE_DEFENDERS

SCREEN = Rect(0, 0, 1400, 900)
USABLE = Rect(0, 30, 1400, 800)
ZERO = Vec2(0, 0)


def session(**kwargs):
    return DesktopSession(
        SCREEN, USABLE, FakeWindowSource(), seed=5, max_stickmen=0,
        enforce_unlocks=True, **kwargs,
    )


def defeat(world, variant, source, count):
    for _ in range(count):
        victim = world.add_stickman(Vec2(250, USABLE.bottom), variant)
        assert victim.hurt(victim.max_hp, victim.center(), ZERO, source, "Defeated")


def test_progression_session_starts_with_exactly_the_base_rotation():
    world = session()
    assert world.defenders == world.available_defenders == BASE_DEFENDERS
    assert world.defender == "goblins" and world.goblins
    assert not world.can_spawn_hero("hero_barbarian")
    assert not world.can_spawn_hero("unknown")
    before = world.defenders
    with pytest.raises(ValueError, match="not unlocked"):
        world.set_defenders(("goblins", "minotaur"))
    with pytest.raises(ValueError, match="not unlocked"):
        world.spawn_at_edge(variant="hero_barbarian")
    assert world.defenders == before and not world.heroes


def test_actual_enemy_deaths_unlock_minotaur_then_mighty_only_after_claiming():
    world = session()
    progress = world.progression
    assert not world.claim_unlock("monster:minotaur")
    defeat(world, "barbarian", "goblin", 49)
    assert not world.claim_unlock("monster:minotaur")
    defeat(world, "barbarian", "goblin", 1)
    assert progress.can_unlock("monster:minotaur")
    assert "minotaur" not in world.available_defenders
    assert "minotaur" not in world.defenders
    assert world.claim_unlock("monster:minotaur")
    assert world.defenders == (*BASE_DEFENDERS, "minotaur")
    assert world.defender == "goblins"
    assert not world.claim_unlock("monster:minotaur")
    assert world.defenders.count("minotaur") == 1
    world.set_defenders(("minotaur",))
    assert world.defender == "minotaur" and world.minotaurs

    defeat(world, "fighter", "minotaur", 99)
    assert not world.claim_unlock("hero:hero_barbarian")
    defeat(world, "fighter", "minotaur", 1)
    assert progress.can_unlock("hero:hero_barbarian")
    assert not world.can_spawn_hero("hero_barbarian")
    with pytest.raises(ValueError, match="not unlocked"):
        world.spawn_at_edge(variant="hero_barbarian")
    assert world.claim_unlock("hero:hero_barbarian")
    assert not world.claim_unlock("hero:hero_barbarian")
    hero = world.spawn_at_edge(edge="left", variant="hero_barbarian")
    assert hero in world.heroes and hero.display_name == "The Mighty"
    assert progress.skulls_earned == progress.total_kills == world.kills == 150
    assert progress.enemies_killed == {"barbarian": 50, "fighter": 100}
    assert progress.monster_kills == {"goblin": 50, "minotaur": 100}


def test_claiming_a_monster_restarts_an_explicitly_empty_rotation():
    progress = Progression(50, {"barbarian": 50}, {"goblin": 50})
    world = session(progression=progress, defenders=())
    assert world.defender is None and not world.live_monsters
    assert world.claim_unlock("monster:minotaur")
    assert world.defenders == ("minotaur",)
    assert world.defender == "minotaur" and len(world.minotaurs) == 1
    assert progress.skulls_earned == 50


def test_old_enabled_settings_cannot_bypass_unlocks_and_empty_selection_is_preserved(tmp_path):
    settings = QSettings(str(tmp_path / "roster.ini"), QSettings.Format.IniFormat)
    progress = Progression()
    assert load_defenders(settings, progress) == BASE_DEFENDERS
    save_defenders(settings, DEFENDERS)
    assert load_defenders(settings, progress) == BASE_DEFENDERS
    save_defenders(settings, ("minotaur", "lich", "worm"))
    assert load_defenders(settings, progress) == BASE_DEFENDERS
    world = session(progression=progress, defenders=load_defenders(settings, progress))
    assert world.defenders == BASE_DEFENDERS
    assert not world.minotaurs and not world.liches and not world.worms
    save_defenders(settings, ())
    assert load_defenders(settings, progress) == ()
    progress.enemies_killed["barbarian"] = 50
    assert progress.claim_unlock("monster:minotaur")
    save_defenders(settings, ("minotaur", "lich"))
    assert load_defenders(settings, progress) == ("minotaur",)


def test_explicit_locked_roster_in_constructor_is_filtered():
    world = session(defenders=("dragon", "minotaur", "lich", "worm"))
    assert world.defenders == ("dragon",)
    assert len(world.dragons) == 1 and not world.minotaurs and not world.liches and not world.worms


def test_natural_hero_spawn_requires_claim_and_avoids_a_second_living_hero(monkeypatch):
    progress = Progression(
        150, {"barbarian": 50, "fighter": 100}, {"goblin": 50, "minotaur": 100},
    )
    world = session(progression=progress, defenders=())
    monkeypatch.setattr(world.random, "random", lambda: 0.0)
    assert world.spawn_at_edge(edge="left").variant in CLASSES
    assert not world.heroes
    assert world.claim_unlock("monster:minotaur")
    assert world.spawn_at_edge(edge="left").variant in CLASSES
    assert not world.heroes
    assert world.claim_unlock("hero:hero_barbarian")
    hero = world.spawn_at_edge(edge="left")
    assert hero.variant == "hero_barbarian"
    assert world.spawn_at_edge(edge="left").variant in CLASSES
    assert len(world.heroes) == 1
    assert Stickman.hurt(hero, hero.max_hp, hero.center(), ZERO, "dragon", "Defeated")
    replacement = world.spawn_at_edge(edge="left")
    assert replacement is not hero and replacement.variant == "hero_barbarian"
    assert sum(actor.animated for actor in world.heroes) == 1


def test_unlocked_heroes_still_spawn_only_on_the_rare_roll(monkeypatch):
    progress = Progression(claimed_unlocks={"monster:minotaur", "hero:hero_barbarian"})
    world = session(progression=progress, defenders=())
    monkeypatch.setattr(world.random, "random", lambda: 0.5)
    assert world.spawn_at_edge(edge="left").variant in CLASSES
    assert not world.heroes


def test_unrestricted_simulations_keep_the_full_roster_and_explicit_hero_spawning():
    world = DesktopSession(SCREEN, USABLE, FakeWindowSource(), seed=5, max_stickmen=0)
    assert world.defenders == DEFENDERS
    world.set_defenders(("minotaur", "lich", "dragon"))
    assert world.can_spawn_hero("hero_barbarian")
    assert world.spawn_at_edge(edge="left", variant="hero_barbarian").variant == "hero_barbarian"
    assert not world.progression.claimed_unlocks
