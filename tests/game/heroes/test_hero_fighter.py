"""The Soulforger model, shared Fighter AI, mark, and independent abilities."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.desktop.session import DesktopSession
from dungeons_desktops.desktop.windows import FakeWindowSource
from dungeons_desktops.game.adventurers import model as adventurer
from dungeons_desktops.game.adventurers.render import draw_stickman
from dungeons_desktops.game.defenders.mindflayer.actor import PULSE_WINDUP, Power
from dungeons_desktops.game.heroes.hero_fighter.actor import (
    HeroAction,
    HeroFighter,
)
from dungeons_desktops.game.heroes.hero_fighter.combat import (
    FLURRY_HITS,
    FLURRY_SEQUENCE,
    LEAP_COOLDOWN,
    MARK_CAST_TIME,
    MARK_REACQUIRE,
    MARK_SPEED,
    SHIELD_COOLDOWN,
    THROW_COOLDOWN,
    THROW_MIN_RANGE,
)
from dungeons_desktops.game.heroes.hero_fighter.render import PLATE, PLATE_DARK, SILVER
from dungeons_desktops.game.heroes.hero_fighter.weapon import (
    SoulforgedTridentAndShield,
)
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.navigation.planner import Anchor
from dungeons_desktops.navigation.terrain import SurfaceKind
from dungeons_desktops.preview.controller import RigPreviewController
from dungeons_desktops.rig.locomotion import PoseMode

DT = 1 / 60
FLOOR = 300.0


def advance_until(world, condition, seconds=10.0):
    for _ in range(round(seconds / DT)):
        world.advance(DT)
        if condition():
            return
    pytest.fail("condition did not become true")


def durable_goblin(world, point):
    target = world.add_goblin(point, "flag")
    target.max_hp = 100
    target.update = lambda dt: None
    return target


def test_soulforger_uses_the_base_fighter_model_gait_stats_and_new_identity():
    world = SimWorld([], FLOOR, 700, ceiling=0, seed=3)
    hero = world.add_stickman(Vec2(100, FLOOR), "hero_fighter")
    fighter = world.add_stickman(Vec2(500, FLOOR), "fighter")

    assert isinstance(hero, HeroFighter)
    assert hero.display_name == "The Soulforger"
    assert hero.max_hp == 60
    assert hero.layout.skeleton.bones == fighter.layout.skeleton.bones
    assert hero.layout.walk == fighter.layout.walk
    assert hero.calling.speed == fighter.calling.speed
    assert hero.calling.reach == 38.0 and hero.calling.cooldown == 0.8
    assert isinstance(hero.weapon, SoulforgedTridentAndShield)
    assert not hasattr(hero, "wings") and not hasattr(hero, "flying")
    assert "hero_fighter" in adventurer.HEROES


def test_death_mark_only_finishes_after_aggro_and_waits_before_handoff():
    world = SimWorld([], FLOOR, 800, ceiling=0, seed=4)
    hero = world.add_stickman(Vec2(100, FLOOR), "hero_fighter", wander=True)
    for _ in range(30):
        world.advance(DT)
    assert hero.marked is None and hero.action is None

    first = durable_goblin(world, Vec2(300, FLOOR))
    second = durable_goblin(world, Vec2(350, FLOOR))
    world.advance(DT)
    assert hero.action is HeroAction.MARK and hero.marked is None
    for _ in range(round((MARK_CAST_TIME - 2 * DT) / DT)):
        world.advance(DT)
    assert hero.marked is None
    advance_until(world, lambda: hero.marked is first)

    world.goblins.remove(first)
    world.advance(DT)
    assert hero.marked is None
    assert hero.mark_wait == pytest.approx(MARK_REACQUIRE)
    for _ in range(round((MARK_REACQUIRE - 2 * DT) / DT)):
        world.advance(DT)
    assert hero.marked is None
    advance_until(world, lambda: hero.marked is second)


def test_marked_pursuit_uses_regular_routes_at_double_fighter_speed_and_climbs():
    window = Rect(300, 160, 160, 140)
    world = SimWorld([window], FLOOR, 700, ceiling=0, seed=5)
    hero = world.add_stickman(Vec2(100, FLOOR), "hero_fighter", wander=True)
    target = durable_goblin(world, Vec2(380, window.top))
    hero.throw_cooldown = hero.leap_cooldown = 999.0
    modes = set()
    speeds = []
    previous = hero.contact()
    for _ in range(600):
        world.advance(DT)
        modes.add(hero.locomotion.mode)
        step = hero.contact().distance_to(previous)
        if hero.quarry is target and hero.locomotion.mode is PoseMode.WALK:
            speeds.append(step / DT)
        previous = hero.contact()
        if PoseMode.CLIMB in modes:
            break

    assert hero.marked is target
    assert PoseMode.CLIMB in modes
    assert speeds and max(speeds) == pytest.approx(
        adventurer.MOVES.walk_speed * MARK_SPEED, rel=0.08
    )


def test_basic_trident_attacks_only_the_mark_for_two_damage():
    world = SimWorld([], FLOOR, 500, ceiling=0, seed=6)
    hero = world.add_stickman(Vec2(100, FLOOR), "hero_fighter")
    marked = durable_goblin(world, Vec2(130, FLOOR))
    nearer = durable_goblin(world, Vec2(120, FLOOR))
    hero.marked = marked
    hero.quarry = marked
    hero.throw_cooldown = hero.leap_cooldown = 999.0

    advance_until(world, lambda: marked.damage > 0)

    assert marked.damage == 2
    assert nearer.damage == 0


def test_basic_trident_melee_alternates_slash_then_stab():
    world = SimWorld([], FLOOR, 500, ceiling=0, seed=17)
    hero = world.add_stickman(Vec2(100, FLOOR), "hero_fighter")
    target = durable_goblin(world, Vec2(130, FLOOR))
    hero.marked = target
    hero.quarry = target
    hero.throw_cooldown = hero.leap_cooldown = 999.0
    styles = []
    busy = False

    for _ in range(round(4.0 / DT)):
        world.advance(DT)
        if hero.weapon.busy and not busy:
            styles.append(hero.weapon.melee_style)
        busy = hero.weapon.busy
        if len(styles) == 2 and target.damage >= 4:
            break

    assert styles == ["slash", "stab"]
    assert target.damage == 4
    assert abs(hero.weapon.STAB_WINDUP.angle - hero.weapon.STAB_STRIKE.angle) < 0.1
    assert hero.weapon.SLASH_WINDUP.angle != hero.weapon.SLASH_STRIKE.angle


def test_spectral_trident_is_not_thrown_at_close_targets():
    world = SimWorld([], FLOOR, 500, ceiling=0, seed=19)
    hero = world.add_stickman(Vec2(100, FLOOR), "hero_fighter")
    target = durable_goblin(world, Vec2(130, FLOOR))
    hero.marked = target
    hero.quarry = target
    hero.leap_cooldown = 999.0

    advance_until(world, lambda: target.damage > 0)

    assert hero.center().distance_to(world.locate(target)) < THROW_MIN_RANGE
    assert target.damage == 2
    assert hero.throw_cooldown == 0.0
    assert not hero.spectral_tridents


def test_spectral_trident_pierces_but_only_marked_target_gets_bonus():
    world = SimWorld([], FLOOR, 700, ceiling=0, seed=7)
    hero = world.add_stickman(Vec2(100, FLOOR), "hero_fighter")
    first = durable_goblin(world, Vec2(240, FLOOR))
    marked = durable_goblin(world, Vec2(340, FLOOR))
    hero.marked = marked
    hero.quarry = marked
    hero.leap_cooldown = 999.0

    advance_until(world, lambda: bool(hero.spectral_tridents))
    assert hero.throw_cooldown == pytest.approx(THROW_COOLDOWN)
    assert hero.weapon_strokes()
    advance_until(world, lambda: marked.damage > 0)

    assert first.damage == 4
    assert marked.damage == 5


def test_unreleased_throw_cancels_without_spending_cooldown():
    world = SimWorld([], FLOOR, 600, ceiling=0, seed=8)
    hero = world.add_stickman(Vec2(100, FLOOR), "hero_fighter")
    target = durable_goblin(world, Vec2(300, FLOOR))
    hero.marked = target
    hero.quarry = target
    hero.leap_cooldown = 999.0

    advance_until(world, lambda: hero.action is HeroAction.THROW)
    world.goblins.remove(target)
    world.advance(DT)

    assert hero.action is None
    assert not hero.spectral_tridents
    assert hero.throw_cooldown == 0.0


def test_combat_leap_is_grounded_and_six_hits_only_the_marked_target():
    world = SimWorld([], FLOOR, 600, ceiling=0, seed=9)
    hero = world.add_stickman(Vec2(100, FLOOR), "hero_fighter")
    target = durable_goblin(world, Vec2(230, FLOOR))
    nearby = durable_goblin(world, Vec2(240, FLOOR))
    hero.marked = target
    hero.quarry = target
    modes = set()
    flurry_actions = set()
    pushes = []
    hurt_monster = world.hurt_monster

    def track_push(monster, amount, point, push, **how):
        if monster is target:
            pushes.append(push)
        return hurt_monster(monster, amount, point, push, **how)

    world.hurt_monster = track_push

    advance_until(world, lambda: hero.action is HeroAction.LEAP)
    assert hero.leap_cooldown == pytest.approx(LEAP_COOLDOWN)
    while hero.action is not None:
        world.advance(DT)
        modes.add(hero.locomotion.mode)
        if hero.action is HeroAction.FLURRY:
            flurry_actions.add(hero.hero_weapon.hero_action)

    assert PoseMode.AIR in modes
    assert target.damage == FLURRY_HITS * 2
    assert nearby.damage == 0
    assert {"trident_slice", "trident_stab", "shield_slice"} <= flurry_actions
    assert FLURRY_SEQUENCE.count("trident_stab") == 2
    assert pushes[:-1] == [Vec2(0.0, 0.0)] * (FLURRY_HITS - 1)
    assert pushes[-1].length() > 0.0
    assert hero.contact().y == FLOOR
    assert not hasattr(hero, "wing_open")


def test_combat_leap_needs_a_clear_arc_and_falls_back_to_throw():
    obstacle = Rect(150, 255, 40, 20)
    world = SimWorld([obstacle], FLOOR, 600, ceiling=0, seed=15)
    hero = world.add_stickman(Vec2(100, FLOOR), "hero_fighter")
    target = durable_goblin(world, Vec2(230, FLOOR))
    hero.marked = target
    hero.quarry = target

    assert hero._plan_leap(world.closest_part(target, hero.center())) is None
    advance_until(world, lambda: hero.action is HeroAction.THROW)


def test_combat_leap_ignores_the_desktop_ceiling_boundary():
    platform = Rect(80, 30, 320, 120)
    world = SimWorld([platform], FLOOR, 600, ceiling=0, seed=18)
    hero = world.add_stickman(Vec2(120, platform.top), "hero_fighter")
    target = durable_goblin(world, Vec2(245, platform.top))
    hero.marked = target
    hero.quarry = target

    landing = hero._plan_leap(world.closest_part(target, hero.center()))
    assert landing is not None
    advance_until(world, lambda: hero.action is HeroAction.LEAP)

    assert hero.leap_cooldown == pytest.approx(LEAP_COOLDOWN)


def test_a_target_that_moves_after_landing_avoids_the_remaining_flurry_hits():
    world = SimWorld([], FLOOR, 700, ceiling=0, seed=16)
    hero = world.add_stickman(Vec2(100, FLOOR), "hero_fighter")
    target = durable_goblin(world, Vec2(230, FLOOR))
    hero.marked = target
    hero.quarry = target

    advance_until(world, lambda: hero.action is HeroAction.FLURRY and target.damage > 0)
    surface = target.follower.current_anchor().surface
    target.follower.reset(Anchor(surface, Vec2(500, FLOOR)))
    target.locomotion.teleport(target.follower.command())
    advance_until(world, lambda: hero.action is None)

    assert 0 < target.damage < FLURRY_HITS * 2
    assert hero.contact().x < 300


def test_spectral_shield_retaliates_only_against_a_near_marked_target():
    world = SimWorld([], FLOOR, 500, ceiling=0, seed=10)
    hero = world.add_stickman(Vec2(100, FLOOR), "hero_fighter")
    marked = durable_goblin(world, Vec2(135, FLOOR))
    nearby = durable_goblin(world, Vec2(145, FLOOR))
    hero.marked = marked
    hero.quarry = marked

    killed = hero.hurt(1, hero.center(), Vec2(0.0, 0.0), "test", "fallen")
    assert not killed and hero.spectral_shield is not None
    assert hero.shield_cooldown == SHIELD_COOLDOWN
    hero._update_released_effects(0.2)

    assert hero.spectral_shield is None
    assert marked.damage == 3
    assert nearby.damage == 0

    far = durable_goblin(world, Vec2(300, FLOOR))
    hero.marked = far
    hero.shield_cooldown = 0.0
    hero.hurt(1, hero.center(), Vec2(0.0, 0.0), "test 2", "fallen")
    assert hero.spectral_shield is None


def test_soulforger_is_immune_to_mindflayer_stuns():
    world = SimWorld([], FLOOR, 500, ceiling=0, seed=11)
    hero = world.add_stickman(Vec2(120, FLOOR), "hero_fighter")
    flayer = world.add_mindflayer(Vec2(145, FLOOR))

    flayer._blast(hero, hero.center())
    flayer._start(Power.PULSE, None)
    flayer._use_power(PULSE_WINDUP)

    assert hero.stun == 0.0 and not hero.knocked and hero.animated


def test_soulforger_marks_and_attacks_while_climbing_like_a_fighter():
    window = Rect(400, 250, 300, 450)
    ledge = Rect(300, 470, 85, 230)
    world = SimWorld([window, ledge], 700, 1200, ceiling=20, seed=12)
    wall = next(
        surface
        for surface in world.planner.surfaces
        if surface.kind is SurfaceKind.LEFT and surface.box == 0
    )
    anchor = Anchor(wall, wall.closest_point(Vec2(window.left, 480)))
    hero = HeroFighter(world, anchor)
    world.stickmen.append(hero)
    hero.set_goal(Vec2(450, window.top))
    target = durable_goblin(world, Vec2(374, ledge.top))

    advance_until(world, lambda: target.damage > 0)

    assert target.damage == 2
    assert hero.marked is target
    assert hero.locomotion.mode is PoseMode.CLIMB


def test_unreleased_actions_cancel_for_control_and_engulf_states():
    class Lure:
        def holds(self, hero):
            return True

    class Reel:
        def reel_feet(self, hero):
            return hero.contact()

        def center(self):
            return Vec2(200, FLOOR)

    class Ooze:
        def engulfed_feet(self, hero):
            return hero.contact()

        def center(self):
            return Vec2(200, FLOOR)

    for state in ("thrall", "lure", "reel", "engulf"):
        world = SimWorld([], FLOOR, 600, ceiling=0, seed=13)
        hero = world.add_stickman(Vec2(100, FLOOR), "hero_fighter")
        target = durable_goblin(world, Vec2(300, FLOOR))
        hero.marked = target
        hero.quarry = target
        hero.leap_cooldown = 999.0
        advance_until(world, lambda hero=hero: hero.action is HeroAction.THROW)
        if state == "thrall":
            hero.enthrall()
        elif state == "lure":
            hero.lure = Lure()
        elif state == "reel":
            hero.reeled = Reel()
        else:
            hero.engulfed_by = Ooze()

        world.advance(DT)

        assert hero.action is None
        assert not hero.spectral_tridents
        assert hero.throw_cooldown == 0.0


def test_death_cleans_up_unreleased_state_but_a_released_trident_continues():
    world = SimWorld([], FLOOR, 700, ceiling=0, seed=14)
    hero = world.add_stickman(Vec2(100, FLOOR), "hero_fighter")
    target = durable_goblin(world, Vec2(320, FLOOR))
    hero.marked = target
    hero.quarry = target
    hero.leap_cooldown = 999.0
    advance_until(world, lambda: bool(hero.spectral_tridents))
    trident = hero.spectral_tridents[0]
    before = trident.position

    hero.go_ragdoll()
    world.advance(DT)

    assert hero.action is None and hero.marked is None
    assert hero.spectral_tridents == [trident]
    assert trident.position != before


def test_full_plate_standard_helmet_and_divine_equipment_render_without_wings():
    world = SimWorld([], FLOOR, 500, ceiling=0, seed=12)
    hero = world.add_stickman(Vec2(180, FLOOR), "hero_fighter")
    world.advance(DT)
    image = QImage(500, 340, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    draw_stickman(painter, hero)
    painter.end()

    colors = {
        image.pixelColor(x, y).name()
        for x in range(120, 250)
        for y in range(190, 310)
        if image.pixelColor(x, y).alpha()
    }
    assert {PLATE.name(), PLATE_DARK.name(), SILVER.name()} <= colors
    kinds = {stroke.kind for stroke in hero.weapon_strokes()}
    assert {"divine_glow", "divine", "divine_core", "hero_shield"} <= kinds


def test_preview_desktop_spawn_and_health_label_use_soulforger_name():
    preview = RigPreviewController(700, 400)
    preview.spawn_hero_fighter()
    assert isinstance(preview.selected, HeroFighter)
    assert "Soulforger" in preview.status

    session = DesktopSession(
        Rect(0, 0, 700, 500),
        Rect(0, 0, 700, 450),
        FakeWindowSource(),
        max_stickmen=0,
        defenders=(),
        seed=3,
    )
    hero = session.spawn_at_edge("left", variant="hero_fighter")
    assert isinstance(hero, HeroFighter)
    assert session.hero_health_bars == [("The Soulforger", 1)]
