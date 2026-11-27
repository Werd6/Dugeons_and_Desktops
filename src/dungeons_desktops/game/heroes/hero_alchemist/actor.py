"""A masked alchemist hero with a pressurized reagent rig."""

from dungeons_desktops.core.geometry import Vec2, clamp
from dungeons_desktops.game.actors.base import surface_below
from dungeons_desktops.game.adventurers.actor import Stickman
from dungeons_desktops.game.heroes.hero_alchemist.beast import (
    MUTAGEN_COOLDOWN,
    NOTICE_RANGE,
    MutagenBeast,
)
from dungeons_desktops.game.heroes.hero_alchemist.poison import (
    POISON_COOLDOWN,
    POISON_RADIUS,
    VENT_RELEASE,
    VENT_TIME,
    PoisonCloud,
)
from dungeons_desktops.game.heroes.hero_alchemist.servant import (
    CAST_RELEASE,
    CAST_TIME,
    SUMMON_COOLDOWN,
    SUMMON_RANGE,
    TOSS_DISTANCE,
    AlchemicalOoze,
    OozeToss,
)
from dungeons_desktops.game.unlocks import HERO_NAMES
from dungeons_desktops.game.world.api import World
from dungeons_desktops.navigation.planner import Anchor
from dungeons_desktops.navigation.terrain import TerrainChange
from dungeons_desktops.rig.locomotion import LocomotionInput, PoseMode


