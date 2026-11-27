"""The desktop's actual unlock controls and saved claims across fresh processes."""

import os
import subprocess
import sys
from textwrap import dedent


def test_desktop_claims_enable_the_roster_and_hero_and_survive_restart(tmp_path):
    script = dedent("""
        import json
        import os
        import sys
        from PySide6.QtCore import QEvent, QSettings
        from PySide6.QtWidgets import QApplication, QSystemTrayIcon
        from dungeons_desktops.desktop.menu import DEFENDERS_KEY
        from dungeons_desktops.desktop.overlay import DesktopPet
        from dungeons_desktops.desktop.progression import PROGRESSION_KEY
        from dungeons_desktops.desktop.windows import FakeWindowSource
        from dungeons_desktops.game.unlocks import BASE_DEFENDERS

        app = QApplication([])
        app.setOrganizationName("Unlock flow test")
        app.setApplicationName("Dungeons & Desktops")
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, sys.argv[1])
        stage = int(sys.argv[2])
        settings = QSettings()
        if stage == 0:
            # A roster saved before unlocks existed must not grant locked monsters.
            settings.setValue(DEFENDERS_KEY, json.dumps([*BASE_DEFENDERS, "minotaur", "lich"]))
            settings.sync()

        # Exercise the real tray QAction wiring even on the offscreen platform.
        QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: True)
        pet = DesktopPet(app, FakeWindowSource(), False)
        session = pet.session
        progress = session.progression
        menu = pet.defender_menu
        dialog = menu.unlocks_dialog
        monster = "monster:minotaur"
        hero = "hero:hero_barbarian"

        if stage == 0:
            assert session.defenders == BASE_DEFENDERS
            assert not menu.checkboxes["minotaur"].isEnabled()
            assert not menu.checkboxes["lich"].isEnabled()
            assert not menu.spawn_mighty_button.isEnabled()
            assert not pet.hero_actions["hero_barbarian"].isEnabled()
            menu.spawn_mighty_button.click()
            assert not session.heroes
            for _ in range(50):
                progress.record_kill("barbarian", "dragon")
            assert "minotaur" not in session.defenders
            assert not progress.claimed_unlocks
        else:
            assert progress.claimed_unlocks == {monster, hero}
            assert session.defenders == (*BASE_DEFENDERS, "minotaur")
            assert progress.skulls_earned == 150
            assert progress.enemies_killed == {"barbarian": 50, "wizard": 100}
            assert progress.monster_kills == {"dragon": 50, "minotaur": 100}
            assert session.kills == 0

        pet._activation_menu_ready = True
        menu.unlocks_button.click()
        app.sendEvent(app, QEvent(QEvent.Type.ApplicationActivate))
        app.processEvents()
        assert dialog.isVisible()
        assert not menu.isVisible(), "Settings must not obscure the Unlocks page"

        if stage == 0:
            assert dialog.buttons[monster].isEnabled()
            dialog.buttons[monster].click()
            assert monster in progress.claimed_unlocks
            assert session.defenders == (*BASE_DEFENDERS, "minotaur")
            assert menu.checkboxes["minotaur"].isEnabled()
            assert menu.checkboxes["minotaur"].isChecked()
            assert json.loads(settings.value(DEFENDERS_KEY)) == list(session.defenders)
            assert not menu.spawn_mighty_button.isEnabled()
            for _ in range(100):
                progress.record_kill("wizard", "minotaur")
            dialog.refresh_timer.timeout.emit()
            assert dialog.buttons[hero].isEnabled()
            assert hero not in progress.claimed_unlocks
            dialog.buttons[hero].click()

        assert dialog.buttons[monster].text() == "Unlocked"
        assert dialog.buttons[hero].text() == "Unlocked"
        assert not dialog.buttons[monster].isEnabled()
        assert not dialog.buttons[hero].isEnabled()
        assert menu.spawn_mighty_button.isEnabled()
        assert pet.hero_actions["hero_barbarian"].isEnabled()
        assert not pet.hero_actions["hero_wizard"].isEnabled()
        # The other earned milestones remain unclaimed until clicked.
        assert "worm" not in session.defenders and "lich" not in session.defenders
        saved = json.loads(settings.value(PROGRESSION_KEY))
        assert set(saved["claimed_unlocks"]) == {monster, hero}
        assert saved["skulls_earned"] == 150
        menu.spawn_mighty_button.click()
        assert len(session.heroes) == 1
        assert session.heroes[0].display_name == "The Mighty"
        assert session.heroes[0].variant == "hero_barbarian"

        # Claims and rotation must already be durable without shutdown callbacks.
        os._exit(0)
    """)
    for stage in (0, 1):
        result = subprocess.run(
            [sys.executable, "-c", script, str(tmp_path), str(stage)],
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
