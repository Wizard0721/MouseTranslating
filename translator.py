"""DeepSeek Flash 翻译（OpenAI 兼容 /chat/completions，SSE 流式）。

已按官方文档（api-docs.deepseek.com）核实：
  - 模型名 deepseek-flash（deepseek-chat 已于 2026-07-24 停用）
  - 关闭思考模式："thinking": {"type": "disabled"}
"""
import json
import re
import threading
from collections import OrderedDict

import requests

API_URL = "https://api.deepseek.com/chat/completions"
TIMEOUT = 15
CACHE_SIZE = 200

_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


class TranslateError(Exception):
    pass


def looks_chinese(text):
    s = text.strip()
    if not s:
        return False
    return len(_CJK.findall(s)) / max(len(s), 1) > 0.3


def _system_prompt(to_zh):
    if to_zh:
        return ("你是翻译引擎。把用户发来的内容翻译成简体中文，"
                "只输出译文本身，不要任何解释、前缀或后缀。")
    return ("You are a translation engine. Translate the user's content into "
            "natural English. Output only the translation itself, with no "
            "explanations, prefixes or suffixes.")


_cache = OrderedDict()
_lock = threading.Lock()


def translate_stream(text, api_key, model="deepseek-flash", timeout=TIMEOUT):
    """生成器：逐段产出译文。失败抛 TranslateError。"""
    to_zh = not looks_chinese(text)
    key = (text, to_zh)

    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            yield _cache[key]
            return

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _system_prompt(to_zh)},
            {"role": "user", "content": text},
        ],
        "temperature": 0.2,
        "stream": True,
        "thinking": {"type": "disabled"},
    }
    headers = {
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(API_URL, headers=headers, json=payload,
                             stream=True, timeout=timeout)
    except requests.RequestException as e:
        raise TranslateError("网络错误：" + str(e))

    if resp.status_code != 200:
        raise TranslateError("API 返回 %d：%s" % (resp.status_code, resp.text[:200]))

    parts = []
    try:
        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            choices = obj.get("choices") or []
            if not choices:
                continue
            piece = (choices[0].get("delta") or {}).get("content") or ""
            if piece:
                parts.append(piece)
                yield piece
    finally:
        resp.close()

    full = "".join(parts).strip()
    if not full:
        raise TranslateError("API 返回了空结果")

    with _lock:
        _cache[key] = full
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
