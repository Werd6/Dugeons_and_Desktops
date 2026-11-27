"""A brief, hittable decoy and terrain-aware retreat for the Slayer."""

from dataclasses import replace

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.adventurers.actor import Stickman
from dungeons_desktops.navigation.planner import Anchor
from dungeons_desktops.rig.equipment import Stroke
from dungeons_desktops.rig.skeleton import Pose

HEALTH_THRESHOLDS = (0.75, 0.5, 0.25)
BLINK_DISTANCE = 160.0
ESCAPE_RECOVERY = 0.75
CLONE_LIFETIME = 4.0


def retreat_anchor(hero: Stickman) -> Anchor:
    """Prefer a clear standing spot behind him, even across window edges."""
    origin = hero.contact()
    desired = origin - Vec2(hero.facing * BLINK_DISTANCE, 0)
    layout = hero.layout
    height = (
        layout.leg_length + layout.skeleton.bone(layout.torso).length
        + layout.skeleton.bone(layout.head).length + layout.head_radius
    )
    margin = layout.head_radius + 2
    choices = []
    for surface in hero.planner.surfaces:
        if not surface.walkable or surface.length < margin * 2:
            continue
        for offset in (0, -40, 40, -80, 80):
            x = max(surface.low + margin, min(surface.high - margin, desired.x + offset))
            point = surface.point_at(x)
            if abs(point.x - origin.x) > BLINK_DISTANCE * 1.5:
                continue
            if point.y < origin.y - BLINK_DISTANCE:
                continue
            if hero.world.ceiling is not None and point.y - height < hero.world.ceiling:
                continue
            if any(
                box.left < point.x + margin and box.right > point.x - margin
                and box.top < point.y - 0.1 and box.bottom > point.y - height
                for box in hero.world.boxes
            ):
                continue
            # A shorter step backward beats blinking through the enemy in front.
            ahead = (point.x - origin.x) * hero.facing >= -1
            score = point.distance_to(desired) + abs(point.y - origin.y) + 1000 * ahead
            choices.append((score, Anchor(surface, point)))
    return min(choices, key=lambda item: item[0])[1] if choices else hero.follower.current_anchor()


class ShadowClone(Stickman):
    """A stationary copy of the departure pose; it has no attacks or hero passives."""

    display_name = "Slayer's Shadow"
    is_shadow_clone = True

    def __init__(self, hero: Stickman) -> None:
        super().__init__(hero.world, hero.follower.current_anchor(), "hero_rogue")
        self.calling = replace(self.calling, hp=1)
        self.age = 0.0
        self.cape_time = hero.cape_time
        self._shadow_pose = hero.pose().copy()
        self._shadow_feet = hero.contact()
        self._shadow_facing = hero.facing
        self._shadow_strokes = [replace(stroke, kind="shadow") for stroke in hero.weapon_strokes()]

    def pose(self) -> Pose:
        return self._shadow_pose

    def contact(self) -> Vec2:
        return self._shadow_feet

    @property
    def facing(self) -> int:
        return self._shadow_facing

    @property
    def prey(self) -> bool:
        return not self.gone

    @property
    def visibility(self) -> float:
        return 0.7 * min(1.0, max(0.0, (CLONE_LIFETIME - self.age) / 0.4))

    def hits(self, point: Vec2, margin: float = 0.0) -> bool:
        return not self.gone and super().hits(point, margin)

    def weapon_strokes(self) -> list[Stroke]:
        return self._shadow_strokes

    def update(self, dt: float) -> None:
        self.age += dt
        self.cape_time += dt
        if self.age + 1e-9 >= CLONE_LIFETIME:
            self.dissolve()

    def attack(self) -> None:
        pass

    def dissolve(self) -> None:
        self.damage = self.max_hp
        self.swallowed = True  # Remove the illusion without a corpse, gore, or kill reward.
        self.go_ragdoll()

    def hurt(self, amount, point, push, source, death, bleed=True, attacker=None) -> bool:
        if self.gone or amount <= 0:
            return False
        self.dissolve()
        return True

    def ignite(self) -> None:
        self.dissolve()

    def succumb(self, breath: str) -> None:
        self.dissolve()

    def enthrall(self) -> None:
        self.dissolve()
