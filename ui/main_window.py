import os
import re
import sys
import html
import time
import ctypes
from PySide6.QtCore import Qt, QThreadPool, QRunnable, Signal, QObject, Slot, QTimer
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QTextEdit, QFrame, QStackedWidget,
    QSlider, QCheckBox, QMessageBox, QApplication, QButtonGroup
)
from PySide6.QtGui import QIcon, QFont, QColor

from config import config_mgr
from audio.recorder import AudioRecorder, PushToTalkRecorder
from ai.client import AIClient, GeminiLiveStreamWorker, MicTranslateWorker
from ui.styles import VALORANT_STYLE, ACCENT, MUTED, GREEN, AMBER

VK_F8 = 0x77  # hold to speak Chinese -> English / Korean
CHAT_LANGUAGES = {"en": "英语", "ko": "韩语"}  # F8 typing language: English for the Asia server, Korean for the KR server
from ui.overlay_window import SubtitleOverlay
from ui.components.audio_meter import AudioControlWidget
from ui.components.api_settings import APISettingsWidget
from ui.components.guide_widget import GuideWidget
from ui.components.card import make_card, make_header

# Async Worker Signals for API requests
class AIWorkerSignals(QObject):
    finished = Signal(str, str, bool)  # original, translated, is_final
    error = Signal(str)

class AIWorker(QRunnable):
    def __init__(self, wav_bytes: bytes):
        super().__init__()
        self.wav_bytes = wav_bytes
        self.signals = AIWorkerSignals()

    def run(self):
        try:
            client = AIClient()
            orig, trans = client.process_audio(self.wav_bytes)
            if orig or trans:
                self.signals.finished.emit(orig, trans, True)
        except Exception as e:
            self.signals.error.emit(str(e))


