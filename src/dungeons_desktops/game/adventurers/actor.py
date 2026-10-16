"""Characters in a world of boxes: the stickman adventurers and the base they share
with the goblins (see `goblins`).

Adventurers come in classes (`stick_figure.CLASSES`) with their own weapon, HP and
speed. Monsters hurt them through `Stickman.hurt`; at 0 HP they go down. Their own
attacks go for whatever monster comes in reach, and every one that lands (a melee
blow, an arrow, a magic missile, an alchemist's bomb blast, a druid's vine) takes
`mortal.ADVENTURER_DAMAGE` off it through `World.hurt_monster`. An alchemist the worm
kills goes off in its mouth (`World.detonate`).

A mind flayer's powers can paralyse an adventurer (`paralyze`), knock him flat
(`knock_down`) or make him its thrall (`enthrall`): a thrall turns on the others, who
treat him as a monster, and when he dies an intellect devourer bursts out of his head.
Monsters hunt only `prey`: adventurers still on their feet and in their right mind.

An actor owns where it is (a route follower) and how it looks (a locomotion
driver). The world it lives in supplies terrain, planners, projectiles, and a
random source; see `World`.
"""

from __future__ import annotations

import math
from enum import Enum

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.actors.base import Actor, out_of_boxes, surface_below
from dungeons_desktops.game.actors.hunting import nearest
from dungeons_desktops.game.adventurers import model as stick_figure
from dungeons_desktops.game.adventurers.combat import ADVENTURER_DAMAGE
from dungeons_desktops.game.adventurers.spells import ARROW_GRAVITY
from dungeons_desktops.game.effects.ballistics import GRAVITY as BOMB_GRAVITY
from dungeons_desktops.game.effects.ballistics import has_clear_lob, lob_velocity
from dungeons_desktops.game.effects.breath import DEATH_TIME, Demise
from dungeons_desktops.game.effects.fire import BURN_TIME, Burn
from dungeons_desktops.game.world.api import World
from dungeons_desktops.navigation.planner import Anchor
from dungeons_desktops.rig.biped import BipedLayout
from dungeons_desktops.rig.equipment import (
    CLINGING,
    Bombs,
    Bow,
    DruidStaff,
    HolyStaff,
    Stroke,
    Sword,
    Wand,
    Weapon,
)
from dungeons_desktops.rig.locomotion import (
    LocomotionInput,
    PoseMode,
    UpperBodyLayer,
)
from dungeons_desktops.rig.ragdoll import Ragdoll
from dungeons_desktops.rig.skeleton import BoneTransform, Pose, forward_kinematics

ACTING_MODES = frozenset({PoseMode.WALK, PoseMode.CLIMB, PoseMode.HANG})
BODY_RADIUS = 4.0
KICK_RADIUS = 25.0
KICK_SPEED = 520.0
BLAST_SPEED = 430.0
GOAL_SNAP = 80.0
REANCHOR_DISTANCE = 12.0
GET_UP_TIME = 0.6
DESPAWN_AFTER = 2.5
FADE_TIME = 0.6
WANDER_PAUSE = 0.8
EDGE_WALL_WEIGHT = 0.15
TRAIL_LENGTH = 10
GOBLIN_DAMAGE = 1
DRAGON_DAMAGE = 5
CHIMERA_FIRE_DAMAGE = DRAGON_DAMAGE
WORM_DAMAGE = 10
THRALL_DAMAGE = 1
THRALL_REACH = 20.0
"""How close a thrall gets to another adventurer before it strikes."""
THRALL_WINDUP = 0.3
THRALL_COOLDOWN = 1.2
THRALL_REPLAN = 0.5
HURT_GRACE = {"dragon": 1.0, "worm": 1.0, "hydra": 1.0, "chimera's fire": 1.0}
"""Seconds after a hit from this source before it can hurt the same adventurer again,
so one breath of fire or one bite lands once."""
MELEE_HEIGHT = 30.0
"""A monster must be within this height of a melee fighter for it to swing."""
MELEE_SLACK = 12.0
"""How far past its reach a melee blow still lands, for a monster that moved."""
MELEE_PUSH = 160.0
HEAL_RADIUS = 70.0
HEAL_AMOUNT = 2
ARROW_PACE = 0.45
SPELL_RANGE_AHEAD = 200.0
"""How far ahead a spell or arrow loosed at nothing (a manual attack) goes."""
SEEK_RADIUS = 380.0
"""How far off a wandering adventurer spots a monster and goes after it."""
SEEK_EVERY = 0.5
SEEK_GIVE_UP = 6.0
"""How long he leaves alone a monster he found no way any nearer to."""
RANGED_STAND = 0.6
"""A wizard, ranger or alchemist closes to this fraction of his reach, then holds."""
MELEE_STAND = 0.8
CLERIC_STAND = 80.0
"""How close to the fight a cleric hangs back, to heal whoever is in it."""
LURE_HASTE = 1.5
"""A lured adventurer hurries to his treasure chest."""
BLIND_PACE = 0.4
"""A blind adventurer feels his way along at this fraction of his pace..."""
GROPE_EVERY = (0.6, 1.4)
GROPE_STEP = 18.0
"""...a few steps either way at a time."""
ILLUSION_GLANCE = 160.0
"""A displacer beast's illusion this near draws his eye even out of his reach."""

ZERO = Vec2(0.0, 0.0)


