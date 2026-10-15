# Dungeons & Desktops
## Product Requirements Document + Technical Implementation Plan

**Version:** 0.1 — Development kickoff  
**Status:** Ready for prototyping; technical risks explicitly identified  
**Primary target:** macOS desktop; Windows as a subsequent platform  
**Implementation language:** Python 3.12+  
**Rendering/UI:** PySide6 (Qt 6), using programmatic vector drawing only  
**Primary audience:** Solo developer working with Cursor

---

## 0. Instructions for Cursor (read first)

You are the lead engineer for **Dungeons & Desktops**, a code-only, procedural 2D desktop dungeon-defense game. This document is the source of truth for product scope, architecture, and acceptance criteria.

**Working rules:**

1. Implement **one milestone at a time**. Begin with **Milestone 0 (project and simulation skeleton)** and **Milestone 1 (transparent overlay + interactive treasure window)**. Do not implement later milestones until the earlier ones run on the user's Mac.
2. **No sprites, sprite sheets, video, image assets, Godot, Unity, Electron, web frontend, or embedded browser.** Render game characters and effects via `QPainter`, `QPainterPath`, basic vector geometry, math, and code-generated shapes.
3. Build and test the game rules **independently of Qt and macOS APIs**. The engine must be testable with a synthetic desktop geometry provider.
4. Wrap all OS integrations behind interfaces. Never mix raw Quartz window dictionaries directly into entities, pathfinding, or game logic.
5. Make the app safe for everyday desktop use. Overlay windows must **not steal routine mouse clicks**; provide Pause/Hide/Quit controls and recover cleanly from monitor/window changes.
6. **Do not move, resize, close, read the content of, or otherwise modify other applications' windows.** Players arrange their own windows with normal OS controls.
7. Use a single canonical world-coordinate system, with explicit conversions from native OS coordinates and individual overlay-local coordinates. Test negative monitor origins and mixed display scaling.
8. Any OS API limitation or permission dependency must have a documented fallback. Do not claim an API works universally unless demonstrated on the target machine.
9. At the completion of each milestone: run tests, explain manual test steps, list remaining known issues, and update `docs/IMPLEMENTATION_STATUS.md`.
10. Keep the design minimal and extensible; no large frameworks beyond the stack listed here without a justified need.

**Start here:** Create the repository skeleton, `pyproject.toml`, a runnable `python -m dungeons_desktops` entry point, an OS-independent mock world, and the first transparent click-through overlay demo with a separate draggable treasure window. Include a clear `README.md` for macOS setup and running the app.

---

## 1. Product vision

### 1.1 One-sentence pitch

**Turn your actual desktop into a dungeon: arrange your application windows as the level, place monsters and traps on their edges, and defend a treasure-hoard window from invading stick-figure adventurers.**

### 1.2 Fantasy and differentiation

The player is **the dungeon**, not the hero. Their desktop is a living environment: browser windows become ramparts, editor windows become platforms, narrow gaps become ambush routes, and the borders between monitors form connected dungeon space. Adventurers try to navigate that geometry and steal the treasure. The player rearranges windows and deploys monsters to shape a defensible level.

The central design principle is **desktop layout = level design**. An attractive implementation of the concept depends more on correct surface extraction, routing, and overlay behavior than on a large roster of creatures.

### 1.3 Experience pillars

1. **Your windows are the map.** Actual positions and dimensions of eligible application windows determine walkable/climbable surfaces.
2. **Be the dungeon master.** Players build a defensive landscape with windows, monsters, and traps.
3. **Living procedural creatures.** Every character and creature is animated in real time through geometry, joints, curves, simple IK, spring motion, and state machines.
4. **Desktop-friendly by default.** Ambient mode is low-distraction; game mode is explicitly entered and clearly dismissible.
5. **Tactical readability.** Players can understand which routes the invaders will take and why a path is or is not reachable.

### 1.4 Target user

A desktop user who enjoys idle mascots, reverse tower defense, simulation toys, and fantasy dungeon themes; comfortable with intentionally arranging windows to create interesting gameplay.

---

## 2. Scope and release definition

### 2.1 First playable MVP: Desktop Dungeon Defense

A complete minimal raid on macOS that supports:

- At least one active monitor and at least two connected monitors when present.
- Read-only detection of eligible on-screen application-window bounds.
- A see-through visual overlay that renders window-edge terrain and moving entities.
- A separate, real, draggable **Treasure Hoard** application window.
- A route preview from a designated spawn to the hoard, built from window edges and allowed movement transitions.
- A procedurally drawn stick-figure adventurer that actually follows the route (not teleporting node-to-node).
- One deployable monster: **Burrow Worm** (short-range timed ambush).
- One deployable trap: **Spikes** (stationary contact damage).
- A simple, finite multi-wave raid and a game-over state.
- Victory when all scheduled invaders have been defeated; defeat immediately when any adventurer touches the treasure trigger area.
- Pausing, hiding overlays, resetting the raid, and quitting without affecting other applications.

