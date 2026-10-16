"""The desktop app's small settings window."""

from __future__ import annotations

import json

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QCheckBox, QDialog, QLabel, QPushButton, QVBoxLayout

from dungeons_desktops.desktop.session import DEFENDERS, SUPPORTED_DEFENDERS, DesktopSession

DEFENDERS_KEY = "defenders/enabled"

DEFENDER_NAMES = {
    "elementals": "Elemental",
    "ooze": "Ooze",
    "chimera": "Chimera",
    "drow": "Drow lizard riders",
    "drakes": "Kobold drake riders",
    "hydra": "Hydra",
    "mimic": "Mimic",
    "lich": "Lich",
    "minotaur": "Minotaur",
    "displacer": "Displacer beast",
    "mindflayer": "Mind flayer",
    "worm": "Worm",
    "goblins": "Goblins",
    "dragon": "Dragon",
}


def load_defenders(settings: QSettings) -> tuple[str, ...]:
    """Load the enabled roster, falling back to the normal rotation on first run."""
    raw = settings.value(DEFENDERS_KEY)
    if raw is None:
        return DEFENDERS
    try:
        saved = json.loads(str(raw))
    except (json.JSONDecodeError, TypeError):
        return DEFENDERS
    if not isinstance(saved, list):
        return DEFENDERS
    return tuple(kind for kind in SUPPORTED_DEFENDERS if kind in saved)


def save_defenders(settings: QSettings, defenders: tuple[str, ...]) -> None:
    settings.setValue(DEFENDERS_KEY, json.dumps(defenders))


class DefenderMenu(QDialog):
    """Checkboxes that update the live defender rotation as they are changed."""

    def __init__(self, session: DesktopSession, settings: QSettings | None = None) -> None:
        super().__init__()
        self.session = session
        self.settings = settings
        self.setWindowTitle("Dungeons & Desktops")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        self.setMinimumWidth(300)

        layout = QVBoxLayout(self)
        heading = QLabel("<b>Defender rotation</b>")
        heading.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(heading)
        layout.addWidget(QLabel("Choose which monsters can defend your desktop."))

        self.checkboxes: dict[str, QCheckBox] = {}
        for kind in SUPPORTED_DEFENDERS:
            checkbox = QCheckBox(DEFENDER_NAMES[kind])
            checkbox.setChecked(kind in session.defenders)
            checkbox.toggled.connect(self._apply_selection)
            self.checkboxes[kind] = checkbox
            layout.addWidget(checkbox)

        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        hero_heading = QLabel("<b>Heroes</b>")
        hero_heading.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(hero_heading)
        self.spawn_dio_button = QPushButton("Spawn Dio")
        self.spawn_dio_button.clicked.connect(self._spawn_dio)
        layout.addWidget(self.spawn_dio_button)
        self._update_status()

    def sync(self) -> None:
        """Reflect changes made outside the menu before showing it again."""
        enabled = set(self.session.defenders)
        for kind, checkbox in self.checkboxes.items():
            checkbox.blockSignals(True)
            checkbox.setChecked(kind in enabled)
            checkbox.blockSignals(False)
        self._update_status()

    def _apply_selection(self) -> None:
        selected = tuple(
            kind for kind in SUPPORTED_DEFENDERS if self.checkboxes[kind].isChecked()
        )
        self.session.set_defenders(selected)
        if self.settings is not None:
            save_defenders(self.settings, selected)
        self._update_status()

    def _spawn_dio(self) -> None:
        self.session.spawn_at_edge(variant="hero_fighter")

    def _update_status(self) -> None:
        count = len(self.session.defenders)
        if count:
            suffix = "monster" if count == 1 else "monsters"
            self.status.setText(f"{count} defender {suffix} enabled")
        else:
            self.status.setText("No defenders enabled")
