from PySide6.QtCore import Qt, QThreadPool, QRunnable, Signal, QObject
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTextEdit, QPushButton, QCheckBox, QMessageBox
)

from config import config_mgr
from ai.client import AIClient
from ai.gaming_prompts import VALORANT_KOREAN_SYSTEM_PROMPT
from ui.components.card import make_card, make_header

class TestWorkerSignals(QObject):
    result = Signal(bool, str)

class TestWorker(QRunnable):
    def __init__(self):
        super().__init__()
        self.signals = TestWorkerSignals()

    def run(self):
        client = AIClient()
        success, msg = client.test_connection()
        self.signals.result.emit(success, msg)


class APISettingsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.thread_pool = QThreadPool.globalInstance()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        layout.addLayout(make_header(self, "API 设置", "使用 Google Gemini 3.5 Live Translate 实时语音同传模型"))

        # Credentials Card
        card, card_layout, _ = make_card(self, "Gemini API Key", "Credentials")

        self.input_api_key = QLineEdit(card)
        self.input_api_key.setEchoMode(QLineEdit.Password)
        self.input_api_key.setPlaceholderText("AIza...")
        self.input_api_key.setText(config_mgr.get("api_key", ""))
        card_layout.addWidget(self.input_api_key)

        lbl_key_hint = QLabel("在 Google AI Studio 创建；只保存在本机的 config.json 里。", card)
        lbl_key_hint.setObjectName("HintLabel")
        card_layout.addWidget(lbl_key_hint)

        # Mock Mode Checkbox
        self.chk_mock = QCheckBox("演示模式：不连接 API，检测到语音时显示随机韩语报点，用来测试字幕效果", card)
        self.chk_mock.setChecked(config_mgr.get("mock_mode", False))
        card_layout.addWidget(self.chk_mock)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        self.btn_test = QPushButton("测试连接", card)
        self.btn_test.clicked.connect(self.test_connection)

        self.btn_save = QPushButton("保存", card)
        self.btn_save.setObjectName("PrimaryButton")
        self.btn_save.clicked.connect(self.save_settings)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_test)
        btn_layout.addWidget(self.btn_save)
        card_layout.addLayout(btn_layout)
        layout.addWidget(card)

        # Model Info Card
        card_model, model_layout, _ = make_card(self, "模型", "Model")
        lbl_model = QLabel("models/gemini-3.5-live-translate-preview", card_model)
        lbl_model.setStyleSheet("font-family: Consolas, 'Cascadia Mono'; font-size: 13px; color: #ece8e1;")
        lbl_model.setTextInteractionFlags(Qt.TextSelectableByMouse)
        model_layout.addWidget(lbl_model)

        lbl_model_info = QLabel(
            "队友语音（韩语、英语等 70 多种语言，自动识别）→ 简体中文字幕；按住 F8 说的中文 → 英语或韩语。"
            "该模型不支持自定义提示词，译法和语气由模型自行决定。",
            card_model
        )
        lbl_model_info.setObjectName("HintLabel")
        lbl_model_info.setWordWrap(True)
        model_layout.addWidget(lbl_model_info)
        layout.addWidget(card_model)

        layout.addStretch()

    def save_settings(self):
        config_mgr.set("api_key", self.input_api_key.text().strip())
        config_mgr.set("mock_mode", self.chk_mock.isChecked())

        QMessageBox.information(self, "成功", "API 配置已保存！")

    def test_connection(self):
        self.save_settings()
        self.btn_test.setEnabled(False)
        self.btn_test.setText("正在测试…")

        worker = TestWorker()
        worker.signals.result.connect(self.on_test_result)
        self.thread_pool.start(worker)

    def on_test_result(self, success: bool, message: str):
        self.btn_test.setEnabled(True)
        self.btn_test.setText("测试连接")

        if success:
            QMessageBox.information(self, "连接成功", message)
        else:
            QMessageBox.warning(self, "连接失败", message)
