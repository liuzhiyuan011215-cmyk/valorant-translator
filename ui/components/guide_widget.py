from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QPushButton, QStyle
)
from PySide6.QtGui import QFont, QPixmap

from ui.components.card import make_header

class GuideWidget(QWidget):
    """
    Step-by-Step Audio & Valorant Setup Guide Widget.
    Recreates the tutorial cards from user reference screenshots.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(28, 24, 28, 24)
        main_layout.setSpacing(16)

        # Header
        main_layout.addLayout(make_header(
            self, "使用指南", "第一次使用按下面 4 步设置好声卡和游戏，之后只需要点「开始同传」"
        ))

        # Scroll Area for setup cards
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)

        container = QWidget()
        container.setObjectName("Page")
        c_layout = QVBoxLayout(container)
        c_layout.setSpacing(12)
        c_layout.setContentsMargins(0, 0, 6, 0)

        # Step 1: Install VB-Cable
        c_layout.addWidget(self.create_step_card(
            step_num="1",
            title="安装 VB-Cable 虚拟声卡",
            badge_text="必备配置",
            content=(
                "到 vb-audio.com/Cable 下载 VB-CABLE Driver（免费），解压后右键「以管理员身份运行」VBCABLE_Setup_x64.exe，装完重启电脑。\n"
                "软件会自动找到 CABLE Output 并用它收音，不需要手动选设备。只有队友语音会进这条虚拟声卡，游戏枪声、音乐不会干扰识别。"
            )
        ))

        # Step 2: Valorant Audio Output Setup
        c_layout.addWidget(self.create_step_card(
            step_num="2",
            title="把游戏语音输出切到 CABLE Input",
            badge_text="游戏内设置",
            content=(
                "以 Valorant (无畏契约) 为例：\n"
                "1. 进入 游戏设置 → 音频 (AUDIO) → 语音聊天 (VOICE CHAT)。\n"
                "2. 把【输出设备 (Output Device)】改为 CABLE Input (VB-Audio Virtual Cable)。\n"
                "3. 麦克风设备保持你原来的硬件麦克风，不要修改。\n"
                "4. 自己也要听到队友：Windows 声音设置 → 更多声音设置 → 录制 → CABLE Output → 属性 → 侦听，"
                "勾选「侦听此设备」，播放设备选你的耳机。"
            )
        ))

        # Step 3: Adjust Incoming Volume
        c_layout.addWidget(self.create_step_card(
            step_num="3",
            title="适量调大队友音量 (Incoming Volume)",
            badge_text="识别优化",
            content=(
                "以 Valorant (无畏契约) 为例：\n"
                "1. 进入 游戏设置 → 音频 → 语音聊天。\n"
                "2. 确认【输出设备】仍为 CABLE Input。\n"
                "3. 将 Incoming Volume (队友音量) 适量调高，让队内语音清晰进入翻译器。音量太低会导致识别率下降。"
            )
        ))

        # Step 4: Display Mode Setup
        c_layout.addWidget(self.create_step_card(
            step_num="4",
            title="把游戏显示模式调成【无边框窗口化】",
            badge_text="字幕悬浮必备",
            content=(
                "以 Valorant (无畏契约) 为例：\n"
                "1. 进入 游戏设置 → 画面 (VIDEO) → 一般 (GENERAL)。\n"
                "2. 把【显示模式 (Display Mode)】改为 【无边框窗口化 (Windowed Fullscreen)】。\n"
                "3. 这样翻译字幕弹窗才能稳定置顶在游戏上方，同时不需要切出游戏即可点击弹窗交互！"
            )
        ))

        # Step 5: Hold F8 to type in English / Korean
        c_layout.addWidget(self.create_step_card(
            step_num="5",
            title="按住 F8 说中文，自动翻成英语 / 韩语",
            badge_text="打字聊天",
            content=(
                "1. 在「实时同传」页选好 F8 打字语言：亚服选英语，韩服选韩语。\n"
                "2. 同传开着时按住 F8 说中文，松开后约 2 秒，译文自动复制到剪贴板。\n"
                "3. 回车打开游戏聊天，Ctrl+V 粘贴，再回车发送。字幕框里绿色竖条那条，上面是识别到的中文、下面是复制好的译文，粘贴前可以先看一眼。"
            )
        ))

        c_layout.addStretch()
        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    def create_step_card(self, step_num: str, title: str, badge_text: str, content: str) -> QFrame:
        card = QFrame(self)
        card.setObjectName("Card")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(18)

        # Step number
        lbl_num = QLabel(f"{int(step_num):02d}", card)
        lbl_num.setStyleSheet("font-family: Bahnschrift; font-size: 30px; font-weight: 600; color: #ff4655;")
        layout.addWidget(lbl_num, 0, Qt.AlignTop)

        body = QVBoxLayout()
        body.setSpacing(8)

        # Title row
        h_layout = QHBoxLayout()
        h_layout.setSpacing(10)
        lbl_t = QLabel(title, card)
        lbl_t.setStyleSheet("font-size: 15px; font-weight: bold; color: #ffffff;")

        lbl_badge = QLabel(badge_text, card)
        lbl_badge.setObjectName("Badge")

        h_layout.addWidget(lbl_t)
        h_layout.addWidget(lbl_badge)
        h_layout.addStretch()
        body.addLayout(h_layout)

        # Body Content
        lbl_body = QLabel(content, card)
        lbl_body.setStyleSheet("color: #aab4be; font-size: 13px;")
        lbl_body.setWordWrap(True)
        body.addWidget(lbl_body)

        layout.addLayout(body, 1)
        return card
