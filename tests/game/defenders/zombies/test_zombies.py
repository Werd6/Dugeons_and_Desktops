import pytest

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.desktop.menu import DEFENDER_NAMES
from dungeons_desktops.desktop.session import DesktopSession
from dungeons_desktops.desktop.windows import FakeWindowSource
from dungeons_desktops.game.defenders.zombies.actor import ZOMBIE_PACK
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.navigation.planner import Anchor
from dungeons_desktops.navigation.terrain import SurfaceKind, TerrainChange
from dungeons_desktops.rig.locomotion import PoseMode

STEP = 1 / 60


def advance(world, seconds):
    for _ in range(round(seconds / STEP)):
        world.advance(STEP)


def test_zombie_moves_slower_than_a_walking_adventurer():
    world = SimWorld([], 600, 1400)
    zombie = world.add_zombie(Vec2(100, 600))
    adventurer = world.add_stickman(Vec2(300, 600))
    adventurer.set_goal(Vec2(1300, 600))
    advance(world, 2.0)
    assert 25 < zombie.contact().x - 100 <= 50
    assert adventurer.contact().x - 300 > 90
    assert zombie.target is adventurer


@pytest.mark.parametrize("facing", [-1, 1])
@pytest.mark.parametrize("moving", [False, True])
def test_both_arms_reach_forward_when_idle_and_shambling(facing, moving):
    world = SimWorld([], 600, 1400)
    zombie = world.add_zombie(Vec2(700, 600))
    zombie.follower.facing = facing
    zombie.locomotion.teleport(zombie.follower.command())
    if moving:
        assert zombie._go(Vec2(700 + facing * 300, 600))
    for _ in range(120):
        command = zombie.follower.update(STEP * zombie._regroup_pace())
        zombie.locomotion.update(STEP, command)
        transforms = zombie.transforms()
        shoulder = transforms[zombie.layout.torso].end
        for arm in zombie.layout.arms:
            hand = transforms[arm.bones[-1]].end
            assert facing * (hand.x - shoulder.x) > 5.0
            assert abs(hand.y - shoulder.y) < 4.0
        feet = [transforms[leg.bones[-1]].end for leg in zombie.layout.legs]
        assert all(abs(foot.y - 600) < 1.1 for foot in feet)


def test_zombie_claws_hurt_nearby_prey_but_cannot_hit_from_afar():
    world = SimWorld([], 600, 1400)
    zombie = world.add_zombie(Vec2(400, 600))
    prey = world.add_stickman(Vec2(415, 600))
    zombie.cooldown = 0.0
    advance(world, 1.0)
    assert prey.hp < prey.max_hp
    assert prey.animated
    assert world.zombies == [zombie]
    distant = world.add_stickman(Vec2(1100, 600))
    zombie.target = distant
    zombie.weapon.start()
    zombie.weapon.apply(zombie.pose().copy(), zombie.locomotion.mode, 0.5, frozenset())
    zombie._resolve_attack()
    assert distant.hp == distant.max_hp


def test_zombie_can_be_targeted_killed_and_despawned():
    world = SimWorld([], 600, 1400)
    zombie = world.add_zombie(Vec2(400, 600))
    assert zombie in world.monsters() and zombie in world.actors
    assert world.locate(zombie) == zombie.center()
    assert world.monster_at(zombie.center()) is zombie
    assert world.nearest_monster(zombie.center(), 10)[0] is zombie
    assert world.hurt_monster(zombie, zombie.hp, zombie.center(), Vec2(30, -20))
    assert zombie.dead and zombie.ragdoll is not None
    assert zombie not in world.zombies and zombie in world.fallen
    assert world.locate(zombie) is None
    advance(world, 4.0)
    assert zombie not in world.fallen


