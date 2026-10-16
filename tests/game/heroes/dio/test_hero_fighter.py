"""Dio's autonomous combat, movement, passive counter, and procedural model."""

from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.desktop.session import DesktopSession
from dungeons_desktops.desktop.windows import FakeWindowSource
from dungeons_desktops.game.adventurers.model import CALLINGS, CLASSES, HEROES
from dungeons_desktops.game.defenders.mindflayer.actor import PULSE_WINDUP, Power
from dungeons_desktops.game.heroes.dio.actor import (
    DIO_AWARENESS_RANGE,
    HERO_FIGHTER_GAIT,
    MARK_DAMAGE,
    MARK_SPEED,
    MARK_TIME,
    MOVE_PAUSE,
    SHIELD_COOLDOWN,
    SHIELD_DAMAGE,
    SLICE_HITS,
    TRIDENT_DAMAGE,
    TRIDENT_SCALE,
    WALK_SPEED,
    Dio,
    DioMove,
    DioPhase,
    HeroFighter,
    SpectralShield,
)
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.preview.controller import RigPreviewController
from dungeons_desktops.render import scene as render
from dungeons_desktops.render.scene import (
    HERO_PLATE,
    HERO_PLATE_DARK,
    HERO_SILVER,
    draw_dio_effects,
    draw_stickman,
)
from dungeons_desktops.rig.equipment import HeroTridentAndShield
from dungeons_desktops.rig.locomotion import PoseMode

DT = 1 / 60
FLOOR = 200.0


def advance_until(world, condition, seconds=10.0):
    for _ in range(round(seconds / DT)):
        world.advance(DT)
        if condition():
            return
    raise AssertionError("condition was not reached")


def test_dio_is_explicit_and_starts_with_piercing_trident_throw():
    assert "hero_fighter" in HEROES and "hero_fighter" not in CLASSES
    world = SimWorld([], FLOOR, 500, ceiling=0, seed=3)
    hero = world.add_stickman(Vec2(100, FLOOR), "hero_fighter")
    assert hero.calling is CALLINGS["hero_fighter"]
    assert hero.max_hp == 60 and hero.calling.reach == 38.0
    assert isinstance(hero, Dio)
    assert HeroFighter is Dio
    assert hero.layout.walk is HERO_FIGHTER_GAIT
    assert isinstance(hero.weapon, HeroTridentAndShield)

    goblin = world.add_goblin(Vec2(128, FLOOR), "flag")
    goblin.update = lambda dt: None
    for _ in range(120):
        world.advance(DT)
        if goblin.damage:
            break
    assert goblin.damage == TRIDENT_DAMAGE
    assert hero.current_move is DioMove.TRIDENT_THROW


def test_divine_trident_and_shield_are_layered_procedural_equipment():
    world = SimWorld([], FLOOR, 500, ceiling=0, seed=3)
    hero = world.add_stickman(Vec2(100, FLOOR), "hero_fighter")
    strokes = hero.weapon_strokes()
    kinds = {stroke.kind for stroke in strokes}
    assert {
        "divine_glow",
        "divine",
        "divine_core",
        "hero_shield",
        "hero_shield_trim",
        "hero_shield_strap",
    } <= kinds
    assert sum(stroke.kind == "divine_core" for stroke in strokes) == 6


