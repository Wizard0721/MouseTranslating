"""弹窗定位：选区矩形 → 弹窗物理像素位置。

规则：上方优先（留 8px 间距）；上方放不下翻到下方；下方也放不下贴工作区底边；
水平方向钳制在目标显示器工作区内。多显示器按鼠标所在屏幕的 DPI 换算弹窗物理尺寸。
"""
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
try:
    _shcore = ctypes.WinDLL("shcore")
except Exception:
    _shcore = None

MONITOR_DEFAULTTONEAREST = 2
MDT_EFFECTIVE_DPI = 0


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]


def _work_area(x, y):
    pt = wintypes.POINT(int(x), int(y))
    hmon = user32.MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST)
    if not hmon:
        # 兜底：主屏全屏区域
        return wintypes.RECT(0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    if not user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
        return wintypes.RECT(0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
    return mi.rcWork


def _scale_at(x, y):
    """该屏幕的 DPI 缩放系数（96 DPI = 1.0）。"""
    if _shcore:
        pt = wintypes.POINT(int(x), int(y))
        hmon = user32.MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST)
        if hmon:
            dx = wintypes.UINT()
            dy = wintypes.UINT()
            _shcore.GetDpiForMonitor.argtypes = [
                wintypes.HMONITOR, wintypes.DWORD,
                ctypes.POINTER(wintypes.UINT), ctypes.POINTER(wintypes.UINT),
            ]
            if _shcore.GetDpiForMonitor(hmon, MDT_EFFECTIVE_DPI,
                                        ctypes.byref(dx), ctypes.byref(dy)) == 0 and dx.value:
                return dx.value / 96.0
    return 1.0


def compute_popup_position(rect, start, end, logical_w, logical_h, gap=8):
    """rect: UIA 选区矩形 (l,t,w,h) 或 None；start/end: 鼠标按下/松开点。
    logical_w/h: 弹窗逻辑尺寸。返回弹窗左上角物理像素 (x, y)。"""
    if rect and rect[2] > 0 and rect[3] > 0:
        l, t, w, h = rect
    else:
        l, t = end
        w = h = 0

    scale = _scale_at(l, t if h else end[1])
    pw = logical_w * scale
    ph = logical_h * scale

    wa = _work_area(l, t if h else end[1])

    x = min(max(l, wa.left), max(wa.right - pw, wa.left))

    if t - ph - gap >= wa.top:
        y = t - ph - gap            # 上方放得下 → 上方
    else:
        y = t + h + gap             # 翻到下方
    if y + ph > wa.bottom:
        y = wa.bottom - ph          # 下方也放不下 → 贴底边

    return int(x), int(max(y, wa.top))