class MainWindow(QMainWindow):
    # Signal to update volume meter from audio thread safely
    volume_signal = Signal(float)
    audio_chunk_signal = Signal(bytes)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("瓦语通 · VALORANT 实时同传")
        self.resize(980, 680)

        self.thread_pool = QThreadPool.globalInstance()
        self.ai_client = AIClient()
        self.live_worker = None
        self.mic_worker = None
        self.mic_ready = False
        self.last_mock_time = 0.0

        # Create Floating Overlay Subtitle Window
        self.overlay = SubtitleOverlay()
        self.overlay.show()

        # Setup Recorder
        self.recorder = AudioRecorder(
            audio_chunk_callback=self.on_audio_chunk_detected,
            volume_callback=self.on_volume_update
        )
        self.ptt_recorder = PushToTalkRecorder(audio_chunk_callback=self.on_mic_chunk)

        self.init_ui()

        # Connect signals
        self.volume_signal.connect(self.audio_meter_widget.update_volume)
        self.audio_chunk_signal.connect(self.process_audio_chunk)

        # Refresh device list
        self.refresh_devices()

        # Hold F8 to speak Chinese -> Korean: poll the key state (GetAsyncKeyState, no keyboard hook)
        self.ptt_down = False
        self.ptt_timer = QTimer(self)
        self.ptt_timer.timeout.connect(self.poll_ptt_key)
        self.ptt_timer.start(20)

        # 启动后自动开始同传（找到了 VB-Cable 且填了 API Key 才自动开）
        if (config_mgr.get("auto_start_listening", True) and self.audio_device
                and config_mgr.get("api_key", "").strip()):
            QTimer.singleShot(300, self.toggle_listening)

    def init_ui(self):
        self.setStyleSheet(VALORANT_STYLE)

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar Navigation
        sidebar = QWidget(self)
        sidebar.setObjectName("SidebarWidget")
        sidebar.setFixedWidth(208)

        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(0, 24, 0, 20)
        sb_layout.setSpacing(2)

        # App Logo & Name
        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(20, 0, 16, 0)
        brand_row.setSpacing(10)
        brand_mark = QFrame(sidebar)
        brand_mark.setFixedSize(8, 22)
        brand_mark.setStyleSheet(f"background-color: {ACCENT}; border: none;")
        brand_lbl = QLabel("VALOVOICE", sidebar)
        brand_lbl.setObjectName("Brand")
        brand_row.addWidget(brand_mark)
        brand_row.addWidget(brand_lbl)
        brand_row.addStretch()
        sb_layout.addLayout(brand_row)

        brand_sub = QLabel("瓦语通 · 实时语音同传", sidebar)
        brand_sub.setObjectName("BrandSub")
        brand_sub.setContentsMargins(38, 4, 0, 0)
        sb_layout.addWidget(brand_sub)
        sb_layout.addSpacing(28)

        # Nav Buttons
        self.btn_nav_control = QPushButton("实时同传", sidebar)
        self.btn_nav_control.setObjectName("SidebarButton")
        self.btn_nav_control.setCheckable(True)
        self.btn_nav_control.setChecked(True)
        self.btn_nav_control.clicked.connect(lambda: self.switch_page(0))

        self.btn_nav_overlay = QPushButton("字幕样式", sidebar)
        self.btn_nav_overlay.setObjectName("SidebarButton")
        self.btn_nav_overlay.setCheckable(True)
        self.btn_nav_overlay.clicked.connect(lambda: self.switch_page(1))

        self.btn_nav_api = QPushButton("API 设置", sidebar)
        self.btn_nav_api.setObjectName("SidebarButton")
        self.btn_nav_api.setCheckable(True)
        self.btn_nav_api.clicked.connect(lambda: self.switch_page(2))

        self.btn_nav_guide = QPushButton("使用指南", sidebar)
        self.btn_nav_guide.setObjectName("SidebarButton")
        self.btn_nav_guide.setCheckable(True)
        self.btn_nav_guide.clicked.connect(lambda: self.switch_page(3))

        for btn in (self.btn_nav_control, self.btn_nav_overlay, self.btn_nav_api, self.btn_nav_guide):
            btn.setCursor(Qt.PointingHandCursor)
            sb_layout.addWidget(btn)
        sb_layout.addStretch()

        # Bottom Status Badge
        self.lbl_status_badge = QLabel(sidebar)
        self.lbl_status_badge.setObjectName("StatusLabel")
        self.lbl_status_badge.setWordWrap(True)
        self.lbl_status_badge.setContentsMargins(20, 0, 16, 0)
        sb_layout.addWidget(self.lbl_status_badge)
        self.set_status("未开始", MUTED)

        main_layout.addWidget(sidebar)

        # Stacked Pages Widget
        self.stacked_widget = QStackedWidget(self)

        # Page 0: Control Center
        self.page_control = self.create_control_page()
        # Page 1: Subtitle Overlay Settings
        self.page_overlay_settings = self.create_overlay_settings_page()
        # Page 2: API Settings
        self.page_api_settings = APISettingsWidget(self)
        # Page 3: Guide
        self.page_guide = GuideWidget(self)

        self.stacked_widget.addWidget(self.page_control)
        self.stacked_widget.addWidget(self.page_overlay_settings)
        self.stacked_widget.addWidget(self.page_api_settings)
        self.stacked_widget.addWidget(self.page_guide)

        main_layout.addWidget(self.stacked_widget)

    def switch_page(self, index: int):
        self.stacked_widget.setCurrentIndex(index)
        self.btn_nav_control.setChecked(index == 0)
        self.btn_nav_overlay.setChecked(index == 1)
        self.btn_nav_api.setChecked(index == 2)
        self.btn_nav_guide.setChecked(index == 3)
        if index == 1:
            # 字幕框上的锁定按钮也能切换状态，回到这页时同步一下文字
            self.btn_lock_overlay.setText(self.lock_button_text())

    def set_status(self, text: str, color: str):
        self.lbl_status_badge.setText(f"<span style='color:{color};'>●</span>&nbsp; {html.escape(text)}")
        # 同步到游戏里的字幕框底部：锁定后没人说话时，也能看出软件在不在工作
        self.overlay.set_status(text, color, self.recorder.is_recording)

    def create_control_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        # Header Title & Start / Stop
        header = QHBoxLayout()
        header.addLayout(make_header(page, "实时同传", "监听队友的游戏语音，实时翻译成中文字幕叠加在游戏画面上"), 1)

        self.btn_toggle_start = QPushButton("开始同传", page)
        self.btn_toggle_start.setObjectName("PrimaryButton")
        self.btn_toggle_start.setMinimumSize(148, 44)
        self.btn_toggle_start.setCursor(Qt.PointingHandCursor)
        self.btn_toggle_start.clicked.connect(self.toggle_listening)

        self.chk_auto_start = QCheckBox("启动软件后自动开始", page)
        self.chk_auto_start.setChecked(config_mgr.get("auto_start_listening", True))
        self.chk_auto_start.toggled.connect(lambda checked: config_mgr.set("auto_start_listening", checked))

        start_box = QVBoxLayout()
        start_box.setSpacing(6)
        start_box.addWidget(self.btn_toggle_start)
        start_box.addWidget(self.chk_auto_start, 0, Qt.AlignRight)
        header.addLayout(start_box)
        layout.addLayout(header)

        # Audio Card: Auto-detected Devices & VU Meter
        card_top, ct_layout, _ = make_card(page, "音频输入", "Audio Input")

        dev_panel, dev_row, self.lbl_device, self.lbl_device_detail = self.make_device_panel(card_top)
        self.btn_refresh_dev = QPushButton("重新检测", dev_panel)
        self.btn_refresh_dev.clicked.connect(self.refresh_devices)
        dev_row.addWidget(self.btn_refresh_dev, 0, Qt.AlignVCenter)
        ct_layout.addWidget(dev_panel)

        mic_panel, mic_row, self.lbl_mic, self.lbl_mic_detail = self.make_device_panel(card_top)
        # F8 typing language: two segment buttons, Asia server types English, KR server types Korean
        self.lang_group = QButtonGroup(mic_panel)
        for code, label in (("en", "英语 · 亚服"), ("ko", "韩语 · 韩服")):
            btn = QPushButton(label, mic_panel)
            btn.setObjectName("SegmentButton")
            btn.setCheckable(True)
            btn.setChecked(config_mgr.get("chat_language", "ko") == code)
            btn.setProperty("lang", code)
            self.lang_group.addButton(btn)
            mic_row.addWidget(btn, 0, Qt.AlignVCenter)
        self.lang_group.buttonClicked.connect(self.on_chat_language_changed)
        ct_layout.addWidget(mic_panel)

        # Audio VU Level Meter Widget
        self.audio_meter_widget = AudioControlWidget(card_top)
        ct_layout.addWidget(self.audio_meter_widget)

        layout.addWidget(card_top)

        # Subtitle History Log Card
        card_log, cl_layout, log_head = make_card(page, "字幕记录", "History")
        btn_clear_log = QPushButton("清空", card_log)
        btn_clear_log.setObjectName("LinkButton")
        btn_clear_log.setCursor(Qt.PointingHandCursor)
        btn_clear_log.clicked.connect(lambda: self.txt_log.clear())
        log_head.addWidget(btn_clear_log)

        self.txt_log = QTextEdit(card_log)
        self.txt_log.setObjectName("LogView")
        self.txt_log.setReadOnly(True)
        self.txt_log.setPlaceholderText("开始同传后，翻译完成的每一句都会记录在这里")
        cl_layout.addWidget(self.txt_log)

        layout.addWidget(card_log, 1)
        return page

    def create_overlay_settings_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        layout.addLayout(make_header(page, "字幕样式", "调整游戏内字幕的位置、大小、透明度和停留时间"))

        # Position Card: Show / Hide, Lock Toggle, Reset
        card_pos, pos_layout, _ = make_card(page, "位置", "Position")
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        self.btn_show_overlay = QPushButton("显示 / 隐藏字幕", card_pos)
        self.btn_show_overlay.clicked.connect(self.toggle_overlay_visible)

        self.btn_lock_overlay = QPushButton(self.lock_button_text(), card_pos)
        self.btn_lock_overlay.clicked.connect(self.toggle_overlay_lock)

        self.btn_reset_overlay = QPushButton("放到推荐位置", card_pos)
        self.btn_reset_overlay.clicked.connect(self.on_reset_overlay_pos)

        row1.addWidget(self.btn_show_overlay)
        row1.addWidget(self.btn_lock_overlay)
        row1.addWidget(self.btn_reset_overlay)
        row1.addStretch()
        pos_layout.addLayout(row1)

        pos_hint = QLabel(
            "推荐位置在准星正下方、技能栏上方：视线往下一瞥就能看到，不用把眼睛挪到屏幕角落。"
            "解锁后可以直接拖动字幕框；锁定后鼠标会穿透字幕，不影响游戏操作。",
            card_pos
        )
        pos_hint.setObjectName("HintLabel")
        pos_hint.setWordWrap(True)
        pos_layout.addWidget(pos_hint)
        layout.addWidget(card_pos)

        # Appearance Card: Font Size, Opacity, Display Duration
        card_look, look_layout, _ = make_card(page, "外观", "Appearance")
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)
        grid.setColumnStretch(1, 1)

        self.slider_font = QSlider(Qt.Horizontal, card_look)
        self.slider_font.setRange(14, 40)
        self.slider_font.setValue(config_mgr.get("overlay_font_size", 22))
        self.lbl_font_val = QLabel(f"{self.slider_font.value()} px", card_look)
        self.slider_font.valueChanged.connect(self.on_font_size_changed)

        self.slider_opacity = QSlider(Qt.Horizontal, card_look)
        self.slider_opacity.setRange(20, 100)
        self.slider_opacity.setValue(int(config_mgr.get("overlay_opacity", 0.85) * 100))
        self.lbl_op_val = QLabel(f"{self.slider_opacity.value()}%", card_look)
        self.slider_opacity.valueChanged.connect(self.on_opacity_changed)

        self.slider_dur = QSlider(Qt.Horizontal, card_look)
        self.slider_dur.setRange(2, 20)
        self.slider_dur.setValue(config_mgr.get("overlay_display_time_sec", 6))
        self.lbl_dur_val = QLabel(f"{self.slider_dur.value()} 秒", card_look)
        self.slider_dur.valueChanged.connect(self.on_display_time_changed)

        rows = [
            ("字号", self.slider_font, self.lbl_font_val),
            ("背景不透明度", self.slider_opacity, self.lbl_op_val),
            ("每条停留时间", self.slider_dur, self.lbl_dur_val),
        ]
        for r, (name, slider, value_lbl) in enumerate(rows):
            name_lbl = QLabel(name, card_look)
            name_lbl.setObjectName("FieldLabel")
            value_lbl.setObjectName("ValueLabel")
            value_lbl.setMinimumWidth(56)
            value_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            grid.addWidget(name_lbl, r, 0)
            grid.addWidget(slider, r, 1)
            grid.addWidget(value_lbl, r, 2)
        look_layout.addLayout(grid)

        # Test Subtitle Button
        test_row = QHBoxLayout()
        test_row.addStretch()
        self.btn_test_sub = QPushButton("发送测试字幕", card_look)
        self.btn_test_sub.clicked.connect(self.send_test_subtitle)
        test_row.addWidget(self.btn_test_sub)
        look_layout.addLayout(test_row)

        layout.addWidget(card_look)
        layout.addStretch()
        return page

    @staticmethod
    def make_device_panel(parent):
        """一行设备信息：状态点 + 名称，下面一行小字说明。返回 (panel, 行布局, 标题, 说明)。"""
        panel = QFrame(parent)
        panel.setObjectName("DevicePanel")
        row = QHBoxLayout(panel)
        row.setContentsMargins(12, 8, 8, 8)
        row.setSpacing(8)
        text = QVBoxLayout()
        text.setSpacing(2)
        title = QLabel(panel)
        title.setObjectName("DeviceLabel")
        detail = QLabel(panel)
        detail.setObjectName("HintLabel")
        detail.setWordWrap(True)
        text.addWidget(title)
        text.addWidget(detail)
        row.addLayout(text, 1)
        return panel, row, title, detail

    def lock_button_text(self) -> str:
        return "解锁以拖动字幕" if self.overlay.is_locked else "锁定位置（鼠标穿透）"

    def refresh_devices(self):
        # 不让用户在一堆重复设备里挑：只用 VB-Cable 的 CABLE Output（自动选 WASAPI 版本）
        self.audio_device = AudioRecorder.find_cable_device()
        if self.audio_device:
            api = self.audio_device["hostapi"].replace("Windows ", "")
            self.lbl_device.setText(f"<span style='color:{GREEN};'>●</span>&nbsp; VB-Cable 虚拟声卡")
            self.lbl_device_detail.setText(
                f"已自动选好：{self.audio_device['raw_name']} · {api} · {self.audio_device['default_samplerate']} Hz"
            )
            config_mgr.set("selected_device_name", self.audio_device["name"])
            config_mgr.set("audio_device_index", self.audio_device["index"])
        else:
            self.lbl_device.setText(f"<span style='color:{ACCENT};'>●</span>&nbsp; 没有找到 VB-Cable 虚拟声卡")
            self.lbl_device_detail.setText("按「使用指南」第 1 步安装（免费），装好后点「重新检测」")

        # 你的麦克风（按住 F8 说中文用）：Windows 默认录音设备
        self.mic_device = AudioRecorder.find_microphone()
        if self.mic_device:
            # "麦克风 (WO Mic Device)" -> "WO Mic Device"
            mic_name = re.sub(r'^(麦克风|Microphone)\s*\((.*)\)$', r'\2', self.mic_device['raw_name'])
            self.lbl_mic.setText(f"<span style='color:{GREEN};'>●</span>&nbsp; 麦克风：{html.escape(mic_name)}")
            self.update_mic_hint()
        else:
            self.lbl_mic.setText(f"<span style='color:{ACCENT};'>●</span>&nbsp; 没有找到麦克风")
            self.lbl_mic_detail.setText("插好麦克风、在 Windows 声音设置里设为默认录音设备后，点「重新检测」")

    def toggle_listening(self):
        if not self.recorder.is_recording:
            # Start
            if not self.audio_device:
                QMessageBox.warning(
                    self, "没有找到 VB-Cable",
                    "没有检测到 VB-Cable 虚拟声卡。\n请按「使用指南」第 1 步安装，装好后在本页点「重新检测」。"
                )
                return
            dev_idx = self.audio_device["index"]
            try:
                self.recorder.start(dev_idx)

                # Start Gemini Live API WebSocket Worker
                api_key = config_mgr.get("api_key", "").strip()
                if api_key and not config_mgr.get("mock_mode", False):
                    self.live_worker = GeminiLiveStreamWorker(self)
                    self.live_worker.translation_received.connect(self.on_ai_success)
                    self.live_worker.status_changed.connect(self.on_worker_status)
                    self.live_worker.start()

                    # Hold F8: Chinese -> Korean on its own connection, kept warm (no audio sent until F8)
                    self.mic_ready = False
                    self.start_mic_worker()

                self.set_start_button(running=True)
                if not self.live_worker:
                    self.set_status("监听中（演示模式）", GREEN)
            except Exception as e:
                QMessageBox.critical(self, "音频启动失败", f"无法打开选中音频设备: {e}")
        else:
            # Stop
            self.recorder.stop()
            self.ptt_recorder.stop()
            if self.live_worker:
                self.live_worker.stop()
                self.live_worker = None
            if self.mic_worker:
                self.mic_worker.stop()
                self.mic_worker = None

            self.set_start_button(running=False)
            self.set_status("未开始", MUTED)

    def set_start_button(self, running: bool):
        self.btn_toggle_start.setText("停止同传" if running else "开始同传")
        self.btn_toggle_start.setObjectName("StopButton" if running else "PrimaryButton")
        self.btn_toggle_start.style().unpolish(self.btn_toggle_start)
        self.btn_toggle_start.style().polish(self.btn_toggle_start)

    def on_worker_status(self, text: str):
        if not self.recorder.is_recording:
            return  # 已经点了停止，后台线程晚到的状态不再显示，免得状态显示错
        self.set_status(text, GREEN if "就绪" in text else AMBER)

    def chat_language_name(self) -> str:
        return CHAT_LANGUAGES.get(config_mgr.get("chat_language", "ko"), "韩语")

    def update_mic_hint(self):
        if self.mic_device:
            self.lbl_mic_detail.setText(
                f"同传开着时按住 F8 说中文，松开后{self.chat_language_name()}自动复制，在游戏聊天里 Ctrl+V 粘贴"
            )

    def start_mic_worker(self):
        self.mic_ready = False
        self.mic_worker = MicTranslateWorker(config_mgr.get("chat_language", "ko"), self)
        self.mic_worker.phrase_updated.connect(self.on_mic_phrase_updated)
        self.mic_worker.phrase_done.connect(self.on_mic_phrase_done)
        self.mic_worker.status_changed.connect(self.on_mic_worker_status)
        self.mic_worker.start()

    def on_chat_language_changed(self, button):
        config_mgr.set("chat_language", button.property("lang"))
        self.update_mic_hint()
        if self.mic_worker:  # running: reconnect the F8 channel with the new target language
            self.ptt_recorder.stop()
            self.mic_worker.stop()
            self.start_mic_worker()

    def on_mic_worker_status(self, text: str):
        self.mic_ready = "就绪" in text

    def poll_ptt_key(self):
        if sys.platform != "win32":
            return
        down = bool(ctypes.windll.user32.GetAsyncKeyState(VK_F8) & 0x8000)
        if down != self.ptt_down:
            self.ptt_down = down
            if down:
                self.start_mic_phrase()
            else:
                self.end_mic_phrase()

    def start_mic_phrase(self):
        """F8 按下：打开麦克风，开始收你说的中文。"""
        if not self.mic_worker:
            self.overlay.flash_status(f"先在主窗口点「开始同传」，按住 F8 说中文才会翻译成{self.chat_language_name()}", AMBER, 4)
            return
        if not self.mic_device:
            self.overlay.flash_status("没有找到麦克风，F8 说中文用不了", ACCENT, 4)
            return
        if not self.mic_ready:
            self.overlay.flash_status("F8 翻译通道还在连接，稍等一两秒再按", AMBER, 3)
            return
        self.mic_worker.begin_phrase()
        try:
            self.ptt_recorder.start(self.mic_device["index"])
        except Exception as e:
            self.overlay.flash_status(f"麦克风打不开：{e}", ACCENT, 5)
            return
        self.overlay.flash_status(f"正在听你说中文…松开 F8 翻译成{self.chat_language_name()}", ACCENT, 60)

    def end_mic_phrase(self):
        """F8 松开：关麦克风，等这句的译文出来。"""
        if self.ptt_recorder.stream is None:
            return
        self.ptt_recorder.stop()
        if self.mic_worker:
            self.mic_worker.end_phrase()
            self.overlay.flash_status(f"翻译成{self.chat_language_name()}中…", AMBER, 8)

    def on_mic_chunk(self, pcm_bytes: bytes):
        worker = self.mic_worker  # runs on the audio thread
        if worker:
            worker.put_audio(pcm_bytes)

    def on_mic_phrase_updated(self, zh: str, ko: str):
        self.overlay.update_subtitle(zh, ko, False, source="me")

    def on_mic_phrase_done(self, zh: str, ko: str):
        ko = re.sub(r'[\s.,。，]+$', '', ko)  # 聊天里不带句末标点
        self.overlay.update_subtitle(zh, ko, True, source="me")
        if not ko:
            self.overlay.flash_status("没听清，按住 F8 再说一次", AMBER, 4)
            return
        QApplication.clipboard().setText(ko)
        self.overlay.flash_status(f"{self.chat_language_name()}已复制：回车打开聊天，Ctrl+V 粘贴", GREEN, 6)
        self.append_log(zh, ko, mine=True)

    def on_volume_update(self, rms: float):
        self.volume_signal.emit(rms)

    def on_audio_chunk_detected(self, wav_bytes: bytes):
        if self.live_worker and self.live_worker.isRunning():
            self.live_worker.put_audio(wav_bytes)
        else:
            self.audio_chunk_signal.emit(wav_bytes)

    @Slot(bytes)
    def process_audio_chunk(self, wav_bytes: bytes):
        """Pass detected speech audio to async worker thread pool for API translation."""
        # 演示模式：音频是 100ms 一块送来的，只在检测到语音时、最多每 3 秒出一条随机报点，否则会刷屏
        if not self.recorder.in_speech or time.monotonic() - self.last_mock_time < 3.0:
            return
        self.last_mock_time = time.monotonic()
        worker = AIWorker(wav_bytes)
        worker.signals.finished.connect(self.on_ai_success)
        worker.signals.error.connect(self.on_ai_error)
        self.thread_pool.start(worker)

    def on_ai_success(self, orig: str, trans: str, is_final: bool = True):
        if not orig and not trans:
            return

        # Update overlay subtitle HUD dynamically in real-time
        self.overlay.update_subtitle(orig, trans, is_final)

        # Only append finished complete sentences to the history log
        if is_final and trans:
            self.append_log(orig, trans)

    def append_log(self, orig: str, trans: str, mine: bool = False):
        """队友：中文译文 + 原文；mine=True（F8 说的）：复制的译文 + 你说的中文。"""
        stamp = time.strftime("%H:%M:%S")
        orig_html = f"<br/><span style='color:#8a96a3;'>{html.escape(orig)}</span>" if orig else ""
        mine_tag = f"<span style='color:{GREEN};'>我 · </span>" if mine else ""
        self.txt_log.append(
            "<table width='100%' cellspacing='0' cellpadding='0' style='margin-bottom:10px;'><tr>"
            f"<td width='72' style='color:#5f6b77; font-family:Bahnschrift; padding-top:2px;'>{stamp}</td>"
            f"<td>{mine_tag}<span style='color:#ece8e1; font-size:15px; font-weight:bold;'>{html.escape(trans)}</span>"
            f"{orig_html}</td></tr></table>"
        )
        scrollbar = self.txt_log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def on_ai_error(self, err_msg: str):
        self.txt_log.append(f"<p style='color:{ACCENT};'>[错误] {html.escape(err_msg)}</p>")

    def toggle_overlay_visible(self):
        if self.overlay.isVisible():
            self.overlay.hide()
        else:
            self.overlay.show()

    def toggle_overlay_lock(self):
        self.overlay.set_locked(not self.overlay.is_locked)
        self.btn_lock_overlay.setText(self.lock_button_text())

    def on_reset_overlay_pos(self):
        self.overlay.reset_position()
        self.btn_lock_overlay.setText(self.lock_button_text())
        self.slider_opacity.setValue(85)
        config_mgr.set("overlay_opacity", 0.85)
        self.lbl_op_val.setText("85%")
        self.overlay.update_card_style()

    def on_font_size_changed(self, value: int):
        config_mgr.set("overlay_font_size", value)
        self.lbl_font_val.setText(f"{value} px")
        self.overlay.update_card_style()

    def on_opacity_changed(self, value: int):
        opacity = value / 100.0
        config_mgr.set("overlay_opacity", opacity)
        self.lbl_op_val.setText(f"{value}%")
        self.overlay.update_card_style()

    def on_display_time_changed(self, value: int):
        config_mgr.set("overlay_display_time_sec", value)
        self.lbl_dur_val.setText(f"{value} 秒")

    def send_test_subtitle(self):
        self.on_ai_success("상대 세 명 A 사이트로 와요! 체임버 조심하세요!", "敌人三个往A点来了！小心Chamber！")

    def closeEvent(self, event):
        self.recorder.stop()
        self.ptt_recorder.stop()
        if self.live_worker:
            self.live_worker.stop()
            self.live_worker = None
        if self.mic_worker:
            self.mic_worker.stop()
            self.mic_worker = None
        self.overlay.close()
        event.accept()