def test_zombie_is_carried_by_moved_window_and_falls_when_removed():
    box = Rect(200, 350, 300, 150)
    world = SimWorld([box], 600, 1400)
    zombie = world.add_zombie(Vec2(300, 350))
    world.apply_terrain(
        TerrainChange(moves={0: Vec2(40, 20)}, remap={0: 0}), [Rect(240, 370, 300, 150)]
    )
    assert zombie.contact() == Vec2(340, 370)
    assert zombie.planner.owns(zombie.follower.current_anchor().surface)
    world.apply_terrain(TerrainChange(remap={0: None}), [])
    advance(world, 2.0)
    assert zombie.contact().y == 600


def test_desktop_zombie_pack_health_rotation_and_dismissal():
    session = DesktopSession(
        Rect(0, 0, 1400, 900), Rect(0, 30, 1400, 800), FakeWindowSource(),
        defenders=("zombies", "goblins"), max_stickmen=0,
    )
    assert DEFENDER_NAMES["zombies"] == "Zombies"
    assert len(session.zombies) == ZOMBIE_PACK
    assert session.defender_health == 1.0
    first = session.zombies[0]
    session.hurt_monster(first, first.hp, first.center(), Vec2(0, 0))
    assert session.defender_health == pytest.approx((ZOMBIE_PACK - 1) / ZOMBIE_PACK)
    for zombie in list(session.zombies):
        session.hurt_monster(zombie, zombie.hp, zombie.center(), Vec2(0, 0))
    advance(session, 0.1)
    assert session.defender == "goblins"
    session.set_defenders(("zombies",))
    assert len(session.zombies) == ZOMBIE_PACK and not session.goblins
    session.set_defenders(())
    assert not session.zombies and not session.live_monsters


