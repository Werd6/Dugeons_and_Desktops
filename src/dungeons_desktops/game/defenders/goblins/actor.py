"""The goblin pack: a war band that runs down the invaders together.

`GoblinPack` is the shared brain. While the standard bearer lives, the whole pack
hunts one stickman: the one nearest the flag, switching as soon as the flag is
clearly nearer someone else (`SWITCH_MARGIN`). Once it falls, every goblin hunts the
stickman nearest itself. Goblins making their way back toward a living flag move
faster (`REGROUP_BOOST`), so the band closes ranks. With nobody to hunt, the pack
roams to a rally point. Each `Goblin` routes there with the same planner moves the
stickmen use (running, jumping, climbing walls, mantling ledges), to a spot with
`ELBOW_ROOM` from where the others are headed, so the band spreads out.

There are three kinds:

- "sword": runs straight at the quarry and chops at it in melee.
- "spear": hangs back and lobs spears from range.
- "flag": carries the war banner with the pack and never attacks.

Each goblin hit does `GOBLIN_DAMAGE` (1): a base 4 HP adventurer takes four of
them, from any goblins, to bring down (see `Stickman.hurt`). A goblin has
`GOBLIN_HP`; brought down, it goes limp as a ragdoll like a stickman does.
"""

from __future__ import annotations

import math

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.actors.hunting import Hunt
from dungeons_desktops.game.actors.mortal import GOBLIN_HP, Mortal
from dungeons_desktops.game.adventurers.actor import (
    GOAL_SNAP,
    GOBLIN_DAMAGE,
    Actor,
    Stickman,
    World,
    surface_below,
)
from dungeons_desktops.game.adventurers.alchemy import lob_velocity
from dungeons_desktops.game.defenders.goblins import model as goblin
from dungeons_desktops.game.defenders.goblins.spears import GRAVITY as SPEAR_GRAVITY
from dungeons_desktops.navigation.planner import Anchor, Planner
from dungeons_desktops.navigation.terrain import TerrainChange
from dungeons_desktops.rig.locomotion import LocomotionInput, PoseMode
from dungeons_desktops.rig.ragdoll import Ragdoll
from dungeons_desktops.rig.skeleton import Pose
from dungeons_desktops.rig.weapons import Banner, GoblinSword, SpearThrower

KINDS = ("sword", "spear", "flag")
PACK = (
    "sword", "spear", "sword", "spear", "sword", "flag",
    "sword", "spear", "sword", "spear", "sword",
)  # fmt: skip
"""One war band, in line-up order: the standard bearer in the middle, six swords
and four spears. Goblins added one at a time fill packs in this order, round and round."""
REPLAN_EVERY = 0.4
SWORD_REACH = 6.0
SWORD_START_REACH = 1.0
"""Fraction of `SWORD_REACH` the quarry must be within before a swing starts."""
SWORD_STRIKE_REACH = 1.6
"""Fraction of `SWORD_REACH` the quarry may be within when the blade lands."""
SWORD_LEAD = 0.6
"""Seconds ahead of a moving quarry the swordsman aims, so it runs flat out onto him
rather than easing to a stop where he just was."""
SWORD_COOLDOWN = 0.7
SWORD_PUSH = 160.0
SPEAR_RANGE = (40.0, 240.0)
SPEAR_COOLDOWN = 1.6
SPEAR_PUSH = 220.0
SPEAR_PACE = 0.6
"""Spear flight time relative to a vial lob: lower throws flatter and harder."""
SPEAR_MAX_ARC = 50.0
"""Highest a spear may rise above the higher end of its throw; no lobbing over windows."""
HANG_BACK = {"sword": 0.0, "spear": 80.0, "flag": 24.0}
"""How far short of the quarry (on its own side of it) each kind aims to stop."""
GIVE_UP_AFTER = 3.0
"""Seconds with no goblin able to route to the quarry before the pack drops it."""
RETARGET_EVERY = 0.3
"""How often the quarry is re-picked, so the band turns as soon as the flag (or, with
it fallen, the goblin) has clearly come nearer to someone else..."""
SWITCH_MARGIN = 30.0
"""...that is, nearer by this much (or by `hunt.SWITCH_IF_BETTER` up close): enough
that two stickmen side by side don't have the band flip-flopping between them."""
ELBOW_ROOM = 8.0
"""How far apart (along a surface) goblins pick the spots they head for, so the band
spreads around its quarry instead of piling onto one point."""
SWORD_ELBOW_ROOM = 6.0
"""`ELBOW_ROOM` between two swords: they crowd in closer, so more get within reach."""
ELBOW_SLOTS = 6
"""Spots tried each way along the surface before settling for a crowded one."""
REGROUP_BOOST = 1.5
"""Speed multiplier for a goblin heading toward the living standard bearer..."""
REGROUP_RADIUS = 60.0
"""...from further away than this."""
RALLY_WAIT = (5.0, 9.0)
RALLY_SPACING = 12.0


