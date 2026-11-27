"""Durable progress stored beside the desktop application's other preferences."""

from __future__ import annotations

import json
import logging

from PySide6.QtCore import QSettings

from dungeons_desktops.game.progression import SAVE_VERSION, Progression

PROGRESSION_KEY = "progression/stats"
RECOVERY_KEY = "progression/recovery"
logger = logging.getLogger(__name__)


class ProgressionStore:
    """Save counters and unlock claims immediately, without waiting for app exit."""

    def __init__(self, settings: QSettings) -> None:
        self.settings = settings
        self.dirty = False
        self.error: str | None = None
        self._recovery: str | None = None
        self._read_only = False
        self.progression = self._load()
        self.progression.on_change = self._changed
        self.flush()

    def _load(self) -> Progression:
        raw = self.settings.value(PROGRESSION_KEY)
        if raw is None:
            return Progression()
        try:
            data = json.loads(str(raw))
            if (
                isinstance(data, dict)
                and type(data.get("version")) is int
                and data["version"] > SAVE_VERSION
            ):
                # An older app must never replace a newer app's save.
                self._read_only = True
                raise ValueError("Progress was saved by a newer version of the app")
            progression = Progression.from_dict(data)
            self.dirty = (
                data["version"] != SAVE_VERSION
                or progression.monster_kills != data.get("monster_kills", {})
                or sorted(progression.claimed_unlocks) != data.get("claimed_unlocks", [])
            )
            return progression
        except (ValueError, TypeError) as error:
            self.error = str(error)
            self._recovery = str(raw)
            logger.warning("Could not load progress: %s. Original save retained.", error)
            return Progression()

    def _changed(self) -> None:
        self.dirty = True
        self.flush()

    def flush(self) -> None:
        """Retry pending writes after a storage error; clean saves need no work."""
        if not self.dirty or self._read_only:
            return
        if self._recovery is not None:
            self.settings.setValue(RECOVERY_KEY, self._recovery)
        self.settings.setValue(PROGRESSION_KEY, json.dumps(self.progression.to_dict()))
        self.settings.sync()
        if self.settings.status() != QSettings.Status.NoError:
            message = "Could not save progress; keeping totals in memory and retrying."
            if self.error != message:
                logger.warning(message)
            self.error = message
            return
        self.dirty = False
        self._recovery = None
        self.error = None
