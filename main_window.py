"""主窗口：小型设置/控制界面（剪贴板监听模式）。

行为：启动即显示；关闭窗口 = 最小化到托盘（不退出），由托盘菜单退出。
"""
from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

QSS = """
QWidget { background: #17181c; color: #e8eaed; font-size: 13px; }
#title { font-size: 17px; font-weight: 600; }
#status { font-size: 12px; }
QCheckBox { spacing: 8px; padding: 4px 0; }
QLineEdit { background: #22242a; border: 1px solid #3a3b42;
            border-radius: 6px; padding: 5px 8px; }
QLineEdit:focus { border-color: #4f8cff; }
QPushButton { background: #4f8cff; color: white; border: none;
              border-radius: 6px; padding: 6px 16px; }
QPushButton:hover { background: #3d7bf0; }
QPushButton:pressed { background: #346bd0; }
#hint { color: #6b6f76; font-size: 11px; }
QFrame#sep { background: #2a2c33; max-height: 1px; border: none; }
"""


class MainWindow(QMainWindow):
    enabled_changed = pyqtSignal(bool)   # 用户改动剪贴板翻译开关
    mouse_changed = pyqtSignal(bool)     # 用户改动鼠标划词开关
    minimize_requested = pyqtSignal()    # 关闭窗口 → 托盘

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.setWindowTitle("MouseTranslating 剪贴板翻译")
        self.setMinimumSize(360, 300)
        self.setStyleSheet(QSS)

        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 16, 20, 14)
        root.setSpacing(12)

        # 标题行：标题 + 运行状态
        head = QHBoxLayout()
        title = QLabel("剪贴板翻译")
        title.setObjectName("title")
        self.status_label = QLabel()
        self.status_label.setObjectName("status")
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(self.status_label)
        root.addLayout(head)

        sep = QFrame()
        sep.setObjectName("sep")
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

        self.chk = QCheckBox("启用剪贴板翻译（复制即翻译）")
        self.chk.setChecked(bool(cfg.enabled))
        self.chk.toggled.connect(self._on_chk)
        root.addWidget(self.chk)

        self.chk_mouse = QCheckBox("鼠标划词翻译（实验性，选中长按拖动触发）")
        self.chk_mouse.setChecked(bool(getattr(cfg, "mouse_trigger", False)))
        self.chk_mouse.toggled.connect(self._on_mouse_chk)
        root.addWidget(self.chk_mouse)

        key_cap = QLabel("DeepSeek API Key")
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("sk-…（platform.deepseek.com 申请）")
        if cfg.api_key:
            self.key_edit.setPlaceholderText("已配置（输入新值可覆盖）")
        root.addWidget(key_cap)
        root.addWidget(self.key_edit)

        self.save_btn = QPushButton("保存设置")
        self.save_btn.clicked.connect(self._save)
        root.addWidget(self.save_btn)

        root.addStretch(1)

        hint = QLabel("用法：复制任意文字（Ctrl+C），翻译自动弹出，Esc 关闭弹窗。\n"
                      "关闭窗口会最小化到托盘，翻译继续生效；右键托盘图标可退出。")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.refresh_status()

    # ---- 状态 ----
    def refresh_status(self):
        if self.cfg.enabled:
            self.status_label.setText('<span style="color:#5dd39e">● 运行中</span>')
        else:
            self.status_label.setText('<span style="color:#6b6f76">○ 已停用</span>')

    def set_enabled_ui(self, v):
        """程序方改动开关时同步界面（不发 enabled_changed 信号）。"""
        self.chk.blockSignals(True)
        self.chk.setChecked(bool(v))
        self.chk.blockSignals(False)
        self.refresh_status()

    def set_mouse_ui(self, v):
        self.chk_mouse.blockSignals(True)
        self.chk_mouse.setChecked(bool(v))
        self.chk_mouse.blockSignals(False)

    def show_and_activate(self):
        self.show()
        self.raise_()
        self.activateWindow()

    # ---- 槽 ----
    def _on_chk(self, v):
        self.cfg.enabled = bool(v)
        self.cfg.save()
        self.refresh_status()
        self.enabled_changed.emit(bool(v))

    def _on_mouse_chk(self, v):
        self.cfg.mouse_trigger = bool(v)
        self.cfg.save()
        self.mouse_changed.emit(bool(v))

    def _save(self):
        text = self.key_edit.text().strip()
        if text:
            self.cfg.api_key = text
        self.cfg.save()
        self.key_edit.clear()
        if self.cfg.api_key:
            self.key_edit.setPlaceholderText("已配置（输入新值可覆盖）")
        self.save_btn.setText("已保存 ✓")
        self.save_btn.setEnabled(False)
        QTimer.singleShot(1200, self._restore_btn)

    def _restore_btn(self):
        self.save_btn.setText("保存设置")
        self.save_btn.setEnabled(True)

    # ---- 关闭 = 最小化到托盘 ----
    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.minimize_requested.emit()