class StickMode(Enum):
    ANIMATED = "Animated"
    RAGDOLL = "Ragdoll"


class Stickman(Actor):
    def __init__(
        self,
        world: World,
        anchor: Anchor,
        variant: str = "unarmed",
        wander: bool = False,
        layout: BipedLayout | None = None,
    ) -> None:
        super().__init__(world, layout or stick_figure.build_stick_figure(), anchor)
        self.ragdoll = Ragdoll(
            self.layout.skeleton,
            ground_y=world.floor_y,
            end_radius={self.layout.head: self.layout.head_radius},
        )
        self.ragdoll.obstacles = world.boxes
        self.ragdoll.engage(self.locomotion.pose, world.step)
        self.mode = StickMode.ANIMATED
        self.wander = wander
        self._wander_wait = 0.0
        self.down_time = 0.0
        self.burn: Burn | None = None
        self.demise: Demise | None = None
        """Killed by poison, lightning, acid or frost breath: how he goes."""
        self.severed: set[str] = set()
        """Bones that were bitten off; they're no longer drawn."""
        self.damage = 0
        """Damage taken; at `max_hp` he goes down."""
        self._grace: dict[str, float] = {}
        self._incoming_attacker: object | None = None
        self.cooldown = 0.0
        self.foe: object | None = None
        """The monster the current attack is aimed at."""
        self._foe_point = ZERO
        self._struck = False
        """The current melee attack has landed (or missed) its blow."""
        self._resume_route = False
        """Halted a route to attack; pick it up again once the attack is done."""
        self.dragging_limb: str | None = None
        self.stun = 0.0
        """Seconds left paralysed (standing frozen, or lying flat while `knocked`)."""
        self.knocked = False
        """Knocked flat by a psychic pulse: down until `stun` runs out, then gets up."""
        self._stun_after = 0.0
        """How long he stays paralysed once he's back on his feet."""
        self.quarry: object | None = None
        """The monster a wandering adventurer has spotted and is going after."""
        self._seek_wait = 0.0
        self._shunned: dict[object, float] = {}
        self.thrall = False
        """Under a mind flayer's control: hunts the other adventurers, who hunt him."""
        self.lure: object | None = None
        """The mimic he's been lured to (he thinks it's a treasure chest)."""
        self.lure_age = 0.0
        self.reeled: object | None = None
        """The mimic reeling him in on its tongue."""
        self.swallowed = False
        """Swallowed whole by a mimic: gone, body and all."""
        self.engulfed_by: object | None = None
        """The ooze holding this adventurer, who remains able to attack from inside."""
        self.blind = 0.0
        """Seconds left blind (in a drow's globe of darkness): he can't attack, and gropes
        about slowly instead of going anywhere."""
        self._grope_wait = 0.0
        self.faerie = 0.0
        """Seconds left outlined in faerie fire."""
        self.hunt = nearest()
        self._blow: float | None = None
        """A thrall's blow, landing in this many seconds."""
        self._thrall_replan = 0.0
        self.variant = "unarmed"
        self.calling = stick_figure.CALLINGS["unarmed"]
        self.weapon: Weapon | None = None
        self.trail: list[Vec2] = []
        self.set_variant(variant)

    @property
    def animated(self) -> bool:
        return self.mode is StickMode.ANIMATED

    @property
    def prey(self) -> bool:
        """Fair game for the monsters: on his feet and in his right mind."""
        return self.animated and not self.thrall and self.engulfed_by is None

    @property
    def paralysed(self) -> bool:
        return self.knocked or (self.animated and self.stun > 0.0)

    @property
    def facing(self) -> int:
        return self.locomotion.facing if self.animated else self.ragdoll.facing

    def pose(self) -> Pose:
        return self.locomotion.pose if self.animated else self.ragdoll.pose()

    def center(self) -> Vec2:
        return self.transforms()[self.layout.torso].start

    @property
    def fade(self) -> float:
        """0 while alive or freshly down; rises to 1 as a downed body fades out."""
        if self.animated:
            return 0.0
        return min(1.0, max(0.0, (self.down_time - self._despawn_after) / FADE_TIME))

    @property
    def gone(self) -> bool:
        if self.swallowed:
            return True
        return not self.animated and self.down_time >= self._despawn_after + FADE_TIME

    @property
    def _despawn_after(self) -> float:
        if self.demise is not None:
            return DEATH_TIME - FADE_TIME
        return DESPAWN_AFTER if self.burn is None else BURN_TIME - FADE_TIME

    def limb_tips(self) -> dict[str, Vec2]:
        return self.locomotion.limb_tips()

    @property
    def limbs_draggable(self) -> bool:
        return self.animated and not self.follower.moving and self.locomotion.mode is PoseMode.WALK

    @property
    def max_hp(self) -> int:
        return self.calling.hp

    @property
    def hp(self) -> int:
        return max(0, self.max_hp - self.damage)

    # ----- classes and attacks -------------------------------------------------

    def set_variant(self, variant: str) -> None:
        """Switch class ("barbarian", "wizard", ... or "unarmed")."""
        self.variant = variant
        self.calling = stick_figure.CALLINGS[variant]
        self.weapon = stick_figure.make_weapon(variant, self.layout)
        self.locomotion.upper = self.weapon
        self.trail.clear()

    def attack(self) -> None:
        """Attack now: at the nearest monster in reach, else straight ahead."""
        weapon = self.weapon
        if weapon is None:
            self.say("Unarmed - press 1-9 or 0 to pick a class")
            return
        if not self.animated or weapon.busy:
            return
        if not self._can_act():
            self.say("Can't attack mid-jump")
            return
        if not self._engage():
            ahead = self.center() + Vec2(self.facing * SPELL_RANGE_AHEAD, 0.0)
            self._strike(None, ahead)

    def _can_act(self) -> bool:
        """On his feet, on a wall or hanging from an underside: anywhere but mid-jump
        or mid-climb-over. Never while he's blind."""
        if self.blind > 0.0:
            return False
        if self.engulfed_by is not None:
            return True
        return self.locomotion.mode in ACTING_MODES and not self.follower.in_transition

    def _engage(self) -> bool:
        """Start the class's action if there's a reason to: a wounded ally near a
        cleric, a monster in reach of anyone else."""
        center = self.center()
        if isinstance(self.weapon, HolyStaff):
            if not self._wounded_near(center):
                return False
            self._resume_route = not self.wander and self.goal is not None and self.follower.moving
            self.halt()
            self.weapon.start()
            return True
        reach = self.calling.reach
        vines = isinstance(self.weapon, DruidStaff)
        found = self.world.nearest_monster(center, reach, through_ground=vines) if reach else None
        if found is None:
            return False
        monster, point = found
        if (
            not isinstance(self.weapon, Wand | Bow | Bombs | DruidStaff)
            and abs(point.y - center.y) > MELEE_HEIGHT
        ):
            return False
        if self.locomotion.mode in CLINGING and not self._clear_shot(monster, point):
            return False
        self._strike(monster, point)
        return True

    def _clear_shot(self, monster: object, point: Vec2) -> bool:
        """Whether an arrow or bomb would get to `point` without hitting the floor first
        (they fly through windows)."""
        weapon = self.weapon
        if not isinstance(weapon, Bow | Bombs):
            return True
        origin = self._shot_origin(None, self.transforms())
        moving = getattr(monster, "velocity", ZERO)
        if isinstance(weapon, Bow):
            gravity, pace = ARROW_GRAVITY, ARROW_PACE
        else:
            gravity, pace = BOMB_GRAVITY, 1.0
        return has_clear_lob(origin, point, moving, (), self.world.floor_y, gravity, pace)

    def _shot_origin(self, hand: Vec2 | None, transforms: dict[str, BoneTransform]) -> Vec2:
        """Where an arrow or bomb sets off: the hand, or for a climber his shoulder (his
        hand is up against his window)."""
        if hand is None or self.locomotion.mode in CLINGING:
            return transforms[self.layout.torso].end
        return hand

    def _face_nearest_monster(self) -> None:
        """Stand facing the closest monster in reach (or a displacer beast's illusion
        near him, which even a cleric watches), ready for the next attack."""
        center = self.center()
        reach = self.calling.reach
        vines = isinstance(self.weapon, DruidStaff)
        found = self.world.nearest_monster(center, reach, through_ground=vines) if reach else None
        illusions = self.world.illusions()
        if illusions and (found is None or found[0] not in illusions):
            near = self.world.nearest_monster(center, max(ILLUSION_GLANCE, reach))
            if near is not None and near[0] in illusions:
                found = near
        if found is not None and abs(found[1].x - center.x) > 1.0:
            self.follower.facing = 1 if found[1].x > center.x else -1

    def _strike(self, monster: object | None, point: Vec2) -> None:
        weapon = self.weapon
        assert weapon is not None
        self._resume_route = not self.wander and self.goal is not None and self.follower.moving
        self.halt()
        self._face(point, weapon)
        center = self.center()
        self.foe, self._foe_point = monster, point
        self._struck = False
        if isinstance(weapon, Bow):
            velocity = self._arrow_velocity(center, point)
            weapon.aim = math.atan2(velocity.y, abs(velocity.x))
        elif isinstance(weapon, Wand):
            offset = point - center
            weapon.aim = max(-1.2, min(1.2, math.atan2(offset.y, abs(offset.x))))
        weapon.start()

    def _face(self, point: Vec2, weapon: Weapon) -> None:
        """Turn toward `point`; a climber can't turn from his wall, so his weapon strikes
        behind him instead."""
        center = self.center()
        weapon.reverse = False
        if abs(point.x - center.x) <= 1.0:
            return
        side = 1 if point.x > center.x else -1
        if self.locomotion.mode is PoseMode.CLIMB:
            weapon.reverse = side != self.locomotion.facing
        else:
            self.follower.facing = side

    def _arrow_velocity(self, origin: Vec2, point: Vec2) -> Vec2:
        moving = getattr(self.foe, "velocity", ZERO)
        floor_y = self.world.floor_y
        return lob_velocity(origin, point, moving, (), floor_y, ARROW_GRAVITY, pace=ARROW_PACE)

    def _wounded_near(self, center: Vec2) -> list[Stickman]:
        return [
            s
            for s in self.world.stickmen
            if s.prey and s.damage and s.center().distance_to(center) <= HEAL_RADIUS
        ]

    @property
    def movement_paused(self) -> bool:
        weapon = self.weapon
        return weapon is not None and weapon.busy and weapon.stops_movement

    def weapon_strokes(self) -> list[Stroke]:
        if self.weapon is None:
            return []
        return self.weapon.strokes(self.transforms(), self.facing, slung=not self.animated)

    @property
    def weapon_held(self) -> bool:
        return self.weapon is not None and self.animated and self.weapon.held

    def _update_weapon(self) -> None:
        weapon = self.weapon
        if weapon is None:
            return
        transforms = self.transforms()
        facing = self.locomotion.facing
        if (
            isinstance(weapon, Wand | Bow | Bombs | DruidStaff | HolyStaff)
            and weapon.take_release()
        ):
            self._release(weapon, transforms, facing)
        hit_time = weapon.hit_time
        if (
            hit_time is not None
            and not self._struck
            and weapon.time is not None
            and weapon.time >= hit_time
        ):
            self._struck = True
            self._land_blow()
        if isinstance(weapon, Sword) and weapon.trail_active and weapon.held:
            self.trail.append(weapon.tip(transforms, facing))
            del self.trail[:-TRAIL_LENGTH]
        elif self.trail:
            self.trail.pop(0)

    def _land_blow(self) -> None:
        """The melee blow lands: on the monster it was aimed at if that's still in
        reach, else on whatever monster is."""
        world = self.world
        center = self.center()
        reach = self.calling.reach + MELEE_SLACK

        def in_reach(part: Vec2 | None) -> bool:
            return (
                part is not None
                and part.distance_to(center) <= reach
                and abs(part.y - center.y) <= MELEE_HEIGHT
            )

        monster, part = self.foe, None
        if monster is not None:
            part = world.closest_part(monster, center)
        if not in_reach(part):
            found = world.nearest_monster(center, reach)
            if found is None or not in_reach(found[1]):
                return
            monster, part = found
        assert part is not None
        push = Vec2(self.facing * MELEE_PUSH, -MELEE_PUSH * 0.4)
        world.hurt_monster(monster, ADVENTURER_DAMAGE, part, push, attacker=self)

    def _release(self, weapon: Weapon, transforms: dict[str, BoneTransform], facing: int) -> None:
        """The spell, arrow, bomb, vine or blessing leaves now (a thrall's at the free
        adventurer it's aimed at)."""
        world = self.world
        hostile = self.thrall
        point = self._foe_point
        if self.foe is not None:
            locate = world.locate_prey if hostile else world.locate
            point = locate(self.foe) or point
        if isinstance(weapon, Wand):
            world.spells.cast_missile(
                weapon.tip(transforms, facing),
                self.foe,
                point,
                hostile,
                owner=self,
                kind=weapon.missile_kind,
            )
        elif isinstance(weapon, Bow):
            nock = self._shot_origin(weapon.nock(transforms, facing)[0], transforms)
            world.spells.shoot(nock, self._arrow_velocity(nock, point), hostile, owner=self)
        elif isinstance(weapon, Bombs):
            hand = self._shot_origin(weapon.hand(transforms), transforms)
            moving = getattr(self.foe, "velocity", ZERO)
            velocity = lob_velocity(hand, point, moving, (), world.floor_y, BOMB_GRAVITY)
            world.vials.throw(hand, velocity, hostile, owner=self)
        elif isinstance(weapon, DruidStaff):
            root = self.contact() + Vec2(facing * 4.0 * self.layout.scale, 0.0)
            root = out_of_boxes(root, world.boxes)
            if self.foe is not None and not hostile:
                point = world.closest_part(self.foe, root, through_ground=True) or point
            world.spells.vine(root, self.foe, point, hostile, owner=self)
        else:
            center = self.center()
            world.spells.pulse(center, HEAL_RADIUS)
            for ally in self._wounded_near(center):
                ally.heal(HEAL_AMOUNT)
                world.spells.sparkle(ally.center(), "holy", 8, 60.0)

    # ----- simulation ----------------------------------------------------------

    def update(self, dt: float) -> None:
        self.faerie = max(0.0, self.faerie - dt)
        if not self.animated:
            self.ragdoll.step(dt)
            if self.knocked:
                self.stun -= dt
                if self.stun <= 0.0:
                    self.knocked = False
                    self.get_up()
                    self.stun = self._stun_after
                return
            self.down_time += dt
            if self.burn is not None:
                self._burn(dt)
            elif self.demise is not None:
                self._succumb(dt)
            return
        if self.engulfed_by is not None:
            self._engulfed_update(dt)
            return
        for source in self._grace:
            self._grace[source] -= dt
        self.cooldown -= dt
        if self.reeled is not None:
            self._reeling(dt)
            return
        if self.stun > 0.0:
            self.stun -= dt
            self._hold_still(dt)
            return
        if self.thrall:
            self._thrall_update(dt)
            return
        if self.lure is not None:
            self._lured(dt)
            return
        if self.blind > 0.0:
            self._grope(dt)
            return
        self._replan_if_needed()
        weapon = self.weapon
        if weapon is not None and not weapon.busy and self.dragging_limb is None:
            if self._resume_route:
                self._resume_route = False
                self.replan()
            if self._can_act():
                if self.cooldown <= 0.0 and self._engage():
                    self.cooldown = self.calling.cooldown
                elif not self.follower.moving:
                    self._face_nearest_monster()
        weapon_busy = weapon is not None and weapon.busy
        seeking = self.wander and not weapon_busy and self._seek(dt)
        if self.wander and not seeking and not self.follower.moving and not weapon_busy:
            self._wander_wait -= dt
            if self._wander_wait <= 0.0:
                self._wander_wait = WANDER_PAUSE
                self._pick_wander_goal()
        if self.movement_paused:
            command = self.follower.command()
        else:
            command = self.follower.update(dt * self.calling.speed)
        self.locomotion.update(dt, command)
        self._update_weapon()
        self.ragdoll.facing = self.locomotion.facing
        self.ragdoll.drive(self.locomotion.pose, dt)
        self._track_velocity(dt)

    def engulf(self, ooze: object) -> None:
        """Float inside an ooze while keeping the normal weapon and attack logic."""
        if self.lure is not None:
            self.free_from_lure()
        if self.reeled is not None:
            self.free_from_reel(drop=False)
        self.engulfed_by = ooze
        self.goal = None
        self._resume_route = False
        self.halt()

    def free_from_ooze(self, point: Vec2) -> None:
        self.engulfed_by = None
        if not self.animated:
            return
        anchor = surface_below(self.planner, point)
        self.follower.reset(anchor)
        self.locomotion.teleport(self.follower.command())
        self.ragdoll.drive(self.locomotion.pose, self.world.step)

    def _engulfed_update(self, dt: float) -> None:
        ooze = self.engulfed_by
        if ooze is None:
            return
        self.faerie = max(0.0, self.faerie - dt)
        for source in self._grace:
            self._grace[source] -= dt
        self.cooldown -= dt
        weapon = self.weapon
        if weapon is not None and not weapon.busy and self.dragging_limb is None:
            if self.cooldown <= 0.0 and self._engage():
                self.cooldown = self.calling.cooldown
            else:
                self._face_nearest_monster()
        feet = ooze.engulfed_feet(self)  # type: ignore[attr-defined]
        facing = 1 if ooze.center().x >= self.center().x else -1  # type: ignore[attr-defined]
        command = LocomotionInput(PoseMode.AIR, feet, facing, ("engulfed", id(ooze)), blend=0.1)
        self.locomotion.update(dt, command)
        self._update_weapon()
        self.ragdoll.facing = self.locomotion.facing
        self.ragdoll.drive(self.locomotion.pose, dt)
        self._track_velocity(dt)

    def _lured(self, dt: float) -> None:
        """Off to the "treasure chest" his mimic routed him to, minding nothing else."""
        lure = self.lure
        if lure is None or not lure.holds(self):  # type: ignore[attr-defined]
            self.free_from_lure()
            return
        self.lure_age += dt
        self._replan_if_needed()
        command = self.follower.update(dt * self.calling.speed * LURE_HASTE)
        self.locomotion.update(dt, command)
        self._update_weapon()
        self.ragdoll.facing = self.locomotion.facing
        self.ragdoll.drive(self.locomotion.pose, dt)
        self._track_velocity(dt)

    def blind_for(self, seconds: float) -> None:
        """Struck blind for at least `seconds`: whatever he was doing, he stops."""
        if not self.prey:
            return
        if self.blind <= 0.0:
            if self.weapon is not None:
                self.weapon.cancel()
            self._blow = None
            self._resume_route = False
            self.quarry = None
            self.goal = None
            self._grope_wait = 0.0
            self.halt()
        self.blind = max(self.blind, seconds)

    def _grope(self, dt: float) -> None:
        """Blind: shuffle a few steps this way or that along where he stands, slowly."""
        self.blind = max(0.0, self.blind - dt)
        self._replan_if_needed()
        self._grope_wait -= dt
        if self._grope_wait <= 0.0 and not self.follower.in_transition:
            random = self.world.random
            self._grope_wait = random.uniform(*GROPE_EVERY)
            here = self.follower.current_anchor()
            surface = here.surface
            if surface.walkable:
                coord = surface.coord(here.point) + random.uniform(-GROPE_STEP, GROPE_STEP)
                coord = min(max(coord, surface.low + 2.0), surface.high - 2.0)
                route = self.planner.plan(here, Anchor(surface, surface.point_at(coord)))
                self.follower.reset(here)
                if route is not None:
                    self.follower.set_route(route)
        command = self.follower.update(dt * self.calling.speed * BLIND_PACE)
        self.locomotion.update(dt, command)
        self._update_weapon()
        self.ragdoll.facing = self.locomotion.facing
        self.ragdoll.drive(self.locomotion.pose, dt)
        self._track_velocity(dt)

    def free_from_lure(self) -> None:
        self.lure = None
        self.locomotion.upper = self.weapon
        self.goal = None
        if self.animated:
            self.halt()

    def seize(self, mimic: object, flail: UpperBodyLayer) -> None:
        """Caught on `mimic`'s tongue: yanked off his feet, flailing, until it lets go."""
        if self.lure is not None:
            self.free_from_lure()
        self.reeled = mimic
        self.stun = 0.0
        self._blow = None
        self._resume_route = False
        if self.weapon is not None:
            self.weapon.cancel()
        self.locomotion.upper = flail
        self.halt()

    def _reeling(self, dt: float) -> None:
        mimic = self.reeled
        feet = mimic.reel_feet(self)  # type: ignore[attr-defined]
        if feet is None:
            self.free_from_reel()
            return
        facing = 1 if mimic.center().x >= self.center().x else -1  # type: ignore[attr-defined]
        command = LocomotionInput(PoseMode.AIR, feet, facing, ("reeled", id(mimic)), blend=0.08)
        self.locomotion.update(dt, command)
        self.ragdoll.facing = self.locomotion.facing
        self.ragdoll.drive(self.locomotion.pose, dt)
        self._track_velocity(dt)

    def squeeze(self) -> tuple[Vec2, Vec2, float] | None:
        """Going down a mimic's throat: its mouth, its way out, and how small he's shrunk."""
        if self.reeled is None:
            return None
        return self.reeled.squeeze(self)  # type: ignore[attr-defined]

    def free_from_reel(self, drop: bool = True) -> None:
        """Off the tongue: back to himself (or, `drop`ped mid-air, tumbling down)."""
        self.reeled = None
        self.locomotion.upper = self.weapon
        if drop and self.animated:
            self.knock_down(self.center() + Vec2(0.0, -20.0), 40.0, 0.5, 0.2)

    def _hold_still(self, dt: float) -> None:
        """Paralysed: frozen where he is (a jump or climb-over already under way lands)."""
        moving = self.follower.in_transition
        command = self.follower.update(dt) if moving else self.follower.command()
        self.locomotion.update(dt, command)
        self.ragdoll.facing = self.locomotion.facing
        self.ragdoll.drive(self.locomotion.pose, dt)
        self._track_velocity(dt)

    # ----- mind control ---------------------------------------------------------

    def paralyze(self, seconds: float) -> None:
        if not self.animated:
            return
        self.stun = max(self.stun, seconds)
        self._resume_route = False
        self._blow = None
        if self.weapon is not None:
            self.weapon.cancel()
        self.halt()

    def knock_down(self, center: Vec2, speed: float, down: float, stunned: float) -> None:
        """Flung away from `center`; lies there `down` seconds, then gets up and stays
        paralysed for `stunned` more."""
        if not self.animated:
            return
        body = self.center()
        away = (body - center).normalized()
        if away.length() == 0.0:
            away = Vec2(float(self.facing), 0.0)
        self.go_ragdoll()
        self.ragdoll.apply_impulse(body, (away + Vec2(0.0, -0.7)).normalized() * speed, 40.0)
        self.knocked = True
        self.stun = down
        self._stun_after = stunned

    def enthrall(self) -> None:
        """An intellect devourer now rides his skull: he turns on the other adventurers."""
        if not self.animated:
            return
        self.thrall = True
        self.wander = False
        self.goal = None
        self.hunt = nearest()
        self._blow = None
        self._resume_route = False
        self.cooldown = THRALL_COOLDOWN
        if self.weapon is not None:
            self.weapon.cancel()
        self.halt()
        self.say("Its mind is not its own!")

    def release(self) -> None:
        """The devourer in his skull lets go: he's himself again and wanders on."""
        if not self.thrall:
            return
        self.thrall = False
        self.wander = True
        self._blow = None
        self._resume_route = False
        self.goal = None
        if self.weapon is not None:
            self.weapon.cancel()
        self.halt()
        self.say("Free of the mind flayer!")

    def _in_thrall_reach(self, target: Stickman, slack: float = 0.0) -> bool:
        center, theirs = self.center(), target.center()
        return (
            abs(theirs.y - center.y) <= MELEE_HEIGHT
            and theirs.distance_to(center) <= THRALL_REACH + slack
        )

    @property
    def _shoots(self) -> bool:
        return isinstance(self.weapon, Wand | Bow | Bombs | DruidStaff)

    def _thrall_update(self, dt: float) -> None:
        """Hunt down the nearest free adventurer: a wizard, ranger, alchemist or druid
        thrall casts, shoots, throws or lashes at him from range like they would at a
        monster; the others strike him with whatever is in hand."""
        self._replan_if_needed()
        others = [s for s in self.world.stickmen if s is not self]
        target = self.hunt.update(dt, self.contact(), others)
        shoots = self._shoots
        in_range = (
            shoots
            and target is not None
            and target.center().distance_to(self.center()) <= self.calling.reach
        )
        if shoots:
            weapon = self.weapon
            assert weapon is not None
            if target is not None and in_range and self._can_act() and not weapon.busy:
                if self.cooldown <= 0.0:
                    self._strike(target, target.center())
                    self._resume_route = False
                    self.cooldown = self.calling.cooldown
                elif self.follower.moving:
                    self.halt()
        elif self._blow is not None:
            self._blow -= dt
            if self._blow <= 0.0:
                self._blow = None
                if target is not None and self._in_thrall_reach(target, MELEE_SLACK):
                    push = Vec2(self.facing * MELEE_PUSH, -MELEE_PUSH * 0.4)
                    target.hurt(
                        THRALL_DAMAGE,
                        target.center(),
                        push,
                        "thrall",
                        "Struck down by a mind-controlled friend!",
                    )
        elif (
            target is not None
            and self.cooldown <= 0.0
            and self._can_act()
            and self._in_thrall_reach(target)
        ):
            self.halt()
            if self.weapon is not None:
                self.weapon.cancel()
                self._face(target.center(), self.weapon)
                self.weapon.start()
            self._blow = THRALL_WINDUP
            self.cooldown = THRALL_COOLDOWN
        self._thrall_replan -= dt
        rooted = self._blow is not None or (shoots and self.movement_paused)
        if (
            target is not None
            and not rooted
            and not in_range
            and self._thrall_replan <= 0.0
            and not self.follower.in_transition
        ):
            self._thrall_replan = THRALL_REPLAN
            anchor = self.planner.anchor_near(target.contact(), GOAL_SNAP)
            if anchor is not None:
                self.goal = anchor.point
                self.replan()
        if rooted:
            command = self.follower.command()
        else:
            command = self.follower.update(dt * self.calling.speed)
        self.locomotion.update(dt, command)
        if shoots:
            self._update_weapon()
        self.ragdoll.facing = self.locomotion.facing
        self.ragdoll.drive(self.locomotion.pose, dt)
        self._track_velocity(dt)

    # ----- going after monsters ---------------------------------------------------

    def _stand_off(self) -> float:
        """How close he wants to be to his quarry: in reach (with room to spare) for a
        fighter, comfortably in range for a shooter, near the fight for a cleric."""
        weapon = self.weapon
        if isinstance(weapon, HolyStaff):
            return CLERIC_STAND
        if isinstance(weapon, Wand | Bow | Bombs):
            return self.calling.reach * RANGED_STAND
        return self.calling.reach * MELEE_STAND

    def _seek(self, dt: float) -> bool:
        """Go after the nearest monster within `SEEK_RADIUS`, stopping once it's close
        enough to fight (see `_stand_off`). True while he has one to go after; a
        monster he can't get any nearer to is left alone for `SEEK_GIVE_UP`."""
        self._shunned = {m: t - dt for m, t in self._shunned.items() if t > dt}
        self._seek_wait -= dt
        if self._seek_wait > 0.0:
            return self.quarry is not None
        if self.follower.in_transition:
            return self.quarry is not None
        self._seek_wait = SEEK_EVERY
        self.quarry = None
        if self.weapon is None:
            return False
        center = self.center()
        vines = isinstance(self.weapon, DruidStaff)
        found = [
            (m, part)
            for m, part in self.world.monsters_near(center, SEEK_RADIUS, through_ground=vines)
            if m not in self._shunned
        ]
        if not found:
            return False
        monster, part = found[0]
        self.quarry = monster
        melee = not isinstance(self.weapon, Wand | Bow | Bombs | DruidStaff | HolyStaff)
        level = not melee or abs(part.y - center.y) <= MELEE_HEIGHT
        if part.distance_to(center) <= self._stand_off() and level:
            if self.follower.moving:
                self.goal = None
                self.halt()
            return True
        start = self.follower.current_anchor()
        anchor = self.planner.anchor_near(part, GOAL_SNAP)
        route = None
        if anchor is not None and anchor.point.distance_to(start.point) >= 2.0:
            route = self.planner.plan(start, anchor)
        if route is None or not route.steps:
            self._shunned[monster] = SEEK_GIVE_UP
            self.quarry = None
            return False
        self.goal = anchor.point
        self.goal_reachable = True
        self.follower.reset(start)
        self.follower.set_route(route)
        return True

    def toggle_wander(self) -> None:
        self.wander = not self.wander
        self._wander_wait = 0.0
        self.say("Wandering" if self.wander else "Stopped wandering")

    def _pick_wander_goal(self) -> None:
        random = self.world.random
        start = self.follower.current_anchor()
        reachable = self.planner.reachable(start.surface)
        surfaces = [
            s
            for s in self.planner.surfaces
            if s.id in reachable and s.length > 1.0 and not s.hanging
        ]
        if not surfaces:
            return
        weights = [
            s.length * (EDGE_WALL_WEIGHT if s.box is None and s.wall else 1.0) for s in surfaces
        ]
        for _ in range(4):
            surface = random.choices(surfaces, weights=weights)[0]
            point = surface.point_at(random.uniform(surface.low, surface.high))
            route = self.planner.plan(start, Anchor(surface, point))
            if route is not None and route.steps:
                self.goal = point
                self.goal_reachable = True
                self.follower.set_route(route)
                return

    def stop(self) -> None:
        self.wander = False
        self.goal = None
        self.halt()
        self.say("Stopped")

    # ----- ragdoll -------------------------------------------------------------

    def lost_support(self, contact: Vec2) -> None:
        self.say("The ground moved out from under it!")
        self.go_ragdoll()

    def fall_in(self, start: Vec2) -> None:
        """Appear falling from `start` onto the current anchor, e.g. from the top of the screen."""
        self.drop_from(start)
        self.locomotion.teleport(self.follower.command())
        self.ragdoll.engage(self.locomotion.pose, self.world.step)
        self._last_contact = start

    def go_ragdoll(self) -> None:
        if not self.animated:
            return
        self.stun = 0.0
        self._blow = None
        self.release_limb()
        self.ragdoll.facing = self.locomotion.facing
        self.ragdoll.release()
        self.mode = StickMode.RAGDOLL
        self.goal = None
        self.down_time = 0.0
        self.velocity = ZERO
        if self.weapon is not None:
            self.weapon.cancel()
        self.trail.clear()

    def hurt(
        self,
        amount: int,
        point: Vec2,
        push: Vec2,
        source: str,
        death: str,
        bleed: bool = True,
        attacker: object | None = None,
    ) -> bool:
        """`amount` damage from `source` ("goblin", "dragon", "worm") landing at `point`,
        shoving along `push`. At 0 HP he goes down (saying `death`) and it counts as a
        kill. `attacker`, when known, lets named heroes answer the creature that
        landed the hit. Returns True if this hit killed him."""
        if not self.animated or self._grace.get(source, 0.0) > 0.0:
            return False
        if source in HURT_GRACE:
            self._grace[source] = HURT_GRACE[source]
        self.damage += amount
        if bleed:
            self.world.gore.spray(point, push, 5 + 2 * min(self.damage, 8), 160.0)
        if self.damage < self.max_hp:
            self.say(f"Hit by the {source} ({self.hp}/{self.max_hp} HP)")
            return False
        head = self.transforms()[self.layout.head].end
        self.world.mark_kill(head)
        self.go_ragdoll()
        self.ragdoll.apply_impulse(point, push, radius=30.0)
        self.world.kills += 1
        self.say(death)
        if source == "worm" and isinstance(self.weapon, Bombs):
            self.world.detonate(self.center())
            self.say("The alchemist's bombs went off in the worm's mouth!")
        if self.thrall:
            self.world.spawn_devourer(head)
            self.say("An intellect devourer bursts from its skull!")
        return True

    def hurt_from(
        self,
        attacker: object,
        amount: int,
        point: Vec2,
        push: Vec2,
        source: str,
        death: str,
        bleed: bool = True,
    ) -> bool:
        """Attribute a hit without changing the long-standing ``hurt`` call shape.

        Keeping the attacker in a short-lived context also preserves compatibility with
        preview and test doubles that replace ``hurt`` with the original six-argument
        callable.
        """
        previous = self._incoming_attacker
        self._incoming_attacker = attacker
        try:
            return self.hurt(amount, point, push, source, death, bleed)
        finally:
            self._incoming_attacker = previous

    def heal(self, amount: int) -> None:
        self.damage = max(0, self.damage - amount)

    def ignite(self) -> None:
        """Catch fire: drop, writhe, and burn until the body is gone."""
        self.go_ragdoll()
        if self.burn is None:
            self.burn = Burn()
            self.down_time = 0.0

    def succumb(self, breath: str) -> None:
        """Die of a dragon's `breath`: "fire" burns, "poison", "lightning", "acid" and
        "cold" are a `Demise`."""
        if breath == "fire":
            self.ignite()
            return
        self.go_ragdoll()
        if self.burn is None and self.demise is None:
            self.demise = Demise(breath, self.ragdoll.pose())
            self.down_time = 0.0

    def _succumb(self, dt: float) -> None:
        demise = self.demise
        assert demise is not None
        points = []
        for t in self.transforms().values():
            points += [t.start, t.start.lerp(t.end, 0.5), t.end]
        random = self.world.random
        jolt = demise.update(dt, points, random)
        if demise.held:
            pose = demise.held_pose(self.layout, self.ragdoll.facing, random)
            if self.ragdoll.motors_on:
                self.ragdoll.drive(pose, dt)
            else:
                self.ragdoll.engage(pose, dt)
        elif self.ragdoll.motors_on:
            self.ragdoll.release()
        if jolt is not None:
            self.ragdoll.apply_impulse(self.center(), jolt, radius=30.0)

    def _burn(self, dt: float) -> None:
        assert self.burn is not None
        points = []
        for t in self.transforms().values():
            points += [t.start, t.start.lerp(t.end, 0.5), t.end]
        jolt = self.burn.update(dt, points, self.world.random, self.world.floor_y)
        if jolt is not None:
            spot = self.world.random.choice(points)
            self.ragdoll.apply_impulse(spot, jolt, radius=12.0 * self.layout.scale + 8.0)

    def get_up(self) -> None:
        """Leave ragdoll: stand up on the walkable surface nearest the body."""
        if self.animated:
            return
        self.burn = None
        self.demise = None
        self.severed.clear()
        lying = self.ragdoll.pose()
        pelvis = forward_kinematics(self.layout.skeleton, lying)[self.layout.pelvis].start
        anchor = self.planner.anchor_near(pelvis, walk_only=True)
        self.follower.reset(anchor)
        self.locomotion.teleport(self.follower.command())
        self.locomotion.blend_from(lying, GET_UP_TIME)
        self.ragdoll.engage(lying, self.world.step)
        self.mode = StickMode.ANIMATED
        self._last_contact = anchor.point
        self.say("Back on its feet")

    def kick(self, point: Vec2) -> None:
        center = self.center()
        direction = (center - point).normalized()
        if direction.length() == 0.0:
            direction = Vec2(1.0, 0.0)
        hit = center.lerp(point, 0.5)
        self.ragdoll.apply_impulse(
            hit, (direction + Vec2(0.0, -0.6)) * KICK_SPEED, radius=KICK_RADIUS
        )

    def in_blast(self, center: Vec2, radius: float) -> bool:
        return any(
            t.end.distance_to(center) <= radius or t.start.distance_to(center) <= radius
            for t in self.transforms().values()
        )

    def blast(self, center: Vec2, radius: float) -> None:
        body = self.center()
        away = body - center
        distance = away.length()
        direction = away.normalized() if distance > 1e-6 else Vec2(0.0, -1.0)
        strength = BLAST_SPEED * (1.0 - 0.5 * min(1.0, distance / radius))
        self.go_ragdoll()
        self.down_time = 0.0
        launch = (direction + Vec2(0.0, -0.9)).normalized() * strength
        self.ragdoll.apply_impulse(body, launch, radius=45.0)

    # ----- limb dragging -------------------------------------------------------

    def grab_limb(self, name: str, point: Vec2) -> None:
        self.dragging_limb = name
        self.locomotion.overrides[name] = point

    def release_limb(self) -> None:
        if self.dragging_limb is not None:
            self.locomotion.overrides.pop(self.dragging_limb, None)
            self.dragging_limb = None
