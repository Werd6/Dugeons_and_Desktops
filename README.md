# Dungeons & Desktops

A procedural desktop dungeon-defense game in Python and PySide6. The full product spec is in [docs/PRD.md](docs/PRD.md).

It runs as a **desktop pet** on your real windows (macOS and Windows), with a local creature-rig preview for development.

## Download test builds

Prebuilt apps are published to GitHub Releases:

- **Latest test builds:** https://github.com/Werd6/Dugeons_and_Desktops/releases/tag/dev
- **All releases:** https://github.com/Werd6/Dugeons_and_Desktops/releases

Grab the build for your platform from the release:

- **macOS:** `Dungeons-and-Desktops-macOS.zip` — unpack and open the app. CI signs and notarizes when the Apple secrets below are set.
- **Windows:** `Dungeons-and-Desktops-Windows-Setup.exe` — run the installer (Start Menu + Desktop shortcuts; no folder juggling). Still unsigned; if SmartScreen warns, choose More info → Run anyway.

CI rebuilds the `dev` prerelease on every push to `main` and on manual **Build apps** workflow runs. Version tags `v*` publish immutable releases.

### macOS signing secrets (GitHub Actions)

Create a **Developer ID Application** certificate in your Apple Developer account, export it as a `.p12`, then add these repository secrets:

| Secret | Value |
| --- | --- |
| `APPLE_CERTIFICATE_BASE64` | `base64 -i YourCert.p12 \| pbcopy` (paste the result) |
| `APPLE_CERTIFICATE_PASSWORD` | Password you set when exporting the `.p12` |
| `CODESIGN_IDENTITY` | Exact name, e.g. `Developer ID Application: Your Name (TEAMID)` |
| `APPLE_TEAM_ID` | 10-character Team ID |

For notarization (recommended), create an [App Store Connect API key](https://appstoreconnect.apple.com/access/integrations/api) with **Developer** access and add:

| Secret | Value |
| --- | --- |
| `APPLE_API_KEY_ID` | Key ID |
| `APPLE_API_ISSUER_ID` | Issuer UUID |
| `APPLE_API_KEY` | Full contents of `AuthKey_XXXXXX.p8` |

Local sign after a PyInstaller build:

```bash
export CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)"
# optional notarization env vars same as above
packaging/macos/sign_and_notarize.sh "dist/Dungeons and Desktops.app"
```

## Setup (macOS / Windows)

Requires Python 3.12+.

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

On macOS this also installs `pyobjc-framework-Quartz`, which desktop mode uses to read window positions. Windows uses Win32 window enumeration via ctypes (no extra dependency).

## Run the desktop pet

New games start with **Dragon, Goblins, and Mimic** (Dragon first). Open **Unlocks…** from the
tray or settings window to claim more monsters and heroes. The Worm requires
**100 total enemy kills**. Each class-linked monster requires **50 kills of its
ordinary enemy class**, and its hero requires **100 kills credited to that monster**
plus claiming the monster first:

| Enemy class | Monster | Hero |
| --- | --- | --- |
| Barbarian | Minotaur | The Mighty |
| Wizard | Lich | The Inquisitive |
| Rogue | Kobolds | The Slayer |
| Paladin | Zombies | The Indomitable |
| Ranger | Drow | The Outlaw |
| Cleric | Graveknights | The Burning Dawn |
| Alchemist | Displacer beast | The Biologist |
| Druid | Chimera | Natures Wrath |
| Sorcerer | Mind flayer | The Darkblood |
| Fighter | Hydra | The Soulforger |

Reaching a target makes its **Unlock** button available; click it to claim the
reward permanently. Claiming preserves your kill totals and skulls. Claimed
monsters join the enabled rotation and can be toggled in **Defenders**. Claimed
heroes become available in **Heroes**, and can appear naturally with a 1% chance
per spawn while no other hero is alive. Kobold/drake kills share the Slayer's
requirement, and drow/lizard kills share the Outlaw's. Skeleton and mind flayer
summon credit also counts toward the corresponding heroes.

Existing saves retain their lifetime kills and skulls; eligible rewards are
ready to claim on the Unlocks page. An old enabled-monster selection cannot
bypass an unlock. The rig preview keeps its full roster for testing.

Desktop mode saves **lifetime progression** after every enemy defeated: one skull,
the enemy's class (named heroes have separate entries), and a kill for the monster
type that landed the finishing hit. The skull counter retains its total across
launches. Open **Lifetime progress…** in the tray or settings menu for both
breakdowns. Summon kills credit their summoner: skeletons count for the lich,
and thralls and intellect devourers count for the mind flayer, even after the
summoner dies. A thrall's own death also earns one skull and credits the mind
flayer, counted under the thrall's original adventurer class. Existing saved
summon kill totals merge into their summoner's totals automatically. Losing
other defenders earns no skulls. Progress is stored locally
alongside the app's preferences using Qt's `QSettings` (`progression/stats`).
The rig preview and `--mock-desktop` keep separate, temporary totals. Tracking
starts with this update; older launches did not save their kill counts.

Resizing a supporting window or switching it to fullscreen preserves living
characters and their HP. If a surface disappears, adventurers fall briefly, get
back up on the current terrain, and continue; the fall does not count as a death.

```bash
.venv/bin/python -m dungeons_desktops --desktop
```

### Build a local app package

```bash
.venv/bin/pip install -e '.[packaging]'
.venv/bin/pyinstaller packaging/dungeons_desktops.spec
```

Outputs land in `dist/` (`Dungeons and Desktops.app` on macOS, an onedir folder on Windows).

A transparent overlay covers the main screen and the creatures run around on your actual app windows: window tops are walkable, window sides and the screen's left and right edges are climbable, window undersides and the top of the screen can be hung from, and the bottom of the screen (above the Dock) is the floor. Every 6 seconds a wandering stickman adventurer of a random class appears at a random screen edge (clinging to the left or right edge, or falling in from the top), up to 8 at a time. Move a window and anyone standing on it rides along; close or minimize it and they fall.

A **mimic** is the first defender: it sits on the frontmost window (or the floor) **disguised as a treasure chest**, drawn front-on: a wooden chest with iron bands, a barrel-topped lid and a brass lock plate in the middle, a gold glint now and then. The tells: it breathes very faintly, and every 3.5 to 7 s its lid twitches. While disguised it is **not a monster** to anyone: it can't be targeted, hit or blasted, wanderers don't go after it, and it doesn't count for seeking. Every 0.4 s it baits its **marks**: the **3 nearest ordinary adventurers** on their feet who can walk up beside it. **Named heroes ignore the bait completely.** Fewer are marked if there aren't 3; anyone with no route there is skipped for 4 s, and a mark who dies or gets away is just dropped. With all 3 baited, a newcomer at least 30% nearer than the farthest mark takes his place until that mark is within 60 px. The first mark to get there springs the trap; the others are let go ("!" and haste gone) the moment it's out of its disguise, or as soon as they arrive while it's still busy with him (they never open it too), so they're right there to fight it. Each mark gets a bouncing yellow **"!"** over his head, drops whatever he was doing (no seeking, wandering or attacking) and hurries over (1.5x his speed, only while he has the "!") by his usual routes. Hurt on the way, he snaps out of it. Beside the chest he **stows his weapon** on his back (0.45 s), bends and **reaches for the lid** (0.35 s) and lifts it a crack, gold light spilling out (0.5 s)... and the trap springs: the lid flies open on a toothy maw, its **tongue** shoots out and wraps round him, yanks him off his feet (flailing) and reels him up over its mouth, and he's **swallowed whole**: he shrinks down into the chest and is gone (body and all, always deadly), the lid snaps shut and the chest bulges with a "GULP!". If the mimic dies or leaves mid-swallow, the tongue lets go and he drops. A regular **rogue** can't be fooled: baited like anyone else, he runs over, but on reaching it he sees through it, starts back and hops away from it (0.4 s), winds up and **throws a dagger** at it. The dagger always lands, forcing it out of its disguise into monster form (its camouflage cooldown starting as on any reveal) and hitting it for 1; he's off the bait as soon as he spots it and goes back to fighting as usual. Disguised again, it may bait him again, and he'll expose it again. Then the mimic is **revealed**: it flips side-on (the front view squashes narrow and the side profile widens out, 0.6 s), the lid now a jaw hinged at the back, gaping forward, and a beady eye on the lid. Like everything else it's drawn **flat**: front-on as a chest, in pure side profile as a monster. On floors and window tops it has **no legs: it hops**, like a Terraria mimic: a squash of anticipation, a stretched launch, its lid flapping (teeth flashing) in the air, then a squashed landing with a puff of dust and a short settle. Each hop is 40 to 60 px long and 16 to 26 px high (about every half second while chasing, more lazily otherwise), with bigger hops across gaps between windows and down drops, and a quick flat flip (squash narrow, widen facing the other way) to turn round between hops. Only to **climb walls and undersides does it grow legs**: eight jointed spider legs, each a two-bone IK chain from a hip on the box to a foot planted on the wall. A planted foot stays put while the body moves on; once it's fallen 6 px behind where it wants to be (out to its side, a little ahead the way it's going), it lifts and swings along a short arc to there (0.09 s) and plants again. The legs step in two alternating groups of four (one group's feet stay down while the other's are up), never more than four up at once, and the knees always bend out away from the body. Hopping at a wall, the legs burst out of it mid-air, its front feet reach out and plant on the wall, and its body swings 90 degrees up round them, the back feet stepping on after. At the top of a wall its front feet step over the corner onto the ceiling or a window's underside as the body swings round; crawling back onto a top it folds its legs away, and dropping off, they fold mid-air and it lands with a squash. It scuttles at 88 px/s up walls and 80 along undersides, on its own terrain (left out wherever a window is too close to fit it). Now it's a monster like any other. It chases the nearest adventurer (sticking with him 1.5 s unless another is much nearer), stopping 14 px short of him on his surface. Within 150 px it **leap-chomps** him: it crouches (0.2 s), leaps at him jaws wide and chomps him on contact for **4 damage**, lands just short of him (never on top of him) and recovers, then waits 1.4 s before the next one. Under 50 px it's a quick **hop-chomp** for the same 4. It only leaps when where it lands puts him within its jaws, along an arc clear of every window, so it never chomps air. Hanging under an underside it can't jump from, it snaps at whoever comes in front of its jaws (also 4). It never attacks thralls. **12 s after the reveal** its camouflage is ready again: on a floor or window top an adventurer can walk up to, it stops where it is; on a wall or underside (or a ledge too short to stand beside it) it first scuttles to the nearest such spot (after 8 s without one, any floor will do). It closes its jaw and turns front-on (0.6 s) and is just a chest again: adventurers fighting it lose interest, and 1.5 s later the next mark gets his "!". It has **10 HP**, and only takes damage while revealed. It survives windows moving (it rides them, in either form) and closing under it (it falls and lands upright). At 0 HP its legs crumple, its lid falls open and a few gold coins spill out before it fades.

