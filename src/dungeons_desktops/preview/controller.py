"""Qt-free state for the preview: stickmen and goblins on draggable boxes.

The boxes stand in for desktop windows: tops are walkable, sides climbable.
One stickman is selected; clicking empty space sends it there and the keys act
on it. Goblins hunt the stickmen as a pack and can be picked up and dropped
somewhere else. Dragging a box rebuilds the terrain and every actor re-anchors.
"""

from __future__ import annotations

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.game.actors.base import Actor
from dungeons_desktops.game.adventurers import model as stick_figure
from dungeons_desktops.game.defenders.elementals.actor import KINDS
from dungeons_desktops.game.defenders.goblins.actor import Goblin
from dungeons_desktops.game.effects.breath import BREATHS, VARIANTS
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.navigation.planner import RouteStep
from dungeons_desktops.navigation.terrain import TerrainChange

GRAB_RADIUS = 6.0
RAGDOLL_KICK_REACH = 12.0


def default_boxes(width: float, floor_y: float) -> list[Rect]:
    """A starter layout where every surface can reach every other: a box on the floor,
    a floor box overlapped by a floating one (climb onto the lower, then up the upper),
    and a low floating box near the right edge."""
    middle = width * 0.40
    return [
        Rect(width * 0.12, floor_y - 170.0, 150.0, 170.0),
        Rect(middle, floor_y - 160.0, 210.0, 160.0),
        Rect(middle + 120.0, floor_y - 320.0, 260.0, 255.0),
        Rect(width - 190.0, floor_y - 180.0, 130.0, 140.0),
    ]


