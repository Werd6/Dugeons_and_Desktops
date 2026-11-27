"""Unlock claims survive app restarts and old kill totals remain claimable."""

import json
import os
import subprocess
import sys
from textwrap import dedent

from PySide6.QtCore import QSettings

from dungeons_desktops.desktop.progression import PROGRESSION_KEY, ProgressionStore
from dungeons_desktops.game.progression import SAVE_VERSION
from dungeons_desktops.game.unlocks import BASE_DEFENDERS


def settings_at(tmp_path):
    return QSettings(str(tmp_path / "unlocks.ini"), QSettings.Format.IniFormat)


def test_version_one_totals_upgrade_without_automatically_claiming_unlocks(tmp_path):
    legacy = {
        "version": 1,
        "skulls_earned": 150,
        "enemies_killed": {"barbarian": 150},
        "monster_kills": {"minotaur": 100, "goblin": 50},
    }
    settings = settings_at(tmp_path)
    settings.setValue(PROGRESSION_KEY, json.dumps(legacy))
    settings.sync()

    store = ProgressionStore(settings_at(tmp_path))
    progress = store.progression
    assert progress.skulls_earned == progress.total_kills == 150
    assert progress.monster_kills == legacy["monster_kills"]
    assert progress.unlocked_defenders == BASE_DEFENDERS
    assert not progress.claimed_unlocks and not progress.unlocked_heroes
    assert progress.can_unlock("monster:minotaur") and progress.can_unlock("monster:worm")
    assert not progress.can_unlock("hero:hero_barbarian")
    saved = json.loads(settings_at(tmp_path).value(PROGRESSION_KEY))
    assert saved["version"] == SAVE_VERSION
    assert saved["claimed_unlocks"] == []
    assert not store.dirty


def test_claims_are_durable_before_process_exit_and_keep_kills(tmp_path):
    script = dedent("""
        import os
        import sys
        from PySide6.QtCore import QSettings
        from dungeons_desktops.desktop.progression import ProgressionStore
        settings = QSettings(sys.argv[1], QSettings.Format.IniFormat)
        store = ProgressionStore(settings)
        progress = store.progression
        if sys.argv[2] == 'earn':
            for _ in range(50):
                progress.record_kill('barbarian', 'goblin')
            assert progress.claim_unlock('monster:minotaur')
            for _ in range(100):
                progress.record_kill('fighter', 'minotaur')
            assert progress.claim_unlock('hero:hero_barbarian')
        else:
            assert progress.skulls_earned == progress.total_kills == 150
            assert progress.monster_kills == {'goblin': 50, 'minotaur': 100}
            assert progress.enemies_killed == {'barbarian': 50, 'fighter': 100}
            assert progress.unlocked_heroes == ('hero_barbarian',)
            assert 'minotaur' in progress.unlocked_defenders
            assert not progress.claim_unlock('hero:hero_barbarian')
            assert progress.can_unlock('monster:worm')
        os._exit(0)
    """)
    for mode in ("earn", "reload", "reload"):
        result = subprocess.run(
            [sys.executable, "-c", script, str(tmp_path / "restart.ini"), mode],
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stderr
