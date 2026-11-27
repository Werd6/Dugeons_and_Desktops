"""A plated squad protector whose third melee hit calls down a healing Smite."""

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.adventurers.actor import MELEE_HEIGHT, MELEE_PUSH, MELEE_SLACK, Stickman
from dungeons_desktops.game.adventurers.combat import ADVENTURER_DAMAGE
from dungeons_desktops.game.heroes.hero_paladin.aura import AURA_RADIUS
from dungeons_desktops.game.heroes.hero_paladin.hammer_throw import HammerThrow
from dungeons_desktops.game.heroes.hero_paladin.model import build_hero_paladin
from dungeons_desktops.game.heroes.hero_paladin.patrol import Patrol
from dungeons_desktops.game.heroes.hero_paladin.smite import HEAL_AMOUNT, SMITE_TIME, Smite
from dungeons_desktops.game.unlocks import HERO_NAMES
from dungeons_desktops.game.world.api import World
from dungeons_desktops.navigation.planner import Anchor, Planner


class HeroPaladin(Stickman):
    display_name = HERO_NAMES["hero_paladin"]
    seek_radius = 760.0

    def __init__(self, world: World, anchor: Anchor, wander: bool = False) -> None:
        anchor = world.hero_paladin_planner.anchor_near(anchor.point)
        super().__init__(world, anchor, "hero_paladin", wander, layout=build_hero_paladin())
        self.melee_hits = 0
        self.smite: Smite | None = None
        self.heal_flash = 0.0
        self.hammer_throw = HammerThrow(self)
        self.patrol = Patrol()

    @property
    def planner(self) -> Planner:
        return self.world.hero_paladin_planner

    @property
    def aura_active(self) -> bool:
        return self.hp > 0 and (self.animated or self.knocked) and not self.thrall and not self.gone

    @property
    def target_priority(self) -> int:
        return 1 if self.aura_active else 0

    def _pick_wander_goal(self) -> None:
        if not self.patrol.advance(self):
            super()._pick_wander_goal()

    def update(self, dt: float) -> None:
        self.heal_flash = max(0.0, self.heal_flash - dt)
        self.hammer_throw.prepare()
        super().update(dt)
        self.hammer_throw.update(dt)
        if not self.animated or self.thrall or self.paralysed:
            self.smite = None
        if self.smite is not None:
            self.smite.update(self, dt)
            if self.smite.age >= SMITE_TIME:
                self.smite = None

    def begin_divine_prayer(self, seconds: float) -> bool:
        joined = super().begin_divine_prayer(seconds)
        if joined:
            self.hammer_throw.cancel()
            self.smite = None
        return joined

    def _strike(self, monster: object | None, point: Vec2) -> None:
        super()._strike(monster, point)
        if not self.thrall and self.melee_hits % 3 == 2:
            self.smite = Smite(monster, point)

    def _update_weapon(self) -> None:
        if self.weapon.throwing or self.weapon.hammer_away:
            return
        super()._update_weapon()

    def in_melee_range(self, point: Vec2 | None, slack: float = 0.0) -> bool:
        center = self.center()
        return (
            point is not None and point.distance_to(center) <= self.calling.reach + slack
            and abs(point.y - center.y) <= MELEE_HEIGHT
        )

    def _land_blow(self) -> None:
        center = self.center()
        target = self.foe
        point = self.world.closest_part(target, center) if target is not None else None
        if not self.in_melee_range(point, MELEE_SLACK):
            found = self.world.nearest_monster(center, self.calling.reach + MELEE_SLACK)
            if found is None or not self.in_melee_range(found[1], MELEE_SLACK):
                return
            target, point = found
        before = target.hp
        self.world.hurt_monster(
            target, ADVENTURER_DAMAGE, point,
            Vec2(self.facing * MELEE_PUSH, -MELEE_PUSH * 0.4), attacker=self,
        )
        if target.hp >= before:
            return
        self.melee_hits += 1
        if self.melee_hits % 3:
            return
        if self.smite is None:
            self.smite = Smite(target, point, age=self.weapon.hit_time)
        self.smite.target, self.smite.point = target, point
        self.smite.confirmed = True
        self.heal_flash = 0.6
        for ally in self.world.stickmen:
            if (
                ally is not self and not ally.thrall and not ally.gone and ally.hp > 0
                and (ally.animated or ally.knocked)
                and ally.center().distance_to(self.center()) <= AURA_RADIUS
            ):
                ally.heal(HEAL_AMOUNT)

    def hurt(
        self, amount: int, point: Vec2, push: Vec2, source: str, death: str,
        bleed: bool = True, attacker: object | None = None,
    ) -> bool:
        before = self.hp
        killed = super().hurt(amount, point, push, source, death, bleed, attacker)
        if killed:
            self.hammer_throw.cancel()
        elif self.hp < before:
            self.hammer_throw.request()
        return killed
