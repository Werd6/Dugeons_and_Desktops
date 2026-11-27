"""Distance bands, boulders, and ground impacts for The Mighty."""

from dataclasses import dataclass
from enum import Enum

from dungeons_desktops.core.geometry import Vec2


class Attack(Enum):
    MELEE = "melee"
    SWING = "mighty_swing"
    LEAP = "leap_smash"
    BOULDER = "boulder_throw"


MELEE_RANGE = 50.0
LEAP_RANGE = 220.0
BOULDER_RANGE = 520.0
BOULDER_COOLDOWN = 6.0
MELEE_DAMAGE = 2
SWING_DAMAGE = 12
LEAP_DAMAGE = 8
BOULDER_DAMAGE = 6
SWING_RADIUS = 65.0
LEAP_RADIUS = 70.0
BOULDER_RADIUS = 28.0
RAGE_TIME = 10.0
RAGE_SIZE = 2.0
RAGE_DAMAGE = 2
LEAP_WINDUP = 0.25
LEAP_RECOVER = 0.4
BOULDER_GRAVITY = 480.0
IMPACT_TIME = 0.65


@dataclass
class Boulder:
    position: Vec2
    velocity: Vec2
    duration: float
    damage: int
    size: float
    age: float = 0.0


@dataclass
class Impact:
    center: Vec2
    radius: float
    ground: bool
    age: float = 0.0


class MightyCombat:
    def __init__(self, hero) -> None:
        self.hero = hero
        self.boulders: list[Boulder] = []
        self.impacts: list[Impact] = []

    def throw(self, origin: Vec2, target: Vec2, velocity: Vec2) -> None:
        duration = max(0.45, min(1.35, origin.distance_to(target) / 380.0))
        aim = target + velocity * min(duration, 0.5)
        offset = aim - origin
        self.boulders.append(
            Boulder(
                origin,
                Vec2(offset.x / duration, offset.y / duration - 0.5 * BOULDER_GRAVITY * duration),
                duration,
                BOULDER_DAMAGE + self.hero.damage_bonus,
                self.hero.size_multiplier,
            )
        )

    def impact(self, center: Vec2, radius: float, damage: int, ground: bool = True) -> None:
        self.impacts.append(Impact(center, radius, ground))
        for monster, part in self.hero.world.monsters_near(center, radius):
            # Ground shocks stay on the impacted floor/window, not the one below it.
            if ground and abs(part.y - center.y) > 40.0 * self.hero.size_multiplier:
                continue
            away = (part - center).normalized()
            self.hero.world.hurt_monster(
                monster,
                damage,
                part,
                away * 260.0 + Vec2(0, -180),
                ranged=not ground,
                attacker=self.hero,
            )

    def update(self, dt: float) -> None:
        for impact in self.impacts:
            impact.age += dt
        self.impacts = [impact for impact in self.impacts if impact.age < IMPACT_TIME]
        flying = []
        for rock in self.boulders:
            duration = min(dt, max(0.0, rock.duration - rock.age))
            count = max(
                1, int((rock.velocity.length() + BOULDER_GRAVITY * duration) * duration / 3.0) + 1
            )
            step = duration / count
            for _ in range(count):
                rock.age += step
                rock.position += rock.velocity * step + Vec2(0, 0.5 * BOULDER_GRAVITY * step**2)
                rock.velocity += Vec2(0, BOULDER_GRAVITY * step)
                if (
                    self.hero.world.monsters_near(rock.position, 7.0 * rock.size)
                    or rock.position.y >= self.hero.world.floor_y
                    or rock.age >= rock.duration - 1e-9
                ):
                    point = Vec2(rock.position.x, min(rock.position.y, self.hero.world.floor_y))
                    self.impact(point, BOULDER_RADIUS * rock.size, rock.damage, ground=False)
                    break
            else:
                flying.append(rock)
        self.boulders = flying
