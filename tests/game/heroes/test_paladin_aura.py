"""Live protection, defender priorities, and idle squad movement."""

import pytest

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.actors.hunting import Hunt
from dungeons_desktops.game.heroes.hero_paladin.aura import AURA_RADIUS, keep_with_squad
from dungeons_desktops.game.world.simulation import SimWorld

DT = 1 / 60


def scene():
    world = SimWorld([], 300, 1000)
    hero = world.add_stickman(Vec2(400, 300), "hero_paladin")
    ally = world.add_stickman(Vec2(450, 300), "fighter", wander=True)
    return world, hero, ally


def place(actor, x):
    anchor = actor.planner.anchor_near(Vec2(x, 300), walk_only=True)
    actor.follower.reset(anchor)
    actor.locomotion.teleport(actor.follower.command())


def hit(actor, amount=1):
    return actor.hurt(amount, actor.center(), Vec2(0, 0), "test", "defeated")


def test_protection_tracks_current_position_and_does_not_protect_the_caster():
    world, hero, ally = scene()
    assert ally.protector is hero and hero.protector is None
    drops = len(world.gore.drops)
    assert not hit(ally, 100)
    assert ally.damage == 0 and len(world.gore.drops) == drops
    hit(hero)
    assert hero.damage == 1
    place(ally, 550)
    assert ally.protector is None
    hit(ally)
    assert ally.damage == 1
    place(ally, 500)
    hit(ally)
    assert ally.damage == 1 and ally.protector is hero


@pytest.mark.parametrize("condition", ["dead", "thrall", "removed"])
def test_protection_ends_when_hero_is_unavailable(condition):
    world, hero, ally = scene()
    if condition == "dead":
        hit(hero, hero.max_hp)
    elif condition == "thrall":
        hero.enthrall()
    else:
        world.heroes.remove(hero)
        world.stickmen.remove(hero)
    assert ally.protector is None
    hit(ally)
    assert ally.damage == 1


def test_thralls_are_not_allies_and_death_effects_cannot_bypass_protection():
    _, hero, ally = scene()
    ally.ignite()
    ally.succumb("acid")
    ally.succumb("cold")
    assert ally.animated and ally.burn is None and ally.demise is None
    ally.enthrall()
    assert ally.protector is None
    hit(ally)
    assert ally.damage == 1 and hero.damage == 0


def test_hunt_switches_cached_target_to_paladin_and_can_ignore_unreachable_hero():
    world, hero, ally = scene()
    hunt = Hunt(retarget_every=60)
    hunt.target = ally
    hunt._retarget = 60
    assert hunt.update(DT, ally.contact(), world.stickmen) is hero
    hunt.unreachable(1, 0.5)
    assert hunt.update(DT, ally.contact(), world.stickmen) is ally


@pytest.mark.parametrize("kind", ["lich", "minotaur", "displacer", "worm"])
def test_custom_targeting_prefers_paladin_over_nearer_ally(kind):
    world, hero, ally = scene()
    enemy = getattr(world, "add_" + kind)(Vec2(470, 300))
    if kind == "displacer":
        enemy.harried = 10
    choose = enemy._choose_target if kind == "worm" else enemy._choose_foe
    assert choose() is hero
    hero.enthrall()
    assert choose() is ally


@pytest.mark.parametrize("kind", ["dragon", "drake", "hydra"])
def test_other_defenders_prefer_paladin_instead_of_cached_ally(kind):
    world, hero, ally = scene()
    if kind == "dragon":
        enemy = world.add_dragon(Vec2(470, 260), facing=-1)
        assert enemy._spot_prey() is hero
    elif kind == "drake":
        enemy = world.add_drake(Vec2(470, 300), facing=-1)
        enemy.quarry, enemy.retarget = ally, 60
        enemy._pick_quarry(DT)
        assert enemy.quarry is hero
    else:
        enemy = world.add_hydra(Vec2(470, 300), facing=-1, emerge=False)
        enemy.foe, enemy._foe_commit = ally, 60
        assert enemy._pick_foe(DT) is hero
        head = enemy.heads[0]
        head.target, head.commit = ally, 60
        enemy._choose_target(head, world.stickmen)
        assert head.target is hero


def test_mimic_cannot_remove_a_protected_ally_by_swallowing_it():
    world, hero, ally = scene()
    mimic = world.add_mimic(Vec2(460, 300))
    mimic._gulp_down(ally, 1)
    assert ally.animated and not ally.swallowed and ally.damage == 0
    assert ally.protector is hero


def test_displacer_frenzy_pounces_on_paladin_before_a_closer_ally():
    world, hero, _ = scene()
    enemy = world.add_displacer(Vec2(520, 300))
    enemy._start_frenzy()
    enemy._frenzy(DT)
    assert enemy.pending is not None and enemy.pending.quarry is hero


def test_all_idle_destinations_remain_in_aura_and_are_reachable():
    _, hero, ally = scene()
    for _ in range(20):
        ally._pick_wander_goal()
        assert ally.goal is not None and ally.goal_reachable
        assert ally.goal.distance_to(hero.center()) < AURA_RADIUS
        assert ally.follower.moving and ally._aura_leader is hero
        assert ally.follower.route.steps[-1].surface.id == hero.follower.current_anchor().surface.id


def test_existing_idle_route_is_redirected_when_ally_enters_aura():
    _, hero, ally = scene()
    ally.set_goal(Vec2(850, 300))
    ally._wander_destination = ally.goal
    keep_with_squad(ally, DT)
    assert ally.goal.distance_to(hero.center()) < AURA_RADIUS
    assert ally.follower.route.steps[-1].surface.id == hero.follower.current_anchor().surface.id


def test_squad_idle_route_uses_the_paladins_exact_window_surface():
    from dungeons_desktops.core.geometry import Rect
    from dungeons_desktops.navigation.planner import Anchor

    world = SimWorld([Rect(300, 180, 300, 120)], 500, 900, ceiling=0)
    hero = world.add_stickman(Vec2(450, 180), "hero_paladin")
    ally = world.add_stickman(Vec2(450, 500), "fighter", wander=True)
    top = next(
        surface
        for surface in hero.planner.surfaces
        if surface.walkable and surface.box == 0
    )
    hero.follower.reset(Anchor(top, top.point_at(450)))
    hero.locomotion.teleport(hero.follower.command())
    ally._aura_leader = hero
    ally._pick_wander_goal()
    assert ally.follower.route.steps[-1].surface.id == top.id
    assert ally._aura_surface_id == top.id


def test_squad_replans_idle_route_when_leader_moves_and_returns_after_separation():
    _, hero, ally = scene()
    ally._pick_wander_goal()
    place(hero, 700)
    assert ally.protector is None
    keep_with_squad(ally, 1)
    assert ally._aura_leader is hero
    assert ally.goal.distance_to(hero.center()) < AURA_RADIUS
    for _ in range(60 * 15):
        ally.update(DT)
    assert ally.protector is hero


def test_explicit_destination_and_combat_pursuit_remain_available():
    world, hero, ally = scene()
    ally._pick_wander_goal()
    destination = Vec2(800, 300)
    ally.set_goal(destination)
    keep_with_squad(ally, 1)
    assert ally.goal == destination
    target = world.add_goblin(Vec2(640, 300), "flag")
    assert ally._seek(1)
    assert ally.quarry is target and ally.goal.distance_to(hero.center()) > AURA_RADIUS


def test_surviving_squad_releases_dead_leader():
    _, hero, ally = scene()
    ally._pick_wander_goal()
    hit(hero, hero.max_hp)
    keep_with_squad(ally, 1)
    assert ally._aura_leader is None
