"""
Valorant-Inspired UI Stylesheet
深海军蓝底 + 米白文字 + 唯一强调色瓦罗兰特红，直角、细线、留白。
"""

ACCENT = "#ff4655"
TEXT = "#ece8e1"
MUTED = "#8a96a3"
DIM = "#5f6b77"
GREEN = "#3ddc97"
AMBER = "#f2b233"

VALORANT_STYLE = """
QMainWindow {
    background-color: #0f1923;
}

QWidget {
    color: #ece8e1;
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 13px;
}

QStackedWidget, QWidget#Page {
    background-color: #0f1923;
}

/* Sidebar Navigation */
#SidebarWidget {
    background-color: #0b131b;
    border-right: 1px solid #1c2833;
}

QLabel#Brand {
    font-family: "Bahnschrift";
    font-size: 21px;
    font-weight: 600;
    color: #ece8e1;
}

QLabel#BrandSub {
    color: #5f6b77;
    font-size: 11px;
}

QPushButton#SidebarButton {
    background-color: transparent;
    color: #8a96a3;
    border: none;
    border-left: 3px solid transparent;
    border-radius: 0px;
    padding: 11px 16px;
    font-size: 14px;
    text-align: left;
}

QPushButton#SidebarButton:hover {
    background-color: #111b25;
    color: #ece8e1;
}

QPushButton#SidebarButton:checked {
    background-color: #16212c;
    color: #ffffff;
    border-left: 3px solid #ff4655;
    font-weight: bold;
}

QLabel#StatusLabel {
    color: #8a96a3;
    font-size: 12px;
}

/* Page headings */
QLabel#HeaderTitle {
    font-size: 22px;
    font-weight: bold;
    color: #ffffff;
}

QLabel#SubTitle {
    font-size: 13px;
    color: #8a96a3;
}

QLabel#CardTitle {
    font-size: 14px;
    font-weight: bold;
    color: #ffffff;
}

QLabel#SectionLabel {
    font-family: "Bahnschrift";
    font-size: 11px;
    font-weight: 600;
    color: #5f6b77;
}

QLabel#FieldLabel {
    color: #c5ccd3;
}

QLabel#ValueLabel {
    font-family: "Bahnschrift";
    font-size: 13px;
    color: #ece8e1;
}

QFrame#DevicePanel {
    background-color: #0b131b;
    border: 1px solid #26333f;
    border-radius: 2px;
}

QLabel#DeviceLabel {
    font-size: 14px;
    font-weight: bold;
    color: #ece8e1;
}

QLabel#HintLabel {
    color: #5f6b77;
    font-size: 12px;
}

QLabel#Badge {
    color: #ff4655;
    border: 1px solid #5c2b35;
    border-radius: 2px;
    padding: 1px 8px;
    font-size: 11px;
}

/* Cards */
QFrame#Card {
    background-color: #16212c;
    border: 1px solid #202d39;
    border-radius: 2px;
}

QFrame#Divider {
    background-color: #202d39;
    max-height: 1px;
    border: none;
}

/* Buttons */
QPushButton {
    background-color: transparent;
    color: #ece8e1;
    border: 1px solid #34444f;
    border-radius: 2px;
    padding: 8px 16px;
    font-size: 13px;
}

QPushButton:hover {
    border-color: #ece8e1;
    background-color: #1a2632;
}

QPushButton:pressed {
    background-color: #0f1923;
}

QPushButton#PrimaryButton {
    background-color: #ff4655;
    color: #ffffff;
    border: none;
    padding: 10px 26px;
    font-size: 15px;
    font-weight: bold;
}

QPushButton#PrimaryButton:hover {
    background-color: #ff5a68;
}

QPushButton#PrimaryButton:pressed {
    background-color: #e63e4c;
}

QPushButton#PrimaryButton:disabled {
    background-color: #4a2c33;
    color: #887077;
}

QPushButton#StopButton {
    background-color: transparent;
    color: #ff4655;
    border: 1px solid #ff4655;
    padding: 10px 26px;
    font-size: 15px;
    font-weight: bold;
}

QPushButton#StopButton:hover {
    background-color: #2a1c25;
}

QPushButton#SegmentButton {
    color: #8a96a3;
    padding: 5px 12px;
    font-size: 12px;
}

QPushButton#SegmentButton:checked {
    background-color: #ff4655;
    border-color: #ff4655;
    color: #ffffff;
    font-weight: bold;
}

QPushButton#LinkButton {
    border: none;
    color: #8a96a3;
    padding: 4px 8px;
}

QPushButton#LinkButton:hover {
    color: #ece8e1;
    background-color: transparent;
}

/* Inputs & ComboBoxes */
QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #0b131b;
    color: #ece8e1;
    border: 1px solid #26333f;
    border-radius: 2px;
    padding: 8px 10px;
    selection-background-color: #ff4655;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border-color: #5f6b77;
}

QTextEdit#LogView {
    border: none;
    background-color: #0b131b;
    padding: 6px 4px;
}

QComboBox {
    background-color: #0b131b;
    color: #ece8e1;
    border: 1px solid #26333f;
    border-radius: 2px;
    padding: 8px 10px;
}

QComboBox:hover {
    border-color: #5f6b77;
}

QComboBox::drop-down {
    border: none;
    width: 26px;
}

QComboBox QAbstractItemView {
    background-color: #16212c;
    color: #ece8e1;
    border: 1px solid #34444f;
    selection-background-color: #ff4655;
    selection-color: #ffffff;
    outline: 0;
    padding: 4px;
}

/* Sliders */
QSlider::groove:horizontal {
    height: 4px;
    background: #26333f;
}

QSlider::sub-page:horizontal {
    background: #ff4655;
}

QSlider::handle:horizontal {
    background: #ece8e1;
    width: 10px;
    margin: -7px 0;
    border-radius: 1px;
}

QSlider::handle:horizontal:hover {
    background: #ffffff;
}

/* CheckBox */
QCheckBox {
    spacing: 10px;
}

QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #5f6b77;
    border-radius: 2px;
    background: #0b131b;
}

QCheckBox::indicator:hover {
    border-color: #ece8e1;
}

QCheckBox::indicator:checked {
    background: #ff4655;
    border-color: #ff4655;
}

/* ScrollBars */
QScrollArea {
    border: none;
    background: transparent;
}

QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 2px;
}

QScrollBar::handle:vertical {
    background: #2c3a46;
    border-radius: 3px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background: #ff4655;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}

QToolTip {
    background-color: #16212c;
    color: #ece8e1;
    border: 1px solid #34444f;
    padding: 6px;
}

QMessageBox {
    background-color: #16212c;
}
"""
