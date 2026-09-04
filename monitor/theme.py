"""Color palette and the global QSS stylesheet for Pulse."""

BG = "#0B0F17"
CARD = "#101826"
CARD_BORDER = "#1D2A3A"
TEXT = "#E6EAF2"
MUTED = "#8B96A8"
FAINT = "#5F6B7E"

CPU = "#22D3EE"
RAM = "#A78BFA"
DISK = "#34D399"
NET_DOWN = "#38BDF8"
NET_UP = "#F472B6"
WARN = "#FBBF24"
DANGER = "#F87171"

STYLESHEET = """
QMainWindow, QDialog {
    background: #0B0F17;
}

QWidget {
    color: #E6EAF2;
    font-size: 13px;
}

QLabel {
    background: transparent;
}

QLabel#appTitle {
    font-size: 21px;
    font-weight: 800;
    color: #F4F7FC;
}

QLabel#appSubtitle {
    color: #8B96A8;
    font-size: 12px;
}

QLabel#chip {
    background: #141E2C;
    border: 1px solid #1F2B3C;
    border-radius: 10px;
    padding: 5px 12px;
    color: #A9B4C6;
    font-size: 12px;
}

QLabel#cardTitle {
    color: #7C8AA0;
    font-size: 11px;
    font-weight: 700;
}

QLabel#cardSub {
    color: #5F6B7E;
    font-size: 11px;
}

QLabel#subValue {
    color: #8B96A8;
    font-size: 12px;
}

QLabel#netValue {
    font-size: 20px;
    font-weight: 700;
    color: #F4F7FC;
}

QLabel#netLabel {
    color: #8B96A8;
    font-size: 11px;
}

QFrame#card {
    background: #101826;
    border: 1px solid #1D2A3A;
    border-radius: 16px;
}

QTableWidget {
    background: transparent;
    border: none;
    alternate-background-color: #121B29;
    selection-background-color: #16324D;
    selection-color: #F4F7FC;
    font-size: 12.5px;
}

QTableWidget::item {
    padding: 5px 10px;
    border: none;
}

QTableWidget::item:selected {
    background: #16324D;
}

QHeaderView {
    background: transparent;
}

QHeaderView::section {
    background: transparent;
    color: #7C8AA0;
    border: none;
    border-bottom: 1px solid #1F2B3C;
    padding: 8px 10px;
    font-size: 11px;
    font-weight: 700;
}

QTableCornerButton::section {
    background: transparent;
    border: none;
}

QComboBox {
    background: #141E2C;
    border: 1px solid #1F2B3C;
    border-radius: 8px;
    padding: 4px 10px;
    color: #A9B4C6;
    font-size: 12px;
}

QComboBox:hover {
    border-color: #2C3E58;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 22px;
    border: none;
}

QComboBox::down-arrow {
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #8B96A8;
}

QComboBox QAbstractItemView {
    background: #101826;
    border: 1px solid #1F2B3C;
    color: #E6EAF2;
    selection-background-color: #16324D;
}

QPushButton {
    background: #1C2941;
    color: #E6EAF2;
    border: none;
    border-radius: 9px;
    padding: 7px 16px;
    font-weight: 600;
    font-size: 12.5px;
}

QPushButton:hover {
    background: #253453;
}

QPushButton:pressed {
    background: #16223A;
}

QPushButton:disabled {
    color: #5F6B7E;
    background: #131C2B;
}

QPushButton#endTask {
    background: transparent;
    border: 1px solid #4A2A34;
    color: #F87171;
}

QPushButton#endTask:hover {
    background: #2A1620;
}

QPushButton#endTask:pressed {
    background: #331B26;
}

QPushButton#endTask:disabled {
    color: #5F6B7E;
    border-color: #1F2B3C;
    background: transparent;
}

QStatusBar {
    background: transparent;
    color: #5F6B7E;
    font-size: 11.5px;
    border-top: 1px solid #16202E;
}

QStatusBar::item {
    border: none;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}

QScrollBar::handle:vertical {
    background: #223047;
    border-radius: 5px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background: #2E3F5C;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
    width: 0;
}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}

QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px;
}

QScrollBar::handle:horizontal {
    background: #223047;
    border-radius: 5px;
    min-width: 30px;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    height: 0;
    width: 0;
}

QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: transparent;
}

QToolTip {
    background: #101826;
    color: #E6EAF2;
    border: 1px solid #1F2B3C;
    padding: 5px 8px;
    border-radius: 6px;
}
"""
