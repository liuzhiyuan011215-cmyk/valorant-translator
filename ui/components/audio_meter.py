from PySide6.QtCore import Qt, QRectF
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider
from PySide6.QtGui import QPainter, QColor

from config import config_mgr

class AudioLevelMeter(QWidget):
    """Segmented volume level meter with VAD threshold marker."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.level = 0.0  # Current RMS level (0.0 to 1.0)
        self.threshold = config_mgr.get("vad_threshold", 0.015)
        self.setMinimumHeight(18)

    def set_level(self, level: float):
        self.level = min(1.0, max(0.0, level * 5.0)) # Scale for visibility
        self.update()

    def set_threshold(self, threshold: float):
        self.threshold = threshold
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)

        w = self.width()
        h = self.height()
        seg_w, gap = 4, 2
        count = max(1, (w + gap) // (seg_w + gap))
        lit = int(count * self.level)
        thresh_seg = int(count * min(1.0, self.threshold * 5.0))

        # 阈值以下亮灰色，超过阈值的部分亮红色（= 正在发送给 AI）
        for i in range(count):
            if i < lit:
                color = QColor("#ff4655") if i >= thresh_seg else QColor("#6b7a87")
            else:
                color = QColor("#1c2833")
            painter.fillRect(i * (seg_w + gap), 0, seg_w, h, color)

        # Threshold marker line
        painter.fillRect(max(0, thresh_seg * (seg_w + gap) - gap), 0, 2, h, QColor("#ece8e1"))


class AudioControlWidget(QWidget):
    """Widget wrapper containing volume meter and sensitivity slider."""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(8)

        # Header
        top_layout = QHBoxLayout()
        lbl_title = QLabel("输入电平", self)
        lbl_title.setObjectName("FieldLabel")

        self.lbl_val = QLabel(f"触发阈值 {config_mgr.get('vad_threshold', 0.015):.3f}", self)
        self.lbl_val.setObjectName("ValueLabel")

        top_layout.addWidget(lbl_title)
        top_layout.addStretch()
        top_layout.addWidget(self.lbl_val)
        layout.addLayout(top_layout)

        # Meter
        self.meter = AudioLevelMeter(self)
        layout.addWidget(self.meter)

        # Threshold Slider
        bot_layout = QHBoxLayout()
        bot_layout.setSpacing(12)
        lbl_low = QLabel("更灵敏", self)
        lbl_low.setObjectName("HintLabel")
        lbl_high = QLabel("更抗噪", self)
        lbl_high.setObjectName("HintLabel")

        self.slider = QSlider(Qt.Horizontal, self)
        self.slider.setRange(5, 100) # 0.005 to 0.100
        val = int(config_mgr.get("vad_threshold", 0.015) * 1000)
        self.slider.setValue(val)
        self.slider.valueChanged.connect(self.on_threshold_changed)

        bot_layout.addWidget(lbl_low)
        bot_layout.addWidget(self.slider)
        bot_layout.addWidget(lbl_high)
        layout.addLayout(bot_layout)

        lbl_hint = QLabel("白线是触发阈值：队友说话时电平应明显越过白线（变红），没人说话时停在白线左边。", self)
        lbl_hint.setObjectName("HintLabel")
        lbl_hint.setWordWrap(True)
        layout.addWidget(lbl_hint)

    def on_threshold_changed(self, value: int):
        thresh = value / 1000.0
        config_mgr.set("vad_threshold", thresh)
        self.lbl_val.setText(f"触发阈值 {thresh:.3f}")
        self.meter.set_threshold(thresh)

    def update_volume(self, rms: float):
        self.meter.set_level(rms)