def _hunt() -> Hunt:
    return Hunt(RETARGET_EVERY, switch_margin=SWITCH_MARGIN)


class GoblinPack:
    def __init__(self, world: World) -> None:
        self.world = world
        self.hunt = _hunt()
        """The band's quarry while the standard bearer lives."""
        self.rally: Vec2 | None = None
        self._rally_wait = 0.0

    @property
    def goblins(self) -> list[Goblin]:
        return self.world.goblins

    @property
    def planner(self) -> Planner:
        return self.world.goblin_planner

    @property
    def flag(self) -> Goblin | None:
        """The standard bearer, while it lives."""
        return next((g for g in self.goblins if g.kind == "flag" and not g.dead), None)

    @property
    def target(self) -> Stickman | None:
        """The band's shared quarry; None once the flag has fallen (each goblin then
        hunts its own, see `hunt_for`)."""
        return self.hunt.target if self.flag is not None else None

    def hunt_for(self, goblin: Goblin) -> Hunt:
        return self.hunt if self.flag is not None else goblin.hunt

    def center(self) -> Vec2 | None:
        goblins = self.goblins
        if not goblins:
            return None
        total = Vec2(0.0, 0.0)
        for member in goblins:
            total += member.contact()
        return total * (1.0 / len(goblins))

    def update(self, dt: float) -> None:
        flag = self.flag
        if flag is not None:
            banner = flag.held_at if flag.held_at is not None else flag.contact()
            hunting = self.hunt.update(dt, banner, self.world.stickmen) is not None
        else:
            hunting = all(g.hunt.target is not None for g in self.goblins)
        if hunting:
            self.rally = None
            return
        self._rally_wait -= dt
        if self.rally is None or self._rally_wait <= 0.0:
            self._pick_rally()

    def unreachable(self, goblin: Goblin, dt: float) -> None:
        """`goblin` couldn't route to its quarry. The band's shared quarry is only
        dropped once none of them has managed to for a while."""
        if self.flag is not None:
            self.hunt.unreachable(dt, GIVE_UP_AFTER * max(1, len(self.goblins)))
        else:
            goblin.hunt.unreachable(dt, GIVE_UP_AFTER)

    def reached(self, goblin: Goblin) -> None:
        self.hunt_for(goblin).reached()

    def _pick_rally(self) -> None:
        random = self.world.random
        self._rally_wait = random.uniform(*RALLY_WAIT)
        planner = self.planner
        reachable: set[int] = set()
        for member in self.goblins:
            surface = member.follower.current_anchor().surface
            if planner.owns(surface):
                reachable |= planner.reachable(surface)
        surfaces = [
            s for s in planner.surfaces if s.walkable and s.length >= 40.0 and s.id in reachable
        ]
        if not surfaces:
            return
        surface = random.choices(surfaces, weights=[s.length for s in surfaces])[0]
        self.rally = surface.point_at(random.uniform(surface.low + 15.0, surface.high - 15.0))


