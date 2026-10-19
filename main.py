"""MouseTranslating 入口。

主功能：剪贴板监听翻译（复制即翻译，始终可用）。
可选功能：鼠标划词翻译（长按拖动选中后自动取词，配置里开关，默认关）。
--smoke：启动自检后退出；--selftest：写剪贴板验证全链路后退出。
"""
import argparse
import ctypes
import logging
import os
import sys
import threading
import time
from ctypes import wintypes

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "translate.log")
logger = logging.getLogger("mt")

user32 = ctypes.windll.user32
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]


def set_dpi_awareness():
    """PerMonitorV2，取不到时逐级降级。必须在启动 Qt 之前调用。"""
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    set_dpi_awareness()

    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication

    import capture
    import config as config_mod
    import locator
    import main_window as main_window_mod
    import popup as popup_mod
    import translator
    import trigger as trigger_mod
    import tray as tray_mod

    cfg = config_mod.Config.load()

    logger.setLevel(logging.INFO)
    _fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.addHandler(_fh)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    pw = popup_mod.PopupWindow()
    win = main_window_mod.MainWindow(cfg)
    tray = tray_mod.Tray(cfg, None, on_quit=app.quit,
                         show_window=win.show_and_activate,
                         on_clipboard_toggle=win.set_enabled_ui,
                         on_mouse_toggle=win.set_mouse_ui)
    win.enabled_changed.connect(tray.set_clipboard_enabled)
    win.mouse_changed.connect(tray.set_mouse_enabled)
    win.minimize_requested.connect(
        lambda: tray.show_message("MouseTranslating",
                                  "已最小化到托盘，翻译继续生效"))
    win.show()

    state = {"busy": False, "last": "", "suppress": False,
             "cb_paused_until": 0.0}
    state_lock = threading.Lock()

    def start_worker(text, rect=None, start=None, end=None):
        if not cfg.enabled:
            return
        with state_lock:
            if state["busy"]:
                return
            state["busy"] = True
        threading.Thread(target=worker, args=(text, rect, start, end),
                         daemon=True).start()

    def worker(text, rect=None, start=None, end=None):
        try:
            pw.sig_hide.emit()

            src_full = text[:cfg.max_chars]
            src = src_full if len(src_full) <= 300 else src_full[:300] + "…"
            chip = ("中 → EN" if translator.looks_chinese(src_full)
                    else "EN → 中")
            w, h = popup_mod.estimate_logical_size(len(src_full))

            if start is not None and end is not None:
                px, py = locator.compute_popup_position(
                    rect, start, end, w, h)
            else:
                pt = wintypes.POINT()
                user32.GetCursorPos(ctypes.byref(pt))
                px, py = locator.compute_popup_position(
                    None, (pt.x, pt.y), (pt.x, pt.y), w, h)

            pw.sig_show.emit(px, py, src, "翻译中…", chip)
            logger.info("translate start: %d chars", len(src_full))

            if not cfg.api_key:
                pw.sig_append.emit(
                    "尚未配置 DeepSeek API Key：右键托盘图标 → 打开主窗口。")
                return

            try:
                for chunk in translator.translate_stream(
                        src_full, cfg.api_key, cfg.model):
                    pw.sig_append.emit(chunk)
                pw.sig_copy_enable.emit(True)
                logger.info("translate done")
            except translator.TranslateError as e:
                pw.sig_error.emit(str(e))
                logger.info("translate error: %s", e)
            except Exception as e:  # noqa: BLE001
                pw.sig_error.emit("未知错误：" + str(e))
                logger.info("translate error: %s", e)
        finally:
            with state_lock:
                state["busy"] = False

    # ---- 主功能：剪贴板监听（Qt 原生，防抖 300ms） ----
    debounce = QTimer()
    debounce.setSingleShot(True)
    debounce.setInterval(300)

    def on_clipboard_changed():
        if not cfg.enabled:
            return
        if time.time() < state["cb_paused_until"]:
            return  # 划词取词正在模拟复制，忽略这次剪贴板变化
        if state["suppress"]:
            state["suppress"] = False
            return
        text = QApplication.clipboard().text().strip()
        if not text or text == state["last"]:
            return
        state["last"] = text
        logger.info("clipboard updated: %d chars", len(text))
        debounce.start()

    debounce.timeout.connect(lambda: start_worker(state["last"]))
    QApplication.clipboard().dataChanged.connect(on_clipboard_changed)
    pw.sig_copied.connect(lambda: state.update(suppress=True))

    # ---- 可选功能：鼠标划词 ----
    def mouse_capture(start, end):
        try:
            # 取词要模拟复制，暂停剪贴板监听以免自己触发自己
            state["cb_paused_until"] = time.time() + 2.0
            res = capture.get_selection(start, end, cfg.max_chars)
            text = (res.get("text") or "").strip()
            logger.info("mouse trigger=%s,%s ibeam=%s elevated=%s captured=%s",
                        start, end, res.get("ibeam"), res.get("elevated"),
                        len(text) if text else 0)
            if not text:
                if res.get("elevated") or res.get("ibeam"):
                    chip = "提示"
                    msg = ("该窗口可能以管理员权限运行，需要以管理员身份运行本"
                           "程序才能翻译。" if res.get("elevated")
                           else "这个位置没有取到可选中的文字。")
                    w, h = popup_mod.estimate_logical_size(30)
                    px, py = locator.compute_popup_position(
                        None, end, end, w, h)
                    pw.sig_show.emit(px, py, "未取到选中文本", msg, chip)
                # 光标不是 I 形 → 大概率不是文本选区，静默不打扰
                return
            start_worker(text, res.get("rect"), start, end)
        except Exception as e:  # noqa: BLE001
            logger.info("mouse capture error: %s", e)
        finally:
            state["cb_paused_until"] = 0.0

    def on_mouse_select(start, end):
        if not cfg.mouse_trigger:
            return
        with state_lock:
            if state["busy"]:
                return
        threading.Thread(target=mouse_capture, args=(start, end),
                         daemon=True).start()

    def guard(x, y):
        """左键按下时的拦截：点在弹窗上→消费；点在弹窗外→关弹窗。"""
        if pw.is_visible_native():
            if pw.is_over(x, y):
                return True
            pw.sig_hide.emit()
        return False

    detector = trigger_mod.TriggerDetector(cfg, on_mouse_select, guard)

    from pynput import keyboard as kb_mod
    from pynput import mouse as mouse_mod

    mouse_listener = mouse_mod.Listener(
        on_move=detector.on_move, on_click=detector.on_click)
    mouse_listener.start()

    def on_key(key):
        if key == kb_mod.Key.esc:
            pw.sig_hide.emit()
    kb_listener = kb_mod.Listener(on_press=on_key)
    kb_listener.start()

    if args.smoke:
        def smoke():
            try:
                print("[smoke] mouse trigger enabled:", cfg.mouse_trigger)
                print("[smoke] locator:",
                      locator.compute_popup_position(
                          None, (100, 100), (120, 120),
                          *popup_mod.estimate_logical_size(30)))
                print("[smoke] PASS")
            except Exception as e:  # noqa: BLE001
                print("[smoke] FAIL:", e)
            app.quit()
        QTimer.singleShot(1500, smoke)

    if args.selftest:
        def selftest_set():
            QApplication.clipboard().setText(
                "Life is like a box of chocolates. You never know "
                "what you're gonna get.")
            print("[selftest] clipboard set, waiting for translation...")

        def selftest_sample(tag):
            g = pw.geometry()
            print("[selftest %s] qtVisible=%s nativeVisible=%s geo=(%d,%d,%d,%d) "
                  "contentLen=%d"
                  % (tag, pw.isVisible(), pw.is_visible_native(),
                     g.x(), g.y(), g.width(), g.height(),
                     len(pw.result_label.text())))

        def selftest_check():
            try:
                selftest_sample("final")
                visible = pw.is_visible_native()
                content = pw.result_label.text()
                ok = visible and bool(content) and content != "翻译中…"
                print("[selftest]", "PASS" if ok else "FAIL")
            except Exception as e:  # noqa: BLE001
                print("[selftest] FAIL:", e)
            app.quit()
        QTimer.singleShot(1000, selftest_set)
        QTimer.singleShot(9000, selftest_check)

    app.exec()

    mouse_listener.stop()
    kb_listener.stop()


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001  # pythonw 无控制台，崩溃必须留痕
        import traceback
        try:
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write("FATAL\n" + traceback.format_exc() + "\n")
        except OSError:
            pass
        raise