class RigPreviewController(SimWorld):
    def __init__(self, width: float, height: float, ground_margin: float = 30.0) -> None:
        self.ground_margin = ground_margin
        floor_y = height - ground_margin
        self.status = "Click empty space to send the figure there"
        self.selected = None
        super().__init__(default_boxes(width, floor_y), floor_y, width)
        self.selected = self.add_stickman(Vec2(width * 0.05, self.floor_y))
        self.status = "Click empty space to send the figure there"
        self._dragging_box: tuple[int, Vec2] | None = None
        self._dragging_goblin: Goblin | None = None

    def say(self, actor: Actor, message: str) -> None:
        if actor is self.selected:
            self.status = message

    # ----- population ----------------------------------------------------------

    def populate(self) -> None:
        """The demo scene: a goblin on the first box and a party of adventurers wandering."""
        first = self.boxes[0]
        self.add_goblin(Vec2(first.x + first.width / 2, first.top - 5.0))
        for i, variant in enumerate(("paladin", "wizard", "ranger", "cleric")):
            self.add_stickman(Vec2(self.width * (0.7 + 0.08 * i), self.floor_y), variant, True)

    def spawn_stickman(self) -> None:
        variant = self.random.choice(list(stick_figure.CLASSES))
        self.add_stickman(variant=variant, wander=True)
        self.status = f"Added a wandering {variant}"

    def spawn_dio(self) -> None:
        hero = self.add_stickman(variant="hero_fighter", wander=True)
        self.selected = hero
        self.status = "Dio arrives with a divine trident and shield"

    def spawn_hero_fighter(self) -> None:
        """Compatibility name retained for older preview callers."""
        self.spawn_dio()

    def next_class(self) -> None:
        classes = list(stick_figure.CLASSES)
        current = self.variant
        index = classes.index(current) + 1 if current in classes else 0
        self.set_variant(classes[index % len(classes)])

    def spawn_goblin(self) -> None:
        self.add_goblin()
        self.status = f"Added a {self.goblins[-1].kind} goblin to the pack"

    def spawn_worm(self) -> None:
        self.add_worm()
        self.status = "Added a burrow worm - it tunnels through boxes and hunts stickmen"

    def spawn_dragon(self) -> None:
        dragon = self.add_dragon()
        breath = BREATHS[dragon.variant]
        self.status = (
            f"A {dragon.variant} dragon flies in - it strafes with {breath} breath, lands, "
            "and mauls whoever is near"
        )

    def next_dragon_variant(self) -> None:
        """Recolour every dragon to the next colour; with none about, one flies in."""
        dragons = [d for d in self.dragons if not d.dead]
        if not dragons:
            self.add_dragon(variant=VARIANTS[0])
            self.status = "A red dragon flies in (V again for the next colour)"
            return
        index = VARIANTS.index(dragons[0].variant) if dragons[0].variant in VARIANTS else -1
        variant = VARIANTS[(index + 1) % len(VARIANTS)]
        for dragon in dragons:
            dragon.variant = variant
        self.status = f"The dragon is now {variant}: {BREATHS[variant]} breath"

    def spawn_mindflayer(self) -> None:
        self.add_mindflayer()
        self.status = "A mind flayer floats in - it blasts, stuns and enthralls adventurers"

    def spawn_displacer(self) -> None:
        self.add_displacer()
        self.status = (
            "A displacer beast prowls in - it climbs walls and undersides, stalks and pounces"
        )

    def spawn_minotaur(self) -> None:
        self.add_minotaur()
        self.status = (
            "A minotaur stomps in - it charges and tramples, smashes and stomps, "
            "hurls adventurers, and enrages when shot"
        )

    def spawn_ooze(self) -> None:
        self.add_ooze()
        self.status = (
            "An ooze hunts over floors, walls, and ceilings, then engulfs adventurers"
        )

    def spawn_hydra(self) -> None:
        self.add_hydra()
        self.status = (
            "A hydra bursts out of the ground - five heads spit acid, and it dives "
            "and breaks out again next to its prey (even out of a window's side)"
        )

    def spawn_drake(self) -> None:
        drake = self.add_drake()
        self.status = (
            f"A kobold archer rides in on a {drake.variant} drake - it circles and shoots, "
            "spits breath bolts, then dives in to bite"
        )

    def spawn_drow(self) -> None:
        self.add_lizard()
        self.status = (
            "A drow rides in on a wall-crawling lizard - it perches on walls and ceilings to "
            "shoot its crossbow, globes of darkness blind adventurers in faerie fire, and once "
            "the lizard falls the drow fights on with twin scimitars"
        )

    def spawn_chimera(self) -> None:
        self.add_chimera()
        self.status = (
            "A chimera prowls in - the lion stalks and pounces, the goat breathes fire, "
            "the serpent strikes"
        )

    def spawn_elemental(self) -> None:
        self.add_elemental()
        self.status = (
            "An elemental rises as water - every 5 damage it turns to earth, air, then fire "
            "(J to change it now)"
        )

    def shift_elementals(self) -> None:
        for elemental in self.elementals:
            if elemental.vulnerable and elemental.form < len(KINDS) - 1:
                elemental.shift()
                self.status = f"The {elemental.kind} elemental changes form..."

    def spawn_mimic(self) -> None:
        self.add_mimic()
        self.status = (
            "A treasure chest appears... the nearest adventurer can't resist it - "
            "it's a mimic: it chomps him, then scuttles about on spider legs"
        )

    def spawn_lich(self) -> None:
        self.add_lich()
        self.status = (
            "A lich rises - he keeps his distance, levitates between windows, "
            "and raises his green flame to cast"
        )

    def select_next(self) -> None:
        index = self.stickmen.index(self.selected)
        self.selected = self.stickmen[(index + 1) % len(self.stickmen)]
        self.status = f"Selected a {self.selected.variant}"

    # ----- the selected stickman -------------------------------------------------

    @property
    def layout(self):
        return self.selected.layout

    @property
    def follower(self):
        return self.selected.follower

    @property
    def locomotion(self):
        return self.selected.locomotion

    @property
    def ragdoll(self):
        return self.selected.ragdoll

    @property
    def weapon(self):
        return self.selected.weapon

    @property
    def variant(self) -> str:
        return self.selected.variant

    @property
    def mode(self):
        return self.selected.mode

    @property
    def animated(self) -> bool:
        return self.selected.animated

    @property
    def goal(self) -> Vec2 | None:
        return self.selected.goal

    @property
    def goal_reachable(self) -> bool:
        return self.selected.goal_reachable

    @property
    def trail(self) -> list[Vec2]:
        return self.selected.trail

    @property
    def wander(self) -> bool:
        return self.selected.wander

    @property
    def dragging_limb(self) -> str | None:
        return self.selected.dragging_limb

    @property
    def limbs_draggable(self) -> bool:
        return self.selected.limbs_draggable

    def transforms(self):
        return self.selected.transforms()

    def contact(self) -> Vec2:
        return self.selected.contact()

    def limb_tips(self):
        return self.selected.limb_tips()

    def route_steps(self) -> tuple[RouteStep, ...]:
        return self.follower.remaining_steps() if self.animated else ()

    def set_variant(self, variant: str) -> None:
        self.selected.set_variant(variant)
        self.status = f"Class: {variant} ({self.selected.max_hp} HP)"

    def attack(self) -> None:
        self.selected.attack()

    def set_goal(self, point: Vec2) -> None:
        self.selected.set_goal(point)

    def toggle_wander(self) -> None:
        self.selected.toggle_wander()

    def stop(self) -> None:
        self.selected.stop()

    def go_ragdoll(self) -> None:
        self.selected.go_ragdoll()

    def get_up(self) -> None:
        if self.selected.animated:
            self.selected.stop()
        else:
            self.selected.get_up()

    # ----- simulation ----------------------------------------------------------

    def _despawn(self) -> None:
        selected_gone = self.selected.gone
        super()._despawn()
        if not selected_gone:
            return
        if self.stickmen:
            self.selected = self.stickmen[0]
            self.status = f"Your stickman despawned - now controlling a {self.variant}"
        else:
            self.selected = self.add_stickman(Vec2(self.width * 0.05, self.floor_y))
            self.status = "Your stickman despawned - a new one arrived"

    # ----- terrain -------------------------------------------------------------

    def resize(self, width: float, height: float) -> None:
        floor_y = height - self.ground_margin
        dy = floor_y - self.floor_y
        self.width = width
        self.floor_y = floor_y
        self.boxes = [box.moved(0.0, dy) for box in self.boxes]
        self._terrain_changed(moved_box=None, delta=Vec2(0.0, dy), everything=True)

    def _terrain_changed(self, moved_box: int | None, delta: Vec2, everything: bool = False):
        if everything:
            change = TerrainChange(shift=delta)
        else:
            change = TerrainChange(moves={moved_box: delta} if moved_box is not None else {})
        self.apply_terrain(change)

    # ----- pointer -------------------------------------------------------------

    def press(self, point: Vec2) -> None:
        for goblin_ in self.goblins:
            if goblin_.hits(point, margin=3.0):
                goblin_.pick_up(point)
                self._dragging_goblin = goblin_
                self.status = "Drop the goblin somewhere"
                return
        for stickman in self.stickmen:
            if not stickman.animated and stickman.hits(point, margin=RAGDOLL_KICK_REACH):
                stickman.kick(point)
                return
        selected = self.selected
        if selected.limbs_draggable:
            tips = selected.limb_tips().items()
            name, tip = min(tips, key=lambda item: item[1].distance_to(point))
            if tip.distance_to(point) <= GRAB_RADIUS:
                selected.grab_limb(name, point)
                return
        for stickman in self.stickmen:
            if stickman.animated and stickman.hits(point):
                stickman.go_ragdoll()
                stickman.kick(point)
                self.say(stickman, "Knocked over - it despawns soon unless you press Space")
                return
        for index in reversed(range(len(self.boxes))):
            box = self.boxes[index]
            if box.contains(point):
                self._dragging_box = (index, point - Vec2(box.x, box.y))
                return
        self.set_goal(point)

    def drag(self, point: Vec2) -> None:
        if self._dragging_goblin is not None:
            self._dragging_goblin.hold_at(point)
            return
        if self.selected.dragging_limb is not None:
            self.locomotion.overrides[self.selected.dragging_limb] = point
            return
        if self._dragging_box is None:
            return
        index, grip = self._dragging_box
        box = self.boxes[index]
        x = point.x - grip.x
        y = min(point.y - grip.y, self.floor_y - box.height)
        delta = Vec2(x - box.x, y - box.y)
        if delta.length_sq() == 0.0:
            return
        self.boxes[index] = box.moved(delta.x, delta.y)
        self._terrain_changed(moved_box=index, delta=delta)

    def drop(self, point: Vec2 | None = None) -> None:
        if self._dragging_goblin is not None:
            goblin_ = self._dragging_goblin
            goblin_.place(point if point is not None else goblin_.held_at)
            self._dragging_goblin = None
            self.status = "Goblin dropped"
        self.selected.release_limb()
        self._dragging_box = None