class Goblin(Actor, Mortal):
    max_hp = GOBLIN_HP
    linger = 2.5

    def __init__(self, world: World, anchor: Anchor, kind: str = "sword") -> None:
        layout = goblin.build_goblin()
        weapons = {"sword": GoblinSword, "spear": SpearThrower, "flag": Banner}
        self.weapon = weapons[kind](layout)
        super().__init__(world, layout, anchor, upper=self.weapon)
        self.kind = kind
        self.cooldown = world.random.uniform(0.3, 1.0)
        self.target: Stickman | None = None
        self.hunt = _hunt()
        """Its own quarry, once the standard bearer has fallen."""
        self.held_at: Vec2 | None = None
        self._replan_wait = world.random.uniform(0.0, REPLAN_EVERY)
        self.ragdoll: Ragdoll | None = None

    @property
    def planner(self) -> Planner:
        return self.world.goblin_planner

    @property
    def pack(self) -> GoblinPack:
        return self.world.goblin_pack

    @property
    def held(self) -> bool:
        return self.held_at is not None

    @property
    def spot(self) -> Vec2:
        """Where it means to stand: its goal while it's on the way, else where it is."""
        if self.follower.moving and self.goal is not None:
            return self.goal
        return self.contact()

    @property
    def facing(self) -> int:
        return self.ragdoll.facing if self.ragdoll is not None else self.locomotion.facing

    def pose(self) -> Pose:
        return self.ragdoll.pose() if self.ragdoll is not None else self.locomotion.pose

    def hand(self) -> Vec2:
        return self.transforms()[self.weapon.hand_chain.bones[-1]].end

    # ----- simulation ----------------------------------------------------------

    def update(self, dt: float) -> None:
        if self.held_at is not None:
            self.locomotion.update(dt, self._held_command(self.held_at))
            return
        self._replan_if_needed()
        self.cooldown -= dt
        pack = self.pack
        if pack.flag is None:
            self.hunt.update(dt, self.contact(), self.world.stickmen)
        self.target = pack.hunt_for(self).target
        busy = self.weapon.busy
        ready = (
            not busy
            and not self.follower.in_transition
            and self.locomotion.mode in self.weapon.held_modes
        )
        if ready and self.target is not None and self.cooldown <= 0.0:
            self._try_attack(self.target)
            busy = self.weapon.busy
        rooted = busy and self.kind != "sword"
        if not rooted:
            self._replan_wait -= dt
            if self._replan_wait <= 0.0 and not self.follower.in_transition:
                self._replan_wait = REPLAN_EVERY
                self._head_out(dt)
        pace = 1.0 if rooted else self._regroup_pace()
        command = self.follower.command() if rooted else self.follower.update(dt * pace)
        self.locomotion.update(dt, command)
        self._resolve_attack()
        self._track_velocity(dt)

    def _head_out(self, dt: float) -> None:
        target = self.target
        if target is not None:
            goal = target.contact()
            if self.kind == "sword":
                goal = goal + target.velocity * SWORD_LEAD
            back = HANG_BACK[self.kind]
            away = self.contact() - goal
            if self.kind == "spear":
                goal = self._throwing_spot(target)
            elif back and away.length() > 1e-6:
                goal = goal + away.normalized() * min(back, away.length())
            if self._go(goal, walk_only=self.kind != "sword"):
                self.pack.reached(self)
            else:
                self.pack.unreachable(self, REPLAN_EVERY)
            return
        rally = self.pack.rally
        if rally is None:
            return
        index = self.pack.goblins.index(self) if self in self.pack.goblins else 0
        offset = (index - (len(self.pack.goblins) - 1) / 2) * RALLY_SPACING
        self._go(rally + Vec2(offset, 0.0))

    def _throwing_spot(self, target: Stickman) -> Vec2:
        """Footing `HANG_BACK` short of the quarry, on this goblin's side of it if there's
        any, else past it: never a wall (no throwing while climbing) and never so close
        that the quarry is inside `SPEAR_RANGE`."""
        here = self.follower.current_anchor()
        distance = target.center().distance_to(self.center())
        in_range = SPEAR_RANGE[0] <= distance <= SPEAR_RANGE[1]
        if here.surface.walkable and in_range and self._spear_arc(target) is not None:
            return here.point
        quarry = target.contact()
        back = HANG_BACK["spear"]
        away = self.contact() - quarry
        side = 1.0 if away.x >= 0.0 else -1.0
        aims = [Vec2(side * back, 0.0), Vec2(-side * back, 0.0)]
        if away.length() > 1e-6:
            aims.insert(0, away.normalized() * back)
        spots = []
        for aim in aims:
            anchor = self.planner.anchor_near(quarry + aim, walk_only=True)
            if anchor is not None:
                spots.append(anchor.point)
        clear = [p for p in spots if p.distance_to(quarry) >= SPEAR_RANGE[0]]
        return (clear or spots or [quarry])[0]

    def _regroup_pace(self) -> float:
        """`REGROUP_BOOST` while closing in on the living standard bearer, else 1."""
        flag = self.pack.flag
        if flag is None or flag is self:
            return 1.0
        to_flag = flag.contact() - self.contact()
        distance = to_flag.length()
        if distance < REGROUP_RADIUS or self.velocity.dot(to_flag) <= 0.0:
            return 1.0
        return REGROUP_BOOST

    def _go(self, point: Vec2, walk_only: bool = False) -> bool:
        """Route toward `point` (quietly); False if there's no way there. `walk_only`
        stops on the nearest walkable surface however far, never on a wall or ceiling."""
        snap = math.inf if walk_only else GOAL_SNAP
        anchor = self.planner.anchor_near(point, snap, walk_only=walk_only)
        if anchor is None:
            return False
        anchor = self._make_room(anchor)
        start = self.follower.current_anchor()
        if anchor.surface is start.surface and anchor.point.distance_to(start.point) < 2.0:
            self.halt()
            return True
        route = self.planner.plan(start, anchor)
        if route is None:
            return False
        self.goal = anchor.point
        self.follower.reset(start)
        self.follower.set_route(route)
        return True

    def _make_room(self, anchor: Anchor) -> Anchor:
        """`anchor`, or the nearest spot along its surface with elbow room from every
        other goblin's `spot`, trying this goblin's own side first and then
        alternating, so a crowd wraps around the quarry."""
        others = [
            (g.spot, self._elbow_room(g))
            for g in self.pack.goblins
            if g is not self and not g.dead and not g.held
        ]
        surface = anchor.surface
        coord = surface.coord(anchor.point)
        side = 1.0 if surface.coord(self.contact()) >= coord else -1.0
        step = self._elbow_room(self)
        for i in range(2 * ELBOW_SLOTS + 1):
            along = coord + (i + 1) // 2 * step * (side if i % 2 else -side)
            if not surface.low <= along <= surface.high:
                continue
            point = surface.point_at(along)
            if all(point.distance_to(spot) > room - 1.0 for spot, room in others):
                return Anchor(surface, point)
        return anchor

    def _elbow_room(self, other: Goblin) -> float:
        swords = self.kind == other.kind == "sword"
        return SWORD_ELBOW_ROOM if swords else ELBOW_ROOM

    # ----- fighting ------------------------------------------------------------

    def _face(self, point: Vec2) -> None:
        self.follower.facing = 1 if point.x >= self.contact().x else -1

    def _blade_point(self, toward: Vec2) -> Vec2:
        side = 1.0 if toward.x >= self.contact().x else -1.0
        return self.center() + Vec2(side * 5.0 * goblin.SCALE * 3.0, 0.0)

    def _in_reach(self, target: Stickman, slack: float = 1.0) -> bool:
        point = self._blade_point(target.center())
        return target.prey and target.hits(point, margin=SWORD_REACH * slack)

    def _try_attack(self, target: Stickman) -> None:
        if self.kind == "sword" and self._in_reach(target, slack=SWORD_START_REACH):
            self._face(target.center())
            self.weapon.start()
            self.cooldown = SWORD_COOLDOWN
        elif self.kind == "spear" and self.locomotion.mode is PoseMode.WALK:
            distance = target.center().distance_to(self.center())
            if SPEAR_RANGE[0] <= distance <= SPEAR_RANGE[1] and self._spear_arc(target) is not None:
                self.halt()
                self._face(target.center())
                self.weapon.start()
                self.cooldown = SPEAR_COOLDOWN

    def _spear_arc(self, target: Stickman) -> Vec2 | None:
        """Launch velocity for a spear at `target` (spears fly through windows), or None
        when only a lob higher than `SPEAR_MAX_ARC` would get there."""
        world = self.world
        origin = self.hand()
        aim = target.center()
        velocity = lob_velocity(
            origin,
            aim,
            target.velocity,
            (),
            world.floor_y,
            gravity=SPEAR_GRAVITY,
            pace=SPEAR_PACE,
        )
        rise = velocity.y * velocity.y / (2.0 * SPEAR_GRAVITY) if velocity.y < 0.0 else 0.0
        arc = rise - max(0.0, origin.y - aim.y)
        return velocity if arc <= SPEAR_MAX_ARC else None

    def _resolve_attack(self) -> None:
        target = self.target
        weapon = self.weapon
        if isinstance(weapon, GoblinSword) and weapon.take_strike():
            if target is not None and self._in_reach(target, slack=SWORD_STRIKE_REACH):
                push = Vec2(self.facing * SWORD_PUSH, -SWORD_PUSH * 0.5)
                point = self._blade_point(target.center())
                target.hurt_from(
                    self, GOBLIN_DAMAGE, point, push, "goblin", "Cut down by the goblins!"
                )
        elif isinstance(weapon, SpearThrower) and weapon.take_release():
            if target is not None and target.prey:
                velocity = self._spear_arc(target)
                if velocity is not None:
                    self.world.spears.throw(self.hand(), velocity, weapon.length)

    # ----- picking up and placing ----------------------------------------------

    def _held_command(self, point: Vec2) -> LocomotionInput:
        hang = self.layout.leg_length + 4.0 * self.layout.scale
        return LocomotionInput(
            PoseMode.AIR, point + Vec2(0.0, hang), self.follower.facing, ("held",), blend=0.12
        )

    def pick_up(self, point: Vec2) -> None:
        self.weapon.cancel()
        self.follower.reset(self.follower.current_anchor())
        self.held_at = point

    def hold_at(self, point: Vec2) -> None:
        self.held_at = point

    def place(self, point: Vec2) -> None:
        """Drop onto the walkable surface below `point`."""
        hang = self.layout.leg_length + 4.0 * self.layout.scale
        anchor = surface_below(self.planner, point + Vec2(0.0, hang))
        self.held_at = None
        self.follower.reset(anchor)
        self.cooldown = max(self.cooldown, 0.6)

    def lost_support(self, contact: Vec2) -> None:
        """Fall to whatever is below and carry on from there."""
        self.weapon.cancel()
        anchor = surface_below(self.planner, contact)
        self.follower.reset(anchor)
        self.cooldown = max(self.cooldown, 0.6)
        if anchor.point.y - contact.y > 2.0:
            self.drop_from(contact)

    def terrain_changed(self, change: TerrainChange) -> None:
        if self.held:
            return
        super().terrain_changed(change)

    # ----- death ---------------------------------------------------------------

    def die(self, point: Vec2, push: Vec2) -> None:
        """Go limp where it stands, shoved along `push` from `point`, weapon on its back."""
        self.dead = True
        self.down_time = 0.0
        self.held_at = None
        self.weapon.cancel()
        self.weapon.held = False
        world = self.world
        ragdoll = Ragdoll(
            self.layout.skeleton,
            ground_y=world.floor_y,
            end_radius={self.layout.head: self.layout.head_radius},
        )
        ragdoll.obstacles = world.boxes
        ragdoll.facing = self.locomotion.facing
        ragdoll.engage(self.locomotion.pose, world.step)
        ragdoll.release()
        ragdoll.apply_impulse(point, push, radius=25.0)
        self.ragdoll = ragdoll

    def update_dead(self, dt: float) -> None:
        assert self.ragdoll is not None
        self.ragdoll.obstacles = self.world.boxes
        self.ragdoll.step(dt)
        self.down_time += dt