def test_full_plate_and_enclosed_spartan_helmet_render():
    world = SimWorld([], FLOOR, 500, ceiling=0, seed=3)
    hero = world.add_stickman(Vec2(100, FLOOR), "hero_fighter")
    world.advance(DT)
    image = QImage(220, 240, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    draw_stickman(painter, hero)
    painter.end()

    colors = {image.pixelColor(x, y).name() for x in range(55, 150) for y in range(130, 205)}
    for color in (
        HERO_PLATE,
        HERO_PLATE_DARK,
        HERO_SILVER,
    ):
        assert color.name() in colors


def test_trident_and_shield_follow_the_gait_and_render_behind_the_body(monkeypatch):
    world = SimWorld([], FLOOR, 500, ceiling=0, seed=3)
    hero = world.add_stickman(Vec2(100, FLOOR), "hero_fighter")
    target = world.add_minotaur(Vec2(400, FLOOR))
    target.update = lambda dt: None
    hero.queue_index = 1
    relative: list[tuple[Vec2, Vec2]] = []
    for _ in range(45):
        world.advance(DT)
        strokes = hero.weapon_strokes()
        trident = next(stroke for stroke in strokes if stroke.kind == "divine")
        shield = next(stroke for stroke in strokes if stroke.kind == "hero_shield")
        relative.append((trident.start - hero.contact(), shield.start - hero.contact()))
    assert max(point.x for point, _ in relative) - min(point.x for point, _ in relative) > 0.4
    assert max(point.y for _, point in relative) - min(point.y for _, point in relative) > 0.4

    order = []
    original_strokes = render.draw_strokes
    original_body = render.draw_body

    def record_strokes(painter, strokes):
        order.append("equipment")
        return original_strokes(painter, strokes)

    def record_body(*args, **kwargs):
        order.append("body")
        return original_body(*args, **kwargs)

    monkeypatch.setattr(render, "draw_strokes", record_strokes)
    monkeypatch.setattr(render, "draw_body", record_body)
    image = QImage(500, 240, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    render.draw_stickman(painter, hero)
    painter.end()
    assert order.index("equipment") < order.index("body")
    assert max(
        stroke.width for stroke in hero.weapon_strokes() if stroke.kind == "divine"
    ) == 1.0 * hero.weapon.unit


def test_dio_has_dedicated_preview_and_desktop_spawns():
    preview = RigPreviewController(700, 400)
    before = len(preview.stickmen)
    preview.spawn_dio()
    assert preview.selected.variant == "hero_fighter"
    assert len(preview.stickmen) == before + 1 and preview.selected in preview.stickmen

    session = DesktopSession(
        Rect(0, 0, 700, 500),
        Rect(0, 0, 700, 450),
        FakeWindowSource(),
        seed=3,
        max_stickmen=0,
        defenders=(),
    )
    hero = session.spawn_at_edge("left", variant="hero_fighter")
    assert hero.variant == "hero_fighter" and hero.wander
    assert hero in session.heroes and session.hero_health == 1.0


def test_hero_health_bar_sits_below_the_monster_bar(monkeypatch):
    session = DesktopSession(
        Rect(0, 0, 700, 500),
        Rect(0, 0, 700, 450),
        FakeWindowSource(),
        seed=3,
        max_stickmen=0,
    )
    hero = session.add_stickman(Vec2(200, 450), "hero_fighter")
    bars = []
    monkeypatch.setattr(
        "dungeons_desktops.desktop.overlay.draw_health_bar",
        lambda painter, health, corner, color, label: bars.append((label, corner, health)),
    )
    monkeypatch.setattr("dungeons_desktops.desktop.overlay.draw_kill_counter", lambda *args: None)
    owner = SimpleNamespace(
        session=session,
        _kills_seen=session.kills,
        _kill_time=-1.0,
    )
    image = QImage(700, 500, QImage.Format.Format_ARGB32_Premultiplied)
    painter = QPainter(image)
    from dungeons_desktops.desktop.overlay import DesktopOverlay

    DesktopOverlay._draw_kills(owner, painter)
    painter.end()
    assert [label for label, _, _ in bars] == ["Dio", "Chimera"]
    assert bars[0][1].y > bars[1][1].y

    hero.hurt(hero.max_hp, hero.center(), Vec2(0, 0), "test", "fallen")
    assert session.hero_health is None


def test_dio_preserves_the_queue_without_targets_and_pierces_a_line_of_monsters():
    world = SimWorld([], FLOOR, 650, ceiling=0, seed=7)
    dio = world.add_stickman(Vec2(70, FLOOR), "hero_fighter")
    for _ in range(90):
        world.advance(DT)
    assert dio.phase is DioPhase.IDLE
    assert dio.current_move is DioMove.TRIDENT_THROW

    targets = [world.add_goblin(Vec2(x, FLOOR), "flag") for x in (220, 360)]
    for target in targets:
        target.update = lambda dt: None
    advance_until(world, lambda: dio.phase is DioPhase.THROW_CHARGE)
    for _ in range(10):
        world.advance(DT)
    assert 1.0 < dio.dio_weapon.trident_scale <= TRIDENT_SCALE
    advance_until(world, lambda: dio.thrown_trident is not None)
    assert not dio.dio_weapon.trident_visible
    advance_until(world, lambda: dio.phase is DioPhase.IDLE and dio.queue_index == 1)
    assert [target.damage for target in targets] == [TRIDENT_DAMAGE, TRIDENT_DAMAGE]
    assert dio.dio_weapon.trident_visible
    assert dio.move_pause == MOVE_PAUSE


def test_dio_waits_until_a_monster_enters_his_awareness_range():
    world = SimWorld([], FLOOR, 800, ceiling=0, seed=7)
    dio = world.add_stickman(Vec2(70, FLOOR), "hero_fighter")
    far = world.add_goblin(Vec2(500, FLOOR), "flag")
    far.update = lambda dt: None

    for _ in range(90):
        world.advance(DT)
    assert dio.phase is DioPhase.IDLE
    assert dio.target is None

    near = world.add_goblin(Vec2(70 + DIO_AWARENESS_RANGE - 20, FLOOR), "flag")
    near.update = lambda dt: None
    advance_until(world, lambda: dio.phase is DioPhase.THROW_CHARGE)
    assert dio.target is near


def test_double_slice_leaps_then_alternates_six_hits_with_only_a_final_push():
    world = SimWorld([], FLOOR, 600, ceiling=0, seed=4)
    dio = world.add_stickman(Vec2(80, FLOOR), "hero_fighter")
    target = world.add_goblin(Vec2(270, FLOOR), "flag")
    nearby = world.add_goblin(Vec2(285, FLOOR), "flag")
    target.max_hp = nearby.max_hp = 100
    target.update = lambda dt: None
    nearby.update = lambda dt: None
    dio.queue_index = 1
    calls = []
    original = world.hurt_monster

    def record(monster, amount, point, push, ranged=False, attacker=None):
        if attacker is dio:
            calls.append((monster, amount, push, ranged))
        return original(monster, amount, point, push, ranged, attacker)

    world.hurt_monster = record
    poses = set()
    for _ in range(round(10.0 / DT)):
        world.advance(DT)
        poses.add(dio.dio_weapon.dio_action)
        if dio.phase is DioPhase.IDLE and dio.queue_index == 2:
            break
    else:
        raise AssertionError("Double Slice did not finish")
    assert target.damage == SLICE_HITS
    assert nearby.damage == SLICE_HITS
    assert len(calls) == SLICE_HITS * 2
    assert {call[0] for call in calls} == {target, nearby}
    assert all(call[1] == 1 and not call[3] for call in calls)
    assert sum(call[2].length() > 0.0 for call in calls) == 2
    assert {"trident_slice", "shield_slice"} <= poses
    assert not dio.flying


def test_death_mark_locks_one_target_doubles_pursuit_and_expires():
    world = SimWorld([], FLOOR, 900, ceiling=0, seed=5)
    dio = world.add_stickman(Vec2(80, FLOOR), "hero_fighter")
    target = world.add_goblin(Vec2(350, FLOOR), "flag")
    target.update = lambda dt: None
    dio.queue_index = 2
    calls = []

    def record(monster, amount, point, push, ranged=False, attacker=None):
        calls.append((monster, amount, attacker))
        return False

    world.hurt_monster = record
    advance_until(world, lambda: dio.phase is DioPhase.MARK_HUNT)
    assert dio.marked is target
    nearby = world.add_goblin(Vec2(350, FLOOR), "flag")
    nearby.update = lambda dt: None
    before = dio.follower.current_anchor().point.x
    world.advance(DT)
    walked = dio.follower.current_anchor().point.x - before
    assert walked == pytest.approx(WALK_SPEED * dio.calling.speed * MARK_SPEED * DT)
    elapsed = 0.0
    while dio.phase is DioPhase.MARK_HUNT:
        world.advance(DT)
        elapsed += DT
        assert elapsed <= MARK_TIME + 2 * DT
    assert dio.current_move is DioMove.TRIDENT_THROW
    assert calls and {monster for monster, _, _ in calls} == {target, nearby}
    assert all(amount == MARK_DAMAGE and attacker is dio for _, amount, attacker in calls)


def test_death_mark_ends_early_when_its_locked_target_disappears():
    world = SimWorld([], FLOOR, 500, ceiling=0, seed=5)
    dio = world.add_stickman(Vec2(100, FLOOR), "hero_fighter")
    target = world.add_goblin(Vec2(180, FLOOR), "flag")
    target.update = lambda dt: None
    dio.queue_index = 2
    advance_until(world, lambda: dio.phase is DioPhase.MARK_HUNT)
    world.goblins.remove(target)
    world.advance(DT)
    assert dio.phase is DioPhase.IDLE
    assert dio.current_move is DioMove.TRIDENT_THROW


def test_double_slice_finishes_all_six_animations_after_its_target_dies():
    world = SimWorld([], FLOOR, 500, ceiling=0, seed=6)
    dio = world.add_stickman(Vec2(100, FLOOR), "hero_fighter")
    target = world.add_goblin(Vec2(145, FLOOR), "flag")
    target.update = lambda dt: None
    target.damage = target.max_hp - 1
    dio.queue_index = 1
    animated = []
    original = dio._land_slice

    def record(index):
        animated.append(index)
        original(index)

    dio._land_slice = record
    advance_until(world, lambda: dio.phase is DioPhase.IDLE and dio.queue_index == 2)
    assert target not in world.goblins
    assert animated == list(range(SLICE_HITS))


def test_double_slice_holds_its_landing_distance_from_a_flying_dragon():
    world = SimWorld([], FLOOR, 700, ceiling=0, seed=6)
    dio = world.add_stickman(Vec2(100, FLOOR), "hero_fighter")
    dragon = world.add_dragon(Vec2(240, 120), facing=1, variant="red")
    dragon.update = lambda dt: None
    dio.queue_index = 1
    advance_until(world, lambda: dio.phase is DioPhase.SLICE_FLURRY)
    locked = dio.contact() - dragon.body

    while dio.phase is DioPhase.SLICE_FLURRY:
        dragon._shift(Vec2(2.0, -0.25))
        world.advance(DT)
        if dio.phase is DioPhase.SLICE_FLURRY:
            assert dio.contact() - dragon.body == locked

    assert dragon.damage == SLICE_HITS
    assert dio.queue_index == 2


def test_dio_flies_between_horizontal_surfaces_without_climbing_and_lands_beside_target():
    window = Rect(230, 100, 180, 70)
    world = SimWorld([window], FLOOR, 700, ceiling=0, seed=9)
    dio = world.add_stickman(Vec2(70, FLOOR), "hero_fighter")
    target = world.add_goblin(Vec2(310, window.top), "flag")
    target.update = lambda dt: None
    dio.queue_index = 1
    modes = set()
    saw_wings = False
    for _ in range(600):
        world.advance(DT)
        modes.add(dio.locomotion.mode)
        saw_wings |= dio.wings
        if dio.phase is DioPhase.SLICE_FLURRY:
            break
    assert saw_wings
    assert not ({PoseMode.CLIMB, PoseMode.HANG} & modes)
    assert dio.phase is DioPhase.SLICE_FLURRY
    assert not dio.flying
    assert dio.contact().y == window.top


def test_shield_smash_requires_an_accepted_surviving_close_hit_and_has_a_cooldown():
    world = SimWorld([], FLOOR, 500, ceiling=0, seed=2)
    dio = world.add_stickman(Vec2(100, FLOOR), "hero_fighter")
    attacker = world.add_goblin(Vec2(130, FLOOR), "flag")
    nearby = world.add_goblin(Vec2(145, FLOOR), "flag")
    attacker.update = lambda dt: None
    nearby.update = lambda dt: None
    killed = dio.hurt_from(
        attacker, 1, dio.center(), Vec2(0.0, 0.0), "dragon", "fallen"
    )
    assert not killed
    assert dio.spectral_shield is not None
    assert dio.shield_cooldown == SHIELD_COOLDOWN
    before = attacker.damage
    dio._update_spectral_shield(0.2)
    assert attacker.damage - before == SHIELD_DAMAGE
    assert nearby.damage == SHIELD_DAMAGE
    assert dio.spectral_shield is None
    dio.hurt_from(attacker, 1, dio.center(), Vec2(0.0, 0.0), "second source", "fallen")
    assert dio.spectral_shield is None

    far = world.add_goblin(Vec2(300, FLOOR), "flag")
    dio.shield_cooldown = 0.0
    dio.hurt_from(far, 1, dio.center(), Vec2(0.0, 0.0), "far source", "fallen")
    assert dio.spectral_shield is None

    before = dio.damage
    dio.hurt(1, dio.center(), Vec2(0.0, 0.0), "unknown source", "fallen")
    assert dio.damage == before + 1
    assert dio.spectral_shield is None

    dio.shield_cooldown = 0.0
    dio.hurt_from(
        attacker, 1, dio.center(), Vec2(0.0, 0.0), "dragon", "fallen"
    )
    assert dio.damage == before + 1
    assert dio.spectral_shield is None

    dio.hurt_from(
        attacker,
        dio.hp,
        dio.center(),
        Vec2(0.0, 0.0),
        "fatal source",
        "fallen",
    )
    assert not dio.animated
    assert dio.spectral_shield is None


def test_dio_ignores_mindflayer_blast_and_pulse_stuns():
    world = SimWorld([], FLOOR, 500, ceiling=0, seed=2)
    dio = world.add_stickman(Vec2(120, FLOOR), "hero_fighter")
    flayer = world.add_mindflayer(Vec2(145, FLOOR))

    flayer._blast(dio, dio.center())
    assert dio.stun == 0.0
    assert not dio.knocked

    flayer._start(Power.PULSE, None)
    flayer._use_power(PULSE_WINDUP)
    assert dio.stun == 0.0
    assert not dio.knocked
    assert dio.animated


def test_dio_combat_and_flight_effects_render_as_procedural_layers():
    world = SimWorld([], FLOOR, 500, ceiling=0, seed=3)
    dio = world.add_stickman(Vec2(180, FLOOR), "hero_fighter")
    target = world.add_goblin(Vec2(230, FLOOR), "flag")
    target.update = lambda dt: None
    dio.target = target
    dio.phase = DioPhase.THROW_CHARGE
    dio.move_time = 0.2
    dio.dio_weapon.set_dio_action("throw", 0.6)
    dio._take_flight(Vec2(180, FLOOR - 35))
    dio._drive_air(0.2, Vec2(180, FLOOR - 35))
    dio.spectral_shield = SpectralShield(target, dio.center(), dio.center() + Vec2(15, 0))

    image = QImage(500, 260, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    draw_stickman(painter, dio)
    draw_dio_effects(painter, [dio])
    painter.end()
    colors = {
        image.pixelColor(x, y).name()
        for x in range(130, 260)
        for y in range(100, 220)
        if image.pixelColor(x, y).alpha()
    }
    assert HERO_PLATE.name() in colors
    assert HERO_PLATE_DARK.name() in colors
    assert HERO_SILVER.name() in colors