This is a **vertical slice**: every part of the premise works together, even if visuals and content are rudimentary.

### 2.2 Deliberately out of scope for MVP

- Dragon, kraken, pirate ships, spiders, goblins, complex creature rigs.
- Persistent economy, crafting, talent trees, campaign or metaprogression.
- Multiplayer, networking, cloud accounts, telemetry, online content.
- Screenshots, OCR, window-content analysis, desktop recording, reading documents.
- Automatic manipulation or rearrangement of third-party windows.
- Full 3D graphics, sprites, bitmap animation, skeletal asset editors.
- Native Windows/Linux support (architecture-ready, but not a release criterion).
- Global mouse/keyboard hooks; global interactions requiring invasive permissions.
- Forcing the overlay to work across macOS full-screen Spaces or protected/system windows.

### 2.3 Post-MVP possibilities

Add dragon nests, kraken tentacles, spider webs, mimics, archer/cleric/wizard classes, flying enemies, buildable bridge hazards, upgrades, ambient critter behavior, more elaborate procedural rigs, and Windows support.

---

## 3. Gameplay specification

### 3.1 Modes

**Ambient Mode:** Tiny monsters live unobtrusively near window edges. No treasure or defeat condition. No active invasion. The overlay remains click-through by default; player can open a small control panel to interact with game controls. Ambient Mode may initially be a static/wandering worm only.

**Dungeon Defense Mode:** Explicit play mode with these phases:

1. **Construction:** Player rearranges their real app windows manually and drags the treasure-hoard window. Terrain and route preview update as geometry changes.
2. **Deployment:** Player places monsters/traps on eligible surfaces using the game palette and placement mode. Route preview remains visible.
3. **Invasion:** Waves spawn; invaders navigate the live window geometry toward treasure; defenses attack. The player may inspect, pause, and use allowed creature commands. Window movement during combat causes navigation recalculation.
4. **Result:** Victory or defeat, with Restart / Rearrange Dungeon / Return to Ambient.

Construction and Deployment can be toggled during preparation; beginning the raid is a deliberate button action.

### 3.2 Treasure hoard