def test_preview_spawns_and_renders_green_zombies_alive_and_dead():
    from PySide6.QtGui import QImage, QPainter

    from dungeons_desktops.game.defenders.zombies.render import HEAD, draw_zombies
    from dungeons_desktops.preview.controller import RigPreviewController
    from dungeons_desktops.render.scene import draw_fallen

    world = RigPreviewController(1400, 900)
    world.spawn_zombie()
    zombie = world.zombies[0]
    for dead in (False, True):
        if dead:
            world.hurt_monster(zombie, zombie.hp, zombie.center(), Vec2(0, 0))
        image = QImage(80, 80, QImage.Format.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        try:
            painter.translate(40 - zombie.contact().x, 60 - zombie.contact().y)
            if dead:
                draw_fallen(painter, world.fallen)
            else:
                draw_zombies(painter, world.zombies)
        finally:
            painter.end()
        assert any(image.pixelColor(x, y) == HEAD for y in range(80) for x in range(80))


def lethal_claw(world, zombie):
    prey = world.add_stickman(zombie.contact() + Vec2(10, 0))
    prey.damage = prey.max_hp - 1
    zombie.target = prey
    zombie.weapon.cancel()
    zombie.weapon.start()
    zombie.weapon.apply(zombie.pose().copy(), zombie.locomotion.mode, 0.5, frozenset())
    zombie._resolve_attack()
    return prey


@pytest.mark.parametrize("hp", [6, 2, 0.5])
def test_each_kill_spawns_one_zombie_with_the_killers_current_hp(hp):
    world = SimWorld([], 600, 1400)
    zombie = world.add_zombie(Vec2(400, 600))
    zombie.damage = zombie.max_hp - hp
    prey = lethal_claw(world, zombie)
    assert not prey.animated and world.kills == 1
    assert len(world.zombies) == 2
    newborn = world.zombies[-1]
    assert newborn.contact() == prey.contact()
    assert newborn.hp == zombie.hp == hp
    assert newborn is not zombie and not newborn.dead
    zombie._resolve_attack()
    zombie.weapon.cancel()
    zombie.weapon.start()
    zombie.weapon.apply(zombie.pose().copy(), zombie.locomotion.mode, 0.5, frozenset())
    zombie._resolve_attack()
    assert len(world.zombies) == 2 and world.kills == 1


def test_offspring_passes_its_further_reduced_hp_to_the_next_generation():
    world = SimWorld([], 600, 1400)
    parent = world.add_zombie(Vec2(400, 600))
    parent.damage = 3
    lethal_claw(world, parent)
    child = world.zombies[-1]
    world.hurt_monster(child, 2, child.center(), Vec2(0, 0))
    lethal_claw(world, child)
    assert len(world.zombies) == 3
    assert parent.hp == 3 and child.hp == world.zombies[-1].hp == 1


def test_newborn_waits_until_next_simulation_step_to_act(monkeypatch):
    from dungeons_desktops.game.defenders.zombies.actor import Zombie

    world = SimWorld([], 600, 1400)
    parent = world.add_zombie(Vec2(400, 600))
    prey = world.add_stickman(Vec2(410, 600))
    prey.damage = prey.max_hp - 1
    parent.weapon.start()
    parent.weapon.time = parent.weapon.hit_time - STEP / 2
    updated = []
    original = Zombie.update

    def record_update(zombie, dt):
        updated.append(zombie)
        original(zombie, dt)

    monkeypatch.setattr(Zombie, "update", record_update)
    world.advance(STEP)
    assert len(world.zombies) == 2
    assert updated == [parent]


def test_offspring_keeps_the_defender_active_after_original_pack_dies():
    session = DesktopSession(
        Rect(0, 0, 1400, 900), Rect(0, 30, 1400, 800), FakeWindowSource(),
        defenders=("zombies", "goblins"), max_stickmen=0,
    )
    originals = list(session.zombies)
    parent = originals[0]
    parent.damage = 4
    lethal_claw(session, parent)
    child = session.zombies[-1]
    for zombie in originals:
        session.hurt_monster(zombie, zombie.hp, zombie.center(), Vec2(0, 0))
    advance(session, 0.1)
    assert session.defender == "zombies" and session.zombies == [child]
    assert session.defender_health == pytest.approx(2 / (ZOMBIE_PACK * parent.max_hp))
    session.hurt_monster(child, child.hp, child.center(), Vec2(0, 0))
    advance(session, 0.1)
    assert session.defender == "goblins"


def clinging_pair(kind, separation):
    world = SimWorld([Rect(300, 150, 300, 250)], 700, 1400)
    surface = next(s for s in world.zombie_planner.surfaces if s.kind is kind)
    point = surface.point_at((surface.low + surface.high) / 2)
    zombie = world.add_zombie()
    prey = world.add_stickman(variant="unarmed")
    offset = Vec2(separation, 0) if surface.hanging else Vec2(0, separation)
    for actor, at in ((zombie, point), (prey, point + offset)):
        actor.follower.reset(Anchor(surface, at))
        actor.locomotion.teleport(actor.follower.command())
        actor._last_contact = at
    prey.paralyze(30)
    zombie.cooldown = 0
    return world, zombie, prey, surface


@pytest.mark.parametrize("kind", [SurfaceKind.LEFT, SurfaceKind.RIGHT, SurfaceKind.CEILING])
@pytest.mark.parametrize("separation", [-12, 12])
@pytest.mark.parametrize("lethal", [False, True])
def test_zombies_attack_on_walls_and_ceilings_and_keep_a_grip(kind, separation, lethal):
    world, zombie, prey, surface = clinging_pair(kind, separation)
    zombie.damage = 3.5
    if lethal:
        prey.damage = prey.max_hp - 1
    before = prey.hp
    mode = PoseMode.HANG if surface.hanging else PoseMode.CLIMB
    for _ in range(36):
        world.advance(STEP)
        assert zombie.locomotion.mode is mode
        if zombie.weapon.busy:
            hand = zombie.transforms()[zombie.weapon.support_chain.bones[-1]].end
            if surface.hanging:
                assert hand.y == pytest.approx(surface.grip, abs=0.15)
            else:
                assert hand.x == pytest.approx(surface.start.x, abs=1.0)
                assert zombie.facing == surface.facing
    assert prey.hp == before - 1
    if lethal:
        assert not prey.animated and len(world.zombies) == 2
        assert world.zombies[-1].hp == zombie.hp == 2.5
    else:
        assert len(world.zombies) == 1
        advance(world, 0.5)
        assert prey.hp == before - 1  # One hit per swing, with the normal cooldown.
        advance(world, 1.0)
        assert prey.hp < before - 1


@pytest.mark.parametrize("kind", [SurfaceKind.LEFT, SurfaceKind.RIGHT, SurfaceKind.CEILING])
def test_clinging_zombies_cannot_claw_distant_adventurers(kind):
    world, zombie, prey, _ = clinging_pair(kind, 100)
    advance(world, 0.5)
    assert prey.hp == prey.max_hp
    assert not zombie.weapon.busy


@pytest.mark.parametrize("kind", [SurfaceKind.LEFT, SurfaceKind.RIGHT, SurfaceKind.CEILING])
def test_zombie_can_pause_a_climbing_route_to_claw(kind):
    world, zombie, prey, surface = clinging_pair(kind, 12)
    zombie.cooldown = 0.15
    zombie._replan_wait = 1.0
    start = zombie.contact()
    assert zombie._go(surface.point_at(surface.coord(start) + 60))
    advance(world, 0.1)
    assert zombie.contact() != start and zombie.follower.moving
    advance(world, 0.1)
    assert zombie.weapon.busy and not zombie.follower.moving
    advance(world, 0.5)
    assert prey.hp == prey.max_hp - 1


def test_plague_host_death_frenzies_survivors_with_speed():
    from dungeons_desktops.game.defenders.zombies.actor import (
        FRENZY_ATTACK,
        FRENZY_DURATION,
        FRENZY_SPEED,
        PLAGUE_SIZE,
    )

    world = SimWorld([], 600, 1400)
    pack = [world.add_zombie(Vec2(200 + i * 40, 600), legendary=True) for i in range(3)]
    assert all(z.size == PLAGUE_SIZE for z in pack)
    assert all(z.frenzy == 0.0 for z in pack)
    victim = pack[0]
    world.hurt_monster(victim, victim.hp, victim.center(), Vec2(0, -20))
    survivors = [z for z in world.zombies if not z.dead]
    assert len(survivors) == 2
    assert all(z.frenzy == pytest.approx(FRENZY_DURATION) for z in survivors)
    assert all(z._boost_speed() == FRENZY_SPEED for z in survivors)
    assert all(z._boost_attack() == FRENZY_ATTACK for z in survivors)
    advance(world, FRENZY_DURATION + 0.1)
    assert all(z.frenzy == 0.0 for z in survivors)
    assert all(z._boost_speed() == 1.0 for z in survivors)


def test_plague_host_kill_frenzies_pack_and_doubles_damage():
    from dungeons_desktops.game.defenders.zombies.actor import FRENZY_DAMAGE, FRENZY_DURATION

    world = SimWorld([], 600, 1400)
    hunter = world.add_zombie(Vec2(400, 600), legendary=True)
    ally = world.add_zombie(Vec2(460, 600), legendary=True)
    prey = world.add_stickman(hunter.contact() + Vec2(10, 0))
    prey.damage = prey.max_hp - 1
    hunter.target = prey
    hunter.weapon.cancel()
    hunter.weapon.start()
    hunter.weapon.apply(hunter.pose().copy(), hunter.locomotion.mode, 0.5, frozenset())
    hunter._resolve_attack()
    assert not prey.animated
    assert hunter.frenzy == pytest.approx(FRENZY_DURATION)
    assert ally.frenzy == pytest.approx(FRENZY_DURATION)
    tough = world.add_stickman(hunter.contact() + Vec2(10, 0))
    before = tough.hp
    hunter.target = tough
    hunter.weapon.cancel()
    hunter.weapon.start()
    hunter.weapon.apply(hunter.pose().copy(), hunter.locomotion.mode, 0.5, frozenset())
    hunter._resolve_attack()
    assert tough.hp == before - FRENZY_DAMAGE
