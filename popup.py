"""翻译结果弹窗：无边框置顶、不抢焦点、跟随鼠标位置。

窗口几何统一用 Win32 原生坐标（物理像素）读写：
  - 定位用 SetWindowPos（物理像素），不依赖 Qt 的逻辑坐标系
  - is_over / is_visible_native 用 GetWindowRect / IsWindowVisible，
    供其他线程安全地调用
"""
import ctypes
from ctypes import wintypes

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

user32 = ctypes.windll.user32
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, wintypes.UINT,
]
user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]

# GetMonitorInfoW 的参数类型已在 locator.py 统一声明（避免重复声明互相覆盖）
import locator as _locator_mod  # noqa: E402
MONITORINFO = _locator_mod.MONITORINFO

HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

LOGICAL_W = 420
SHORT_H = 168     # 短文本（原文 ≤140 字符）
LONG_H = 244      # 长文本
COMPACT_SRC = 140
MAX_LOGICAL_H = 560   # 弹窗生长上限，超过才内部滚动


def estimate_logical_size(src_len):
    """按原文长度估算弹窗逻辑尺寸，供定位计算用。"""
    return LOGICAL_W, SHORT_H if src_len <= COMPACT_SRC else LONG_H


QSS = """
#card {
  background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
              stop:0 #24262d, stop:1 #1a1b20);
  border: 1px solid #3a3d46;
  border-radius: 14px;
}
#chip { background: #2e3340; color: #8ab4ff; border-radius: 9px;
        padding: 2px 10px; font-size: 11px; }
#closeBtn { color: #8b919c; background: transparent; border: none;
            font-size: 15px; padding: 0 4px; }
#closeBtn:hover { color: #ffffff; }
#src { color: #98a0ab; font-size: 12px; }
#sep { background: #31343c; max-height: 1px; border: none; }
#result { color: #f2f4f8; font-size: 15px; }
#resultWrap, #resultWrap > QWidget { background: transparent; }
#brand { color: #565b64; font-size: 10px; }
#copyBtn { background: #3d7bf0; color: white; border: none;
           border-radius: 8px; padding: 4px 16px; font-size: 12px; }
#copyBtn:hover { background: #4f8cff; }
#copyBtn:disabled { background: #2a2c33; color: #6b6f76; }
"""


