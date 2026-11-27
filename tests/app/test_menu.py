import os
import subprocess
import sys
from textwrap import dedent

from PySide6.QtCore import QSettings

from dungeons_desktops.core.geometry import Rect
from dungeons_desktops.desktop.menu import load_defenders, save_defenders
from dungeons_desktops.desktop.session import DesktopSession
from dungeons_desktops.desktop.windows import FakeWindowSource

SCREEN = Rect(0, 0, 1400, 900)
USABLE = Rect(0, 30, 1400, 800)


def make_session() -> DesktopSession:
    return DesktopSession(SCREEN, USABLE, FakeWindowSource(), seed=5, max_stickmen=0)


def test_defender_selection_replaces_a_disabled_current_monster():
    session = make_session()
    session.set_defenders(("drow", "dragon"))
    assert session.defenders == ("drow", "dragon")
    assert session.defender == "drow" and len(session.lizards) == 2
    assert not session.chimeras

    session.set_defenders(("dragon",))
    assert session.defender == "dragon" and len(session.dragons) == 1
    assert not session.lizards


def test_empty_defender_selection_dismisses_the_monster():
    session = make_session()
    session.set_defenders(())
    assert session.defender is None and not session.live_monsters
    assert session.defender_health is None


def test_roster_cannot_drop_below_three_enabled_monsters():
    script = dedent("""
        from PySide6.QtWidgets import QApplication
        from dungeons_desktops.core.geometry import Rect
        from dungeons_desktops.desktop.menu import MIN_DEFENDERS, DefenderMenu
        from dungeons_desktops.desktop.session import DesktopSession
        from dungeons_desktops.desktop.windows import FakeWindowSource

        app = QApplication([])
        session = DesktopSession(
            Rect(0, 0, 1400, 900), Rect(0, 30, 1400, 800), FakeWindowSource(),
            seed=5, max_stickmen=0, defenders=("goblins", "mimic", "dragon", "lich"),
        )
        menu = DefenderMenu(session)
        assert MIN_DEFENDERS == 3
        menu.checkboxes["lich"].setChecked(False)
        app.processEvents()
        assert "lich" not in session.defenders and len(session.defenders) == 3
        menu.checkboxes["dragon"].setChecked(False)
        app.processEvents()
        assert "dragon" in session.defenders and len(session.defenders) == 3
        assert menu.checkboxes["dragon"].isChecked()
        menu.close()
    """)
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_menu_checkboxes_update_and_persist_the_live_rotation(tmp_path):
    script = dedent("""
        import sys
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication
        from dungeons_desktops.core.geometry import Rect
        from dungeons_desktops.desktop.menu import DefenderMenu, load_defenders
        from dungeons_desktops.desktop.session import DEFENDERS, DesktopSession
        from dungeons_desktops.desktop.windows import FakeWindowSource

        app = QApplication([])
        settings = QSettings(sys.argv[1], QSettings.Format.IniFormat)
        session = DesktopSession(
            Rect(0, 0, 1400, 900), Rect(0, 30, 1400, 800), FakeWindowSource(),
            seed=5, max_stickmen=0,
        )
        menu = DefenderMenu(session, settings)
        assert tuple(kind for kind, box in menu.checkboxes.items() if box.isChecked()) == DEFENDERS

        menu.spawn_hero_fighter_button.click()
        app.processEvents()
        assert len(session.heroes) == 1
        assert session.heroes[0].display_name == "The Soulforger"

        menu.spawn_natures_wrath_button.click()
        app.processEvents()
        assert len(session.heroes) == 2
        assert session.heroes[1].display_name == "Natures Wrath"
        assert session.heroes[1].weapon is None

        menu.spawn_mighty_button.click()
        app.processEvents()
        assert len(session.heroes) == 3
        assert session.heroes[2].display_name == "The Mighty"
        assert session.heroes[2].weapon.name == "heavy war axe"

        menu.spawn_iggy_button.click()
        app.processEvents()
        assert len(session.heroes) == 4
        assert session.heroes[3].display_name == "The Inquisitive"
        assert session.heroes[3].variant == "hero_wizard"

        menu.spawn_slayer_button.click()
        app.processEvents()
        assert len(session.heroes) == 5
        assert session.heroes[4].display_name == "The Slayer"
        assert session.heroes[4].variant == "hero_rogue"
        assert session.heroes[4].weapon.name == "jagged daggers"

        menu.spawn_hero_paladin_button.click()
        app.processEvents()
        assert len(session.heroes) == 6
        assert session.heroes[5].display_name == "The Indomitable"
        assert session.heroes[5].variant == "hero_paladin"
        assert session.heroes[5].weapon.name == "warhammer and tower shield"

        menu.spawn_hunter_button.click()
        app.processEvents()
        assert len(session.heroes) == 7
        assert session.heroes[6].display_name == "The Outlaw"
        assert session.heroes[6].variant == "hero_ranger"
        assert session.heroes[6].weapon.name == "sniper rifle"

        menu.spawn_hero_cleric_button.click()
        app.processEvents()
        assert len(session.heroes) == 8
        assert session.heroes[7].display_name == "The Burning Dawn"
        assert session.heroes[7].variant == "hero_cleric"
        assert session.heroes[7].weapon.name == "sun staff"

        menu.spawn_hero_alchemist_button.click()
        app.processEvents()
        assert len(session.heroes) == 9
        assert session.heroes[8].display_name == "The Biologist"
        assert session.heroes[8].variant == "hero_alchemist"
        assert session.heroes[8].weapon.name == "green vials"

        menu.spawn_hero_sorcerer_button.click()
        app.processEvents()
        assert len(session.heroes) == 10
        assert session.heroes[9].display_name == "The Darkblood"
        assert session.heroes[9].variant == "hero_sorcerer"
        assert session.heroes[9].weapon.name == "floating skull"

        menu.checkboxes["chimera"].setChecked(False)
        app.processEvents()
        settings.sync()

        assert session.defenders[0] == "drow"
        assert "chimera" not in session.defenders
        assert session.defender == "drow"
        assert load_defenders(settings) == session.defenders
        menu.close()
    """)
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "menu.ini")],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_menu_selection_persists_for_future_runs(tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    save_defenders(settings, ("mimic", "dragon"))
    settings.sync()

    assert load_defenders(settings) == ("mimic", "dragon")
    restored = DesktopSession(
        SCREEN,
        USABLE,
        FakeWindowSource(),
        seed=5,
        max_stickmen=0,
        defenders=load_defenders(settings),
    )
    assert restored.defenders == ("mimic", "dragon") and restored.defender == "mimic"


def test_command_board_applies_the_slate_theme_and_keeps_roster_controls():
    script = dedent("""
        from PySide6.QtWidgets import QApplication
        from dungeons_desktops.core.geometry import Rect
        from dungeons_desktops.desktop.menu import CommandBoard, DefenderMenu
        from dungeons_desktops.desktop.session import DesktopSession
        from dungeons_desktops.desktop.theme import BOARD_STYLE
        from dungeons_desktops.desktop.windows import FakeWindowSource

        app = QApplication([])
        session = DesktopSession(
            Rect(0, 0, 1400, 900), Rect(0, 30, 1400, 800), FakeWindowSource(),
            seed=5, max_stickmen=0,
        )
        menu = DefenderMenu(session)
        assert isinstance(menu, CommandBoard)
        assert menu.styleSheet() and BOARD_STYLE in menu.styleSheet()
        assert [menu.tabs.tabText(i) for i in range(menu.tabs.count())] == [
            "Play", "Unlocks", "Ledger",
        ]
        assert "dragon" in menu.checkboxes and menu.spawn_mighty_button is not None
        assert menu.quit_button is not None and menu.quit_button.text() == "Quit game"
        assert menu.unlocks_dialog.buttons and menu.progress_dialog.summary is not None
        menu.close()
    """)
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_play_menu_cycles_legendary_then_normal_then_off(tmp_path):
    script = dedent("""
        import sys
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication
        from dungeons_desktops.core.geometry import Rect
        from dungeons_desktops.desktop.menu import DefenderMenu, load_legendaries
        from dungeons_desktops.desktop.session import DesktopSession
        from dungeons_desktops.desktop.windows import FakeWindowSource
        from dungeons_desktops.game.progression import Progression
        from dungeons_desktops.game.unlocks import DEFENDER_NAMES, LEGENDARY_NAMES

        app = QApplication([])
        settings = QSettings(sys.argv[1], QSettings.Format.IniFormat)
        progress = Progression(
            claimed_unlocks={
                "monster:goblins", "monster:mimic", "monster:dragon", "monster:minotaur",
                "legendary:minotaur",
            }
        )
        session = DesktopSession(
            Rect(0, 0, 1400, 900), Rect(0, 30, 1400, 800), FakeWindowSource(),
            seed=5, max_stickmen=0,
            defenders=("goblins", "mimic", "dragon"),
            progression=progress,
            enforce_unlocks=True,
        )
        menu = DefenderMenu(session, settings)
        box = menu.checkboxes["minotaur"]
        assert not box.isChecked()
        assert box.text() == DEFENDER_NAMES["minotaur"]

        # off → legendary
        box.setChecked(True)
        app.processEvents()
        assert "minotaur" in session.defenders
        assert session.is_legendary("minotaur")
        assert box.isChecked() and box.text() == LEGENDARY_NAMES["minotaur"]

        # legendary → normal (still enabled)
        box.setChecked(False)
        app.processEvents()
        assert "minotaur" in session.defenders
        assert not session.is_legendary("minotaur")
        assert box.isChecked() and box.text() == DEFENDER_NAMES["minotaur"]

        # normal → off
        box.setChecked(False)
        app.processEvents()
        assert "minotaur" not in session.defenders
        assert not box.isChecked()
        assert box.text() == DEFENDER_NAMES["minotaur"]

        settings.sync()
        assert load_legendaries(settings, progress) == ()
        menu.close()
    """)
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "legendary_cycle.ini")],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
