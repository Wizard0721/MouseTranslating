"""配置读写。"""
import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

_DEFAULTS = {
    "api_key": "",
    "model": "deepseek-flash",
    "max_chars": 5000,
    "enabled": True,
    "mouse_trigger": False,  # 鼠标划词翻译（实验性，默认关）
    "hold_ms": 200,          # 划词判定：按住时长下限（毫秒）
    "drag_px": 12,           # 划词判定：最小拖动位移（像素）
}


class Config:
    def __init__(self, data):
        for k, v in _DEFAULTS.items():
            setattr(self, k, data.get(k, v))

    @classmethod
    def load(cls):
        data = dict(_DEFAULTS)
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data.update(json.load(f))
        except (OSError, json.JSONDecodeError):
            pass
        return cls(data)

    def save(self):
        data = {k: getattr(self, k) for k in _DEFAULTS}
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