class HeroAlchemist(Stickman):
    display_name = HERO_NAMES["hero_alchemist"]

    def __init__(self, world: World, anchor: Anchor, wander: bool = False) -> None:
        self.beast: MutagenBeast | None = None
        self.mutagen_cooldown = 0.0
        self.poison_clouds: list[PoisonCloud] = []
        self.poison_cooldown = 0.0
        self.vent_time: float | None = None
        self.vent_released = False
        self.ooze_servant: AlchemicalOoze | None = None
        self.ooze_toss: OozeToss | None = None
        self.ooze_cooldown = 0.0
        self.ooze_cast_time: float | None = None
        self.ooze_released = False
        super().__init__(world, anchor, "hero_alchemist", wander)

    def update(self, dt: float) -> None:
        self.mutagen_cooldown = max(0.0, self.mutagen_cooldown - dt)
        self.poison_cooldown = max(0.0, self.poison_cooldown - dt)
        self.ooze_cooldown = max(0.0, self.ooze_cooldown - dt)
        self._update_ooze_toss(dt)
        if self.ooze_servant is not None and self.ooze_servant not in self.world.stickmen:
            self.ooze_servant = None
        for cloud in self.poison_clouds:
            cloud.update(dt)
        self.poison_clouds[:] = [cloud for cloud in self.poison_clouds if not cloud.expired]
        if self.ooze_cast_time is not None:
            if not self._vent_allowed(require_idle=False):
                self.ooze_cast_time = None
            else:
                self._update_ooze_cast(dt)
                return
        if self.vent_time is not None:
            if not self._vent_allowed(require_idle=False):
                self.vent_time = None
            else:
                self._update_vent(dt)
                return
        if self.beast is not None:
            if (
                not self.animated
                or self.thrall
                or self.lure is not None
                or self.reeled is not None
                or self.engulfed_by is not None
                or self.swallowed
            ):
                self._end_beastform()
            else:
                self._update_beastform(dt)
                return
        if self._begin_ooze_cast():
            self._update_ooze_cast(dt)
            return
        if self._begin_poison_vent():
            self._update_vent(dt)
            return
        if self._can_start_beastform():
            self._start_beastform()
            self._update_beastform(dt)
            return
        super().update(dt)

    def attack(self) -> None:
        if self.ooze_cast_time is not None or self.vent_time is not None or self.beast is not None:
            return
        if self._begin_ooze_cast():
            return
        if self._begin_poison_vent():
            return
        super().attack()

    def _vent_allowed(self, require_idle: bool = True) -> bool:
        return (
            self.beast is None
            and self.animated
            and self.stun <= 0.0
            and not self.thrall
            and self.lure is None
            and self.reeled is None
            and self.engulfed_by is None
            and not self.swallowed
            and self.dragging_limb is None
            and self.locomotion.mode is PoseMode.WALK
            and not self.follower.in_transition
            and (not require_idle or self.weapon is None or not self.weapon.busy)
        )

    def _begin_poison_vent(self) -> bool:
        if (
            self.vent_time is not None
            or self.ooze_cast_time is not None
            or self.poison_cooldown > 0.0
            or not self._vent_allowed()
            or self.world.nearest_monster(self.center(), POISON_RADIUS) is None
        ):
            return False
        self.goal = None
        self.halt()
        if self.weapon is not None:
            self.weapon.cancel()
        self.vent_time = 0.0
        self.vent_released = False
        self.poison_cooldown = POISON_COOLDOWN
        return True

    def _begin_ooze_cast(self) -> bool:
        active = self.ooze_servant is not None and self.ooze_servant in self.world.stickmen
        if (
            active
            or self.ooze_cast_time is not None
            or self.ooze_toss is not None
            or self.vent_time is not None
            or self.ooze_cooldown > 0.0
            or not self._vent_allowed()
            or self.world.nearest_monster(self.center(), SUMMON_RANGE) is None
        ):
            return False
        self.goal = None
        self.halt()
        if self.weapon is not None:
            self.weapon.cancel()
        self.ooze_cast_time = 0.0
        self.ooze_released = False
        self.ooze_cooldown = SUMMON_COOLDOWN
        return True

    def _update_ooze_cast(self, dt: float) -> None:
        assert self.ooze_cast_time is not None
        self._update_special_timers(dt)
        previous = self.ooze_cast_time
        self.ooze_cast_time += dt
        if not self.ooze_released and previous < CAST_RELEASE <= self.ooze_cast_time:
            self.ooze_released = True
            here = self.follower.current_anchor()
            surface = here.surface
            margin = 18.0
            coord = clamp(
                surface.coord(here.point) + self.facing * TOSS_DISTANCE,
                surface.low + margin,
                surface.high - margin,
            )
            self.ooze_toss = OozeToss(self.center(), surface.point_at(coord), self.facing)
        self.halt()
        self.locomotion.update(dt, self.follower.command())
        self.ragdoll.facing = self.locomotion.facing
        self.ragdoll.drive(self.locomotion.pose, dt)
        self._track_velocity(dt)
        if self.ooze_cast_time >= CAST_TIME:
            self.ooze_cast_time = None

    def _update_ooze_toss(self, dt: float) -> None:
        toss = self.ooze_toss
        if toss is None or not toss.update(dt):
            return
        anchor = self.planner.anchor_near(toss.end, walk_only=True)
        if anchor is None:
            anchor = self.follower.current_anchor()
        servant = AlchemicalOoze(self, anchor)
        self.world.stickmen.append(servant)
        self.ooze_servant = servant
        self.ooze_toss = None

    def _update_vent(self, dt: float) -> None:
        assert self.vent_time is not None
        self._update_special_timers(dt)
        previous = self.vent_time
        self.vent_time += dt
        if not self.vent_released and previous < VENT_RELEASE <= self.vent_time:
            self.vent_released = True
            self.poison_clouds.append(PoisonCloud(self, self.center()))
        self.halt()
        self.locomotion.update(dt, self.follower.command())
        self.ragdoll.facing = self.locomotion.facing
        self.ragdoll.drive(self.locomotion.pose, dt)
        self._track_velocity(dt)
        if self.vent_time >= VENT_TIME:
            self.vent_time = None

    def _update_special_timers(self, dt: float) -> None:
        self.stun = max(0.0, self.stun - dt)
        self.blind = max(0.0, self.blind - dt)
        self.faerie = max(0.0, self.faerie - dt)
        self.cooldown -= dt
        for source in self._grace:
            self._grace[source] -= dt

    def _can_start_beastform(self) -> bool:
        return (
            self.animated
            and self.mutagen_cooldown <= 0.0
            and self.stun <= 0.0
            and not self.thrall
            and self.lure is None
            and self.reeled is None
            and self.engulfed_by is None
            and not self.swallowed
            and self.dragging_limb is None
            and self.locomotion.mode is PoseMode.WALK
            and not self.follower.in_transition
            and (self.weapon is None or not self.weapon.busy)
            and self.world.nearest_monster(self.center(), NOTICE_RANGE) is not None
        )

    def _start_beastform(self) -> None:
        self.goal = None
        self.halt()
        if self.weapon is not None:
            self.weapon.cancel()
        self.beast = MutagenBeast(self)
        self._sync_beast_pose()

    def _update_beastform(self, dt: float) -> None:
        beast = self.beast
        assert beast is not None
        paused = self.stun > 0.0
        self._update_special_timers(dt)
        beast.update(dt, paused=paused)
        self._sync_beast_pose()
        if beast.finished:
            self._end_beastform()

    def _sync_beast_pose(self) -> None:
        beast = self.beast
        assert beast is not None
        self.locomotion.teleport(
            LocomotionInput(
                PoseMode.AIR if beast.flying else PoseMode.WALK,
                beast.contact(),
                beast.facing,
                "mutagen_beast",
            )
        )
        self.follower.facing = beast.facing
        self.ragdoll.facing = beast.facing
        self.ragdoll.engage(self.locomotion.pose, self.world.step)
        self.velocity = beast.velocity
        self._last_contact = beast.contact()

    def _end_beastform(self) -> None:
        beast = self.beast
        if beast is None:
            return
        contact = beast.contact()
        facing = beast.facing
        self.beast = None
        self.mutagen_cooldown = MUTAGEN_COOLDOWN
        self.goal = None
        self.needs_replan = False
        self._pending_changes.clear()
        anchor = surface_below(self.planner, contact - Vec2(0.0, 2.0))
        self.follower.reset(anchor)
        self.follower.facing = facing
        if contact.distance_to(anchor.point) > 2.0:
            self.fall_in(contact)
        else:
            self.locomotion.teleport(self.follower.command())
            self.ragdoll.engage(self.locomotion.pose, self.world.step)
        self._last_contact = self.contact()

    @property
    def facing(self) -> int:
        return self.beast.facing if self.beast is not None else super().facing

    def center(self) -> Vec2:
        return self.beast.body if self.beast is not None else super().center()

    def contact(self) -> Vec2:
        return self.beast.contact() if self.beast is not None else super().contact()

    def hits(self, point: Vec2, margin: float = 0.0) -> bool:
        if self.beast is not None:
            return self.beast.hits(point, margin)
        return super().hits(point, margin)

    @property
    def limbs_draggable(self) -> bool:
        return self.beast is None and super().limbs_draggable

    @property
    def movement_paused(self) -> bool:
        return (
            self.beast is not None
            or self.vent_time is not None
            or self.ooze_cast_time is not None
            or super().movement_paused
        )

    def terrain_changed(self, change: TerrainChange) -> None:
        if self.beast is not None:
            self.beast.terrain_changed(change)
            self._sync_beast_pose()
        else:
            super().terrain_changed(change)

    def go_ragdoll(self) -> None:
        self.vent_time = None
        self.ooze_cast_time = None
        self._end_beastform()
        super().go_ragdoll()
