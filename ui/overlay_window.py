import re
import sys
import time
import ctypes
from PySide6.QtCore import Qt, QTimer, QPoint, QPointF, QRectF, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLayout
)
from PySide6.QtGui import (
    QColor, QFont, QFontMetricsF, QGuiApplication, QPainter, QPainterPath,
    QPen, QTextLayout, QTextOption
)

from config import config_mgr

# Windows API Constants for Mouse Click-Through
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000

# 字幕框一直显示（背景按「背景不透明度」画），底部一行显示工作状态：没人说话时也能看出软件在正常工作。
# 框里最多两条（最新一句 + 上一句），最新的在最上面；文字左对齐、只往右长，位置不跳。
# 每条双语：韩语在上（一听到就先出，方便边听边学），中文在下（译文到了补在下面，韩语不动）。
MAX_LINES = 2
ACCENT = "#ff4655"
MINE_ACCENT = "#3ddc97"      # 你按住 F8 说的话：绿色竖条，上面是你说的中文，下面是复制好的韩语
KO_COLOR = (170, 215, 255)   # 韩语用浅蓝，和白色中文一眼分开
KO_SCALE = 0.8               # 韩语字号 = 中文字号 × 0.8
FRAME_MARGIN = 6
PANEL_PAD_X, PANEL_PAD_Y = 12, 8
ACCENT_W = 3
KO_GAP = 2
ENTRY_GAP = 8
STATUS_GAP = 6
BAR_H = 30

# 解锁调位置时的示例字幕（旧 → 新），和真实字幕画法完全一样，方便看清实际占多大地方
SAMPLE_ENTRIES = [
    {"orig": "A 사이트에 세 명 왔어요.", "trans": "A点来了三个人"},
    {"orig": "뒤 조심하세요.", "trans": "小心后面"},
]


def _display_text(text: str) -> str:
    """字幕惯例：句末句号不显示（！？保留，它们带语气）。"""
    return re.sub(r'[。.]+$', '', text.strip())


