# colors + the stylesheet. everything visual that isn't painted lives here.
# stylesheet() does token replacement on _TEMPLATE using the current globals,
# so switching themes is: use_light() / use_dark() + re-apply the stylesheet.

DARK = {
    # deep navy, cyan/violet/green accents; tuned by eye, not by a color tool
    "BG": "#0A0E16",
    "CARD": "#0F1622",
    "CARD_TOP": "#131D2D",
    "CARD_BORDER": "#1E2C3E",
    "TITLE_TEXT": "#F5F8FD",
    "TEXT": "#DFE6F0",
    "MUTED": "#8C99AC",
    "FAINT": "#647083",
    "TRACK": "#1C2A40",
    "CORE_BASE": "#2C3E5C",
    "CORE_TRACK": "#131D2C",
    "ALT_ROW": "#121B29",
    "SEL_BG": "#173B5C",
    "SEL_TEXT": "#F5F8FD",
    "CHIP_BG": "#151F2F",
    "CHIP_BORDER": "#223046",
    "CHIP_TEXT": "#A9B6C9",
    "HEAD_BORDER": "#223046",
    "BTN_BG": "#1E2C44",
    "BTN_HOVER": "#28395A",
    "BTN_PRESS": "#18243A",
    "END_BORDER": "#4A2A34",
    "END_HOVER": "#2A1620",
    "END_PRESS": "#331B26",
    "END_TEXT": "#F87171",
    "SCROLL": "#24344E",
    "SCROLL_HOVER": "#31456A",
    "STATUS_BORDER": "#17202E",
    "TOOLTIP_BG": "#101826",
    "INPUT_BG": "#141E2E",
    "INPUT_BORDER": "#223046",
    "CPU": "#22D3EE",
    "RAM": "#A78BFA",
    "DISK": "#34D399",
    "GPU": "#FB923C",
    "NET_DOWN": "#38BDF8",
    "NET_UP": "#F472B6",
    "WARN": "#FBBF24",
    "DANGER": "#F87171",
}

LIGHT = {
    "BG": "#EEF2F8",
    "CARD": "#F6F9FC",
    "CARD_TOP": "#FFFFFF",
    "CARD_BORDER": "#DCE3ED",
    "TITLE_TEXT": "#0E1726",
    "TEXT": "#1E293B",
    "MUTED": "#5F6E85",
    "FAINT": "#8391A5",
    "TRACK": "#DFE7F1",
    "CORE_BASE": "#B3C2D8",
    "CORE_TRACK": "#E8EEF6",
    "ALT_ROW": "#F4F7FB",
    "SEL_BG": "#D7E9FA",
    "SEL_TEXT": "#0E1726",
    "CHIP_BG": "#F0F4F9",
    "CHIP_BORDER": "#E0E6EF",
    "CHIP_TEXT": "#475468",
    "HEAD_BORDER": "#E0E6EF",
    "BTN_BG": "#E1E8F1",
    "BTN_HOVER": "#D2DCE9",
    "BTN_PRESS": "#C4D1E1",
    "END_BORDER": "#F0C9C9",
    "END_HOVER": "#FBE9E9",
    "END_PRESS": "#F5D6D6",
    "END_TEXT": "#C93A3A",
    "SCROLL": "#C3D0E0",
    "SCROLL_HOVER": "#A8BAD0",
    "STATUS_BORDER": "#E0E6EF",
    "TOOLTIP_BG": "#FFFFFF",
    "INPUT_BG": "#F7FAFD",
    "INPUT_BORDER": "#D5DEE9",
    # same hues as dark but darkened to hold up on paper white
    "CPU": "#0891B2",
    "RAM": "#7C3AED",
    "DISK": "#059669",
    "GPU": "#EA580C",
    "NET_DOWN": "#0284C7",
    "NET_UP": "#DB2777",
    "WARN": "#B45309",
    "DANGER": "#DC2626",
}

globals().update(DARK)

_is_dark = True


def use_dark():
    global _is_dark
    _is_dark = True
    globals().update(DARK)


def use_light():
    global _is_dark
    _is_dark = False
    globals().update(LIGHT)


def is_dark():
    return _is_dark


def stylesheet():
    sheet = _TEMPLATE
    # longest keys first; replacing @CARD before @CARD_BORDER would
    # leave '#0F1622_BORDER' in the sheet and qt complains on stderr
    for key in sorted(DARK, key=len, reverse=True):
        sheet = sheet.replace("@" + key, globals()[key])
    return sheet


