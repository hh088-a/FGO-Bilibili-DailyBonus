# -*- coding: utf-8 -*-
"""mitmproxy addon: 捕获 FGO 游戏请求的 _key 与参数结构 + 响应体。

用法: mitmdump -s capture_keys.py
输出: captured_keys.log (请求参数敏感值打码; 响应完整记录, 仅本地分析)
"""
import time
import re
from urllib.parse import unquote

OUT_FILE = "captured_keys.log"

# 需要打码的敏感参数(值保留首尾特征即可辨认, 不影响结构分析)
SENSITIVE = {
    "access_token", "usk", "rgusk", "sgusk", "authCode", "sign",
    "idempotencyKey", "password", "refresh_token",
}
# 完全隐藏的值
HIDDEN = {"userId", "sguid", "rguid", "rkuid"}


def redact(key: str, value: str) -> str:
    if key in HIDDEN:
        return f"<hidden:{len(value)}chars>"
    if key in SENSITIVE:
        if len(value) <= 8:
            return "<redacted>"
        return f"{value[:4]}…{value[-4:]}"
    return value


def write(text: str) -> None:
    stamp = time.strftime("%H:%M:%S")
    line = f"[{stamp}] {text}"
    print(line, flush=True)
    with open(OUT_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def request(flow):
    host = flow.request.pretty_host
    if "bilibiligame" not in host and "bilibili" not in host:
        return
    path = flow.request.path
    # 只关注游戏动作接口
    if "ac.php" not in path and "member" not in path and "login" not in path.lower():
        return

    key = flow.request.query.get("_key", "")
    write(f"=== {flow.request.method} https://{host}{path.split('?')[0]}")
    write(f"    _key: {key or '(无)'}")

    items = flow.request.urlencoded_form.items(multi=True)
    parts = []
    for k, v in items:
        parts.append(f"{k}={redact(k, unquote(v))}")
    if parts:
        write("    params:")
        for p in parts:
            write(f"      {p}")
    else:
        # query string 参数
        for k, v in flow.request.query.items(multi=True):
            write(f"      query: {k}={redact(k, unquote(v))}")
    write("")


def response(flow):
    host = flow.request.pretty_host
    if "bilibiligame" not in host and "bilibili" not in host:
        return
    path = flow.request.path.split("?")[0]
    if "ac.php" not in path and "member" not in path and "login" not in path.lower():
        return
    if flow.response is None:
        return

    write(f"--- RESPONSE {flow.response.status_code} {path}")
    try:
        body = flow.response.text
    except Exception as exc:
        write(f"    (body 读取失败: {exc})")
        write("")
        return

    # FGO 响应可能超长(toplogin 含大量存档数据), 截断但保留头尾
    if len(body) > 8000:
        body = body[:5000] + "\n...[TRUNCATED]...\n" + body[-2000:]

    for line in body.splitlines():
        write(f"    {line}")

    # 显式提取所有 usk 相关字段(响应中的新会话种子)
    for m in re.finditer(r'"(usk|umk|sgusk|rgusk|lastAccessTime)"\s*:\s*"([^"]*)"', body):
        write(f"    [field] {m.group(1)}={m.group(2)}")
    write("")