A **lich** is the next defender: a tall, gaunt skeleton king (about 1.45x an adventurer's height) in a ragged **black robe** (a faint grey rim keeps it visible on a dark desktop) with a high pointed collar, a bone-white skull with glowing green pinpoint eyes, and a **gold crown** set with green gems. He walks slowly (30 px/s, eased in and out, a slight forward lean, the hem trailing and swaying) with his **right hand held out before him, palm up, a green flame flickering over it**; he turns round smoothly through a three-quarter view toward you, so the flame hand swings round with him. He walks the floor and window tops but never climbs or jumps: to get to another surface he **levitates** (up to 50 px/s), rising or sinking in a clear column beside the windows, gliding on or off at the surface's level and slowing at every corner, green motes drifting under his hem. He hunts the nearest free adventurer (sticking with him at least 1.5 s) but **keeps his distance**: he looks for a spot 180 to 260 px from him (ideally 220) and at least 150 px from every other adventurer, on his own surface if one will do, else on another window he floats to; anyone coming close, he backs away from (at 20 px/s, still facing his foe), and rather than walk past an adventurer he floats over his head. When his foe is **far** (over 400 px away, or more than about 4 s of walking and levitating from a casting spot), or when a group of at least 3 free adventurers (each within 300 px of the one in the middle) has gathered elsewhere that's at least 2 bigger than his foe's group (`CLUSTER_DOOR`, `CLUSTER_GROWTH` in `game/defenders/lich/actor.py`), he casts **dimension door** instead: he raises the flame hand and traces a glowing green and violet door in the air, which swings open while a matching door shimmers into view about 220 px from the adventurer nearest the middle of the **biggest group** of free adventurers (ties go to the group nearer him), who becomes his foe: on that adventurer's surface or a nearby floor or window top, never inside a window, and at least 100 px from every adventurer (`DOOR_CROWD`), so he lands right by the group. He dissolves into motes that stream into the door, steps out of the other one facing his foe, and both doors close and fade (about 1.35 s in all). In transit he can't be targeted or hurt. If the far spot is lost mid-door (its window closes or moves), he picks another or comes back out where he started. Dimension door has a **20 s cooldown** (`DOOR_COOLDOWN` in `game/defenders/lich/actor.py`) and is first ready 4 s after he appears; it isn't one of his queued spells and doesn't advance the queue. Whenever a foe is within **420 px** (`CAST_RANGE`; windows don't block spells) and he's facing him, he **casts** (0.9 s, the spell leaving his hand 0.45 s in) without stopping: he keeps walking, backing off or levitating toward his spot, the gesture laid over his arms and jaw while his hem and glide carry on (never during a dimension door). The flame flares at the release, with a gesture for each spell: a wind-back and an overhand lob from the flame palm for fireball, a bony finger pointed at the foe with his jaw working as he speaks the word for power word kill, a pull-back and palm thrust for magic missiles, both hands thrust forward with lightning crackling between the fingers for chain lightning, and both arms raised then slammed down, palms to the ground, for black tentacles (`GESTURES` in `game/defenders/lich/actor.py`). Spells: **every cast is the next spell in his queue** (`Lich.spells`, `next_spell()`), whoever the foe, wrapping back to the start, from the flame in his palm (`game/defenders/lich/spells.py`). No spell has a cooldown of its own: after each he waits that spell's delay (`SPELL_DELAY` in `game/defenders/lich/actor.py`) before starting the next: 0.9 s after magic missiles, 1.2 s after chain lightning, 1.4 s after fireball, 1.6 s after black tentacles and 2.2 s after power word kill. The queue runs:

- **Fireball**: a glowing bead lobbed in an arc that bursts in green and orange flame on the foe (or the floor), 70 px across, 4 damage to every adventurer caught, flinging them outward and scorching the ground.
- **Power word kill**: a dark rune spins over the foe, flashes, and he dies outright whatever his HP, his soul drawn off in a pale wisp to the lich.
- **Magic missiles**: six homing violet darts fanned out from his palm, 1 damage each: three at the foe, the rest shared among the adventurers within 250 px of him (all six at the foe if he's alone).
- **Chain lightning**: a jagged bolt to the foe that arcs on to up to three more, each the nearest within 160 px of the last, for 3, 3, 2 and 2 damage, stunning each for half a second.
- **Black tentacles**: writhing tentacles erupt from **every surface within 130 px of the foe**, about 20 px apart (44 at most): the floor, window tops, window sides and undersides, and the screen edges, each growing 40 to 55 px out along its surface for 4 s. Each grabs any adventurer in its reach (never a thrall), standing, climbing, hanging or mid-jump: gripped and wrapped, he can't move or fight and is crushed for 1 damage every 0.8 s. Tentacles on a window ride it when it moves and vanish if it closes.

**Divine smite**: whenever one of his spells kills a **cleric**, the cleric's god answers. A huge golden sword of light, point down, with a crossguard and hilt, fades in about 260 px over the lich (or just under the top of the screen) and hangs there glowing for 0.35 s, following him. Then it plunges onto him in 0.15 s for **3 damage** (through the normal monster damage, so it can finish him off), with a flash, a golden ring along the ground and shafts of light. It stays through him for 0.6 s and dissolves into golden motes. It waits for him to come out of a dimension door, fades harmlessly if he dies first, and each cleric killed brings its own sword, 0.3 s apart (`game/defenders/lich/spells.py`, `SMITE_*`). The cleric still rises as a skeleton. Clerics killed by skeletons or other monsters bring no smite.

His spells fly through windows like the adventurers' missiles and never touch thralls. Every adventurer they kill **rises as a skeleton** 1.5 s later where he fell, clawing up out of the ground: a bare-boned warrior with green pinpoint eyes and a sword, 2 HP, hunting with the goblins' brains (`game/defenders/lich/skeletons.py`: the same pathing and overhead chop, each after the adventurer nearest it, keeping elbow room from the others) for 1 damage a blow. Whoever a skeleton kills stays dead. At most 8 skeletons stand at once. Adventurers fight them like any monster; they don't count toward the lich's health bar, and when the last lich falls they crumble a second later. If he can't get within casting range of his foe at all, by walking, levitating or door (an adventurer on a window top too narrow or too high for him, or climbing the screen edge), after 1.5 s he turns to the nearest adventurer he can reach instead (a new foe, so the next spell in the queue) and passes over the first for 4 s; with nobody in reach he waits on the nearest spot he can stand on, facing his foe and casting if he's within about 320 px. He never targets thralls. A window moving carries him; one closing or opening over him, he floats down to safety. At 0 HP (20) he **crumbles**: the robe collapses, skull, crown and bones tumble down, the flame gutters out, and the heap fades.

The **minotaur** comes next: a hulking, bull-headed brute with brown hide, curved horns, hooved digitigrade legs, huge shoulders and a double-bladed greataxe it carries level across its hips in both hands, blades out at its foe. It is **heavy**: it walks the floor and window tops (never walls or undersides) with a dip at every footfall, speeds up and slows down gradually, stops and takes almost half a second to turn round, and only backs up for a short step. It's too tall to stoop under a window hanging less than 56 px above the floor or another window's top, so it goes round. To get up a window side or a screen edge it **climbs**: it grabs the wall, slings its axe on its back and hauls itself up hand over hand, hooves kicking, at a steady 105 px/s, then rolls straight on over the lip onto the top. Its jumps and drops are ballistic arcs, and it absorbs every landing with a crouch and a puff of dust, harder the further it fell. It hunts the nearest free adventurer (sticking with him at least 1.5 s unless someone else is much nearer). With him on the **same flat surface** (the same window top, or the floor) 100 to 450 px off with a clear run (a lone foe only from 170 px; two or more in the way from 100 px), it paws the ground, lowers its horns and **charges**: it can't steer, runs at up to 230 px/s, skids to a stop 60 px past where he stood (or past anyone bunched up just beyond him, but always 14 px short of the end of the surface), and **tramples** everyone it runs through, each once, for **3 damage**, knocking them flat. It is winded for a moment after, and won't charge again for 3.5 s. Up close it fights with its **axe**, and only starts a swing whose arc will reach him: an overhead **smash** (raised high, then brought down) cleaves whoever the head comes down on for **6 damage** and sends a **shock** along the ground that knocks anyone else within 40 px flat for **1 damage**; a quicker level **sweep** round its body for a foe too close for the smash hews him for **4 damage**. Each swing hits at most two adventurers. **Hit from range** (an arrow, a magic missile, a druid's vine or a bomb; a melee blow doesn't do it), it **enrages** for 5 s (refreshed by every ranged hit): its eyes burn red, it moves and charges 1.5x faster, its charge and axe cooldowns run 1.7x faster, and it goes after whoever shot it, climbing walls to get at him: up the side he's clinging to (a window side or the screen edge) to his height, where it punches him off the wall. As at the top and bottom of the screen, it doesn't let a tight spot stop it: up a narrow slot between two windows it squeezes anyway, its bulk clipping into the window beside. An adventurer it really can't get at (hanging under a window far above, with no wall to climb to him) is dropped within about a second for the nearest one it can reach, even while enraged. With nobody in reach it paces to and fro out of the archer's line rather than stand under him, and if it ever makes no headway toward a foe for 1.8 s it gives him up for a few seconds. It never targets thralls. With nobody to hunt it wanders the windows it can reach. It survives windows moving or closing under it: it falls and lands on its feet. At 0 HP it topples onto its back.

A **displacer beast** follows the minotaur: a big, lean, six-legged panther about as long as two stickmen lying down, with blue-black fur that has an indigo sheen, glowing green eyes with slit pupils, small swept-back ears, a long swaying tail, and two barbed tentacles growing from its shoulders. Each tentacle ends in a flat, barbed pad, and they sway and coil over its back. A faint, flickering blue afterimage of it hovers a few pixels off its real body; you can only hit the real one. It goes anywhere a goblin can, with its feet flat on the surface: it **prowls** window tops and the floor in a low six-legged gait, its shoulder blades rolling and its head held level. It **climbs** window sides and the screen edges, and it **crawls upside down** along window undersides and the top of the screen. Its body is a **bending spine** (neck, chest, belly, hips, tail), so round a corner the head and front legs go first onto the next surface while the hips and hind legs follow along behind: it arches over an outside corner and rears up an inside one with its hind feet still on the floor. When it **turns round** it doesn't flip like a paper cutout: it stops, swings its head round toward you (both eyes showing), its legs and tentacles swap sides and its tail comes round last, all in about a third of a second. It won't turn for a short step back and doesn't turn again within 0.7 s, so it never dithers. It slinks along slowly when it's close to someone, prowls at a walk, and breaks into a fast bounding lope over long distances. It also **leaps**. It crouches with its haunches down and its tail flicking, flies a real ballistic arc stretched out with its tentacles streaming behind, and absorbs the landing on a top, a wall or an underside. With nobody around it wanders, now and then leaping to another window. When a free adventurer comes within 400 px it stalks him, slowing as it gets close, then **pounces** from up to 280 px away to land right on him: if he's still there when it arrives it mauls him for **10 damage** (enough to kill anyone), and if he stepped aside it lands where he was. A pounce that lands (kill or not) sends it into a **frenzy** for 3.5 s (1 s longer for each kill, 6 s at most): its illusion vanishes, its tentacles flare up and writhe and its afterimage flickers bright, and it chains quick pounces (a 0.15 s crouch) at the nearest adventurer within 200 px it can leap to, one about every 0.6 s, up to 3 in all, each mauling for 10 damage like any pounce; anyone too close for one gets clawed and stabbed. It calms down early once nobody is left within 200 px (or it's used its 3 pounces and nobody is close). Then it's back to its usual ways, and won't pounce again for 5 s. If he gets too close, it slinks off and stalks him again. It hunts with its **illusion**: the moment it starts stalking someone, the afterimage peels off its body and becomes a see-through, flickering second beast that bounds at him and lands beside him swiping (it does no harm), then leaps over his head to his other side and swipes again, for up to 7 s before it fades away; 2 s after one is gone it sends out the next. The adventurers take it for the real thing and go for it first, even with the real beast nearer: they turn to face it when it's within 160 px, wanderers head for it, and their blows, arrows and spells pass through it with a shimmer and a ripple, doing nothing. Meanwhile the real beast creeps low to about 210 px off, then in to about 140 px once the illusion is out, and pounces the moment the illusion has drawn him: he goes for it (from its first feint, or as soon as he swings at it), or turns his back on the real beast while it's out; or (on a wall or underside) he's fighting it. If he was still fighting the illusion as it vanished, he stays fair game for 2 s. A drawn quarry gets pounced on even if others are at it. It only stalks and sends out its illusion when it has someone to hunt and isn't under attack. When it's been hit (or someone close by is swinging, shooting or casting at it) in the last 3 s, or anyone comes within 110 px, it **fights** instead: it turns on the nearest adventurer (sticking with him at least 1.5 s unless someone else is much nearer, and not turning round for someone right above or below it) and closes in at a prowl or lope on any surface (an illusion already out finishes its ruse on its own). It stops about 28 px short of him on his surface (or, if he's against a wall, on the wall just above him), backing off first if it ends up on top of him. Then it attacks by turns, one attack about every second: a **claw swipe**, rearing up a little and raking out a front paw for **4 damage**, then a **tentacle stab**, its barbed tentacles drawing back and spearing straight at him from its shoulders in any direction (below, behind, above, on walls and undersides, up to 80 px), for **4 damage** to up to two adventurers in line. The stab's aim follows him while the tentacles draw back and locks as they thrust, so a dodge can still make it miss. It never swipes a claw that won't reach him (say he's under or behind it); it stabs instead. It never attacks thralls, and its illusion never does any harm. Left alone for 3 s, it goes back to stalking. The illusion vanishes early if the real beast dies or is knocked off its window, and it never counts toward the health bar or as a kill. It survives windows moving, opening on top of it, or closing under it: it falls and lands on its feet.

A **mind flayer** in a purple robe, a high flared collar and a long dark cape with a crimson lining appears on the frontmost window. It routes like a stickman (window tops, sides, undersides, jumps and drops) but never walks or climbs: it levitates upright a few pixels over a window top, floats beside a window side, hangs just under an underside, glides from one to the next at a fixed height leaning into the way it's going, its cape streaming behind it and its four thick face tentacles always writhing. It hunts whichever free adventurer is nearest, switching as soon as someone else is clearly closer, with three powers. A **mind blast** from range is a slow purple bolt that homes in on him and, without hurting him, leaves him paralysed for 3 seconds (purple sparks circle his head). On a paralysed adventurer in reach it floats up and does a **tentacle grab**: the tentacles wrap his head, and after a second it plants an intellect devourer in his skull. He's now its **thrall**: tinted lavender with a pink brain on his head, he turns on the other adventurers and goes after whichever free one is nearest, attacking for 1 with his own class's weapon: a wizard thrall casts magic missiles, a ranger shoots arrows, an alchemist lobs bombs and a druid lashes vines at them, while the rest strike with whatever they hold. The other adventurers treat him as a monster and attack him; the monsters ignore him. When a thrall dies an **intellect devourer** bursts from his skull, a brain on four clawed legs that gets around like a goblin (scuttling along tops, up window sides, upside down along undersides, dropping off ledges) and pounces on the nearest free adventurer to bite him for 1, springing back off to go again. When anyone free gets close the mind flayer lets out a **psychic pulse**, a ring that flings every adventurer nearby flat; they get up a second later still paralysed for another 1.5 seconds, usually right in tentacle reach.

A **burrow worm** treats your windows as dirt. It tunnels through the inside of windows (and through a band just past the screen edges), shown as a faint silhouette. When a stickman is standing nearby it tunnels toward him and lunges out of the window, fully visible with its mouth open, to snap him up (2-second cooldown): whatever part of him is in its jaws is bitten clean off in a spray of blood that splats onto the windows and floor below, and the rest goes flying. Every stickman it eats makes it a bit thicker and one segment longer, up to twice as thick and 60 segments (about 3 times its starting length). If he's further away it hops into the window under his feet first. With nobody to hunt it meanders and now and then leaps to another window or a screen border. Every breakout sprays dirt, and every landing leaves an impact ring with cracks across the window it hit. Wherever it goes in or out it tears a jagged hole in the window that rides along with it and closes up after about 12 seconds. It rides along when you drag its window, and if you close the window it falls until it hits a window or the screen border.

A **dragon** trots along window tops and the screen floor on four legs (procedural diagonal-pair trot with IK legs), charging any stickman on the same surface and rearing up to claw-swipe whoever gets in melee range. Every so often it takes off: it patrols the screen, spots stickmen in any direction (above or below, ahead or behind: for prey left more than 110 px behind it, `TURN_BEHIND`, it rears up, brakes and wheels round in mid-air), swoops to strafe them with fire breath (anyone caught catches fire, writhes, chars black and burns until the body is gone), then glides back down to land on a random window or the floor. It rides its window when you drag it and takes off if you close it.

Each dragon comes in one of five **colours**, picked at random when it spawns (`SimWorld.add_dragon(variant=...)` picks one; the list and the death messages live in `game/effects/breath.py`). The colours fight exactly the same (same flights, breath timing, reach, spread and damage; only the look and how its victims die differ):

- **Red**: crimson scales and swept-back horns; breathes **fire**. A victim catches fire, writhes, chars black and burns away ("Roasted by the red dragon!").
- **Green**: emerald scales with a yellow-green belly and a rhino-like horn on the tip of its snout; breathes a billowing **poison cloud** that lingers a moment after the breath. A victim turns sickly green, clutches his throat and staggers, then collapses while green fumes rise off him ("Choked on the green dragon's poison!").
- **Blue**: sapphire scales with a pale blue belly and a single unicorn horn from its forehead; breathes a spray of forked **lightning** bolts. A victim goes rigid and jerks with his skeleton flashing through and sparks flying, then drops charred and smoking ("Struck down by the blue dragon's lightning!").
- **Black**: charcoal scales with a violet sheen, a bone-coloured belly and curled ram's horns; spits a spray of **acid** that drips and sizzles where it lands. A victim slumps and melts into a bubbling acid puddle ("Dissolved by the black dragon's acid!").
- **White**: white and ice-blue, with the red dragon's horns; breathes a **cone of cold** glittering with ice crystals. A victim freezes solid where he stands inside a block of ice, then shatters into shards ("Frozen solid by the white dragon!").

**Zombies** are green, adventurer-sized stick figures with hunched shoulders, drooping heads, and both arms stretched forward. Six arrive as a defender pack. They shamble with short, low steps and an uneven pace, moving at no more than half an ordinary adventurer’s walking speed (25 versus 50 points/s). The initial zombies have 6 HP and claw nearby adventurers for 1 damage with a 1.5-second cooldown. They can also claw while climbing walls or hanging from ceilings, briefly pausing their route and keeping one hand attached while the other attacks. Every adventurer killed by a zombie spawns one new zombie at the victim’s position, inheriting the killer’s current HP exactly. Offspring can also reproduce, passing on their remaining HP after any further damage; a kill never heals the parent. There is no pack-size cap. Zombies reserve personal space and gently separate along their current surface: 14 points on floors and ceilings, and 28 when climbing walls. Crowded ledges use the room available without pushing zombies off the edge. Select **Zombies** in the desktop defender settings, or use **Add zombie** in the preview context menu. Their implementation lives in `game/defenders/zombies/`.

The **Graveknights** arrive as a fixed four-role undead squad: an archer with the ranger's bow, a green-eyed helmeted fighter with sword and heater shield, a mage casting the Hero Sorcerer's harming bolt, and a barbarian with a war axe. Nobody swaps weapons. The archer and mage fire while advancing, stop about 100 points from their quarry, and retreat to reopen that firing distance when rushed; the fighter and barbarian charge into melee. They share one quarry and, like zombies, gently destack along their supporting surface without stepping off short ledges. When a regular adventurer lands the killing blow, the slain spirit possesses that killer and turns them into the closest matching Graveknight role; each lineage can jump bodies twice before its next death becomes final. Heroes, thralls, and environmental kills cannot be possessed. Every role has independent HP, damage, cooldown, range, standoff, knockback, and movement-speed tuning (archer 10 HP, fighter 14, mage 9, barbarian 15). Select **Graveknights** in the desktop defender settings, use **Add Graveknights** in the preview, or press `Q` there.

A **goblin war band** of 11 (a standard bearer, six swords and four spears; `PACK` in `game/defenders/goblins/actor.py`) arrives together on the frontmost window and hunts as a pack: while the standard bearer lives they all go after the stickman nearest the flag, and goblins heading back toward the flag move 50% faster so the band closes ranks; once the flag falls, each goblin goes after whoever is nearest itself. They get around exactly like the stickmen do, running, jumping, climbing window sides and mantling ledges, only faster. The **sword goblin** runs him down and chops at him (even while clinging to a wall), the **spear goblin** hangs back on solid footing (never on a wall, where it can't throw) and lobs spears (through any window in the way) that stick quivering where they land, and the **flag bearer** charges along with the war banner and never attacks. Each goblin hit does 1 damage, so a 4 HP adventurer goes down on the 4th hit, counted across all the goblins. With nobody to hunt, the pack roams to a random spot together.

The stickmen are **adventurers**, each from a fantasy class (`CLASSES` in `game/adventurers/model.py`):

- **Barbarian**: a big war axe and double HP (8).
- **Wizard**: a pointed purple hat and a wand; casts a magic missile, three purple darts weaving along a sine wave that home in on a monster and burst.
- **Rogue**: a dagger in each hand (a quick right-left stab); 1.5x faster.
- **Paladin**: a war hammer and a heater shield held up in front; double HP (8).
- **Ranger**: a longbow; raises it, draws to the cheek and looses arrows that arc to a monster (straight through any window in the way), or stick in the floor where they land.
- **Cleric**: white robes and a staff topped with a white orb; raises it to send out a white pulse that heals wounded adventurers nearby (2 HP each).
- **Alchemist**: blue, with a red bomb in hand and two more at the belt; lobs them (leading moving targets; bombs fly straight through windows) to burst on monsters, hitting every monster in the blast for 1 and sparing adventurers. If the worm eats one, his bombs go off in its mouth for 1.
- **Druid**: teal, with an elk-antler crown on a leafy circlet and a gnarled, leafing staff; drives the staff into the ground to send a vine lashing straight at a monster close by. Vines go through the ground and through windows, so the druid is the one adventurer who can hit the worm while it burrows.

Adventurers attack whichever monster comes in reach (melee up close, the wizard, ranger and alchemist from range, the druid's vines through the ground), on their feet or **in the middle of a climb**: clinging to a window side or hanging from an underside, one hand keeps its grip while the weapon comes off the back for the attack and goes back after (the ranger needs both hands, so on a wall he lets go with his hands and stands on his feet; hanging, he keeps the bow in the hand on the ceiling). A climber always faces his wall, so for a monster behind him he swings, stabs, casts or shoots back over his shoulder. Once the fight is over he carries on along his route. Wandering adventurers (every one on the desktop) also **go after monsters**: every half second each looks for the nearest monster within **380 px** (`SEEK_RADIUS` in `game/adventurers/actor.py`) and heads for it, the fighters until it's in reach, the wizard, ranger and alchemist only until it's at 60% of their range, and the cleric to about 80 px off, to heal whoever is in the fight. The druid also spots the worm under the ground; nobody else does. A monster he can't find a way any nearer to (the dragon high in the air, say) he leaves alone for 6 seconds and wanders on. Every attack that lands does 1 damage: an axe chop, a hammer blow, a pair of dagger stabs, an arrow, a magic missile, a druid's vine, or a bomb blast (to each monster caught in it). Monsters have HP: the **minotaur** 36, the **mimic** 10, the **lich** 5, the **dragon** 15, the **displacer beast** 14, the **mind flayer** 12, the **worm** 4 (only the druid can hit it while it's in the ground), each **goblin** 5, and each **intellect devourer** 3; a **thrall** keeps his own adventurer HP. Monsters only hunt adventurers who are on their feet and in their right mind, so they leave thralls (and anyone knocked flat) alone. A monster at 0 HP goes limp like a downed stickman (a goblin ragdolls, the dragon drops out of the sky and sprawls on whatever is below, the worm flops over with whatever is still underground staying put), lies there a few seconds, fades and despawns; the HP live in `game/actors/mortal.py and the owning feature packages`. Adventurers use the same damage system: they have 4 HP (8 for barbarians and paladins), a goblin hit does 1, a thrall's blow or a devourer's bite 1, the dragon's claws or breath do 5, and the worm's bite and the displacer beast's pounce do 10, and the displacer beast's claw swipe and tentacle stab 4 each; the minotaur's charge tramples for 3, its axe smash cleaves for 6 (its ground shock 1), and its axe sweep hews for 4; the mimic's ambush swallows him whole (10, or his HP if more) and its leap- and hop-chomps do 4. A wounded adventurer reddens and bleeds. One breath (of any colour) or one bite only lands once (`HURT_GRACE`), so a barbarian or paladin can survive a pass of dragon fire; the damage numbers live at the top of `game/adventurers/actor.py`.

One monster defends the screen at a time. In the bottom-right corner a kill counter counts stickmen killed, and below it a health bar shows the defender's HP left (for the goblins, the whole war band's total). When the adventurers kill it (every goblin of the band, for the goblins), the next defender takes over: the **mimic** comes first, then the **lich**, then the **minotaur**, then the **displacer beast**, then the **mind flayer**, which hands over (as soon as it dies; its health bar counts only the mind flayer, and any thralls and intellect devourers it leaves behind fight on alongside the next defender) to the **burrow worm**, then a **goblin war band**, then the **dragon**, and back to the mimic. The rotation and the squad size are `DesktopSession(defenders=..., goblin_squad=...)`.

**Getting around.** Stickmen and goblins plan shortest-time routes made of walking, jumping, climbing window sides, mantling over ledges, dropping off them, and **hanging from ceilings**: they climb up a wall, swing round its bottom corner (or, at the top of a screen edge, onto the screen top) and go hand over hand along a window's underside or the top of the screen, weapon slung, then let go to drop onto a window below. That is how a window floating in mid-screen, too high to jump to and with nothing near it, gets reached. Letting go while hanging (from a ceiling or a wall's bottom) may fall up to `max_hang_drop` (1000 px, so practically any drop on a normal screen); walking off a ledge is still capped at `max_drop` (240 px). Low undersides can be jumped up to and grabbed. Wandering stickmen and the goblins' rally points only pick places the planner can actually reach.

Windows are trimmed clear of a narrow lane along the screen sides and just above the floor, so even with a fullscreen app the stickmen can climb the screen edges, walk the floor, and jump up to climb the window. A window whose top is up against the top of the screen (maximized or fullscreen) counts its top from 40 pt below the real edge (`TITLE_BAR` and `NEAR_TOP` in `desktop/session.py`), so creatures stand on its title/tab bar row instead of hugging the menu bar; other windows use their real top edge.

The overlay is display-only: clicks, scrolling and typing go straight through to your apps. Control it from the goblin icon in the menu bar:

| Menu item | Action |
|---|---|
| Pause | Freeze the simulation |
| Hide | Hide the overlay (the simulation keeps running) |
| Show terrain | Outline the window rectangles and the walkable/climbable surfaces |
| Spawn a stickman now | Skip the 6-second wait |
| Show kill counter | Show or hide the kill counter and the defender's health bar |
| Next monster now | Rotate to the next defender without waiting for this one to die |
| Quit Dungeons & Desktops | Quit; Ctrl+C in the launching terminal works too |

`--mock-desktop` runs the same thing on three made-up (outlined) windows instead of your real ones.

Window positions come from Quartz `CGWindowListCopyWindowInfo`. The app only reads window bounds; it never moves, resizes, focuses or closes anything, and it doesn't read titles or contents, so no Screen Recording or Accessibility permission is needed. It polls 8 times a second while windows are moving and twice a second once they settle. If pyobjc is missing, it falls back to the screen edges only.

Current limitations:

- Main screen only; other monitors are ignored.
- Every window is a solid rectangle, including the hidden parts of windows behind others (a window's top is only walkable where nothing covers it).
- Full-screen apps live in their own Space and aren't supported.
- The overlay sits above the menu bar so characters on a maximized window's top stay visible.

**Natures Wrath**, the hero druid, can be added with **Spawn Natures Wrath** in the
desktop settings or tray menu, or **Add Natures Wrath** in the preview. He uses a
slightly taller goblin body, red mohawk, empty hands, and regular druid movement
speeds. His foundation includes health, targeting, navigation, and ragdolls;
his ability rotation runs **Fireball → Giant Bear → Chain Lightning → Magma Dragon**.
The magma dragon strafes for 6 seconds, uses normal dragon AI for 10, then strafes
for 6 more. The red-mohawk bear wanders and charges on walkable surfaces for
30 seconds without climbing. See
[the hero setup](docs/natures-wrath/README.md).

**The Mighty**, the barbarian hero, uses the standard barbarian at **1.5× size**
with thicker orange lines and a larger, broader war axe. Add him with
**Spawn The Mighty** in desktop settings or the tray menu, or **Add The Mighty**
in the preview. He chooses melee, Leap Smash, or Boulder Throw by distance;
every third melee attack becomes a massive ground smash. Damage triggers
10 seconds of rage, refreshed by further damage: twice his hero size, red eyes
and steam, and +2 damage. See [the hero setup](docs/the-mighty/README.md).

**Iggy the Inquisitive**, the gnome wizard hero, has a **half-height pink wizard body**
with slightly thicker lines, a **full-size blue wizard hat**, and a blue cleric-style robe. Use
**Spawn Iggy** in desktop settings or the tray menu, or **Add Iggy** in the preview.
A small cat follows him. His spells have independent cooldowns: **Simulacrum**
(10 seconds, up to four blue 3-HP copies), **Dimension Door** (20 seconds),
**Chromatic Ray** (6 seconds, a sweeping beam that hits multiple enemies),
and a sequential five-shot **Magic Missile** volley
(4 seconds). Copies use the other three spells but cannot summon copies themselves.
Simulacrum casts whenever ready, even outside combat. Chromatic Ray can disintegrate,
melt, polymorph, freeze, or petrify enemies; slain statues shatter. Iggy and his
copies resist the Mind Flayer's stun.
See [the hero setup](docs/the-inquisitive/README.md).

**The Slayer**, the rogue hero, wears a red mouth bandana and a dark trailing cape,
with thick dark gray body lines and serrated daggers held in reverse grip. His
arms swing with his running gait, and he attacks with alternating downward slashes.
After three seconds without attacking, he becomes a translucent shadow: defenders
cannot target him and he is immune to damage. Attacking immediately reveals him
and restarts the timer.
**Assassinate** throws a dagger up to 320 pixels away. Once it embeds, he waits
0.6 seconds, teleports to it, and spins for two seconds, hitting that target four
times per second (2 damage per hit, plus 2 from the dagger). The cooldown is
10 seconds. He spins in place at the teleport location and stays revealed, but
cannot be targeted, hit, damaged, stunned, or knocked down during the spin.
That protection ends immediately when the spin finishes. If the
marked enemy moves out of melee range, each spin hit instead launches a dagger
that deals its damage on impact. Afterward he returns to normal movement or falls
safely to a surface below him; daggers already in flight continue toward their mark.
Every kill credited to The Slayer resets both Assassinate and his melee cooldown,
including kills from thrown daggers that land after the spin ends.
Each kill also immediately triggers the shadow escape below, ending any active
spin, leaving a clone at his current position, blinking backward, and entering
stealth. Kill escapes do not consume his health thresholds.
At 75%, 50%, and 25% HP (once each), a surviving hit makes him leave a stationary
shadow clone, blink backward up to about 160 pixels onto clear terrain, and enter
stealth immediately. He pauses attacks for 0.75 seconds before resuming. The clone
draws defender attacks, dies in one hit, and disappears after four seconds if it
survives; it cannot attack or inherit his abilities. A hit crossing multiple
thresholds causes one escape and consumes all crossed thresholds. Healing does
not restore them, and lethal hits do not trigger an escape.
He keeps the rogue's size, fast movement, and dagger attacks, with 60 HP and a
named hero health bar. Like every named hero, he ignores disguised Mimic bait.
Use **Spawn The Slayer** in desktop settings or the tray menu, or **Add The Slayer**
in the preview.

**The imovable** stands about a head taller than a normal paladin, with exposed
head, full plate armor, and a blue-and-gold tower shield. His forward-angled hammer
is carried in the far hand, behind his body. He has 120 HP and moves at **90% of
normal adventurer speed**. Between fights he patrols clockwise around the screen,
following reachable window surfaces and screen edges. His **760-pixel enemy
detection range** is twice the usual range; he leaves the patrol to pursue a target
and resumes afterward. His melee reach stays the same as a normal paladin's.
His **140-pixel protection aura** makes nearby allied adventurers immune to damage
and gives them golden halos. Defenders prefer him when he is an eligible target.
Allies who join his squad pick idle wander destinations inside his aura and return
to him between fights, while combat pursuit and explicit destinations still work.
Squad members can follow him across hanging surfaces as well as walls and ledges.
Every **third landed melee hit is SMITE**: three divine hammers appear during the
swing and strike the enemy in quick succession, each adding 2 damage to the normal
hit. The Smite also heals living allies inside the aura for **2 HP**, once per
Smite, capped at their maximum health. Misses do not advance the hit counter.
Taking damage also triggers a **hammer throw** at the nearest enemy outside his
normal melee range. He finishes any current swing, winds up, and throws his actual
hammer for **4 damage**; it spins back into his far hand afterward. Only one hammer
can be out at a time, with no additional cooldown. The throw does not advance his
melee counter or trigger Smite healing, and blocked damage does not trigger it.
Use **Spawn The imovable** in desktop settings or the tray menu, or
**Add The imovable** in the preview.

**The Hunter** uses the ranger's green stick-figure proportions and movement, with
thicker body lines and a brown cowboy hat. He carries a long scoped sniper rifle
in both hands, a wood-stock shotgun on his back, and a holstered pistol on each
hip. He has 60 HP and a named hero health bar. His sniper has global range, deals
**10 damage**, and has a **30-second cooldown**. At close range he prioritizes a
**4-damage shotgun cone**, with a **6-second cooldown**; after firing and a brief
recoil, he rolls backward along his current ledge. Between special attacks he
fires both pistols in alternating shots for **0.5 damage per bullet**, stepping
backward while keeping his guns aimed at the enemy. Once he has enough space he
holds his distance and keeps shooting; enemies beyond pistol range draw him closer.
Each weapon keeps its own cooldown, and spare guns stay visibly on his body.
Use **Spawn The Hunter** in desktop settings or the tray menu, or **Add The Hunter**
in the preview.

**Hero Cleric** retains the regular cleric's movement and healing pulse, with **60
HP** and a named hero health bar. His thicker white-gold figure wears the cleric
robe beneath a large radiant halo. The orb on his staff is replaced by a glowing,
twelve-rayed sun that follows the full staff-raising animation. A warm divine aura,
rising motes, and concentric ground light make his presence clear at a glance.
When a regular adventurer dies while he lives, its soul streaks to him and joins
the souls orbiting his aura. **Heroes Never Die!** raises every gathered soul at
his location after they settle into orbit. Each soul has a **25% chance to return
as a cleric**, a **25% chance to return as a paladin**, and otherwise returns as
its original class. Resurrected adventurers return at full health and resume
wandering. The preview's Attack control casts immediately after the souls arrive;
on the desktop he casts automatically after their short visible orbit.
Use **Spawn Hero Cleric** in desktop settings or the tray menu, or **Add Hero Cleric**
in the preview.

**The Soulforger** replaces the old Hero Fighter implementation. He uses the
ordinary Fighter's skeleton, gait, navigation, climbing, and terrain recovery,
with **60 HP**, thicker body lines, fitted full plate, a divine-silver trident,
and a full shield. He has no wings or flight behavior. On aggro he marks one enemy
until it dies or leaves the world, moves at twice normal speed while pursuing it,
and deals +1 damage to it. At range he can throw a piercing spectral trident; on
the same walkable surface he can leap into a six-hit trident-and-shield flurry.
Taking nonfatal damage can also launch a spectral shield at a nearby marked enemy.
Use **Spawn The Soulforger** in desktop settings or the tray menu, or **Add The
Soulforger** in the preview. See [the hero setup](docs/hero-fighter/README.md).

## Run the preview

```bash
.venv/bin/python -m dungeons_desktops
```

The grey boxes stand in for app windows: their tops are walkable (green), their left and right sides are climbable (orange; the dotted part is the bit you can hang from below a floating box), and their undersides can be hung from (orange line just under the box). The preview has no screen top to hang from, so a floating box there is reached through another box's underside. The dashed line is the planned route, colored by move.

The preview starts with just your stickman (green marker); add adventurers and monsters with the keys below. Downed stickmen fade out and despawn after a few seconds (press `Space` first to stand the selected one back up). When your selected stickman despawns, you take over another one, or a new one arrives if none are left.

| Input | Action |
|---|---|
| Drag a goblin | Pick it up and drop it on the surface below |
| `N` / Add stickman, `Q` / Add Graveknights, `G` / Add goblin, `M` / Add worm, `B` / Add dragon, `I` / Add mind flayer, `P` / Add displacer beast, `T` / Add minotaur, `L` / Add lich, `C` / Add mimic | Spawn a wandering adventurer (random class), a four-Graveknight squad, another goblin, a burrow worm, a dragon (random colour), a mind flayer, a displacer beast, a minotaur, a lich, or a mimic (disguised as a chest) |
| `V` | Recolour the dragons to the next colour (red, green, blue, black, white); with no dragon about, a red one flies in |
| `Tab` | Select the next stickman; the keys below act on the selected one |
| Click empty space | Pathfind there (snaps to the nearest surface) |
| Drag a box | Move a "window"; the figure is carried if it stands on it, falls if its support vanishes, and replans otherwise |
| Click a stickman | Knock it over; click again to kick the ragdoll |
| Drag a circled hand or foot | Move that limb's IK target (only while standing still) |
| `W` / Wander | Pick random reachable goals |
| `S` / Stop | Stop wandering and drop the current route |
| `R` / Ragdoll | Turn the motors off and let the figure fall |
| `Space` / Get up | Stand back up on the nearest walkable surface |
| `D` / Surfaces | Toggle the surface overlay |
| `1`-`8` / Class | Switch the figure's class: barbarian, wizard, rogue, paladin, ranger, cleric, alchemist, druid (the button cycles them) |
| `F` / Attack | Use the class's attack (or the cleric's heal) at the nearest monster in reach, else straight ahead |
| `Esc` | Quit |

## Tests

```bash
.venv/bin/pytest -q
.venv/bin/ruff check .
```

Tests are headless and never import Qt or Quartz (the windows and the overlay are not under test; the desktop session runs on scripted fake windows).

## Layout

Game content is grouped by feature. A defender package owns its simulation, model,
equipment, effects, and renderer; shared infrastructure stays at the top level.

```text
src/dungeons_desktops/
  core/                  geometry and the fixed-step clock
  navigation/            terrain extraction and route planning
  rig/                    IK, skeletons, locomotion, ragdolls, generic equipment
  game/
    world/                World protocol, SimWorld, spawning, combat, and terrain
    actors/               shared Actor, Mortal, movement, and hunting foundations
    effects/              shared breath, fire, ballistics, gore, and projectiles
    adventurers/          Stickman behavior, conditions, model, spells, and weapons
    heroes/hero_fighter/  The Soulforger behavior, equipment, and effects
    heroes/natures_wrath/ hero druid behavior, goblin rig, and mohawk
    defenders/<feature>/  each defender's actor, support code, equipment, and renderer
  render/                 primitives, equipment, shared effects, HUD, and scene dispatch
  desktop/                desktop session, persistent menu, windows, and overlay
  preview/                preview controller and window
  systems/                one-release compatibility shims
  creatures/              one-release compatibility shims
```

Tests mirror these packages under `tests/core`, `tests/navigation`, `tests/app`, and
`tests/game`.

### Canonical imports and compatibility

New code imports feature APIs or their focused canonical modules:

```python
from dungeons_desktops.game.world import SimWorld, World
from dungeons_desktops.game.defenders.dragon import Dragon
from dungeons_desktops.game.heroes.hero_fighter import HeroFighter
from dungeons_desktops.rig.equipment import Sword
from dungeons_desktops.render.scene import draw_actors
```

The former `systems.*`, `creatures.*`, `render.draw`, and `rig.weapons` paths remain
as identity-preserving re-export shims for one tagged release. They emit hidden
`DeprecationWarning`s and will be removed in the following release after internal
and external import scans are clean. Do not add new imports through those paths.

### How the pieces fit

- A creature is data: a tuple of `BoneDef`s (length, rest angle, joint limits, mass) plus named IK chains. It also carries gait settings sized to its proportions (`WalkSettings`, `ClimbSettings`), and its module exports navigation reach (`MOVES`, `HANG_REACH`, `MANTLE_DEPTH`, `HANG_DEPTH`) for building its terrain and planner. Resizing a creature means retuning those together.
- Animation drivers set a few angles directly and hand IK targets to the solvers. The solvers produce joint points; `apply_chain_points` converts them to local angles and clamps every joint to its limits, so bones never stretch.
- Navigation never touches bones. `Terrain` turns rectangles into surfaces, `Planner` searches moves between them, and `RouteFollower` turns the route into a contact point plus a pose mode (walk, climb, hang, or air). `LocomotionDriver` turns that into a pose and blends whenever the mode, facing, or surface changes.
- Drivers work facing right; facing left is a mirror of the finished pose.
- Weapons are an upper-body layer (`LocomotionDriver.upper`) that runs after the gait, before mirroring: it re-solves the arms onto the weapon and plays timed actions. The drawn weapon hangs off the displayed hand, so it stays in hand through blends. When climbing or ragdolled the weapon is slung on the back (upside down while hanging, so it doesn't poke through the ceiling); an adventurer's weapon comes out on a wall or ceiling only while an attack plays, re-solving just the weapon arm (`cling_modes`, `two_handed`), and with `reverse` the attack is mirrored about the shoulder to strike behind a climber who has to keep facing his wall.
- The ragdoll uses the same bones. While its motors are on it copies the animated pose every step, so releasing it keeps the animation's momentum. After release it owns the pose until the figure gets up.
- The displacer beast is not a bone rig either: its sim (`game/defenders/displacer/actor.py`) only tracks its feet, its surface normal and a body point, and `game/defenders/displacer/render.py` builds the six legs (two-bone IK), the tail and tentacles (angle chains) and the silhouette fresh every frame. Its terrain is built with `clearance`, which leaves out any stretch of surface with another window, or the edge of the screen, too close above it to fit the beast's body. Each frame `Displacer.spine()` lays its centre line along the surfaces it stands on (walking its terrain both ways from its feet, offset to body height and smoothed round corners), and its yaw (`head_yaw`, `tail_yaw`, 0 facing right, π facing left) turns the body in depth; `to_world` maps a point on its straight body through the yaw and the spine, and both the renderer and hit testing use it. Mid-leap the spine is straight. It flies exact ballistic arcs, checked against the windows grown by its body size, and takes the planner's jumps and drops as short hops.
- The worm is not a bone rig: it's a follow-the-leader chain of points behind a steered head (the same pull FABRIK's forward pass does), which suits a body that should trace its head's path through a tunnel. `FABRIK` is still unused.