class SubtitleOverlay(QWidget):
    position_changed = Signal(int, int)

    def __init__(self):
        super().__init__()
        self.drag_position = QPoint()
        self.is_locked = config_mgr.get("overlay_locked", False)
        self.entries = []   # [{"orig", "trans", "final", "expire_at"}]，最新的在最后
        self.lock_hint_until = 0.0  # 刚锁定后的几秒里，状态行提示"已锁定"
        self.status_text, self.status_color, self.listening = "未开始", "#8a96a3", False
        self.flash = None           # (文字, 颜色, 截止时间)：临时顶替状态行，比如 F8 录音中 / 已复制

        self.init_ui()
        self.apply_config()

        # 每条字幕在最后一次更新后停留 N 秒再消失（字幕框本身不消失）
        self.expire_timer = QTimer(self)
        self.expire_timer.timeout.connect(self.remove_expired)
        self.expire_timer.start(250)

    def init_ui(self):
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(FRAME_MARGIN, FRAME_MARGIN, FRAME_MARGIN, FRAME_MARGIN)
        main_layout.setSizeConstraint(QLayout.SetNoConstraint)

        # Control Bar (Only visible when unlocked)：放在字幕框下面，锁定前后字幕框位置完全一致；字幕框在 paintEvent 里画
        main_layout.addStretch()
        self.control_bar = QWidget(self)
        self.control_bar.setFixedHeight(BAR_H)
        control_layout = QHBoxLayout(self.control_bar)
        control_layout.setContentsMargins(4, 0, 0, 0)

        self.lbl_title = QLabel("字幕区域 · 按住任意位置拖动", self.control_bar)
        self.lbl_title.setStyleSheet("color: #ece8e1; font-size: 12px; font-weight: bold; background: transparent;")

        self.btn_lock = QPushButton("锁定并穿透", self.control_bar)
        self.btn_lock.setCursor(Qt.PointingHandCursor)
        self.btn_lock.setStyleSheet(f"""
            QPushButton {{
                background-color: {ACCENT}; color: white; border: none;
                border-radius: 2px; padding: 5px 14px; font-size: 12px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #ff5a68; }}
        """)
        self.btn_lock.clicked.connect(self.toggle_lock)

        control_layout.addWidget(self.lbl_title)
        control_layout.addStretch()
        control_layout.addWidget(self.btn_lock)
        main_layout.addWidget(self.control_bar)

    def _make_fonts(self):
        size = config_mgr.get("overlay_font_size", 22)
        self.trans_font = QFont()
        self.trans_font.setFamilies(["Microsoft YaHei UI", "Malgun Gothic"])  # 韩文（F8 复制的那行）回落到 Malgun Gothic 粗体
        self.trans_font.setPixelSize(size)
        self.trans_font.setBold(True)
        self.orig_font = QFont()
        self.orig_font.setFamilies(["Malgun Gothic", "Microsoft YaHei UI"])
        self.orig_font.setPixelSize(max(14, round(size * KO_SCALE)))
        self.orig_font.setBold(True)  # 韩文加粗加描边，扫一眼也能看清字形
        self.hint_font = QFont()
        self.hint_font.setFamilies(["Microsoft YaHei UI", "Microsoft YaHei"])
        self.hint_font.setPixelSize(13)
        self.hint_font.setBold(True)

    def _entry_height(self, orig_rows: int, trans_rows: int) -> float:
        h = (orig_rows * QFontMetricsF(self.orig_font).lineSpacing() +
             trans_rows * QFontMetricsF(self.trans_font).lineSpacing())
        if orig_rows and trans_rows:
            h += KO_GAP
        return h

    def _content_height(self) -> float:
        """字幕区放得下两条（各一行原文 + 一行中文）；最新一句长到折行时，放不下的旧句就不画。"""
        return 2 * self._entry_height(1, 1) + ENTRY_GAP

    def _panel_height(self) -> float:
        return (2 * PANEL_PAD_Y + self._content_height() + STATUS_GAP +
                QFontMetricsF(self.hint_font).lineSpacing())

    def _window_height(self) -> int:
        """窗口高度按字号算好，之后不会再被文字撑大。"""
        return int(2 * FRAME_MARGIN + self._panel_height() + 6 + BAR_H) + 2

    def _place(self, x: int, y: int):
        """放到 (x, y)。拖到屏幕边缘时坐标会略微越界（比如 x=-7）：夹回屏幕内，而不是把你放好的位置重置到中间。"""
        w, h = config_mgr.get("overlay_width", 630), self._window_height()
        screen = QGuiApplication.primaryScreen()
        if screen:
            geom = screen.geometry()
            x = min(max(x, geom.left()), geom.right() + 1 - w)
            y = min(max(y, geom.top()), geom.bottom() + 1 - h)
        self.setGeometry(x, y, w, h)
        config_mgr.set("overlay_x", x)
        config_mgr.set("overlay_y", y)

    def update_card_style(self):
        self._make_fonts()
        if self._window_height() != self.height():
            self._place(self.x(), self.y())  # 字号改变了高度：顶边不动
        self.update()

    def set_status(self, text: str, color: str, listening: bool):
        """主窗口同步过来的工作状态（未开始 / 正在连接 / 同传已就绪 / 重连中），显示在字幕框底部。"""
        self.status_text, self.status_color, self.listening = text, color, listening
        self.update()

    def flash_status(self, text: str, color: str, seconds: float):
        """临时顶替状态行几秒（F8 录音中 / 翻译中 / 已复制），到时恢复正常状态。"""
        self.flash = (text, color, time.monotonic() + seconds)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        if not self.is_locked:
            # 解锁时给整块区域一点底色：全透明的像素在 Windows 上点不中，也就拖不动
            p.fillRect(self.rect(), QColor(15, 25, 35, 90))
            p.setPen(QPen(QColor(255, 70, 85, 210), 1, Qt.DashLine))
            p.drawRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5))

        # 字幕框：锁定后也一直显示，透明度就是设置里的「背景不透明度」
        panel = QRectF(FRAME_MARGIN, FRAME_MARGIN, self.width() - 2 * FRAME_MARGIN, self._panel_height())
        opacity = config_mgr.get("overlay_opacity", 0.85)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(10, 16, 24, int(opacity * 255)))
        p.drawRoundedRect(panel, 4, 4)

        # 字幕：从上往下、最新的在最上面——最新一句永远在同一个位置，眼睛不用找
        content_top = panel.top() + PANEL_PAD_Y
        content_bottom = content_top + self._content_height()
        entries = self.entries[-MAX_LINES:]
        if not entries and not self.is_locked:
            entries = SAMPLE_ENTRIES
        top = content_top
        for i, entry in enumerate(reversed(entries)):
            rows = self._rows(entry, panel)
            height = self._entry_height(len(rows[0]), len(rows[1]))
            if i > 0 and top + height > content_bottom:
                break
            self._paint_entry(p, rows, panel, top, newest=(i == 0), mine=entry.get("source") == "me")
            top += height + ENTRY_GAP

        if not entries:
            hint = "队友说话时，原文和中文字幕会显示在这里" if self.listening else "在主窗口点「开始同传」后，这里显示双语字幕"
            self._draw_outlined(p, panel.left() + PANEL_PAD_X, content_top + QFontMetricsF(self.hint_font).ascent(),
                                self.hint_font, hint, QColor(236, 232, 225, 130))

        self._paint_status(p, panel)

    def _text_x(self, panel: QRectF) -> float:
        return panel.left() + PANEL_PAD_X + ACCENT_W + 8

    def _rows(self, entry: dict, panel: QRectF) -> tuple:
        text_w = panel.right() - PANEL_PAD_X - self._text_x(panel)
        orig = _display_text(entry["orig"])
        trans = _display_text(entry["trans"])
        return (self._wrap(orig, self.orig_font, text_w) if orig else [],
                self._wrap(trans, self.trans_font, text_w) if trans else [])

    def _paint_entry(self, p: QPainter, rows: tuple, panel: QRectF, top: float, newest: bool, mine: bool = False):
        orig_rows, trans_rows = rows
        fm_t, fm_o = QFontMetricsF(self.trans_font), QFontMetricsF(self.orig_font)
        if newest or mine:
            p.fillRect(QRectF(panel.left() + PANEL_PAD_X, top + 2,
                              ACCENT_W, self._entry_height(len(orig_rows), len(trans_rows)) - 4),
                       QColor(MINE_ACCENT if mine else ACCENT))

        tx, ty = self._text_x(panel), top
        # 队友：上面是韩语原文（浅蓝）；你 F8 说的：上面是你说的中文（灰）
        top_color = (200, 208, 216) if mine else KO_COLOR
        ko_fill = QColor(*top_color, 255 if newest else 150)
        for row in orig_rows:
            self._draw_outlined(p, tx, ty + fm_o.ascent(), self.orig_font, row, ko_fill)
            ty += fm_o.lineSpacing()
        if orig_rows and trans_rows:
            ty += KO_GAP
        zh_fill = QColor(255, 255, 255) if newest else QColor(236, 232, 225, 165)
        for row in trans_rows:
            self._draw_outlined(p, tx, ty + fm_t.ascent(), self.trans_font, row, zh_fill)
            ty += fm_t.lineSpacing()

    def _paint_status(self, p: QPainter, panel: QRectF):
        fm = QFontMetricsF(self.hint_font)
        baseline = panel.bottom() - PANEL_PAD_Y - fm.descent()
        line_y = baseline - fm.ascent() - STATUS_GAP / 2
        p.fillRect(QRectF(panel.left() + PANEL_PAD_X, line_y, panel.width() - 2 * PANEL_PAD_X, 1),
                   QColor(255, 255, 255, 28))

        text, color = self.status_text, self.status_color
        if self.flash and time.monotonic() < self.flash[2]:
            text, color = self.flash[0], self.flash[1]
        elif self.is_locked and time.monotonic() < self.lock_hint_until:
            text = f"已锁定，鼠标可穿透 · {text}"
        dot_x = panel.left() + PANEL_PAD_X + 4
        dot_y = baseline - fm.ascent() / 2 + 1
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(color))
        p.drawEllipse(QPointF(dot_x, dot_y), 4, 4)
        text = fm.elidedText(text, Qt.ElideRight, panel.width() - 2 * PANEL_PAD_X - 16)
        self._draw_outlined(p, dot_x + 10, baseline, self.hint_font, text, QColor(214, 222, 230))

    @staticmethod
    def _draw_outlined(p: QPainter, x: float, baseline: float, font: QFont, text: str, fill: QColor):
        """白字黑描边：背景再透明、地图再亮也看得清。"""
        path = QPainterPath()
        path.addText(QPointF(x, baseline), font, text)
        stroke = max(2.0, font.pixelSize() / 8)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(0, 0, 0, int(200 * fill.alphaF())), stroke, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(path)
        p.setPen(Qt.NoPen)
        p.setBrush(fill)
        p.drawPath(path)

    @staticmethod
    def _wrap(text: str, font: QFont, width: float, max_rows: int = 2) -> list:
        """按宽度折行，最多两行；超出时从开头截掉，保留最新的内容。"""
        def rows_of(s):
            layout = QTextLayout(s, font)
            option = QTextOption()
            option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
            layout.setTextOption(option)
            layout.beginLayout()
            rows = []
            while True:
                line = layout.createLine()
                if not line.isValid():
                    break
                line.setLineWidth(width)
                rows.append(s[line.textStart():line.textStart() + line.textLength()].rstrip())
            layout.endLayout()
            return rows

        rows = rows_of(text)
        while len(rows) > max_rows and text:
            text = text[1:]
            rows = rows_of("…" + text)
        return rows

    def apply_config(self):
        self._make_fonts()
        self._place(config_mgr.get("overlay_x", 100), config_mgr.get("overlay_y", 750))
        self.update_lock_state()

    def reset_position(self):
        """推荐位置：准星正下方、技能栏上方——视线往下一瞥就能看到，又不挡准星附近。"""
        w = config_mgr.get("overlay_width", 630)
        screen = QGuiApplication.primaryScreen()
        if screen:
            geom = screen.geometry()
            # 字幕左对齐，窗口略偏左放，常见的短报点正好落在准星正下方
            x = geom.center().x() - int(w * 0.2)
            y = geom.top() + int(geom.height() * 0.7)
        else:
            x, y = 100, 750

        self._place(x, y)
        self.set_locked(False) # Unlock so user can see and move
        self.show()
        self.raise_()

    def toggle_lock(self):
        self.set_locked(not self.is_locked)

    def set_locked(self, locked: bool):
        if locked and not self.is_locked:
            self.lock_hint_until = time.monotonic() + 3.0
        self.is_locked = locked
        config_mgr.set("overlay_locked", self.is_locked)
        self.update_lock_state()

    def update_lock_state(self):
        if self.is_locked:
            self.control_bar.hide()
            self.set_click_through(True)
        else:
            self.control_bar.show()
            self.set_click_through(False)

        self.update_card_style()

    def set_click_through(self, enable: bool):
        """Enable or disable mouse click-through via Win32 API."""
        if sys.platform != 'win32':
            return

        hwnd = int(self.winId())
        try:
            user32 = ctypes.windll.user32
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if enable:
                style |= WS_EX_TRANSPARENT
            else:
                style &= ~WS_EX_TRANSPARENT
            style |= WS_EX_LAYERED
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception as e:
            print(f"Error setting click-through state: {e}")

    def update_subtitle(self, original_text: str, translated_text: str, is_final: bool = True, source: str = "team"):
        """is_final=False 更新同一来源正在说的那条字幕；is_final=True 表示这条已说完，下一次更新另起一条。
        只有原文、译文还没到时也先显示原文（不显示"翻译中"之类的占位字），译文到了补在下面。
        source: "team" 队友（原文 → 中文）/ "me" 你按住 F8 说的（中文 → 英语或韩语）。"""
        if not _display_text(original_text) and not _display_text(translated_text):
            return

        expire_at = time.monotonic() + config_mgr.get("overlay_display_time_sec", 8)
        entry = next((e for e in reversed(self.entries) if e["source"] == source and not e["final"]), None)
        if entry is None:
            entry = {"source": source}
            self.entries.append(entry)
        entry.update(orig=original_text, trans=translated_text, final=is_final, expire_at=expire_at)
        del self.entries[:-MAX_LINES]
        self.update()

    def remove_expired(self):
        now = time.monotonic()
        alive = [e for e in self.entries if e["expire_at"] > now]
        if len(alive) != len(self.entries):
            self.entries = alive
            self.update()
        if self.lock_hint_until and now >= self.lock_hint_until:
            self.lock_hint_until = 0.0
            self.update()
        if self.flash and now >= self.flash[2]:
            self.flash = None
            self.update()

    # Window Drag Handlers
    def mousePressEvent(self, event):
        if not self.is_locked and event.button() == Qt.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if not self.is_locked and event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        if not self.is_locked:
            pos = self.pos()
            config_mgr.set("overlay_x", pos.x())
            config_mgr.set("overlay_y", pos.y())
            self.position_changed.emit(pos.x(), pos.y())