- The treasure is a **real, independently movable Qt top-level window** belonging to this app, visually a tiny chest/coin pile drawn procedurally.
- It has a drag handle and a small title/close-equivalent control where appropriate, so the user can position it on screen in the preparation phase.
- It acts as the **goal entity**, not general third-party terrain; exclude its window from normal window detection to prevent recursive geometry generation.
- Placement valid only in an accessible location (one reachable from spawn using the basic invader's movement rules); show clear invalid-state feedback otherwise.
- On raid start, hoard position becomes logically locked. For MVP the user cannot drag the hoard during invasion; it stays visible as a separate window.
- **Lose condition:** the first living adventurer reaching/intersecting the hoard's defined target trigger causes immediate defeat. Reaching means intersecting a small, visible trigger region at the entrance/front of the hoard; merely passing behind the window does not count.
- When hoard is closed unexpectedly, pause raid and offer Reopen / End Raid, not silent defeat.
- Do not draw gameplay objects *inside* third-party windows; all game visuals belong to our overlay/hoard.

### 3.3 Spawn and route

- The MVP uses one explicit spawn marker, initially generated at an accessible edge of the virtual desktop (such as a left-hand floor edge), with an option to move it in the game UI during setup if necessary.
- The route is calculated from the spawn to the **treasure entrance node**.
- Before invasion, draw a colored route preview; if no route exists, disable **Start Raid**, indicate the broken section, and prompt player to rearrange windows/hoard.
- Do not silently add teleportation to make disconnected paths valid.
- If the desktop changes during combat and a route becomes unavailable, immediately recompute; affected adventurers stop/search at the nearest stable point, and the game displays **Path Blocked**. Allow a safe pause or rearrangement. Do not treat an impossible route as an automatic victory.
- For MVP, enemies use the same navigation abilities; later classes can differ in climbing/jumping capability.

### 3.4 Basic entity roster

| Entity | Role | MVP behavior | Procedural representation |
|---|---|---|---|
| Adventurer | Invader | Spawn → route → traverse → reach hoard; can take damage/die | Head circle, torso segment, arm/leg joints, walking cycle |
| Burrow Worm | Monster | Placed along a traversable edge; detects nearby invader, emerges/attacks, cooldown | Chain of circles/segments on a smoothed spline, head and mouth geometry |
| Spikes | Trap | Placed on a short horizontal ledge; deals contact damage with cooldown | Generated triangular spikes, simple pulse animation |
| Treasure Hoard | Objective | Separate window, preview/lock, defeat trigger | Generated chest/coin polygon/path |

### 3.5 Default prototype balance (data-driven; values are tuning placeholders)

- Adventurer max health: **100**, movement: **65 world units/second** (world units = Qt logical pixels by default).
- Monster cost: **60** construction points; worm strike: **55 damage**, **2.0 s** cooldown, short surface-based attack range.
- Spike cost: **30** construction points; **25 damage per valid contact** with **1.0 s** per-adventurer cooldown.
- Initial construction budget: **150** points. Give **10** points per defeated adventurer, credited for next deployment phase; don't require mid-wave purchases in the MVP.
- Raid: three waves of **3, 5, and 7** adventurers. Spacing and inter-wave gaps are configurable.
- Victory when final wave is cleared and no invaders remain. Defeat immediately when a living invader enters treasure trigger bounds.
- Numbers belong in `data/balance.json` (or a typed settings module), not scattered across entity classes.

### 3.6 Basic UX

Main control panel (normal interactive Qt window, distinct from overlay):

- Mode indicator: Ambient / Construction / Deployment / Invasion / Paused / Victory / Defeat.
- Buttons: `Enter Dungeon Defense`, `Place Hoard`, `Place Worm`, `Place Spikes`, `Preview Path`, `Start Raid`, `Pause/Resume`, `Hide/Show Overlay`, `End Raid`, `Quit`.
- Wave/remaining invaders count, deployment budget, brief status messages.
- Optional debug toggle to draw detected-window bounds, surface IDs, graph nodes/edges, route nodes, entity coordinates, and FPS.

**Interaction rule:** The transparent gameplay overlay is **display-only / click-through** during normal use. Game controls live in normal small, interactive app windows. When placing a monster/trap, a temporary clearly-indicated placement capture overlay may receive clicks; Escape or Cancel exits placement and restores click-through. The player must be able to rearrange real app windows normally during Construction when not actively placing a unit.

---

## 4. Desktop terrain and multi-monitor behavior

### 4.1 Source data

The OS adapter returns read-only snapshots of **monitors** and **eligible window rectangles**. Each window record includes only geometry and minimal ephemeral identifiers needed for tracking; avoid titles, app contents, screenshots, or other sensitive metadata.

Eligible windows, by default:

- Ordinary on-screen windows with sensible nonzero bounds.
- Not minimized, hidden, system-owned overlays, desktop wallpaper, menus, docks, or the app's own overlays/hoard/palette.
- Exclude window layers that are not standard app windows where supported.
- App's own windows are excluded by process ID and explicit known window IDs.

The first version treats each eligible window rectangle as a simplified solid shape. Later: z-order-aware clipping and handling for partially occluded platforms.

### 4.2 Canonical coordinates

Use **world coordinates measured in Qt device-independent/logical pixels**, with a top-left oriented coordinate convention, and allow negative X/Y for monitors arranged left/above the primary display. OS geometry from Quartz must be converted explicitly at the adapter boundary.

Data flow:

`Quartz native window bounds → geometry normalizer → world rectangles → surface extractor → nav graph → route + game simulation → per-monitor overlay-local render coordinates`

Build round-trip tests for native→world→native or world→overlay→world. Do **not** assume every monitor has the same scale factor; compare against real geometry on Retina and mixed-DPI screens.

### 4.3 Physical terrain rules

- **Monitor floor:** Each monitor's usable bottom boundary may be a traversable floor segment.
- **Window top:** Horizontal top edge becomes a walkable platform.
- **Window sides:** Left/right vertical edges become climbable segments.
- **Window bottom:** Not traversable by default (reserved for possible ceiling-crawler creatures later).
- **Corners:** Connect walking/climbing segments where the same rectangle's edges meet.
- **Short gaps:** Traversable by a `JUMP` transition when horizontal/vertical displacement is within explicit class capability and a landing surface exists.
- **Drops:** `DROP` transitions from a ledge to a lower supported surface, subject to max safe fall and geometry rules.
- **Overlaps:** Other window rectangles cannot be passed through as solid geometry unless a route goes around them. For MVP, collision and traversal are based on the same simplified rectangles to avoid contradictory visuals.
- **Monitor seams:** Connected display areas form one world. A route can cross a seam only where the two displays are logically adjacent and the trajectory has supported geometry or an allowed jump/drop. No invented connection across a virtual-coordinate gap.

In the MVP, **basic adventurers can climb window sides** and use short jumps. Their route will show traversal arrows for climbs/jumps.

### 4.4 Navigation graph

Do not use a full-pixel occupancy grid. Build a **surface graph**:

- `Surface`: one horizontal/vertical traversable edge with world endpoints, normal, parent window/monitor ID, and movement tags.
- `NavNode`: edge endpoint, surface junction, jump/drop takeoff/landing, spawn projection, or hoard entrance projection.
- `NavEdge`: feasible transition with `WALK`, `CLIMB`, `JUMP`, `DROP`, or `MONITOR_CROSS`; weighted by estimated traversal time plus configurable hazard cost.
- `Graph`: nodes/edges and a geometry revision ID.

Generate candidate transitions only between nearby surfaces using spatial indexing or cheap bounding-box proximity; for MVP a small O(n²) candidate scan is acceptable if profiled and throttled. Pathfinding: **A\*** with admissible distance/time heuristic or Dijkstra until costs stabilize. Return an ordered route of segments with traversal modes; entities interpolate/animate over segments.

For topology changes: debounce native window events/polling; rebuild graph when rectangles meaningfully change; replan on graph revision, not on every rendered frame. Keep a stable graph snapshot while an update is being computed.

**Validity invariant:** A successful route must be physically executable by the movement controller with the same jump/climb constraints used by the planner. Test against synthetic worlds before using desktop windows.

### 4.5 Window change policy

- Moving/resizing/closing/minimizing third-party windows updates terrain but never modifies those windows.
- Snapshot updates are throttled (prototype target ~2–5 Hz when active; slower when idle) to avoid repeatedly calling relatively expensive OS APIs. Increase responsiveness after profiling.
- Render/simulation never block on native window enumeration; publish snapshots through a thread-safe handoff if necessary, keeping Qt GUI operations on the GUI thread.
- On display disconnect or geometry change: pause if necessary, clamp game-owned windows onto an available screen, rebuild terrain, and explain what changed.
- Covered/overlapping desktop windows, multi-Space behavior, external fullscreen apps, and rotated monitors must be investigated; do not promise correctness for every OS arrangement in MVP.

---

## 5. Rendering and procedural animation

### 5.1 Hard requirement

**No sprite assets and no pre-rendered animation frames.** Characters, effects, and treasure are defined and drawn programmatically with `QPainter`/`QPainterPath` and geometry math. Fonts/standard system icons are acceptable for control UI; gameplay entities remain procedurally rendered.

### 5.2 Rendering layers

1. Optional debug terrain surface lines and path preview.
2. Traps and placement previews.
3. Creatures and adventurers.
4. Procedural particles, hit effects, floating numbers.
5. World-space markers (spawn and treasure entrance).

Maintain one **transparent, borderless, always-on-top render overlay per monitor** where platform behavior permits. Render in world space and clip/transform to the overlay's monitor rectangle. Overlays use Qt's `WA_TranslucentBackground` and frameless flags; test `WindowTransparentForInput` to ensure underlying desktop interaction. The control palette and hoard are separate, ordinarily interactive windows.

### 5.3 Simulation timing

- Fixed timestep game simulation: target **60 updates/sec** (or a stable fixed step with accumulator).
- Rendering: target 60 FPS when active, throttled to 15–30 FPS or event-driven in ambient/paused mode.
- Route recalculation/window polling decoupled from animation updates.
- Speed measured in world units/second; clamp catch-up steps after app sleep/stall to avoid large jumps.

### 5.4 Procedural stick adventurer

Create a rig with head, torso, hips, shoulder joints, elbows, knees, hands, and feet. Starting MVP can use simple segment rotations; progress to two-bone IK for foot placement. Pose driven by traversal mode:

- `WALK`: alternating planted/swing legs, arm counter-swing, mild torso bob.
- `CLIMB`: hands/feet take turns grasping the vertical side, body orientation biased to wall.
- `JUMP`/`DROP`: tucked legs, extended arms, position follows planned transition curve.
- `HIT`/`DEATH`: short squash/recoil and fade; no sprite effects.

### 5.5 Procedural worm

Worm is a chain of points/segments. Head position uses a smooth eased emergence arc or spring; body points follow a spline/constraint chain; mouth opens during attack. Can remain anchored to a surface until enemy enters range. Its gameplay hitbox must not depend on purely decorative wiggle physics.

**Separation of concerns:** Simulation has collision primitives and canonical positions; the animation layer creates poses; the renderer converts poses into Qt draw calls. Never use QPainter state or widget coordinates in entity AI.

---

## 6. Technical stack and system boundaries

### 6.1 Stack

- **Python 3.12 or 3.13**, version pinned per environment test.
- **PySide6**: QApplication, QWidget/QWindow, QScreen, QTimer, painting, palette, hoard window, overlays.
- **Standard library**: `dataclasses`, `enum`, `math`, `time`, `typing`, `logging`, `json`, `pathlib`.
- **PyObjC Quartz bindings on macOS**: `CGWindowListCopyWindowInfo`-based geometry adapter where functional; optional Accessibility APIs for later features only if essential.
- **pytest**: unit/integration tests; `ruff` for formatting/linting; `mypy` optional once interfaces settle.
- **uv** or `pip`/venv: reproducible package setup. Prefer `pyproject.toml` with OS-specific optional dependencies or environment markers.
- Avoid NumPy until a real profiling/math need appears; built-in 2D vector utilities are sufficient for the MVP.

### 6.2 Platform API notes

- Qt documents translucency for frameless macOS top-level widgets and `WindowTransparentForInput` for display-only windows. Verify behavior on the actual target macOS version, including multiple overlays and pointer interaction.
- macOS Core Graphics offers `CGWindowListCopyWindowInfo` for current-session window metadata. Calls can be expensive, so batch/poll appropriately. Some metadata and cross-app introspection may be restricted depending on OS/privacy settings; gracefully degrade and ask for permissions **only when demonstrated necessary**.
- Do not screen-capture or inspect window contents to build terrain. Use bounds only.
- For optional native interactions later, review Accessibility permission prompts independently; the initial implementation should avoid global event taps and invasive monitoring.

### 6.3 Core architecture

```text
App bootstrap / Qt GUI thread
├── ControlPalette (interactive QWidget)
├── TreasureHoardWindow (interactive during setup)
├── OverlayManager
│   └── MonitorOverlay[one per monitor] (transparent, input-pass-through)
├── GameCoordinator (mode/phase, input commands)
├── GameEngine (OS-independent)
│   ├── WorldState / entity registry
│   ├── FixedStepClock
│   ├── Movement / collision / combat systems
│   ├── State machines / procedural rigs
│   ├── WaveManager / economy / victory rules
│   └── NavigationService (surface graph, route planner)
└── DesktopAdapter interface
    ├── MockDesktopAdapter (test/dev)
    └── MacOSDesktopAdapter (Quartz + QScreen)

Flow: DesktopAdapter snapshot -> GeometryNormalizer -> SurfaceExtractor
      -> NavigationService -> GameEngine -> RenderSnapshot -> Qt overlays.
```

### 6.4 Important interfaces (guide, not rigid implementation)

```python
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

@dataclass(frozen=True)
class Vec2:
    x: float
    y: float

@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

@dataclass(frozen=True)
class MonitorInfo:
    monitor_id: str
    bounds: Rect          # canonical world coordinates
    usable_bounds: Rect
    scale_factor: float

@dataclass(frozen=True)
class WindowInfo:
    window_id: str
    owner_pid: int
    bounds: Rect          # canonical world coordinates
    z_index: int | None = None

@dataclass(frozen=True)
class DesktopSnapshot:
    monitors: tuple[MonitorInfo, ...]
    windows: tuple[WindowInfo, ...]
    revision: int

class DesktopAdapter(Protocol):
    def snapshot(self) -> DesktopSnapshot: ...

class TraversalMode(Enum):
    WALK = "walk"
    CLIMB = "climb"
    JUMP = "jump"
    DROP = "drop"
    MONITOR_CROSS = "monitor_cross"

@dataclass(frozen=True)
class RouteStep:
    start: Vec2
    end: Vec2
    mode: TraversalMode
    duration_seconds: float

@dataclass(frozen=True)
class Route:
    steps: tuple[RouteStep, ...]
    graph_revision: int
```

Use **separate identifiers** for OS windows, graph surfaces, and game entities. Don't make a game's state depend on window title strings. Synthetic scenes use the exact same world and navigation interfaces as native snapshots.

---

## 7. Proposed repository layout

```text
dungeons-and-desktops/
├── pyproject.toml
├── README.md
├── .gitignore
├── docs/
│   ├── PRD.md                    # This file
│   ├── IMPLEMENTATION_STATUS.md
│   ├── ARCHITECTURE.md
│   └── MACOS_TEST_MATRIX.md
├── src/
│   └── dungeons_desktops/
│       ├── __init__.py
│       ├── __main__.py
│       ├── app.py
│       ├── config.py
│       ├── core/
│       │   ├── geometry.py
│       │   ├── models.py
│       │   ├── clock.py
│       │   ├── world.py
│       │   └── events.py
│       ├── desktop/
│       │   ├── adapter.py
│       │   ├── mock_adapter.py
│       │   ├── macos_adapter.py
│       │   ├── coordinates.py
│       │   └── surface_extractor.py
│       ├── navigation/
│       │   ├── graph.py
│       │   ├── transitions.py
│       │   └── astar.py
│       ├── entities/
│       │   ├── base.py
│       │   ├── adventurer.py
│       │   ├── worm.py
│       │   └── spikes.py
│       ├── systems/
│       │   ├── movement.py
│       │   ├── combat.py
│       │   ├── waves.py
│       │   └── game_rules.py
│       ├── animation/
│       │   ├── rig.py
│       │   ├── stick_figure.py
│       │   └── worm_chain.py
│       ├── rendering/
│       │   ├── draw_entities.py
│       │   └── draw_debug.py
│       └── ui/
│           ├── overlays.py
│           ├── control_palette.py
│           ├── hoard_window.py
│           └── placement_controller.py
├── data/
│   └── balance.json
└── tests/
    ├── test_geometry.py
    ├── test_coordinates.py
    ├── test_surfaces.py
    ├── test_navigation.py
    ├── test_win_loss.py
    └── fixtures/
        └── synthetic_desktops.py
```

Keep files focused but do not create dozens of empty abstractions ahead of working functionality.

---

## 8. Functional requirements and acceptance criteria

Priority: **P0 = must ship MVP**, **P1 = next**, **P2 = long-term**.

| ID | Pri. | Requirement | Testable acceptance criterion |
|---|---|---|---|
| FR-01 | P0 | Transparent overlay | Renders vectors over visible desktop without painting an opaque background |
| FR-02 | P0 | Input passthrough | With no placement mode active, clicking a browser/button beneath the overlay works normally |
| FR-03 | P0 | Native window geometry | Eligible real application windows are listed with reasonably accurate normalized bounds; own windows excluded |
| FR-04 | P0 | Monitor geometry | Monitor offsets and bounds represented in one coordinate system; adjacent monitor seam handled |
| FR-05 | P0 | Surface extraction | Debug view draws the correct top/side edge segments from selected windows |
| FR-06 | P0 | Graph and path preview | A* computes a route using only feasible walk/climb/jump/drop/seam transitions |
| FR-07 | P0 | Impossible path handling | Start Raid is disabled when hoard cannot be reached; explains why |
| FR-08 | P0 | Real hoard window | User can drag the hoard during setup; it is drawn procedurally and cannot be dragged during invasion |
| FR-09 | P0 | Adventurer animation | Visible procedural stick figure moves smoothly along route with distinct walk/climb poses |
| FR-10 | P0 | Cross-monitor navigation | On adjacent monitors, invader crosses a valid seam without coordinate jump or duplication |
| FR-11 | P0 | Placement | Worm and spikes can only be placed in valid areas, with visible placement feedback |
| FR-12 | P0 | Combat | Worm and spikes can damage adventurer using deterministic hit rules and cooldowns |
| FR-13 | P0 | Waves | Three configured waves spawn and terminate correctly |
| FR-14 | P0 | Victory/defeat | Victory after all enemies defeated; instant defeat when first living enemy enters hoard trigger |
| FR-15 | P0 | Window changes | Moving/resizing a native window causes terrain refresh and path replanning, not crash or teleport |
| FR-16 | P0 | Safe controls | Pause, hide overlays, end raid, and quit all work; quitting leaves other windows untouched |
| FR-17 | P0 | Automated rules tests | `pytest` passes synthetic worlds and victory/combat logic headlessly |
| FR-18 | P1 | Ambient mode behaviors | Worm can idle/wander without active invasion or blocking user input |
| FR-19 | P1 | Additional enemy classes | Archer, rogue, wizard, etc. can implement different traversal/combat strategies |
| FR-20 | P1 | More monsters | Dragon and kraken demonstrate reusable articulated-rig animation systems |
| FR-21 | P2 | Windows platform adapter | Native Windows geometry provider passes the same contract tests |

---

## 9. Nonfunctional requirements

### 9.1 Performance

- Target 60 FPS in simple active MVP scenes on a modern laptop; tolerate temporary frame drops without simulation instability.
- Keep Qt drawing in UI thread; isolate blocking OS polling/path calculation where needed.
- Avoid full-screen screenshots and constant native window metadata calls.
- Do not rebuild the graph every frame; rebuild on changed/debounced geometry snapshots.
- Profile CPU cost on battery; reduce update frequency in Ambient/Paused modes.

### 9.2 Desktop safety and user trust

- Never move, close, resize, focus, or automate other applications' windows.
- No screenshots, OCR, document/file inspection, or collection/transmission of app window contents.
- Don't log app titles by default; prefer window IDs, rectangles, and timings.
- Always expose a visible Escape/Cancel route from input-capturing placement mode.
- Do not activate globally at login or start a raid without explicit opt-in.
- Provide a way to disable overlay on a particular monitor.
- On focus loss, system sleep, monitor disconnect, crash, or native adapter error, fail safe: stop gameplay or restore input passthrough rather than trapping input.

### 9.3 Reliability and testability

- All core gameplay state is isolated from rendering and native OS details.
- Support `--mock-desktop` with deterministic windows/monitor fixtures and optional `--debug-geometry`.
- Unit test geometry and A* without launching Qt.
- Settings persist locally only; saving whole dungeons may come after MVP.

### 9.4 Accessibility/usability

- UI should be keyboard navigable; accessible contrast on route previews.
- Allow reducing motion and hiding animated overlays.
- Respect display cutouts, Dock/menu-bar usable regions where geometry is available.
- Provide settings for visible overlay opacity/path debug lines.

---

## 10. Technical risk register and investigation spikes

| Risk | Why it matters | MVP mitigation / proof |
|---|---|---|
| Transparent window intercepts input | Makes a desktop app unusable | Prove click-through on macOS before any game logic; separate interaction windows |
| Inaccurate Quartz→Qt coordinates | Entities drift on Retina/multi-monitor | Draw labeled edge overlays and compare by eye on two monitor arrangements; roundtrip unit tests |
| Mixed-DPI cross-display seam | Characters teleport at boundary | Canonical logical world, conversions per monitor; explicit seam traversal test |
| Fullscreen/Spaces restrictions | OS may hide windows/overlay or limit enumeration | Support normal desktop Spaces first; document limitations and pause gracefully |
| Window-list privacy/permission changes | Geometry may be restricted by OS | Test adapter on target machine, use bounds-only data, mock fallback; explain specific permission only if required |
| Overlapping/occluded windows | Invisible or confusing pathways | MVP simple rectangles + visible geometry debug; P1 z-order clipping and conservative filtering |
| Path is valid in graph but impossible in simulation | False previews and stuck invaders | Shared traversal constraints, graph-to-movement contract tests, deterministic route fixtures |
| Live topology changes strand invaders | Raid becomes unfair | Replan on revision, pause/blocked notice, reset/rearrange action |
| Always-on-top overlays appear in screen sharing | Privacy/distraction | Hide overlay instantly, allow monitor exclusions; do not claim stealth from capture |
| Animation cost grows with entities | Power consumption | Cap entity count, dirty regions if useful, profile painter workload |

**Mandatory engineering spikes in order:**

1. Transparent click-through overlay on real macOS; independently interactive hoard/control window.
2. Window enumeration and position alignment on Mac with normal applications.
3. Second monitor and mixed coordinate/scale consistency.
4. Mock-world A* route and an animated entity traversing the exact route.

If a spike fails, document it in `docs/IMPLEMENTATION_STATUS.md` and adapt the implementation without weakening the game premise or silently swapping to a game engine.

---

## 11. Milestones and definition of done

### M0 — Repo and OS-independent simulation foundation

**Build:** `pyproject.toml`, `src` package, application entrypoint, typed geometry models, basic event loop, deterministic mock desktop adapter, tests, README, logger.

**Done when:** `python -m dungeons_desktops --mock-desktop` starts; tests run in an isolated environment; synthetic monitor/window world is inspectable via logs or a minimal debug UI.

### M1 — Overlay + treasure window (first tangible demo)

**Build:** Transparent pass-through monitor overlay, Qt vector demo character/edge line, separate draggable hoard window, small control panel, Hide/Quit, explicit placement-capture cancellation proof.

**Done when:** A developer can keep interacting with another app beneath visible drawings; drag the hoard; hide/show/quit cleanly. Test on the actual Mac. **Do not continue until input pass-through is demonstrated.**

### M2 — Live desktop geometry

**Build:** `MacOSDesktopAdapter`, own-window exclusion, geometry normalizer, screen list with offsets/scales, polling/debounce, debug edge renderer.

**Done when:** Moving a browser window updates a corresponding debug rectangle/edge within about one second without noticeable app interference; correct across available monitors; no recursive game-owned windows.

### M3 — Terrain and navigation

**Build:** Surface extraction, traversal transition generation, graph, A*, spawn projection and hoard entrance projection, reachable/unreachable preview, synthetic fixtures; simple adventurer motion following route.

**Done when:** Stick adventurer walks/climbs/jumps along eligible edges from spawn to hoard across a synthetic world and real windows; second monitor seam works on a feasible route; infeasible routes refuse to start.

### M4 — First playable defense raid

**Build:** Phase state machine, worm, spikes, deployment budget, placement mode, 3 waves, damage/death, arrival trigger, victory/defeat UI, pause/restart, graph revision replanning.

**Done when:** Player rearranges windows, places hoard + worm + spikes, starts wave, wins by defeating all attackers or loses if one reaches hoard. Moving a window mid-raid doesn't crash or create a fictional path.

### M5 — Polish / hardening

**Build:** Better procedural poses (IK, worm body springs), particles, event sounds if desired, performance profiling, settings, ambient mode basics, packaging, permissions/failure-state UX.

**Done when:** Stable on a realistic desktop session, responsive under multiple entities, documented installation/running instructions, and passes manual multi-monitor test matrix.

### Do not jump ahead

Cursor should not implement all entities or advanced features from the post-MVP backlog. The shortest credible path to success is: **transparent overlay → actual window surfaces → pathfinding across monitors → hoard defeat condition → worm/trap combat.**

---

## 12. Test matrix

### Automated core cases (must be deterministic)

- No windows: monitor floor only; route either valid or explicitly unavailable as expected.
- One window with climbable side and top: route reaches top with exact traversal sequence.
- Two stacked windows with small/large gaps: short jump allowed; large gap rejected.
- Overlapping windows: no impossible tunnel through a solid rectangle.
- Hoard unreachable: route `None`, `Start Raid` disabled.
- A moved window updates graph revision; stale route isn't followed indefinitely.
- Two adjacent monitors: seam transition exists only when geometrically supported.
- Two monitors with a gap: no automatic seam connection.
- Monitor left of primary: negative X remains valid throughout graph/render conversions.
- Traversal movement finishes at target point within epsilon, without discontinuity.
- Spike damage respects per-entity cooldown; worm damage respects attack range/cooldown.
- One surviving adventurer enters treasure trigger: immediate loss, no victory race condition.
- All scheduled adversaries eliminated before reaching hoard: victory once no active enemies remain.
- Reset restores game state and doesn't reuse stale terrain references.

### Manual macOS tests

- Transparency and click-through over Safari/Chrome, Finder, and terminal/editor windows.
- Normal click, keyboard focus, text input, scrolling in third-party apps while overlay visible.
- Move/resize/minimize an app window during Construction; verify geometry update.
- Begin and cancel trap placement; verify pointer control returns to underlying apps.
- Treasure drag, lock during raid, reopen after close, and on-screen clamping.
- Two-monitor arrangement: left/right, above/below, Retina + non-Retina if available.
- Disconnect a display mid-session; test recovery.
- Sleep/wake app and check for sudden large entity motion.
- Enter/exit macOS fullscreen Space; verify documented graceful behavior.
- Pause, Hide Overlay, End Raid, Quit at all times.

---

## 13. Build instructions and development commands

Prefer a local virtual environment and pinned dependencies. Cursor should generate the exact `pyproject.toml` for the chosen package versions compatible with the local Python/macOS setup; use `uv` if available or standard `venv`/`pip` otherwise.

Proposed developer interface after M0:

```bash
# Run the mock world with no native OS dependency
python -m dungeons_desktops --mock-desktop

# Run against actual macOS desktop geometry when implemented
python -m dungeons_desktops --desktop

# Show surfaces, navigation graph and FPS
python -m dungeons_desktops --desktop --debug-geometry

# Headless rules/unit tests
pytest -q
```

Set package install metadata so the `src` layout imports correctly; document `pip install -e '.[dev]'` or `uv sync` as appropriate. Add `ruff check .` and basic formatting check once the skeleton runs. Do not prescribe unverified PyObjC import names; demonstrate and test them within the adapter.

---

## 14. Open design decisions (defer unless blocking)

1. Exact playable aesthetics: ultra-minimal black/white stick figures vs stylized fantasy color accents.
2. Whether environmental z-order will clip occluded edges before P1. MVP documents its simplified terrain model.
3. Whether tower defense permits mid-wave unit deployment. MVP: deployment between waves only.
4. Whether treasure placement requires physical contact with a platform or can float with a generated access point. MVP: require a clearly defined reachable entrance node.
5. Whether ambient mode interacts with global cursor. MVP: no global pointer hooks; avoid permissions.
6. How to route across rotated/unusual multi-monitor arrangements. Test standard rectangular layouts first.
7. Desktop/window persistence between restarts. MVP: no desktop layout saved or restored.

None of these should block M0/M1.

---

## 15. Future systems roadmap

**Monsters:** Dragon (ledge nest + cone breath), Kraken (corner anchor + IK tentacles), Spider (climb + web bridge), Slime (blocker), Mimic (bait), Goblin (projectiles).  
**Invaders:** Rogue (fast/jump), Knight (tank), Archer (ranged), Wizard (teleport within strict ability limits), Cleric (healing), engineer (temporary bridge).  
**Dungeon tools:** Deployable ladders/bridges, surface hazards, treasure decoys, map presets, difficulty modifiers.  
**Progression:** Resources from defeats, upgrade choices after raids, cosmetic procedural styles, shared monster traits.  
**Cross-platform:** Windows adapter behind same `DesktopAdapter`; investigate Linux X11/Wayland limitations separately.

---

## 16. Official technical references

Use these references to verify platform implementation details; do not treat pseudocode as a substitute for official API contracts.

- Qt for Python — [QWidget transparent top-level windows](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QWidget.html)
- Qt for Python — [Qt.WindowTransparentForInput and window flags](https://doc.qt.io/qtforpython-6/PySide6/QtCore/Qt.html)
- Qt for Python — [QPainter vector geometry](https://doc.qt.io/qtforpython-6/PySide6/QtGui/QPainter.html)
- Qt for Python — [QPainterPath](https://doc.qt.io/qtforpython-6/PySide6/QtGui/QPainterPath.html)
- Qt for Python — [QScreen monitor geometry and device-pixel ratio](https://doc.qt.io/qtforpython-6/PySide6/QtGui/QScreen.html)
- Apple — [CGWindowListCopyWindowInfo](https://developer.apple.com/documentation/coregraphics/cgwindowlistcopywindowinfo(_:_:))
- Apple — [Quartz Window Services](https://developer.apple.com/documentation/coregraphics/quartz-window-services)

---

## 17. Project-wide definition of a successful MVP

A person can open their usual desktop applications, manually arrange those windows into an intentional dungeon across one or more monitors, move a distinct treasure-hoard window to a defensible spot, inspect the valid invader route, deploy a procedurally animated worm and a spike trap, click **Start Raid**, watch procedurally drawn stick adventurers navigate along the actual edges of their desktop windows between monitors, and either defeat the wave or lose when an invader reaches the hoard—**without the game hijacking their normal desktop input or touching the contents of any other application.**

That is **Dungeons & Desktops**.
