import json
import os
import subprocess
import sys
from textwrap import dedent

import pytest
from PySide6.QtCore import QSettings

from dungeons_desktops.desktop.progression import PROGRESSION_KEY, RECOVERY_KEY, ProgressionStore
from dungeons_desktops.game.progression import SAVE_VERSION, Progression


def settings_at(tmp_path):
    return QSettings(str(tmp_path / "progress.ini"), QSettings.Format.IniFormat)


def test_first_launch_starts_empty_without_writing_settings(tmp_path):
    settings = settings_at(tmp_path)
    store = ProgressionStore(settings)
    assert store.progression == Progression()
    store.flush()
    assert not settings.contains(PROGRESSION_KEY)


@pytest.mark.parametrize("raw", [
    "broken json", "null", "[]", '{"version": 1, "skulls_earned": -1}',
    '{"version": 1, "enemies_killed": {"fighter": true}}',
    '{"version": 1, "monster_kills": []}',
])
def test_bad_save_is_preserved_and_new_progress_can_be_saved(tmp_path, raw):
    settings = settings_at(tmp_path)
    settings.setValue(PROGRESSION_KEY, raw)
    store = ProgressionStore(settings)
    assert store.progression == Progression()
    assert store.error is not None
    store.progression.record_kill("fighter", "goblin")
    assert settings.value(RECOVERY_KEY) == raw
    restored = ProgressionStore(settings_at(tmp_path))
    assert restored.progression.enemies_killed == {"fighter": 1}


def test_future_save_version_is_never_overwritten(tmp_path):
    settings = settings_at(tmp_path)
    raw = json.dumps({"version": SAVE_VERSION + 1, "skulls_earned": 5000})
    settings.setValue(PROGRESSION_KEY, raw)
    store = ProgressionStore(settings)
    store.progression.record_kill("fighter", "goblin")
    store.flush()
    assert settings.value(PROGRESSION_KEY) == raw
    assert store.error is not None


def test_unknown_types_survive_a_save_round_trip(tmp_path):
    store = ProgressionStore(settings_at(tmp_path))
    store.progression.record_kill("future_hero", "future_monster")
    restored = ProgressionStore(settings_at(tmp_path))
    assert restored.progression == store.progression


def test_saved_summon_totals_merge_into_summoners_once_without_extra_skulls(tmp_path):
    settings = settings_at(tmp_path)
    legacy = {
        "version": 1,
        "skulls_earned": 27,
        "enemies_killed": {"wizard": 20, "fighter": 7},
        "monster_kills": {
            "lich": 5, "skeleton": 7,
            "mindflayer": 3, "thrall": 4, "devourer": 6,
            "goblin": 2,
        },
    }
    settings.setValue(PROGRESSION_KEY, json.dumps(legacy))
    for _ in range(3):
        store = ProgressionStore(settings_at(tmp_path))
        progress = store.progression
        assert progress.monster_kills == {"lich": 12, "mindflayer": 13, "goblin": 2}
        assert progress.skulls_earned == progress.total_kills == 27
        assert progress.enemies_killed == legacy["enemies_killed"]
        assert not store.dirty and store.error is None
        # The migration is durable immediately, even before another kill is earned.
        saved = json.loads(settings_at(tmp_path).value(PROGRESSION_KEY))
        assert saved == progress.to_dict()


def test_failed_save_retains_totals_and_retries(tmp_path, monkeypatch):
    settings = settings_at(tmp_path)
    store = ProgressionStore(settings)
    with monkeypatch.context() as patch:
        patch.setattr(settings, "status", lambda: QSettings.Status.AccessError)
        store.progression.record_kill("wizard", "lich")
        assert store.dirty and store.error
        assert store.progression.skulls_earned == 1
    store.flush()
    assert not store.dirty and store.error is None
    assert ProgressionStore(settings_at(tmp_path)).progression == store.progression


