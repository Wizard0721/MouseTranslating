"""鼠标划词取词（可选功能）：模拟复制读剪贴板为主，UIA 兜底。

返回 dict:
  text      选中文本（可能为 None）
  rect      选区屏幕矩形 (left, top, width, height)，物理像素，可能为 None
  ibeam     取词时鼠标是否为 I 形文本光标
  elevated  前台窗口疑似以管理员权限运行
"""
import ctypes
import time
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
VK_CONTROL = 0x11
VK_INSERT = 0x2D
VK_C = 0x43
KEYEVENTF_KEYUP = 0x0002
IDC_IBEAM = 32513

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# 声明参数/返回类型：句柄是 64 位，不声明会被截断成 32 位 int 而 OverflowError
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.CloseClipboard.restype = wintypes.BOOL
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = wintypes.LPVOID
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND,
                                            ctypes.POINTER(wintypes.DWORD)]
user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
user32.LoadCursorW.restype = wintypes.HANDLE
user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD,
                               ctypes.c_size_t]


class CURSORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hCursor", wintypes.HANDLE),
        ("ptScreenPos", wintypes.POINT),
    ]


user32.GetCursorInfo.argtypes = [ctypes.POINTER(CURSORINFO)]


# ---------- 剪贴板（ctypes 直连） ----------

def _open_clipboard(retries=10):
    for _ in range(retries):
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.02)
    return False


def read_clipboard_text():
    """读 CF_UNICODETEXT，读不到返回 None。"""
    if not _open_clipboard():
        return None
    try:
        h = user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return None
        ptr = kernel32.GlobalLock(h)
        if not ptr:
            return None
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(h)
    finally:
        user32.CloseClipboard()


def write_clipboard_text(text):
    """写 CF_UNICODETEXT（会清空剪贴板其他格式）。"""
    if not _open_clipboard():
        return False
    try:
        user32.EmptyClipboard()
        data = ctypes.create_unicode_buffer(text)
        h = kernel32.GlobalAlloc(GMEM_MOVEABLE, ctypes.sizeof(data))
        if not h:
            return False
        ptr = kernel32.GlobalLock(h)
        if not ptr:
            return False
        ctypes.memmove(ptr, data, ctypes.sizeof(data))
        kernel32.GlobalUnlock(h)
        user32.SetClipboardData(CF_UNICODETEXT, h)
        return True
    finally:
        user32.CloseClipboard()


def _send_copy(vk):
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


def _wait_clipboard_change(old, timeout):
    """轮询剪贴板直到文本 != old，返回新文本；超时返回 None。"""
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        cur = read_clipboard_text()
        if cur is not None and cur != old:
            return cur
        time.sleep(0.03)
    return None


def clipboard_fallback(timeout=0.35):
    """模拟 Ctrl+Insert（失败再 Ctrl+C）读取选中文本，读完恢复原剪贴板。"""
    time.sleep(0.05)  # 松开鼠标后给应用一点时间稳定选区
    old = read_clipboard_text()
    _send_copy(VK_INSERT)
    text = _wait_clipboard_change(old, timeout)
    if text is None:
        _send_copy(VK_C)
        text = _wait_clipboard_change(old, timeout)
    time.sleep(0.05)
    final = read_clipboard_text()
    if old is not None and final != old:
        write_clipboard_text(old)
    return text


# ---------- 光标形状 / 权限 ----------

def cursor_is_ibeam():
    ci = CURSORINFO()
    ci.cbSize = ctypes.sizeof(CURSORINFO)
    if not user32.GetCursorInfo(ctypes.byref(ci)):
        return False
    return bool(ci.hCursor) and ci.hCursor == user32.LoadCursorW(None, IDC_IBEAM)


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def foreground_elevated():
    """前台窗口进程是否疑似管理员权限（本程序非管理员时打不开它）。"""
    try:
        hwnd = user32.GetForegroundWindow()
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return False
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False,
                                 pid.value)
        if not h:
            return not is_admin()
        kernel32.CloseHandle(h)
    except Exception:
        pass
    return False


# ---------- UI Automation ----------

def uia_current_control():
    import uiautomation as auto
    control = None
    try:
        control = auto.ControlFromCursor()
    except Exception:
        control = None
    if control is None:
        try:
            control = auto.GetFocusedControl()
        except Exception:
            control = None
    return control


def uia_get_selection(max_chars):
    """从鼠标位置/焦点控件读选中文本。返回 (text, rect)。"""
    control = uia_current_control()
    if control is None:
        return None, None
    import uiautomation as auto
    candidates = [control]
    try:
        parent = control.GetParentControl()
        if parent:
            candidates.append(parent)
    except Exception:
        pass
    for c in candidates:
        try:
            pat = c.GetPattern(auto.PatternId.TextPattern)
            if not pat:
                continue
            sels = pat.GetSelection()
            if not sels:
                continue
            t = sels[0].GetText(max_chars + 1)
            if t and t.strip():
                rect = None
                try:
                    rects = sels[0].GetBoundingRect()
                    if rects:
                        l, tp, w, h = rects[0]
                        rect = (int(l), int(tp), int(w), int(h))
                except Exception:
                    pass
                return t[:max_chars], rect
        except Exception:
            continue
    return None, None


# ---------- 入口 ----------

def get_selection(start, end, max_chars):
    """主路径：模拟复制读剪贴板（跨行选区也能完整拿到）。
    兜底：UI Automation 直接读选区（不碰剪贴板）。"""
    res = {"text": None, "rect": None, "ibeam": False, "elevated": False}
    try:
        res["ibeam"] = cursor_is_ibeam()
    except Exception:
        pass
    res["elevated"] = foreground_elevated()

    # 主路径：剪贴板
    try:
        text = clipboard_fallback()
    except Exception:
        text = None
    if text and text.strip():
        res["text"] = text.strip()
        return res

    # 兜底：UIA（剪贴板被占用/权限拦截时）
    try:
        text, rect = uia_get_selection(max_chars)
    except Exception:
        text, rect = None, None
    if text and text.strip():
        res["text"] = text.strip()
        res["rect"] = rect
    return res
