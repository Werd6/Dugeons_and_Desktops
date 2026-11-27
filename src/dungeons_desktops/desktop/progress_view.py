"""A live, read-only view of lifetime progression."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from dungeons_desktops.desktop.theme import apply_board, muted_label
from dungeons_desktops.game.adventurers.model import CALLINGS
from dungeons_desktops.game.progression import MONSTER_NAMES, Progression
from dungeons_desktops.game.unlocks import HERO_NAMES


class ProgressPage(QWidget):
    def __init__(self, progression: Progression, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("BoardPage")
        self.progression = progression
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.summary = QLabel()
        layout.addWidget(self.summary)
        layout.addWidget(muted_label("One skull per enemy defeated, including fallen thralls."))
        tabs = QTabWidget()
        self.enemies = self._table("Enemy type", "Defeated")
        self.monsters = self._table("Monster type", "Kills")
        tabs.addTab(self.enemies, "Enemies defeated")
        tabs.addTab(self.monsters, "Monster kills")
        layout.addWidget(tabs)
        layout.addWidget(
            muted_label(
                "Summon kills credit their summoner. Skeletons credit the lich; thralls, "
                "fallen thralls and intellect devourers credit the mind flayer."
            )
        )
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(500)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh()

    @staticmethod
    def _table(kind: str, count: str) -> QTableWidget:
        table = QTableWidget(0, 2)
        table.setAlternatingRowColors(True)
        table.setHorizontalHeaderLabels([kind, count])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        return table

    @staticmethod
    def _fill(table: QTableWidget, names: dict[str, str], counts: dict[str, int]) -> None:
        kinds = sorted(names.keys() | counts.keys(), key=lambda key: names.get(key, key))
        table.setRowCount(len(kinds))
        for row, kind in enumerate(kinds):
            label = names.get(kind, kind.replace("_", " ").title())
            table.setItem(row, 0, QTableWidgetItem(label))
            count = QTableWidgetItem(f"{counts.get(kind, 0):,}")
            count.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row, 1, count)

    def refresh(self) -> None:
        progress = self.progression
        self.summary.setText(
            f"Skulls earned: {progress.skulls_earned:,}    "
            f"Enemies defeated: {progress.total_kills:,}"
        )
        names = {kind: kind.replace("_", " ").title() for kind in CALLINGS}
        names.update(HERO_NAMES)
        self._fill(self.enemies, names, progress.enemies_killed)
        self._fill(self.monsters, MONSTER_NAMES, progress.monster_kills)

    def showEvent(self, event) -> None:  # noqa: N802
        self.refresh()
        self.refresh_timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        if self.window() is self or not self.window().isVisible():
            self.refresh_timer.stop()
        super().hideEvent(event)


class ProgressDialog(QDialog):
    """Standalone ledger window (tray / tests); same page as the board's Ledger tab."""

    def __init__(self, progression: Progression, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.progression = progression
        self.setWindowTitle("Lifetime progress — Dungeons & Desktops")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        self.resize(440, 520)
        layout = QVBoxLayout(self)
        self.page = ProgressPage(progression, self)
        layout.addWidget(self.page)
        apply_board(self)

    @property
    def summary(self):
        return self.page.summary

    @property
    def enemies(self):
        return self.page.enemies

    @property
    def monsters(self):
        return self.page.monsters

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