def run_script(script, *args):
    result = subprocess.run(
        [sys.executable, "-c", dedent(script), *(str(arg) for arg in args)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_desktop_restarts_keep_totals_even_without_a_clean_exit(tmp_path):
    # Each boot is a fresh process using the actual DesktopPet loading/saving path.
    script = """
        import os
        import sys
        from PySide6.QtCore import QEvent, QSettings
        from PySide6.QtWidgets import QApplication
        from dungeons_desktops.core.geometry import Vec2
        from dungeons_desktops.desktop.overlay import DesktopPet
        from dungeons_desktops.desktop.windows import FakeWindowSource

        app = QApplication([])
        app.setOrganizationName("Progression test")
        app.setApplicationName("Dungeons & Desktops")
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, sys.argv[1])
        previous = int(sys.argv[2])
        pet = DesktopPet(app, FakeWindowSource(), False)
        progress = pet.session.progression
        assert progress.skulls_earned == previous
        assert pet.overlay._kills_seen == previous
        assert pet.session.kills == 0
        victim = pet.session.add_stickman(Vec2(100, pet.session.floor_y), "wizard")
        assert victim.hurt(1000, victim.center(), Vec2(0, 0), "lich", "Defeated")
        assert progress.skulls_earned == previous + 1
        thrall = pet.session.add_stickman(Vec2(200, pet.session.floor_y), "fighter")
        thrall.enthrall()
        assert pet.session.hurt_monster(thrall, 1000, thrall.center(), Vec2(0, 0))
        assert not pet.session.hurt_monster(thrall, 1000, thrall.center(), Vec2(0, 0))
        count = previous // 2 + 1
        assert progress.skulls_earned == previous + 2
        assert progress.enemies_killed == {"wizard": count, "fighter": count}
        assert progress.monster_kills == {"lich": count, "mindflayer": count}

        # Activating the progress window must not raise settings over it.
        pet._activation_menu_ready = True
        pet.defender_menu.show_progress()
        app.sendEvent(app, QEvent(QEvent.Type.ApplicationActivate))
        app.processEvents()
        assert pet.defender_menu.progress_dialog.isVisible()
        assert not pet.defender_menu.isVisible()
        pet.defender_menu.progress_dialog.close()

        # Mock runs have separate in-memory totals, never loading or saving the real ones.
        mock = DesktopPet(app, FakeWindowSource(), False, persist_progress=False)
        assert mock.session.progression.skulls_earned == 0
        mock.session.progression.record_kill("fighter", "dragon")
        assert mock.progress_store is None
        os._exit(0)
    """
    run_script(script, tmp_path, 0)
    run_script(script, tmp_path, 2)
    run_script(script, tmp_path, 4)


def test_progress_menu_shows_saved_counts_and_refreshes_live(tmp_path):
    run_script("""
        from PySide6.QtWidgets import QApplication
        from dungeons_desktops.core.geometry import Rect, Vec2
        from dungeons_desktops.desktop.menu import DefenderMenu
        from dungeons_desktops.desktop.session import DesktopSession
        from dungeons_desktops.desktop.windows import FakeWindowSource
        from dungeons_desktops.game.progression import Progression

        app = QApplication([])
        progress = Progression(12, {"wizard": 12}, {"lich": 12})
        world = DesktopSession(
            Rect(0, 0, 1000, 700), Rect(0, 30, 1000, 600), FakeWindowSource(),
            defenders=(), max_stickmen=0, progression=progress,
        )
        menu = DefenderMenu(world)
        menu.progress_button.click()
        app.processEvents()
        dialog = menu.progress_dialog
        assert dialog.isVisible() and dialog.refresh_timer.isActive()
        assert "Skulls earned: 12" in dialog.summary.text()
        victim = world.add_stickman(Vec2(200, 630), "wizard")
        assert victim.hurt(1000, victim.center(), Vec2(0, 0), "lich", "Defeated")
        dialog.refresh_timer.timeout.emit()
        assert "Skulls earned: 13" in dialog.summary.text()

        def rows(table):
            return {table.item(row, 0).text(): table.item(row, 1).text()
                    for row in range(table.rowCount())}
        assert rows(dialog.enemies)["Wizard"] == "13"
        assert rows(dialog.monsters)["Lich"] == "13"
        assert rows(dialog.monsters)["Dragon"] == "0"
        progress.record_kill("fighter", "skeleton")
        progress.record_kill("fighter", "thrall")
        progress.record_kill("fighter", "devourer")
        dialog.refresh_timer.timeout.emit()
        assert rows(dialog.monsters)["Lich"] == "14"
        assert rows(dialog.monsters)["Mind flayer"] == "2"
        assert not {"Skeleton", "Thrall", "Intellect devourer"} & rows(dialog.monsters).keys()
        dialog.close()
        assert not dialog.refresh_timer.isActive()
        menu.close()
    """)
