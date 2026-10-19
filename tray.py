"""托盘图标与菜单（打开主窗口 / 两个翻译开关 / 退出）。"""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon


def _make_icon():
    pm = QPixmap(32, 32)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#4f8cff"))
    p.drawRoundedRect(2, 2, 28, 28, 7, 7)
    p.setPen(QColor("white"))
    f = QFont()
    f.setBold(True)
    f.setPixelSize(16)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "译")
    p.end()
    return QIcon(pm)


class Tray:
    def __init__(self, cfg, parent, on_quit, show_window,
                 on_clipboard_toggle=None, on_mouse_toggle=None):
        self.cfg = cfg
        self.on_clipboard_toggle_cb = on_clipboard_toggle
        self.on_mouse_toggle_cb = on_mouse_toggle
        self.tray = QSystemTrayIcon(_make_icon(), parent)
        self.tray.setToolTip("MouseTranslating 剪贴板翻译")

        menu = QMenu()
        act_open = QAction("打开主窗口", menu)
        act_open.triggered.connect(show_window)
        menu.addAction(act_open)

        menu.addSeparator()

        self.act_clipboard = QAction("复制翻译：开", menu, checkable=True)
        self.act_clipboard.setChecked(bool(cfg.enabled))
        self.act_clipboard.toggled.connect(self._on_clipboard_toggle)
        menu.addAction(self.act_clipboard)

        self.act_mouse = QAction("鼠标划词翻译：关（实验性）", menu, checkable=True)
        self.act_mouse.setChecked(bool(getattr(cfg, "mouse_trigger", False)))
        self.act_mouse.toggled.connect(self._on_mouse_toggle)
        menu.addAction(self.act_mouse)

        menu.addSeparator()
        act_quit = QAction("退出", menu)
        act_quit.triggered.connect(on_quit)
        menu.addAction(act_quit)

        self.tray.setContextMenu(menu)
        self.tray.show()

    # ---- 剪贴板翻译开关 ----
    def _on_clipboard_toggle(self, checked):
        self.cfg.enabled = bool(checked)
        self.cfg.save()
        self._update_clipboard_text()
        if self.on_clipboard_toggle_cb:
            self.on_clipboard_toggle_cb(bool(checked))

    def set_clipboard_enabled(self, checked):
        """主窗口改动开关时同步托盘（不回环触发）。"""
        self.act_clipboard.blockSignals(True)
        self.act_clipboard.setChecked(bool(checked))
        self.act_clipboard.blockSignals(False)
        self.cfg.enabled = bool(checked)
        self.cfg.save()
        self._update_clipboard_text()

    def _update_clipboard_text(self):
        self.act_clipboard.setText("复制翻译：开" if self.cfg.enabled
                                   else "复制翻译：关")

    # ---- 鼠标划词开关 ----
    def _on_mouse_toggle(self, checked):
        self.cfg.mouse_trigger = bool(checked)
        self.cfg.save()
        self._update_mouse_text()
        if self.on_mouse_toggle_cb:
            self.on_mouse_toggle_cb(bool(checked))

    def set_mouse_enabled(self, checked):
        self.act_mouse.blockSignals(True)
        self.act_mouse.setChecked(bool(checked))
        self.act_mouse.blockSignals(False)
        self.cfg.mouse_trigger = bool(checked)
        self.cfg.save()
        self._update_mouse_text()

    def _update_mouse_text(self):
        on = bool(getattr(self.cfg, "mouse_trigger", False))
        self.act_mouse.setText("鼠标划词翻译：开（实验性）" if on
                               else "鼠标划词翻译：关（实验性）")

    def show_message(self, title, body):
        self.tray.showMessage(title, body,
                              QSystemTrayIcon.MessageIcon.Information, 1500)
