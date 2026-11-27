"""Green alchemical vials for the Hero Alchemist."""

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.rig.equipment import Bombs, Stroke


class GreenVials(Bombs):
    name = "green vials"
    size = 1.5

    def strokes(self, transforms, facing: int, slung: bool = False) -> list[Stroke]:
        hip = transforms[self.layout.torso].start
        s = self.unit
        strokes = [
            *self._bomb(hip + Vec2(facing * 2.25 * s, -1.2 * s), 0.65),
            *self._bomb(hip + Vec2(-facing * 1.9 * s, -0.75 * s), 0.65),
        ]
        thrown = self.time is not None and (
            self.release_time <= self.time < self.release_time + self.restock
        )
        if self.held and not slung and not thrown:
            hand = self.hand(transforms) + Vec2(facing * 1.1 * s, -1.0 * s)
            strokes += self._bomb(hand)
        return strokes

    def _bomb(self, center: Vec2, scale: float = 1.0) -> list[Stroke]:
        s = self.unit * scale
        neck = center + Vec2(0.0, -1.65 * s)
        bottle = tuple(
            center + offset * s
            for offset in (
                Vec2(-0.48, -1.65),
                Vec2(-0.55, -0.9),
                Vec2(-1.05, -0.35),
                Vec2(-0.92, 1.1),
                Vec2(0.0, 1.45),
                Vec2(0.92, 1.1),
                Vec2(1.05, -0.35),
                Vec2(0.55, -0.9),
                Vec2(0.48, -1.65),
            )
        )
        return [
            Stroke(center, center, 0.45 * s, "hero_vial", bottle),
            Stroke(neck, neck + Vec2(0.0, -0.75 * s), 0.95 * s, "glass"),
            Stroke(
                neck + Vec2(0.0, -0.75 * s),
                neck + Vec2(0.0, -1.25 * s),
                1.15 * s,
                "cork",
            ),
        ]
