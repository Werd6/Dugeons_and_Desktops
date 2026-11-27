"""Four fixed-role undead knights that advance, fight, and steal their killers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from dungeons_desktops.core.geometry import Vec2, clamp
from dungeons_desktops.game.actors.base import Actor
from dungeons_desktops.game.actors.spacing import reserve_opening, separate_pack
from dungeons_desktops.game.adventurers import model as stick_figure
from dungeons_desktops.game.adventurers.actor import Stickman
from dungeons_desktops.game.adventurers.spells import ARROW_GRAVITY
from dungeons_desktops.game.defenders.goblins.actor import (
    GIVE_UP_AFTER,
    REPLAN_EVERY,
    SWORD_LEAD,
    Goblin,
    GoblinPack,
    _hunt,
)
from dungeons_desktops.game.defenders.graveknights.equipment import GraveSwordAndShield
from dungeons_desktops.game.defenders.legendary import apply_legendary
from dungeons_desktops.game.defenders.zombies.spacing import (
    SEPARATION_SPEED,
    personal_space,
)
from dungeons_desktops.game.effects.ballistics import lob_velocity
from dungeons_desktops.game.effects.fire import Burn
from dungeons_desktops.game.heroes.hero_sorcerer.weapon import SkullFocus
from dungeons_desktops.game.world.api import World
from dungeons_desktops.navigation.planner import Anchor, Planner
from dungeons_desktops.rig.equipment import Axe, Bow, Weapon
from dungeons_desktops.rig.ragdoll import Ragdoll


class GraveknightRole(StrEnum):
    """The permanent job and loadout of one member of the squad."""

    ARCHER = "archer"
    FIGHTER = "fighter"
    MAGE = "mage"
    BARBARIAN = "barbarian"


POSSESSIONS_PER_GRAVEKNIGHT = 2
POSSESSION_EMERGE_TIME = 0.35
ADVENTURER_GRAVEKNIGHT_ROLE = {
    "ranger": GraveknightRole.ARCHER,
    "fighter": GraveknightRole.FIGHTER,
    "paladin": GraveknightRole.FIGHTER,
    "wizard": GraveknightRole.MAGE,
    "sorcerer": GraveknightRole.MAGE,
    "cleric": GraveknightRole.MAGE,
    "druid": GraveknightRole.MAGE,
    "alchemist": GraveknightRole.MAGE,
    "barbarian": GraveknightRole.BARBARIAN,
    "rogue": GraveknightRole.BARBARIAN,
}


GRAVEKNIGHT_ROSTER = (
    GraveknightRole.ARCHER,
    GraveknightRole.FIGHTER,
    GraveknightRole.MAGE,
    GraveknightRole.BARBARIAN,
)
GRAVEKNIGHT_PACK = len(GRAVEKNIGHT_ROSTER)

# Every role has its own balance knobs. Keeping these named constants in addition to
# the stats table makes single-role tuning straightforward without coupling the four.
ARCHER_HP = 10
ARCHER_DAMAGE = 1
ARCHER_COOLDOWN = 4.0
ARCHER_RANGE = 340.0
ARCHER_PUSH = 140.0
ARCHER_MOVE_SPEED = 1.0
ARCHER_ARROW_PACE = 0.45
ARCHER_STANDOFF = 100.0

FIGHTER_HP = 14
FIGHTER_DAMAGE = 2
FIGHTER_COOLDOWN = 0.8
FIGHTER_RANGE = 30.0
FIGHTER_PUSH = 170.0
FIGHTER_MOVE_SPEED = 0.9
FIGHTER_STANDOFF = 0.0

MAGE_HP = 9
MAGE_DAMAGE = 2
MAGE_COOLDOWN = 2.2
MAGE_RANGE = 280.0
MAGE_PUSH = 140.0
MAGE_MOVE_SPEED = 0.95
MAGE_CAST_DURATION = SkullFocus.NORMAL_DURATION
MAGE_RELEASE_TIME = SkullFocus.NORMAL_RELEASE
MAGE_STANDOFF = 100.0

BARBARIAN_HP = 15
BARBARIAN_DAMAGE = 3
BARBARIAN_COOLDOWN = 1.2
BARBARIAN_RANGE = 34.0
BARBARIAN_PUSH = 220.0
BARBARIAN_MOVE_SPEED = 1.05
BARBARIAN_STANDOFF = 0.0
FUNERAL_PYRE_RADIUS = 90.0
FUNERAL_PYRE_DAMAGE = 3
ASHEN_HASTE_SPEED = 0.7
"""Move-speed bonus at full ashen haste (fewer possession charges left)."""
ASHEN_HASTE_ATTACK = 1.1
"""Attack-speed bonus at full ashen haste."""


@dataclass(frozen=True)
class GraveknightStats:
    hp: int
    damage: int
    cooldown: float
    attack_range: float
    push: float
    move_speed: float
    standoff: float


GRAVEKNIGHT_STATS = {
    GraveknightRole.ARCHER: GraveknightStats(
        ARCHER_HP,
        ARCHER_DAMAGE,
        ARCHER_COOLDOWN,
        ARCHER_RANGE,
        ARCHER_PUSH,
        ARCHER_MOVE_SPEED,
        ARCHER_STANDOFF,
    ),
    GraveknightRole.FIGHTER: GraveknightStats(
        FIGHTER_HP,
        FIGHTER_DAMAGE,
        FIGHTER_COOLDOWN,
        FIGHTER_RANGE,
        FIGHTER_PUSH,
        FIGHTER_MOVE_SPEED,
        FIGHTER_STANDOFF,
    ),
    GraveknightRole.MAGE: GraveknightStats(
        MAGE_HP,
        MAGE_DAMAGE,
        MAGE_COOLDOWN,
        MAGE_RANGE,
        MAGE_PUSH,
        MAGE_MOVE_SPEED,
        MAGE_STANDOFF,
    ),
    GraveknightRole.BARBARIAN: GraveknightStats(
        BARBARIAN_HP,
        BARBARIAN_DAMAGE,
        BARBARIAN_COOLDOWN,
        BARBARIAN_RANGE,
        BARBARIAN_PUSH,
        BARBARIAN_MOVE_SPEED,
        BARBARIAN_STANDOFF,
    ),
}
GRAVEKNIGHT_TOTAL_HP = sum(stats.hp for stats in GRAVEKNIGHT_STATS.values())

# Compatibility aliases for callers written against the original all-archer squad.
GRAVEKNIGHT_HP = ARCHER_HP
GRAVEKNIGHT_DAMAGE = ARCHER_DAMAGE
BOW_RANGE = ARCHER_RANGE
BOW_COOLDOWN = ARCHER_COOLDOWN
ARROW_PACE = ARCHER_ARROW_PACE
MELEE_REACH = FIGHTER_RANGE
MELEE_COOLDOWN = FIGHTER_COOLDOWN
MELEE_PUSH = FIGHTER_PUSH

_WEAPONS: dict[GraveknightRole, type[Weapon]] = {
    GraveknightRole.ARCHER: Bow,
    GraveknightRole.FIGHTER: GraveSwordAndShield,
    GraveknightRole.MAGE: SkullFocus,
    GraveknightRole.BARBARIAN: Axe,
}
_MELEE_ROLES = frozenset({GraveknightRole.FIGHTER, GraveknightRole.BARBARIAN})


class GraveknightPack(GoblinPack):
    """One shared quarry and rally point for the four-role squad."""

    @property
    def goblins(self) -> list[Graveknight]:
        return self.world.graveknights

    @property
    def planner(self) -> Planner:
        return self.world.planner

    @property
    def flag(self) -> Graveknight | None:
        # Treat the first living knight as the formation leader. This gives the squad
        # shared pack targeting without requiring a literal standard bearer.
        return next((knight for knight in self.goblins if not knight.dead), None)

    def update(self, dt: float) -> None:
        flag = self.flag
        if flag is not None:
            banner = flag.held_at if flag.held_at is not None else flag.contact()
            hunting = self.hunt.update(dt, banner, self.world.stickmen) is not None
        else:
            hunting = False
        if hunting:
            self.rally = None
            return
        self._rally_wait -= dt
        if self.rally is None or self._rally_wait <= 0.0:
            self._pick_rally()

    def unreachable(self, goblin: Graveknight, dt: float) -> None:
        self.hunt.unreachable(dt, GIVE_UP_AFTER * max(1, len(self.goblins)))

    def reached(self, goblin: Graveknight) -> None:
        self.hunt.reached()

    def separate(self, dt: float, movable: set[Graveknight]) -> None:
        """Gently spread the squad along each supporting surface."""
        separate_pack(
            self.goblins,
            self.planner,
            dt,
            movable,
            personal_space,
            SEPARATION_SPEED,
        )

    def _can_possess(self, candidate: object) -> bool:
        """True when this living free regular adventurer can host a Graveknight spirit."""
        return (
            isinstance(candidate, Stickman)
            and candidate in self.world.stickmen
            and candidate.prey
            and candidate.variant in stick_figure.CLASSES
            and candidate.variant in ADVENTURER_GRAVEKNIGHT_ROLE
        )

    def _possession_host(self, attacker: object) -> Stickman | None:
        """Killer if possessable; else a random adventurer when a hero landed the kill."""
        if isinstance(attacker, Stickman) and self._can_possess(attacker):
            return attacker
        if (
            not isinstance(attacker, Stickman)
            or not attacker.is_hero
            or attacker not in self.world.stickmen
        ):
            return None
        candidates = [s for s in self.world.stickmen if self._can_possess(s)]
        if not candidates:
            return None
        return self.world.random.choice(candidates)

    def possess(
        self,
        fallen: Graveknight,
        attacker: object,
    ) -> Graveknight | None:
        """Replace a qualifying host with this spirit's next Graveknight body.

        Regular adventurer killers are claimed directly. Hero killers redirect the
        claim onto a random living free adventurer still on screen.
        """
        world = self.world
        if fallen.possessions_left <= 0:
            return None
        host = self._possession_host(attacker)
        if host is None:
            return None
        role = ADVENTURER_GRAVEKNIGHT_ROLE[host.variant]

        anchor = (
            self.planner.anchor_near(host.contact())
            if host.follower.in_transition
            else host.follower.current_anchor()
        )
        if anchor is None:
            return None
        point = host.center()
        facing = host.follower.facing
        remaining = fallen.possessions_left - 1
        fallen.possessions_left = remaining

        # A delayed projectile can land while its owner is being reeled or lured.
        # Break those references before the adventurer leaves the world roster.
        if host.reeled is not None:
            let_go = getattr(host.reeled, "let_go", None)
            if let_go is not None:
                let_go()
            else:
                host.free_from_reel(drop=False)
        if host.lure is not None:
            host.free_from_lure()
        host.release_limb()
        if host.weapon is not None:
            host.weapon.cancel()
        world.stickmen.remove(host)

        possessed = Graveknight(
            world,
            anchor,
            role,
            possessions_left=remaining,
        )
        if getattr(fallen, "legendary", False):
            apply_legendary(possessed)
            # Stronger pyre bloom each resurrection (fewer charges left).
            heat = possessed.ashen_haste
            world.spells.sparkle(point, "fire", 18 + int(24 * heat), 180.0 + 160.0 * heat)
            world.debris.burst(
                point, Vec2(0.0, -1.0), 8 + int(10 * heat), 200.0, spread=2.2, puffs=8, scale=0.9
            )
        possessed.follower.facing = facing
        possessed.locomotion.teleport(possessed.follower.command())
        possessed._last_contact = possessed.contact()
        possessed.possession_time = POSSESSION_EMERGE_TIME
        world.graveknights.append(possessed)
        world.spells.sparkle(point, "life_drain", 18, 170.0)
        possessed.say(f"The {host.variant} is claimed by the Graveknights!")
        return possessed


class Graveknight(Goblin):
    def __init__(
        self,
        world: World,
        anchor: Anchor,
        role: GraveknightRole | str = GraveknightRole.ARCHER,
        possessions_left: int = POSSESSIONS_PER_GRAVEKNIGHT,
    ) -> None:
        self.role = GraveknightRole(role)
        self.possessions_left = max(0, possessions_left)
        self.possession_time = 0.0
        self.stats = GRAVEKNIGHT_STATS[self.role]
        self.max_hp = self.stats.hp
        self.attack_damage = self.stats.damage
        self.attack_cooldown = self.stats.cooldown
        self.attack_range = self.stats.attack_range
        self.attack_push = self.stats.push
        self.move_speed = self.stats.move_speed
        self.standoff = self.stats.standoff

        layout = stick_figure.build_stick_figure()
        self.weapon = _WEAPONS[self.role](layout)
        if isinstance(self.weapon, SkullFocus):
            # Explicit instance values keep the mage's casting cadence independently
            # tunable while retaining the Hero Sorcerer's exact focus animation.
            self.weapon.duration = MAGE_CAST_DURATION
            self.weapon.release_time = MAGE_RELEASE_TIME
        Actor.__init__(self, world, layout, anchor, upper=self.weapon)
        self.kind = "sword"  # Goblin routing treats the whole squad as forward attackers.
        self.cooldown = world.random.uniform(0.3, min(1.0, self.attack_cooldown))
        self.target: Stickman | None = None
        self.hunt = _hunt()
        self.held_at: Vec2 | None = None
        self._replan_wait = world.random.uniform(0.0, REPLAN_EVERY)
        self.ragdoll: Ragdoll | None = None
        self._shot_target: Stickman | None = None
        self._shot_point = anchor.point
        self._melee_struck = False
        self._ashen_ember = 0.0

    @property
    def planner(self) -> Planner:
        return self.world.planner

    @property
    def pack(self) -> GraveknightPack:
        return self.world.graveknight_pack

    @property
    def ashen_haste(self) -> float:
        """0 with a full possession bank → 1 with none left. Legendary only."""
        if not getattr(self, "legendary", False):
            return 0.0
        floor = max(POSSESSIONS_PER_GRAVEKNIGHT, 1)
        spent = 1.0 - clamp(self.possessions_left / floor, 0.0, 1.0)
        return 0.2 + 0.8 * spent

    def _make_room(self, anchor: Anchor) -> Anchor:
        """Choose a route goal with the same personal space used by destacking."""
        return reserve_opening(self, anchor, personal_space(anchor.surface))

    def _ashen_embers(self, dt: float, *, emerging: bool = False) -> None:
        """Fire particles that return on every resurrection and heat up with haste."""
        if not getattr(self, "legendary", False) or self.dead:
            return
        haste = self.ashen_haste
        self._ashen_ember += dt
        gap = max(0.05, 0.26 - 0.16 * haste)
        if emerging:
            gap *= 0.55
        if self._ashen_ember < gap:
            return
        self._ashen_ember = 0.0
        count = 3 + int(6 * haste) + (4 if emerging else 0)
        self.world.spells.sparkle(
            self.center() + Vec2(0.0, -6.0),
            "fire",
            count,
            80.0 + 120.0 * haste + (40.0 if emerging else 0.0),
        )

    def update(self, dt: float) -> None:
        if self.held_at is not None:
            self.locomotion.update(dt, self._held_command(self.held_at))
            return
        if self.possession_time > 0.0:
            self.possession_time = max(0.0, self.possession_time - dt)
            self.locomotion.update(dt, self.follower.command())
            self._track_velocity(dt)
            self._ashen_embers(dt, emerging=True)
            return
        self._replan_if_needed()
        haste = self.ashen_haste
        self.cooldown -= dt * (1.0 + ASHEN_HASTE_ATTACK * haste)
        self.target = self.pack.hunt.target
        self._ashen_embers(dt)

        if (
            self.role is GraveknightRole.MAGE
            and self.weapon.busy
            and self.target is not None
            and self.target.prey
        ):
            self._aim_focus(self.target.center())

        ready = (
            not self.weapon.busy
            and not self.follower.in_transition
            and self.locomotion.mode in (self.weapon.held_modes | self.weapon.cling_modes)
        )
        if ready and self.target is not None and self.cooldown <= 0.0:
            self._try_attack(self.target)

        # Ranged actions deliberately do not root the archer or mage: their upper-body
        # animations play while the squad's route and walking gait continue advancing.
        self._replan_wait -= dt
        if self._replan_wait <= 0.0 and not self.follower.in_transition:
            self._replan_wait = REPLAN_EVERY
            self._head_out(dt)
        speed = self.move_speed * (1.0 + ASHEN_HASTE_SPEED * haste)
        command = self.follower.update(dt * speed * self._regroup_pace())
        self.locomotion.update(dt, command)
        self._resolve_attack()
        self._track_velocity(dt)

    def _head_out(self, dt: float) -> None:
        target = self.target
        if target is not None:
            goal = target.contact()
            if self.standoff:
                away = self.contact() - goal
                if away.length() < 1.0:
                    away = Vec2(-self.facing, 0.0)
                goal += away.normalized() * self.standoff
            else:
                goal += target.velocity * SWORD_LEAD
            if self._go(goal):
                self.pack.reached(self)
            else:
                self.pack.unreachable(self, REPLAN_EVERY)
            return
        super()._head_out(dt)

    def _try_attack(self, target: Stickman) -> None:
        if self.role in _MELEE_ROLES:
            if self._in_reach(target):
                self._face(target.center())
                self._melee_struck = False
                if self.weapon.start():
                    self.cooldown = self.attack_cooldown
            return
        if self.center().distance_to(target.center()) > self.attack_range:
            return
        self._face(target.center())
        self._shot_target = target
        self._shot_point = target.center()
        if self.role is GraveknightRole.ARCHER:
            assert isinstance(self.weapon, Bow)
            velocity = self._arrow_velocity(self.center(), target)
            self.weapon.aim = math.atan2(velocity.y, abs(velocity.x))
        else:
            self._aim_focus(target.center())
        if self.weapon.start():
            self.cooldown = self.attack_cooldown

    def _aim_focus(self, point: Vec2) -> None:
        assert isinstance(self.weapon, SkullFocus)
        offset = point - self.center()
        self.weapon.aim = max(-1.2, min(1.2, math.atan2(offset.y, abs(offset.x))))

    def _in_reach(self, target: Stickman, slack: float = 1.0) -> bool:
        center = self.center()
        point = center + Vec2(self.facing * self.attack_range * 0.65, -2.0)
        return (
            target.prey
            and abs(target.center().y - center.y) <= 30.0
            and target.hits(point, margin=self.attack_range * 0.55 * slack)
        )

    def _arrow_velocity(self, origin: Vec2, target: Stickman) -> Vec2:
        return lob_velocity(
            origin,
            target.center(),
            target.velocity,
            (),
            self.world.floor_y,
            ARROW_GRAVITY,
            pace=ARCHER_ARROW_PACE,
        )

    def _resolve_attack(self) -> None:
        if self.role is GraveknightRole.ARCHER:
            self._release_arrow()
        elif self.role is GraveknightRole.MAGE:
            self._release_harming_bolt()
        else:
            self._land_melee_blow()

    def _release_arrow(self) -> None:
        assert isinstance(self.weapon, Bow)
        if not self.weapon.take_release():
            return
        target = self._shot_target
        point = target.center() if target is not None and target.prey else self._shot_point
        transforms = self.transforms()
        nock, _ = self.weapon.nock(transforms, self.facing)
        moving = target.velocity if target is not None and target.prey else Vec2(0.0, 0.0)
        velocity = lob_velocity(
            nock,
            point,
            moving,
            (),
            self.world.floor_y,
            ARROW_GRAVITY,
            pace=ARCHER_ARROW_PACE,
        )
        self.world.spells.shoot(nock, velocity, hostile=True, owner=self)

    def _release_harming_bolt(self) -> None:
        assert isinstance(self.weapon, SkullFocus)
        if not self.weapon.take_release():
            return
        target = self._shot_target
        point = target.center() if target is not None and target.prey else self._shot_point
        transforms = self.transforms()
        self.world.spells.cast_missile(
            self.weapon.tip(transforms, self.facing),
            target,
            point,
            hostile=True,
            owner=self,
            kind=self.weapon.missile_kind,
        )

    def _land_melee_blow(self) -> None:
        hit_time = self.weapon.hit_time
        if (
            self._melee_struck
            or hit_time is None
            or self.weapon.time is None
            or self.weapon.time < hit_time
        ):
            return
        self._melee_struck = True
        target = self.target
        if target is None or not self._in_reach(target, slack=1.35):
            return
        point = self._blade_point(target.center())
        push = Vec2(self.facing * self.attack_push, -self.attack_push * 0.4)
        killed = target.hurt_from(
            self,
            self.attack_damage,
            point,
            push,
            "graveknight",
            "Cut down by the Graveknights!",
        )
        self._ignite_kill(target, killed)

    def _blade_point(self, toward: Vec2) -> Vec2:
        side = 1.0 if toward.x >= self.center().x else -1.0
        return self.center() + Vec2(side * self.attack_range * 0.75, -2.0)

    def arrow_hit(self, target: Stickman, point: Vec2, push: Vec2) -> bool:
        """Resolve this knight's arrow or harming bolt after its shared flight sim hits."""
        if not target.prey:
            return False
        death = (
            "Withered by the Graveknight mage!"
            if self.role is GraveknightRole.MAGE
            else "Shot down by the Graveknights!"
        )
        killed = target.hurt_from(
            self,
            self.attack_damage,
            point,
            push,
            "graveknight",
            death,
        )
        self._ignite_kill(target, killed)
        return killed

    def _ignite_kill(self, target: Stickman, killed: bool) -> None:
        """Legendary weapons leave already-fallen victims burning (after the kill resolves)."""
        if killed and getattr(self, "legendary", False) and target.burn is None:
            target.burn = Burn()
            target.down_time = 0.0

    def on_killed_by(self, attacker: object) -> None:
        """Claim a host first, then ash the rest — possession must not be cancelled."""
        claimed = self.pack.possess(self, attacker)
        if getattr(self, "legendary", False):
            # Skip whoever the spirit claimed, and never incinerate a hero killer —
            # their kill redirects possession onto a bystander when one is available.
            exclude = None
            if claimed is not None or (
                isinstance(attacker, Stickman) and attacker.is_hero
            ):
                exclude = attacker
            self._funeral_pyre(exclude=exclude)

    def _funeral_pyre(self, exclude: object | None = None) -> None:
        """Burst into ash and fire around the fallen knight.

        The killer who triggered possession is skipped so the spirit claim still resolves.
        Bystanders are ignited (their fire death), not double-killed by a separate lethal hit.
        """
        center = self.center()
        self.world.debris.burst(
            center, Vec2(0.0, -1.0), 16, 260.0, spread=2.4, chunks=4, puffs=10, scale=1.2
        )
        self.world.spells.sparkle(center, "fire", 24, 220.0)
        for stickman in list(self.world.stickmen):
            if stickman is exclude or not stickman.prey:
                continue
            if stickman.center().distance_to(center) > FUNERAL_PYRE_RADIUS:
                continue
            away = (stickman.center() - center).normalized()
            stickman.hurt_from(
                self,
                FUNERAL_PYRE_DAMAGE,
                stickman.center(),
                away * 240.0 + Vec2(0.0, -140.0),
                "graveknight",
                "Consumed by the Graveknights' funeral pyre!",
                False,
            )
            if stickman.animated:
                stickman.ignite()
