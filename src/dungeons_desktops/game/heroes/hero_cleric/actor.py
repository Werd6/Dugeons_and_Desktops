"""A cleric hero who gathers fallen adventurer souls and resurrects them."""

import math

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.adventurers.actor import HEAL_RADIUS, Stickman
from dungeons_desktops.game.heroes.hero_cleric.judgement import (
    JUDGEMENT_COOLDOWN,
    JUDGEMENT_RANGE,
    PRAYER_TIME,
    DivineJudgement,
)
from dungeons_desktops.game.heroes.hero_cleric.souls import (
    AUTO_CAST_AFTER,
    RESURRECTION_FLASH,
    RESURRECTION_RELEASE,
    Soul,
)
from dungeons_desktops.game.unlocks import HERO_NAMES
from dungeons_desktops.game.world.api import World
from dungeons_desktops.navigation.planner import Anchor
from dungeons_desktops.rig.equipment import Weapon
from dungeons_desktops.rig.skeleton import BoneTransform

HOLY_PULSE_DAMAGE = 2


class HeroCleric(Stickman):
    display_name = HERO_NAMES["hero_cleric"]
    mindflayer_stun_immune = True

    def __init__(self, world: World, anchor: Anchor, wander: bool = False) -> None:
        self.divine_time = 0.0
        self.souls: list[Soul] = []
        self.resurrection_cast = False
        self.resurrection_time = 0.0
        self.resurrection_released = False
        self.resurrection_flash = 0.0
        self.judgement: DivineJudgement | None = None
        self.judgement_cooldown = 0.0
        super().__init__(world, anchor, "hero_cleric", wander)

    def update(self, dt: float) -> None:
        self.divine_time += dt
        self.resurrection_flash = max(0.0, self.resurrection_flash - dt)
        self.judgement_cooldown = max(0.0, self.judgement_cooldown - dt)
        center = self.soul_center()
        for index, soul in enumerate(self.souls):
            soul.update(dt, center, index, len(self.souls))
        if self.resurrection_cast and not self._resurrection_allowed(require_idle=False):
            self._cancel_resurrection()
        if self.judgement is not None and not self._casting_allowed(require_idle=False):
            self._cancel_judgement()
        if (
            self.judgement is None
            and not self.resurrection_cast
            and any(not soul.flying and soul.orbit_age >= AUTO_CAST_AFTER for soul in self.souls)
        ):
            self._begin_resurrection()
        if (
            self.judgement is None and not self.resurrection_cast
            and self.judgement_cooldown <= 0.0
        ):
            self._begin_judgement()
        super().update(dt)
        if self.resurrection_cast:
            self.resurrection_time += dt
            if (
                not self.resurrection_released
                and self.resurrection_time >= RESURRECTION_RELEASE
            ):
                self.resurrection_released = True
                self._resurrect_souls()
            if not self.weapon.busy:
                self.resurrection_cast = False
        if self.judgement is not None:
            judgement = self.judgement
            judgement.update(self, dt)
            if judgement.done:
                self._finish_judgement()

    def soul_center(self):
        transforms = self.transforms()
        torso = transforms[self.layout.torso]
        return torso.start.lerp(torso.end, 0.65)

    def capture_soul(self, variant: str, point) -> Soul:
        soul = Soul(variant, point, len(self.souls) * math.pi * (3 - math.sqrt(5)))
        self.souls.append(soul)
        self.say(f"A fallen {variant}'s soul answers {self.display_name}")
        return soul

    def attack(self) -> None:
        if self.heroes_never_die():
            return
        if self.divine_judgement():
            return
        super().attack()

    def heroes_never_die(self) -> bool:
        """Explicitly resurrect every gathered soul once the cleric can cast."""
        return bool(self.souls) and self._begin_resurrection(manual=True)

    def divine_judgement(self) -> bool:
        """Explicitly begin Divine Judgement if it is ready and a target exists."""
        return self._begin_judgement()

    def _wounded_near(self, center):
        """The Hero Cleric's own pulse can heal allies, but never its caster."""
        return [ally for ally in super()._wounded_near(center) if ally is not self]

    def _release(
        self, weapon: Weapon, transforms: dict[str, BoneTransform], facing: int
    ) -> None:
        super()._release(weapon, transforms, facing)
        if self.thrall:
            return
        center = self.center()
        for monster, point in self.world.monsters_near(center, HEAL_RADIUS):
            if isinstance(monster, Stickman) and monster.thrall:
                monster.release()
                self.world.spells.sparkle(monster.center(), "holy", 12, 90.0)
                continue
            away = (point - center).normalized()
            self.world.hurt_monster(
                monster,
                HOLY_PULSE_DAMAGE,
                point,
                away * 90.0 + Vec2(0.0, -35.0),
                ranged=True,
                attacker=self,
            )

    def _casting_allowed(self, require_idle: bool = True) -> bool:
        return (
            self.animated
            and not self.thrall
            and not self.paralysed
            and self.blind <= 0
            and self.lure is None
            and self.reeled is None
            and self.engulfed_by is None
            and self.dragging_limb is None
            and self._can_act()
            and (not require_idle or not self.weapon.busy)
        )

    def _resurrection_allowed(self, require_idle: bool = True) -> bool:
        return self.judgement is None and self._casting_allowed(require_idle)

    def _begin_resurrection(self, manual: bool = False) -> bool:
        if (
            self.resurrection_cast
            or not self.souls
            or not self._resurrection_allowed()
            or (not manual and any(soul.flying for soul in self.souls))
        ):
            return False
        self.halt()
        self.resurrection_cast = True
        self.resurrection_time = 0.0
        self.resurrection_released = False
        self.weapon.start()
        self.say("Heroes Never Die!")
        return True

    def _begin_judgement(self) -> bool:
        if (
            self.judgement is not None or self.resurrection_cast
            or self.judgement_cooldown > 0.0 or not self._casting_allowed()
        ):
            return False
        found = self.world.nearest_monster(self.center(), JUDGEMENT_RANGE)
        if found is None:
            return False
        target, point = found
        prayers = [
            ally
            for ally in self.world.stickmen
            if ally is not self
            and ally.variant in ("cleric", "paladin", "hero_paladin")
            and ally.begin_divine_prayer(PRAYER_TIME)
        ]
        self.halt()
        self.judgement = DivineJudgement(target, point, prayers)
        self.judgement_cooldown = JUDGEMENT_COOLDOWN
        self.weapon.begin_channel()
        self.say("Divine Judgement!")
        return True

    def _finish_judgement(self) -> None:
        self.judgement = None
        self.weapon.end_channel()

    def _cancel_judgement(self) -> None:
        self._finish_judgement()

    def _resurrect_souls(self) -> None:
        souls, self.souls = self.souls, []
        point = self.contact()
        for soul in souls:
            roll = self.world.random.random()
            if roll < 0.25:
                variant = "cleric"
            elif roll < 0.5:
                variant = "paladin"
            else:
                variant = soul.original_variant
            self.world.add_stickman(point, variant, wander=True)
        self.resurrection_flash = RESURRECTION_FLASH

    def _cancel_resurrection(self) -> None:
        self.resurrection_cast = False
        self.resurrection_time = 0.0
        self.resurrection_released = False
        if self.weapon.busy:
            self.weapon.cancel()
