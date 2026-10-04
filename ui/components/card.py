from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtGui import QFont


def make_header(parent, title: str, subtitle: str) -> QVBoxLayout:
    """页面标题 + 一句说明。"""
    layout = QVBoxLayout()
    layout.setSpacing(4)
    lbl_title = QLabel(title, parent)
    lbl_title.setObjectName("HeaderTitle")
    lbl_sub = QLabel(subtitle, parent)
    lbl_sub.setObjectName("SubTitle")
    lbl_sub.setWordWrap(True)
    layout.addWidget(lbl_title)
    layout.addWidget(lbl_sub)
    return layout


def make_card(parent, title: str, eyebrow: str = ""):
    """统一的卡片：中文标题 + 英文小标。返回 (card, 内容布局, 标题行布局——可往右侧加按钮)。"""
    card = QFrame(parent)
    card.setObjectName("Card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(20, 16, 20, 18)
    layout.setSpacing(12)

    head = QHBoxLayout()
    head.setSpacing(10)
    lbl_title = QLabel(title, card)
    lbl_title.setObjectName("CardTitle")
    head.addWidget(lbl_title)
    if eyebrow:
        lbl_eyebrow = QLabel(eyebrow.upper(), card)
        lbl_eyebrow.setObjectName("SectionLabel")
        font = lbl_eyebrow.font()
        font.setLetterSpacing(QFont.AbsoluteSpacing, 1.5)
        lbl_eyebrow.setFont(font)
        head.addWidget(lbl_eyebrow)
    head.addStretch()
    layout.addLayout(head)
    return card, layout, head
