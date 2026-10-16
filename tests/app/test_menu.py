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
        assert not menu.checkboxes["elementals"].isChecked()
        assert not menu.checkboxes["ooze"].isChecked()

        menu.spawn_dio_button.click()
        app.processEvents()
        assert len(session.heroes) == 1
        assert session.heroes[0].display_name == "Dio"

        menu.checkboxes["elementals"].setChecked(True)
        menu.checkboxes["chimera"].setChecked(False)
        app.processEvents()
        settings.sync()

        assert session.defenders[0] == "elementals"
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
