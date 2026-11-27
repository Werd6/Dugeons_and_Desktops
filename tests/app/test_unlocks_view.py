import os
import subprocess
import sys
from textwrap import dedent


def run_script(script):
    result = subprocess.run(
        [sys.executable, "-c", dedent(script)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_unlocks_page_claims_milestones_live_and_requires_the_monster_first():
    run_script("""
        from PySide6.QtWidgets import QApplication
        from dungeons_desktops.desktop.unlocks_view import UnlocksDialog
        from dungeons_desktops.game.progression import Progression

        class Session:
            def __init__(self):
                self.progression = Progression(
                    49, {"barbarian": 49}, {"minotaur": 100},
                )

            def claim_unlock(self, key):
                return self.progression.claim_unlock(key)

        app = QApplication([])
        session = Session()
        dialog = UnlocksDialog(session)
        events = []
        dialog.unlocked.connect(events.append)
        monster = "monster:minotaur"
        hero = "hero:hero_barbarian"
        assert "Goblins, Mimic, Dragon" in dialog.starters.text()
        assert not dialog.buttons[monster].isEnabled()
        assert not dialog.buttons[hero].isEnabled()
        assert "Unlock Minotaur first" in dialog.requirement_labels[hero].text()
        assert dialog.status_labels[monster].text() == "Locked"
        dialog.show()
        app.processEvents()
        assert dialog.refresh_timer.isActive()
        assert dialog.height() <= 600

        session.progression.record_kill("barbarian", "dragon")
        dialog.refresh_timer.timeout.emit()
        assert not session.progression.claimed_unlocks
        assert dialog.progress_bars[monster].format() == "50 / 50"
        assert dialog.status_labels[monster].text() == "Ready to unlock"
        assert dialog.buttons[monster].isEnabled()
        assert not dialog.buttons[hero].isEnabled()
        skulls = session.progression.skulls_earned
        dialog.buttons[monster].click()
        assert events == [monster]
        assert "minotaur" in session.progression.unlocked_defenders
        assert dialog.status_labels[monster].text() == "Unlocked"
        assert not dialog.buttons[monster].isEnabled()
        assert dialog.buttons[hero].isEnabled()
        assert dialog.status_labels[hero].text() == "Ready to unlock"
        dialog.buttons[monster].click()
        assert events == [monster]
        dialog.buttons[hero].click()
        assert events == [monster, hero]
        assert "hero_barbarian" in session.progression.unlocked_heroes
        assert session.progression.skulls_earned == skulls

        dialog.close()
        assert not dialog.refresh_timer.isActive()
        session.progression = Progression.from_dict(session.progression.to_dict())
        reopened = UnlocksDialog(session)
        assert reopened.buttons[monster].text() == "Unlocked"
        assert reopened.buttons[hero].text() == "Unlocked"
        assert not reopened.buttons[hero].isEnabled()
    """)


def test_worm_uses_total_kills_and_progress_bars_keep_actual_counts():
    run_script("""
        from PySide6.QtWidgets import QApplication, QScrollArea
        from dungeons_desktops.desktop.unlocks_view import UnlocksDialog
        from dungeons_desktops.game.progression import Progression
        from dungeons_desktops.game.unlocks import UNLOCKS

        class Session:
            def __init__(self):
                self.progression = Progression(
                    99, {"fighter": 49, "wizard": 50}, {"dragon": 99},
                )

            def claim_unlock(self, key):
                return self.progression.claim_unlock(key)

        app = QApplication([])
        session = Session()
        dialog = UnlocksDialog(session)
        worm = "monster:worm"
        assert len(dialog.buttons) == len(UNLOCKS)
        assert not dialog.buttons[worm].isEnabled()
        session.progression.record_kill("rogue", "dragon")
        dialog.refresh()
        assert dialog.buttons[worm].isEnabled()
        assert dialog.progress_bars[worm].format() == "100 / 100"
        dialog.buttons[worm].click()
        assert "worm" in session.progression.unlocked_defenders

        for _ in range(200):
            session.progression.record_kill("barbarian", "minotaur")
        dialog.refresh()
        assert dialog.progress_bars["monster:minotaur"].value() == 50
        assert dialog.progress_bars["monster:minotaur"].format() == "200 / 50"
        assert not dialog.buttons["hero:hero_barbarian"].isEnabled()
        assert "any type" in dialog.requirement_labels[worm].text()
        assert all(isinstance(dialog.tabs.widget(i), QScrollArea)
                   for i in range(dialog.tabs.count()))
    """)
