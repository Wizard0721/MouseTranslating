"""鼠标划词触发判定（可选功能）：长按拖动状态机。

判定规则：左键按下 → 期间有拖动 → 松开时
  按住时长 >= cfg.hold_ms 且 最大位移 >= cfg.drag_px
才视为一次「有意的长按拖动选区」，触发 on_select(start, end)。
弹窗上的鼠标事件由 guard() 拦截。
"""
import time

from pynput import mouse as _mouse


class TriggerDetector:
    def __init__(self, cfg, on_select, guard):
        """guard(x, y) -> bool：左键按下时先问它。返回 True 表示事件被消费
        （如点在弹窗上），不再参与选区判定。"""
        self.cfg = cfg
        self.on_select = on_select
        self.guard = guard
        self._down = False
        self._t0 = 0.0
        self._sx = self._sy = 0
        self._minx = self._maxx = self._miny = self._maxy = 0

    def on_move(self, x, y):
        if not self._down:
            return
        if x < self._minx:
            self._minx = x
        elif x > self._maxx:
            self._maxx = x
        if y < self._miny:
            self._miny = y
        elif y > self._maxy:
            self._maxy = y

    def on_click(self, x, y, button, pressed):
        if button != _mouse.Button.left:
            self._down = False
            return
        if pressed:
            if self.guard(x, y):
                self._down = False
                return
            self._down = True
            self._t0 = time.perf_counter()
            self._sx, self._sy = x, y
            self._minx = self._maxx = x
            self._miny = self._maxy = y
        else:
            if not self._down:
                return
            self._down = False
            hold_ms = (time.perf_counter() - self._t0) * 1000.0
            span_x = self._maxx - self._minx
            span_y = self._maxy - self._miny
            if hold_ms >= self.cfg.hold_ms and max(span_x, span_y) >= self.cfg.drag_px:
                self.on_select((self._sx, self._sy), (x, y))
