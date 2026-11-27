"""Command Board: themed desktop roster, play controls, unlocks and ledger."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from PySide6.QtCore import QSettings, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from dungeons_desktops.desktop.progress_view import ProgressDialog, ProgressPage
from dungeons_desktops.desktop.session import SUPPORTED_DEFENDERS, DesktopSession
from dungeons_desktops.desktop.theme import apply_board, pill_button, section_label
from dungeons_desktops.desktop.unlocks_view import UnlocksDialog, UnlocksPage
from dungeons_desktops.game.defenders.legendary import legendary_name
from dungeons_desktops.game.progression import Progression
from dungeons_desktops.game.unlocks import BASE_DEFENDERS, DEFENDER_NAMES, HERO_NAMES, UNLOCKS

DEFENDERS_KEY = "defenders/enabled"
LEGENDARIES_KEY = "defenders/legendary"
MIN_DEFENDERS = 3
"""How few monsters the roster may keep enabled (you can't uncheck below this)."""
HERO_BUTTON_ATTRIBUTES = {
    "hero_fighter": "spawn_hero_fighter_button",
    "hero_druid": "spawn_natures_wrath_button",
    "hero_barbarian": "spawn_mighty_button",
    "hero_wizard": "spawn_iggy_button",
    "hero_rogue": "spawn_slayer_button",
    "hero_paladin": "spawn_hero_paladin_button",
    "hero_ranger": "spawn_hunter_button",
    "hero_cleric": "spawn_hero_cleric_button",
    "hero_alchemist": "spawn_hero_alchemist_button",
    "hero_sorcerer": "spawn_hero_sorcerer_button",
}

TAB_PLAY = 0
TAB_UNLOCKS = 1
TAB_LEDGER = 2


def load_defenders(
    settings: QSettings,
    progression: Progression | None = None,
) -> tuple[str, ...]:
    """Restore an enabled roster, keeping locked monsters out of the live game."""
    raw = settings.value(DEFENDERS_KEY)
    if raw is None:
        return BASE_DEFENDERS
    try:
        saved = json.loads(str(raw))
    except (json.JSONDecodeError, TypeError):
        return BASE_DEFENDERS
    if not isinstance(saved, list):
        return BASE_DEFENDERS
    available = progression.unlocked_defenders if progression is not None else SUPPORTED_DEFENDERS
    selected = tuple(kind for kind in available if kind in saved)
    # Preserve an explicitly empty rotation; an obsolete locked-only selection
    # should still leave a migrated game playable with its starting monsters.
    return selected if selected or not saved else BASE_DEFENDERS


def save_defenders(settings: QSettings, defenders: tuple[str, ...]) -> None:
    settings.setValue(DEFENDERS_KEY, json.dumps(defenders))
    settings.sync()


def load_legendaries(
    settings: QSettings,
    progression: Progression | None = None,
) -> tuple[str, ...] | None:
    """Which unlocked legendaries the roster prefers. ``None`` means default (all claimed)."""
    raw = settings.value(LEGENDARIES_KEY)
    if raw is None:
        return None
    try:
        saved = json.loads(str(raw))
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(saved, list):
        return None
    claimed = (
        set(progression.unlocked_legendaries)
        if progression is not None
        else set(SUPPORTED_DEFENDERS)
    )
    return tuple(kind for kind in saved if kind in claimed)


def save_legendaries(settings: QSettings, legendaries: Sequence[str]) -> None:
    settings.setValue(LEGENDARIES_KEY, json.dumps(list(legendaries)))
    settings.sync()


class DefenderMenu(QDialog):
    """Themed Command Board: play controls, roster, unlocks and lifetime ledger."""

    unlocks_changed = Signal()

    def __init__(self, session: DesktopSession, settings: QSettings | None = None) -> None:
        super().__init__()
        self.session = session
        self.settings = settings
        self.host: Any | None = None
        self.setObjectName("CommandBoard")
        self.setWindowTitle("Dungeons & Desktops")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        self.resize(460, 620)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Dungeons & Desktops")
        title.setObjectName("BoardTitle")
        header.addWidget(title, 1)
        self.skull_chip = QLabel()
        self.skull_chip.setObjectName("SkullChip")
        header.addWidget(self.skull_chip, 0, Qt.AlignmentFlag.AlignRight)
        layout.addLayout(header)

        # Compatibility controls: tests and the tray still open standalone windows.
        self.unlocks_dialog = UnlocksDialog(session, self)
        self.unlocks_dialog.unlocked.connect(self._unlock_claimed)
        self.unlocks_button = QPushButton("Unlocks…", self)
        self.unlocks_button.hide()
        self.unlocks_button.clicked.connect(self.show_unlocks)
        self.progress_dialog = ProgressDialog(session.progression, self)
        self.progress_button = QPushButton("Lifetime progress…", self)
        self.progress_button.hide()
        self.progress_button.clicked.connect(self.show_progress)

        # Hidden: tests still click these; summons live in the tray only.
        self.hero_buttons: dict[str, QPushButton] = {}
        for variant, attribute in HERO_BUTTON_ATTRIBUTES.items():
            button = QPushButton(f"Spawn {HERO_NAMES[variant]}", self)
            button.hide()
            button.clicked.connect(lambda _checked=False, kind=variant: self.spawn_hero(kind))
            self.hero_buttons[variant] = button
            setattr(self, attribute, button)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self._build_play_tab()
        self._build_unlocks_tab()
        self._build_ledger_tab()

        self.status = QLabel()
        self.status.setObjectName("StatusLine")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        apply_board(self)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(500)
        self.refresh_timer.timeout.connect(self.sync)
        self.sync()

    def bind_host(self, host: Any) -> None:
        """Wire Pause / Hide / terrain / skulls to the live DesktopPet."""
        self.host = host
        self.sync()

    def _build_play_tab(self) -> None:
        page = QWidget()
        page.setObjectName("BoardPage")
        column = QVBoxLayout(page)
        column.addWidget(section_label("Session"))
        toggles = QHBoxLayout()
        self.pause_button = pill_button("Pause", checkable=True)
        self.pause_button.toggled.connect(self._set_paused)
        toggles.addWidget(self.pause_button)
        self.hide_button = pill_button("Hide overlay", checkable=True)
        self.hide_button.toggled.connect(self._set_hidden)
        toggles.addWidget(self.hide_button)
        column.addLayout(toggles)
        toggles2 = QHBoxLayout()
        self.terrain_button = pill_button("Show terrain", checkable=True)
        self.terrain_button.toggled.connect(self._set_show_terrain)
        toggles2.addWidget(self.terrain_button)
        self.kills_button = pill_button("Show skull counter", checkable=True)
        self.kills_button.toggled.connect(self._set_show_kills)
        toggles2.addWidget(self.kills_button)
        column.addLayout(toggles2)

        column.addWidget(
            section_label(
                "Choose which unlocked monsters defend your desktop. Keep at least "
                f"{MIN_DEFENDERS} enabled. With a legendary unlocked: on → legendary → "
                "normal → off."
            )
        )
        self.checkboxes: dict[str, QCheckBox] = {}
        for kind in SUPPORTED_DEFENDERS:
            checkbox = QCheckBox(DEFENDER_NAMES[kind])
            checkbox.toggled.connect(
                lambda checked, monster=kind: self._on_defender_toggled(monster, checked)
            )
            self.checkboxes[kind] = checkbox
            column.addWidget(checkbox)

        column.addStretch()
        self.tabs.addTab(self._scroll(page), "Play")

    def _build_unlocks_tab(self) -> None:
        self.unlocks_page = UnlocksPage(self.session, self)
        self.unlocks_page.unlocked.connect(self._unlock_claimed)
        self.tabs.addTab(self.unlocks_page, "Unlocks")

    def _build_ledger_tab(self) -> None:
        page = QWidget()
        page.setObjectName("BoardPage")
        column = QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        self.ledger_page = ProgressPage(self.session.progression, page)
        column.addWidget(self.ledger_page, 1)
        reset = pill_button("Reset lifetime progress…")
        reset.clicked.connect(self.reset_progress)
        column.addWidget(reset)
        self.tabs.addTab(page, "Ledger")

    @staticmethod
    def _scroll(content: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        return scroll

    def _set_paused(self, paused: bool) -> None:
        if self.host is not None:
            self.host.set_paused(paused)
            if getattr(self.host, "pause_action", None) is not None:
                self.host.pause_action.setChecked(paused)

    def _set_hidden(self, hidden: bool) -> None:
        if self.host is not None:
            self.host.set_hidden(hidden)
            if getattr(self.host, "hide_action", None) is not None:
                self.host.hide_action.setChecked(hidden)

    def _set_show_terrain(self, show: bool) -> None:
        if self.host is not None:
            self.host.set_show_terrain(show)
            if getattr(self.host, "terrain_action", None) is not None:
                self.host.terrain_action.setChecked(show)

    def _set_show_kills(self, show: bool) -> None:
        if self.host is not None:
            self.host.set_show_kills(show)
            if getattr(self.host, "kills_action", None) is not None:
                self.host.kills_action.setChecked(show)

    def sync(self) -> None:
        """Update roster controls and readiness without changing selection."""
        available = self.session.available_defenders
        for kind, checkbox in self.checkboxes.items():
            unlocked = kind in available
            enabled = kind in self.session.defenders
            legendary = enabled and self.session.is_legendary(kind)
            checkbox.blockSignals(True)
            checkbox.setChecked(enabled)
            checkbox.setEnabled(unlocked)
            if not unlocked:
                label = DEFENDER_NAMES[kind] + " — Locked"
                tip = "Visit Unlocks to view the requirement."
            elif legendary:
                label = legendary_name(kind)
                tip = "Click again for the normal form."
            elif enabled:
                label = DEFENDER_NAMES[kind]
                tip = (
                    "Click again to disable."
                    if kind in self.session.progression.unlocked_legendaries
                    else ""
                )
            else:
                label = DEFENDER_NAMES[kind]
                tip = (
                    "Enable as legendary."
                    if kind in self.session.progression.unlocked_legendaries
                    else ""
                )
            checkbox.setText(label)
            checkbox.setToolTip(tip)
            checkbox.blockSignals(False)
        for variant, button in self.hero_buttons.items():
            ready = self.session.can_spawn_hero(variant)
            button.setEnabled(ready)
            button.setToolTip("" if ready else "Claim this hero on the Unlocks page first.")
        ready_count = sum(self.session.progression.can_unlock(unlock.key) for unlock in UNLOCKS)
        self.unlocks_button.setText(
            f"Unlocks… ({ready_count} ready)" if ready_count else "Unlocks…"
        )
        skulls = self.session.progression.skulls_earned
        self.skull_chip.setText(f"☠  {skulls:,}")
        if self.host is not None:
            toggles = (
                self.pause_button,
                self.hide_button,
                self.terrain_button,
                self.kills_button,
            )
            for button in toggles:
                button.blockSignals(True)
            self.pause_button.setChecked(bool(self.host.paused))
            overlay = getattr(self.host, "overlay", None)
            if overlay is not None:
                self.hide_button.setChecked(not overlay.isVisible())
                self.terrain_button.setChecked(bool(overlay.show_terrain))
                self.kills_button.setChecked(bool(overlay.show_kills))
            for button in toggles:
                button.blockSignals(False)
        count = len(self.session.defenders)
        floor = min(MIN_DEFENDERS, len(self.session.available_defenders))
        if count == 0:
            self.status.setText("No defenders enabled")
        elif count <= floor:
            suffix = "monster" if count == 1 else "monsters"
            self.status.setText(f"{count} defender {suffix} enabled (minimum {floor})")
        else:
            suffix = "monster" if count == 1 else "monsters"
            self.status.setText(f"{count} defender {suffix} enabled")
        if self.unlocks_page.isVisible() or self.tabs.currentIndex() == TAB_UNLOCKS:
            self.unlocks_page.refresh()
        if self.ledger_page.isVisible() or self.tabs.currentIndex() == TAB_LEDGER:
            self.ledger_page.refresh()

    def reset_progress(self) -> None:
        """Wipe saved skulls, kills and unlocks, then restore the starting roster."""
        answer = QMessageBox.question(
            self,
            "Reset lifetime progress?",
            "This clears skulls, kill totals and claimed unlocks, and puts the "
            "roster back to Goblins, Mimic and Dragon. You can't undo it.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.session.progression.reset()
        self.session.legendary_prefs.clear()
        self.session.set_defenders(BASE_DEFENDERS)
        self._save_selection()
        self.unlocks_page.refresh()
        self.unlocks_dialog.refresh()
        self.ledger_page.refresh()
        self.progress_dialog.refresh()
        self.sync()
        self.unlocks_changed.emit()

    def show_progress(self) -> None:
        self.hide()
        self.progress_dialog.show()
        self.progress_dialog.raise_()
        self.progress_dialog.activateWindow()

    def show_unlocks(self) -> None:
        self.hide()
        self.unlocks_dialog.show()
        self.unlocks_dialog.raise_()
        self.unlocks_dialog.activateWindow()

    def open_tab(self, index: int) -> None:
        self.tabs.setCurrentIndex(index)
        self.sync()
        self.show()
        self.raise_()
        self.activateWindow()

    def _on_defender_toggled(self, kind: str, checked: bool) -> None:
        """Cycle roster state: off → legendary (if unlocked) → normal → off."""
        if kind not in self.session.available_defenders:
            self.sync()
            return
        has_legendary = kind in self.session.progression.unlocked_legendaries
        enabled = kind in self.session.defenders
        preferring = self.session.prefers_legendary(kind)

        if checked:
            # Enabling (or re-checking). Prefer legendary when available.
            selected = tuple(
                k
                for k in SUPPORTED_DEFENDERS
                if k in self.session.available_defenders
                and (k == kind or k in self.session.defenders)
            )
            self.session.set_defenders(selected)
            if has_legendary:
                self.session.set_legendary_pref(kind, True)
            self._save_selection()
            self.sync()
            return

        # Unchecking.
        if enabled and has_legendary and preferring:
            # Legendary → normal, still enabled.
            self.session.set_legendary_pref(kind, False)
            self._save_selection()
            self.sync()
            return

        selected = tuple(
            k
            for k in SUPPORTED_DEFENDERS
            if k in self.session.defenders and k != kind
        )
        floor = min(MIN_DEFENDERS, len(self.session.available_defenders))
        if len(selected) < floor:
            # Undo the uncheck: stay at the live roster.
            self.sync()
            return
        self.session.set_defenders(selected)
        self.session.set_legendary_pref(kind, False)
        self._save_selection()
        self.sync()

    def _save_selection(self) -> None:
        if self.settings is not None:
            save_defenders(self.settings, self.session.defenders)
            save_legendaries(self.settings, sorted(self.session.legendary_prefs))

    def _unlock_claimed(self, _key: str) -> None:
        self._save_selection()
        self.sync()
        self.unlocks_page.refresh()
        self.unlocks_dialog.refresh()
        self.unlocks_changed.emit()

    def spawn_hero(self, variant: str) -> None:
        if self.session.can_spawn_hero(variant):
            self.session.spawn_at_edge(variant=variant)

    def showEvent(self, event) -> None:  # noqa: N802
        self.sync()
        self.refresh_timer.start()
        self.unlocks_page.refresh_timer.start()
        self.ledger_page.refresh_timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        self.refresh_timer.stop()
        if not self.unlocks_dialog.isVisible():
            self.unlocks_page.refresh_timer.stop()
        if not self.progress_dialog.isVisible():
            self.ledger_page.refresh_timer.stop()
        super().hideEvent(event)


CommandBoard = DefenderMenu
