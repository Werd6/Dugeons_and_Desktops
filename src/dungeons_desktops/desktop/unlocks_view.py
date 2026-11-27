"""Claim earned monster and hero unlocks from the lifetime kill totals."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from dungeons_desktops.desktop.theme import apply_board, muted_label, section_label
from dungeons_desktops.game.unlocks import (
    BASE_DEFENDERS,
    DEFENDER_NAMES,
    HERO_NAMES,
    UNLOCK_BY_KEY,
    UNLOCKS,
    Unlock,
)

if TYPE_CHECKING:
    from dungeons_desktops.desktop.session import DesktopSession


class UnlocksPage(QWidget):
    """Kills make an unlock available; the player explicitly claims it here."""

    unlocked = Signal(str)

    def __init__(self, session: DesktopSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("BoardPage")
        self.session = session
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        intro = section_label("Earn kills to reach each milestone, then choose Unlock to claim it.")
        layout.addWidget(intro)
        starters = ", ".join(DEFENDER_NAMES[kind] for kind in BASE_DEFENDERS)
        self.starters = muted_label(f"Starting monsters: {starters}")
        layout.addWidget(self.starters)
        self.summary = QLabel()
        layout.addWidget(self.summary)

        self.buttons: dict[str, QPushButton] = {}
        self.status_labels: dict[str, QLabel] = {}
        self.requirement_labels: dict[str, QLabel] = {}
        self.progress_bars: dict[str, QProgressBar] = {}
        self.tabs = QTabWidget()
        for kind, title in (
            ("monster", "Monsters"),
            ("hero", "Heroes"),
            ("legendary", "Legendaries"),
        ):
            content = QWidget()
            content.setObjectName("BoardPage")
            cards = QVBoxLayout(content)
            for unlock in UNLOCKS:
                if unlock.kind == kind:
                    cards.addWidget(self._card(unlock))
            cards.addStretch()
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setWidget(content)
            self.tabs.addTab(scroll, title)
        layout.addWidget(self.tabs)
        note = muted_label(
            "Hero milestones include kills credited through summons. "
            "Class-path legendaries need that monster's named hero defeated; "
            "starter legendaries each have their own milestone. "
            "Claiming an unlock keeps your skulls and kill totals."
        )
        layout.addWidget(note)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(500)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh()

    def _card(self, unlock: Unlock) -> QGroupBox:
        if unlock.kind == "legendary":
            base = DEFENDER_NAMES.get(unlock.target, unlock.target.title())
            title = f"{base} → {unlock.name}"
        elif unlock.enemy_type is not None:
            title = f"{unlock.enemy_type.title()} → {unlock.name}"
        elif unlock.prerequisite is not None:
            title = f"{UNLOCK_BY_KEY[unlock.prerequisite].name} → {unlock.name}"
        else:
            title = unlock.name
        card = QGroupBox(title)
        layout = QVBoxLayout(card)
        requirement = muted_label()
        self.requirement_labels[unlock.key] = requirement
        layout.addWidget(requirement)
        progress = QProgressBar()
        progress.setRange(0, unlock.threshold)
        self.progress_bars[unlock.key] = progress
        layout.addWidget(progress)
        controls = QHBoxLayout()
        status = QLabel()
        status.setWordWrap(True)
        self.status_labels[unlock.key] = status
        controls.addWidget(status, 1)
        button = QPushButton("Unlock")
        button.clicked.connect(lambda _checked=False, key=unlock.key: self._claim(key))
        self.buttons[unlock.key] = button
        controls.addWidget(button)
        layout.addLayout(controls)
        return card

    def refresh(self) -> None:
        progress = self.session.progression
        ready = 0
        for unlock in UNLOCKS:
            claimed = unlock.key in progress.claimed_unlocks
            available = progress.can_unlock(unlock.key)
            ready += available
            current = progress.unlock_progress(unlock.key)
            bar = self.progress_bars[unlock.key]
            bar.setValue(min(current, unlock.threshold))
            bar.setFormat(f"{current:,} / {unlock.threshold:,}")
            if unlock.pending:
                requirement = "Unlock path coming soon."
            elif unlock.requires_kind == "hero":
                requirement = f"Unlock all {unlock.threshold:,} hero adventurers."
            elif unlock.requires_kind == "legendary":
                requirement = f"Unlock all {unlock.threshold:,} other legendary monsters."
            elif unlock.defender_deaths:
                kinds = " / ".join(kind.replace("_", " ") for kind in unlock.defender_deaths)
                requirement = f"Have {unlock.threshold:,} {kinds}s fall in battle."
            elif unlock.kind == "legendary" and unlock.enemy_type is not None:
                fallback = unlock.enemy_type.replace("_", " ").title()
                hero = HERO_NAMES.get(unlock.enemy_type, fallback)
                requirement = f"Defeat {hero} {unlock.threshold:,} times."
                if unlock.prerequisite and unlock.prerequisite not in progress.claimed_unlocks:
                    requirement += f" Unlock {UNLOCK_BY_KEY[unlock.prerequisite].name} first."
            elif unlock.enemy_type is not None:
                requirement = f"Defeat {unlock.threshold:,} {unlock.enemy_type.title()} enemies."
            elif unlock.prerequisite is not None and unlock.kind == "legendary":
                monster = UNLOCK_BY_KEY[unlock.prerequisite].name
                requirement = f"Defeat {unlock.threshold:,} enemies of any type."
                if unlock.prerequisite not in progress.claimed_unlocks:
                    requirement += f" Unlock {monster} first."
            elif unlock.prerequisite is not None:
                monster = UNLOCK_BY_KEY[unlock.prerequisite].name
                requirement = f"Earn {unlock.threshold:,} kills with {monster}."
                if unlock.prerequisite not in progress.claimed_unlocks:
                    requirement += f" Unlock {monster} first."
            else:
                requirement = f"Defeat {unlock.threshold:,} enemies of any type."
            self.requirement_labels[unlock.key].setText(requirement)
            state = "Unlocked" if claimed else "Ready to unlock" if available else "Locked"
            self.status_labels[unlock.key].setText(state)
            button = self.buttons[unlock.key]
            button.setText("Unlocked" if claimed else "Unlock")
            button.setEnabled(available)
            button.setToolTip(requirement)
        self.summary.setText(f"{ready} unlock{'s' if ready != 1 else ''} ready to claim")

    def _claim(self, key: str) -> None:
        claimed = self.session.claim_unlock(key)
        self.refresh()
        if claimed:
            self.unlocked.emit(key)

    def showEvent(self, event) -> None:  # noqa: N802
        self.refresh()
        self.refresh_timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        # Embedded in the board: keep refreshing while the parent dialog is open.
        if self.window() is self or not self.window().isVisible():
            self.refresh_timer.stop()
        super().hideEvent(event)


class UnlocksDialog(QDialog):
    """Standalone unlocks window (tray / tests); same page as the board's Unlocks tab."""

    unlocked = Signal(str)

    def __init__(self, session: DesktopSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session = session
        self.setWindowTitle("Unlocks — Dungeons & Desktops")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        self.resize(650, 600)
        self.setMinimumSize(440, 360)
        layout = QVBoxLayout(self)
        self.page = UnlocksPage(session, self)
        self.page.unlocked.connect(self.unlocked.emit)
        layout.addWidget(self.page)
        apply_board(self)

    @property
    def buttons(self):
        return self.page.buttons

    @property
    def status_labels(self):
        return self.page.status_labels

    @property
    def requirement_labels(self):
        return self.page.requirement_labels

    @property
    def progress_bars(self):
        return self.page.progress_bars

    @property
    def tabs(self):
        return self.page.tabs

    @property
    def starters(self):
        return self.page.starters

    @property
    def summary(self):
        return self.page.summary

    @property
    def refresh_timer(self):
        return self.page.refresh_timer

    def refresh(self) -> None:
        self.page.refresh()

    def showEvent(self, event) -> None:  # noqa: N802
        self.page.refresh()
        self.page.refresh_timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        self.page.refresh_timer.stop()
        super().hideEvent(event)