_TEMPLATE = """
QMainWindow, QDialog {
    background: @BG;
}

QWidget {
    color: @TEXT;
    font-size: 13px;
}

QLabel {
    background: transparent;
}

QLabel#appTitle {
    font-size: 21px;
    font-weight: 800;
    color: @TITLE_TEXT;
}

QLabel#appSubtitle {
    color: @MUTED;
    font-size: 12px;
}

QLabel#chip {
    background: @CHIP_BG;
    border: 1px solid @CHIP_BORDER;
    border-radius: 10px;
    padding: 5px 12px;
    color: @CHIP_TEXT;
    font-size: 12px;
}

QLabel#cardTitle {
    color: @FAINT;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
}

QLabel#cardSub {
    color: @FAINT;
    font-size: 11px;
}

QLabel#subValue {
    color: @MUTED;
    font-size: 12px;
}

QLabel#netValue {
    font-size: 20px;
    font-weight: 700;
    color: @TITLE_TEXT;
}

QFrame#card {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 @CARD_TOP, stop:1 @CARD);
    border: 1px solid @CARD_BORDER;
    border-radius: 14px;
}

QTableWidget {
    background: transparent;
    border: none;
    alternate-background-color: @ALT_ROW;
    selection-background-color: @SEL_BG;
    selection-color: @SEL_TEXT;
    font-size: 12.5px;
}

QTableWidget::item {
    padding: 5px 10px;
    border: none;
}

QTableWidget::item:selected {
    background: @SEL_BG;
}

QHeaderView {
    background: transparent;
}

QHeaderView::section {
    background: transparent;
    color: @FAINT;
    border: none;
    border-bottom: 1px solid @HEAD_BORDER;
    padding: 8px 10px;
    font-size: 11px;
    font-weight: 700;
}

QTableCornerButton::section {
    background: transparent;
    border: none;
}

QComboBox {
    background: @CHIP_BG;
    border: 1px solid @CHIP_BORDER;
    border-radius: 8px;
    padding: 4px 10px;
    color: @CHIP_TEXT;
    font-size: 12px;
}

QComboBox:hover {
    border-color: @SCROLL;
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
    border-top: 5px solid @MUTED;
}

QComboBox QAbstractItemView {
    background: @CARD;
    border: 1px solid @CHIP_BORDER;
    color: @TEXT;
    selection-background-color: @SEL_BG;
}

QLineEdit {
    background: @INPUT_BG;
    border: 1px solid @INPUT_BORDER;
    border-radius: 8px;
    padding: 5px 10px;
    color: @TEXT;
    font-size: 12px;
    selection-background-color: @SEL_BG;
}

QLineEdit:focus {
    border-color: @SCROLL;
}

QPushButton {
    background: @BTN_BG;
    color: @TEXT;
    border: none;
    border-radius: 9px;
    padding: 7px 16px;
    font-weight: 600;
    font-size: 12.5px;
}

QPushButton:hover {
    background: @BTN_HOVER;
}

QPushButton:pressed {
    background: @BTN_PRESS;
}

QPushButton:disabled {
    color: @FAINT;
    background: @ALT_ROW;
}

QPushButton#ghost {
    background: @CHIP_BG;
    border: 1px solid @CHIP_BORDER;
    color: @CHIP_TEXT;
    border-radius: 10px;
    padding: 5px 12px;
    font-size: 12px;
    font-weight: 400;
}

QPushButton#ghost:hover {
    background: @BTN_HOVER;
}

QPushButton#endTask {
    background: transparent;
    border: 1px solid @END_BORDER;
    color: @END_TEXT;
}

QPushButton#endTask:hover {
    background: @END_HOVER;
}

QPushButton#endTask:pressed {
    background: @END_PRESS;
}

QPushButton#endTask:disabled {
    color: @FAINT;
    border-color: @CHIP_BORDER;
    background: transparent;
}

QStatusBar {
    background: transparent;
    color: @FAINT;
    font-size: 11.5px;
    border-top: 1px solid @STATUS_BORDER;
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
    background: @SCROLL;
    border-radius: 5px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background: @SCROLL_HOVER;
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
    background: @SCROLL;
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
    background: @TOOLTIP_BG;
    color: @TEXT;
    border: 1px solid @CHIP_BORDER;
    padding: 5px 8px;
    border-radius: 6px;
}
"""
