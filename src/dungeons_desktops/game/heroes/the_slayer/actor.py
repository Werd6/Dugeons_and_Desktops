"""The Slayer slips into an untouchable shadow between attacks."""

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.actors.base import surface_below
from dungeons_desktops.game.adventurers.actor import Stickman
from dungeons_desktops.game.heroes.the_slayer.assassinate import Assassinate
from dungeons_desktops.game.heroes.the_slayer.shadow import (
    ESCAPE_RECOVERY,
    HEALTH_THRESHOLDS,
    ShadowClone,
    retreat_anchor,
)
from dungeons_desktops.game.world.api import World
from dungeons_desktops.navigation.planner import Anchor
from dungeons_desktops.navigation.terrain import TerrainChange
from dungeons_desktops.rig.locomotion import PoseMode, air_pose
from dungeons_desktops.rig.skeleton import forward_kinematics

STEALTH_DELAY = 3.0


class TheSlayer(Stickman):
    display_name = "The Slayer"

    def __init__(self, world: World, anchor: Anchor, wander: bool = False) -> None:
        self.cape_time = 0.0
        self.since_attack = 0.0
        self.escape_recovery = 0.0
        self.escape_thresholds = set(HEALTH_THRESHOLDS)
        super().__init__(world, anchor, "hero_rogue", wander)
        self.weapon.on_attack = self.reveal
        self.assassinate = Assassinate(self)

    @property
    def stealthed(self) -> bool:
        return self.animated and self.since_attack >= STEALTH_DELAY - 1e-9

    @property
    def invulnerable(self) -> bool:
        ability = getattr(self, "assassinate", None)
        return self.stealthed or (
            self.animated and ability is not None and ability.spinning
        )

    @property
    def prey(self) -> bool:
        return super().prey and not self.invulnerable

    def hits(self, point: Vec2, margin: float = 0.0) -> bool:
        return not self.invulnerable and super().hits(point, margin)

    @property
    def visibility(self) -> float:
        return 0.32 if self.stealthed else 1.0

    def reveal(self) -> None:
        """An actual attack breaks stealth, even if it misses."""
        self.since_attack = 0.0

    def on_kill(self, victim: object) -> None:
        """Every credited kill refreshes his attacks and immediately leaves a decoy."""
        self.cooldown = 0.0
        self.assassinate.cooldown = 0.0
        if self.animated:
            self._shadow_escape()

    def update(self, dt: float) -> None:
        self.escape_recovery = max(0.0, self.escape_recovery - dt)
        if self.animated:
            self.cape_time += dt
            self.since_attack = min(STEALTH_DELAY, self.since_attack + dt)
        self.assassinate.update(dt)
        if self.assassinate.spinning:
            self.faerie = max(0.0, self.faerie - dt)
            self.cooldown -= dt
            for source in self._grace:
                self._grace[source] -= dt
            return
        super().update(dt)

    def attack(self) -> None:
        if self.escape_recovery > 0:
            return
        if not self.assassinate.active and not self.assassinate.start():
            super().attack()

    def _can_act(self) -> bool:
        return self.escape_recovery <= 0 and super()._can_act()

    def _engage(self) -> bool:
        if self.assassinate.active:
            return False
        return self.assassinate.start() or super()._engage()

    def _update_weapon(self) -> None:
        if not self.assassinate.active:
            super()._update_weapon()

    @property
    def movement_paused(self) -> bool:
        return self.escape_recovery > 0 or self.assassinate.active or super().movement_paused

    def _seek(self, dt: float) -> bool:
        return self.escape_recovery > 0 or self.assassinate.active or super()._seek(dt)

    def contact(self) -> Vec2:
        ability = getattr(self, "assassinate", None)
        if ability is not None and ability.spinning:
            return ability.point + Vec2(0, self.layout.leg_length * 0.8)
        return super().contact()

    def _pose_assassinate(self, dt: float) -> None:
        point = self.assassinate.point
        self.follower.reset(surface_below(self.planner, self.contact()))
        self.goal = None
        self.needs_replan = False
        self._pending_changes.clear()
        pose = air_pose(self.layout, self.contact(), rising=False)
        pose.root += point - forward_kinematics(self.layout.skeleton, pose)[self.layout.torso].start
        self.locomotion.mode = PoseMode.AIR
        self.locomotion.pose = pose
        self.ragdoll.drive(pose, dt, snap=True)
        self._last_contact = self.contact()
        self.velocity = Vec2(0, 0)

    def _land_assassinate(self, point: Vec2) -> None:
        feet = point + Vec2(0, self.layout.leg_length * 0.8)
        landing = surface_below(self.planner, feet)
        self.follower.reset(landing)
        self.goal = None
        self.needs_replan = False
        self._pending_changes.clear()
        if feet.distance_to(landing.point) > 4:
            self.fall_in(feet)
        else:
            self.locomotion.teleport(self.follower.command())
            self.ragdoll.engage(self.locomotion.pose, self.world.step)
            self._last_contact = landing.point
        if self.assassinate.cooldown > 0:
            self.cooldown = max(self.cooldown, 0.3)

    def terrain_changed(self, change: TerrainChange) -> None:
        if self.assassinate.spinning:
            self.follower.reset(surface_below(self.planner, self.contact()))
            return
        super().terrain_changed(change)

    def hurt(
        self, amount: int, point: Vec2, push: Vec2, source: str, death: str,
        bleed: bool = True, attacker: object | None = None,
    ) -> bool:
        # Also reject attacks already in flight and area damage, regardless of
        # whether their source rechecks target eligibility before landing.
        if self.invulnerable:
            return False
        before = self.hp
        killed = super().hurt(amount, point, push, source, death, bleed, attacker)
        crossed = {
            threshold for threshold in self.escape_thresholds
            if self.hp <= self.max_hp * threshold < before
        }
        if not killed and self.animated and crossed:
            # A heavy hit crossing several thresholds gets one escape and consumes them all.
            self.escape_thresholds.difference_update(crossed)
            self._shadow_escape()
        return killed

    def _shadow_escape(self) -> None:
        clone = ShadowClone(self)
        self.world.stickmen.append(clone)
        landing = retreat_anchor(self)
        facing = self.facing
        self.assassinate.finish()
        self.foe = self.quarry = self.goal = None
        self._resume_route = False
        self._blow = None
        self.stun = self.blind = 0.0
        self.free_from_lure()
        self.free_from_reel(drop=False)
        self.engulfed_by = None
        self.release_limb()
        self.follower.reset(landing)
        self.follower.facing = facing
        self.needs_replan = False
        self._pending_changes.clear()
        self.locomotion.teleport(self.follower.command())
        self.ragdoll.engage(self.locomotion.pose, self.world.step)
        self._last_contact = landing.point
        self.velocity = Vec2(0, 0)
        self.since_attack = STEALTH_DELAY
        self.escape_recovery = ESCAPE_RECOVERY

    def ignite(self) -> None:
        if not self.invulnerable:
            super().ignite()

    def succumb(self, breath: str) -> None:
        if not self.invulnerable:
            super().succumb(breath)

    def paralyze(self, seconds: float) -> None:
        if not self.invulnerable:
            super().paralyze(seconds)

    def knock_down(self, center: Vec2, speed: float, down: float, stunned: float) -> None:
        if not self.invulnerable:
            super().knock_down(center, speed, down, stunned)