class PopupWindow(QWidget):
    # 供工作线程跨线程调用的信号
    sig_show = pyqtSignal(int, int, str, str, str)  # 物理x, 物理y, 原文, 初始译文, 方向标签
    sig_append = pyqtSignal(str)
    sig_error = pyqtSignal(str)
    sig_hide = pyqtSignal()
    sig_copy_enable = pyqtSignal(bool)
    sig_copied = pyqtSignal()  # 复制按钮写入剪贴板前通知主程序跳过一次监听

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(QSS)
        self._hwnd = None

        self.card = QFrame(self)
        self.card.setObjectName("card")

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 150))
        self.card.setGraphicsEffect(shadow)

        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(16, 12, 12, 12)
        lay.setSpacing(8)

        # 顶行：方向标签 + 关闭按钮
        head = QHBoxLayout()
        self.chip = QLabel("EN → 中")
        self.chip.setObjectName("chip")
        self.chip.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        head.addWidget(self.chip)
        head.addStretch(1)
        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("closeBtn")
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setFixedWidth(24)
        self.close_btn.clicked.connect(self.sig_hide.emit)
        head.addWidget(self.close_btn)
        lay.addLayout(head)

        self.src_label = QLabel()
        self.src_label.setObjectName("src")
        self.src_label.setWordWrap(True)
        self.src_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.src_label)

        sep = QFrame()
        sep.setObjectName("sep")
        sep.setFrameShape(QFrame.Shape.HLine)
        lay.addWidget(sep)

        self.result_view = QScrollArea()
        self.result_view.setObjectName("resultWrap")
        self.result_view.setWidgetResizable(True)
        self.result_view.setFrameShape(QFrame.Shape.NoFrame)
        self.result_view.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.result_label = QLabel()
        self.result_label.setObjectName("result")
        self.result_label.setWordWrap(True)
        self.result_label.setAlignment(Qt.AlignmentFlag.AlignTop |
                                       Qt.AlignmentFlag.AlignLeft)
        self.result_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self.result_view.setWidget(self.result_label)
        lay.addWidget(self.result_view, 1)

        # 底行：品牌小字 + 复制按钮
        foot = QHBoxLayout()
        brand = QLabel("DeepSeek 翻译")
        brand.setObjectName("brand")
        foot.addWidget(brand)
        foot.addStretch(1)
        self.copy_btn = QPushButton("复制译文")
        self.copy_btn.setObjectName("copyBtn")
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.setEnabled(False)
        self.copy_btn.clicked.connect(self._on_copy)
        foot.addWidget(self.copy_btn)
        lay.addLayout(foot)

        self.sig_show.connect(self._show_at)
        self.sig_append.connect(self._append)
        self.sig_error.connect(self._error)
        self.sig_hide.connect(self.hide)
        self.sig_copy_enable.connect(self.copy_btn.setEnabled)

    # ---- 跨线程查询（仅 Win32 调用，可从任意线程调用） ----
    def is_visible_native(self):
        return bool(self._hwnd) and bool(user32.IsWindowVisible(self._hwnd))

    def is_over(self, x, y):
        if not self.is_visible_native():
            return False
        r = wintypes.RECT()
        if not user32.GetWindowRect(self._hwnd, ctypes.byref(r)):
            return False
        return r.left <= x <= r.right and r.top <= y <= r.bottom

    # ---- GUI 线程内部 ----
    def _show_at(self, px, py, src, init_text, chip_text):
        w, h = estimate_logical_size(len(src))
        self.setFixedSize(w, h)
        self.card.setGeometry(0, 0, w, h)

        self.chip.setText(chip_text)
        self.src_label.setText(src)
        self.result_label.setText(init_text)
        self.copy_btn.setText("复制译文")
        self.copy_btn.setEnabled(False)

        self.show()
        self.raise_()
        if not self._hwnd:
            self._hwnd = int(self.winId())
        user32.SetWindowPos(self._hwnd, HWND_TOPMOST, int(px), int(py),
                            0, 0, SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)

    def _append(self, chunk):
        cur = self.result_label.text()
        if cur == "翻译中…":
            cur = ""
        self.result_label.setText(cur + chunk)
        sb = self.result_view.verticalScrollBar()
        sb.setValue(sb.maximum())
        self._grow_if_needed()

    def _grow_if_needed(self):
        """译文变长时向下生长弹窗，上限 MAX_LOGICAL_H，超出走滚动。"""
        try:
            inner_w = self.result_label.width() or self.width() - 32
            result_h = self.result_label.heightForWidth(inner_w)
            src_h = self.src_label.heightForWidth(self.src_label.width())
        except Exception:
            return
        if result_h <= 0:
            return
        # 上下边距24 + 顶行26 + 原文 + 分隔线1 + 译文 + 底行30 + 间距24
        needed = 24 + 26 + src_h + 1 + result_h + 30 + 24 + 8
        needed = max(self.height(), min(needed, MAX_LOGICAL_H))
        if needed > self.height():
            self.setFixedSize(self.width(), needed)
            self.card.setGeometry(0, 0, self.width(), needed)
            self._clamp_vertical()

    def _clamp_vertical(self):
        """生长后底部超出屏幕工作区时，整体上移。"""
        if not self._hwnd:
            return
        r = wintypes.RECT()
        if not user32.GetWindowRect(self._hwnd, ctypes.byref(r)):
            return
        pt = wintypes.POINT((r.left + r.right) // 2, (r.top + r.bottom) // 2)
        hmon = user32.MonitorFromPoint(pt, 2)  # MONITOR_DEFAULTTONEAREST
        if not hmon:
            return
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if not user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            return
        overflow = r.bottom - mi.rcWork.bottom
        if overflow > 0:
            user32.SetWindowPos(self._hwnd, HWND_TOPMOST, r.left,
                                r.top - overflow - 4, 0, 0,
                                SWP_NOSIZE | SWP_NOACTIVATE)

    def _error(self, msg):
        self.result_label.setText(self.result_label.text().rstrip() + "\n⚠ " + msg)
        self._grow_if_needed()

    def _on_copy(self):
        self.sig_copied.emit()
        QApplication.clipboard().setText(self.result_label.text())
        self.copy_btn.setText("已复制 ✓")
        QTimer.singleShot(700, self._after_copy)

    def _after_copy(self):
        self.hide()
