"""Slate–parchment chrome for desktop menus, matching the painted HUD."""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QLabel, QPushButton, QWidget

# Mirrored from render/hud.py and the preview void so menus share the game look.
VOID = QColor(24, 26, 33)
CHIP = QColor(20, 20, 26, 220)
CHIP_SOLID = QColor(32, 34, 44)
CHIP_HOVER = QColor(44, 48, 60)
PARCHMENT = QColor(240, 232, 214)
MUTED = QColor(170, 176, 190)
GOLD = QColor(214, 170, 92)
MINT = QColor(120, 220, 160)
WOUND = QColor(214, 128, 132)
CYAN = QColor(110, 190, 240)


def _hex(color: QColor) -> str:
    if color.alpha() < 255:
        return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha() / 255:.3f})"
    return f"#{color.red():02x}{color.green():02x}{color.blue():02x}"


BOARD_STYLE = f"""
QDialog, QWidget#CommandBoard, QWidget#BoardPage {{
    background-color: {_hex(VOID)};
    color: {_hex(PARCHMENT)};
    font-weight: 700;
    font-size: 12px;
}}
QLabel {{
    color: {_hex(PARCHMENT)};
    background: transparent;
}}
QLabel#MutedLabel, QLabel#SectionHint {{
    color: {_hex(MUTED)};
    font-weight: 600;
    font-size: 11px;
}}
QLabel#BoardTitle {{
    color: {_hex(PARCHMENT)};
    font-size: 15px;
    font-weight: 800;
}}
QLabel#SkullChip {{
    background-color: {_hex(CHIP_SOLID)};
    color: {_hex(PARCHMENT)};
    border-radius: 12px;
    padding: 4px 10px;
    font-size: 12px;
}}
QLabel#StatusLine {{
    color: {_hex(MUTED)};
    font-size: 11px;
}}
QTabWidget::pane {{
    border: 1px solid {_hex(GOLD)};
    border-radius: 8px;
    top: -1px;
    background: {_hex(VOID)};
    padding: 6px;
}}
QTabBar::tab {{
    background: {_hex(CHIP_SOLID)};
    color: {_hex(MUTED)};
    border: 1px solid transparent;
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
    padding: 7px 14px;
    margin-right: 4px;
    font-weight: 700;
}}
QTabBar::tab:selected {{
    color: {_hex(MINT)};
    border: 1px solid {_hex(GOLD)};
    border-bottom-color: {_hex(VOID)};
    background: {_hex(VOID)};
}}
QTabBar::tab:hover:!selected {{
    color: {_hex(PARCHMENT)};
    background: {_hex(CHIP_HOVER)};
}}
QPushButton {{
    background-color: {_hex(CHIP_SOLID)};
    color: {_hex(PARCHMENT)};
    border: 1px solid {_hex(CHIP_HOVER)};
    border-radius: 12px;
    padding: 6px 12px;
    font-weight: 700;
    font-size: 11px;
    min-height: 22px;
}}
QPushButton:hover {{
    background-color: {_hex(CHIP_HOVER)};
    border-color: {_hex(GOLD)};
}}
QPushButton:pressed {{
    border-color: {_hex(GOLD)};
    color: {_hex(GOLD)};
}}
QPushButton:checked {{
    background-color: {_hex(CHIP_HOVER)};
    border-color: {_hex(MINT)};
    color: {_hex(MINT)};
}}
QPushButton:disabled {{
    color: {_hex(WOUND)};
    border-color: {_hex(CHIP_SOLID)};
    background-color: {_hex(CHIP_SOLID)};
}}
QCheckBox {{
    color: {_hex(PARCHMENT)};
    spacing: 8px;
    font-weight: 700;
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border-radius: 4px;
    border: 1px solid {_hex(MUTED)};
    background: {_hex(CHIP_SOLID)};
}}
QCheckBox::indicator:checked {{
    background: {_hex(MINT)};
    border-color: {_hex(MINT)};
}}
QCheckBox::indicator:disabled {{
    border-color: {_hex(WOUND)};
    background: {_hex(CHIP_SOLID)};
}}
QCheckBox:disabled {{
    color: {_hex(WOUND)};
}}
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
QScrollBar:vertical {{
    background: {_hex(VOID)};
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {_hex(CHIP_HOVER)};
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QGroupBox {{
    background-color: {_hex(CHIP_SOLID)};
    border: 1px solid {_hex(CHIP_HOVER)};
    border-radius: 10px;
    margin-top: 12px;
    padding: 12px 10px 10px 10px;
    font-weight: 700;
    color: {_hex(PARCHMENT)};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {_hex(GOLD)};
}}
QProgressBar {{
    background-color: {_hex(CHIP)};
    border: 1px solid {_hex(CHIP_HOVER)};
    border-radius: 8px;
    text-align: center;
    color: {_hex(PARCHMENT)};
    min-height: 16px;
}}
QProgressBar::chunk {{
    background-color: {_hex(MINT)};
    border-radius: 7px;
}}
QTableWidget {{
    background-color: {_hex(VOID)};
    alternate-background-color: {_hex(CHIP_SOLID)};
    color: {_hex(PARCHMENT)};
    gridline-color: {_hex(CHIP_HOVER)};
    border: 1px solid {_hex(CHIP_HOVER)};
    border-radius: 8px;
}}
QHeaderView::section {{
    background-color: {_hex(CHIP_SOLID)};
    color: {_hex(GOLD)};
    border: none;
    border-bottom: 1px solid {_hex(GOLD)};
    padding: 6px 8px;
    font-weight: 700;
}}
QTableWidget::item {{
    padding: 4px 8px;
}}
QMenu {{
    background-color: {_hex(VOID)};
    color: {_hex(PARCHMENT)};
    border: 1px solid {_hex(GOLD)};
    padding: 4px;
}}
QMenu::item {{
    background: transparent;
    padding: 6px 18px 6px 12px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background-color: {_hex(CHIP_HOVER)};
    color: {_hex(MINT)};
}}
QMenu::item:disabled {{
    color: {_hex(WOUND)};
}}
QMenu::separator {{
    height: 1px;
    background: {_hex(CHIP_HOVER)};
    margin: 4px 8px;
}}
"""


def apply_board(widget: QWidget) -> None:
    """Paint `widget` (and its children) with the Command Board stylesheet."""
    widget.setStyleSheet(BOARD_STYLE)
    font = QFont(widget.font())
    font.setBold(True)
    font.setPixelSize(12)
    widget.setFont(font)


def pill_button(text: str, parent: QWidget | None = None, checkable: bool = False) -> QPushButton:
    button = QPushButton(text, parent)
    button.setCheckable(checkable)
    return button


def section_label(text: str, parent: QWidget | None = None) -> QLabel:
    label = QLabel(text, parent)
    label.setObjectName("SectionHint")
    label.setWordWrap(True)
    return label


def muted_label(text: str = "", parent: QWidget | None = None) -> QLabel:
    label = QLabel(text, parent)
    label.setObjectName("MutedLabel")
    label.setWordWrap(True)
    return label
