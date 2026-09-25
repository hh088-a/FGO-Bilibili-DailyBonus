# -*- coding: utf-8 -*-
"""FGO B服每日签到: 执行 toplogin 并输出账号/奖励摘要。

用法:
    python checkin.py           # 读取 auth.json (本地) 或环境变量 FGO_AUTH_JSON (CI)

token 剩余有效期不足 30 天时自动刷新;
凭据有变化时会写回 auth.json (本地) 或生成 updated_auth.json (CI, 供更新 secret)。
"""
import json
import os
import sys
import time

import fgo_cn

AUTH_FILE = "auth.json"
UPDATED_FILE = "updated_auth.json"
REFRESH_THRESHOLD = 30 * 86400  # 剩余不足 30 天则刷新


def load_auth() -> tuple[dict, bool]:
    """返回 (auth, from_env)。"""
    env = os.environ.get("FGO_AUTH_JSON", "").strip().lstrip("﻿")
    if env:
        return json.loads(env), True
    with open(AUTH_FILE, encoding="utf-8") as f:
        return json.load(f), False


def save_auth(auth: dict, from_env: bool) -> None:
    if from_env:
        with open(UPDATED_FILE, "w", encoding="utf-8") as f:
            json.dump(auth, f, ensure_ascii=False, indent=2)
    else:
        with open(AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump(auth, f, ensure_ascii=False, indent=2)


def summarize(payload: dict) -> str:
    """从 toplogin 响应中提取账号信息与签到奖励。"""
    lines = []
    cache = payload.get("cache") or {}
    replaced = cache.get("replaced") or {}
    updated = cache.get("updated") or {}

    user_game = (replaced.get("userGame") or [{}])[0]
    if user_game:
        ticket = 0
        for item in replaced.get("userItem") or []:
            if item.get("itemId") == 4001:
                ticket = item.get("num", 0)
                break
        lines.append(f"御主: {user_game.get('name', '?')}  Lv.{user_game.get('lv', '?')}")
        lines.append(f"圣晶石: {user_game.get('stone', '?')}   呼符: {ticket}")

    user_login = (updated.get("userLogin") or [{}])[0]
    if user_login:
        lines.append(f"连续登录: {user_login.get('seqLoginCount', '?')}天 / "
                     f"累计: {user_login.get('totalLoginCount', '?')}天")

    for resp in payload.get("response") or []:
        success = resp.get("success") or {}
        bonus = success.get("seqLoginBonus")
        if bonus:
            b0 = bonus[0]
            lines.append(f"签到奖励: {b0.get('message', '')}")
            for it in b0.get("items") or []:
                lines.append(f"  - {it.get('name')} x{it.get('num')}")
        campaign = success.get("campaignbonus")
        if campaign:
            c0 = campaign[0]
            lines.append(f"活动奖励: {c0.get('name', '')}")
            for it in c0.get("items") or []:
                lines.append(f"  - {it.get('name')} x{it.get('num')}")

    server_time = cache.get("serverTime")
    if server_time:
        lines.append(f"服务器时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(int(server_time)))}")
    return "\n".join(lines) if lines else "(未解析到账号信息, 但 toplogin 已成功)"


def main() -> int:
    try:
        auth, from_env = load_auth()
    except FileNotFoundError:
        print(f"找不到 {AUTH_FILE} 且未设置 FGO_AUTH_JSON, 请先运行  python login_qr.py  扫码登录")
        return 1

    try:
        apple_num = max(0, int(os.environ.get("FGO_APPLE_NUM") or 0))
    except ValueError:
        apple_num = 0

    changed = False
    remaining = int(auth.get("expires_at") or 0) - time.time()

    if remaining <= 60:
        print("B站 access_token 已过期, 请重新运行  python login_qr.py  扫码")
        return 1

    if remaining < REFRESH_THRESHOLD and auth.get("refresh_token"):
        print(f"token 剩余 {remaining / 86400:.0f} 天, 执行自动刷新…")
        try:
            new = fgo_cn.refresh_access_token(auth["access_token"], auth["refresh_token"])
        except fgo_cn.FgoError as exc:
            print(f"自动刷新失败(将继续用现有 token 尝试签到): {exc}")
        else:
            auth.update(new)
            changed = True
            print("刷新成功, 新有效期 180 天")
    else:
        print(f"token 剩余有效期 {remaining / 86400:.0f} 天")

    try:
        payload, apple = fgo_cn.toplogin(
            access_token=auth["access_token"],
            mid=int(auth["mid"]),
            username=auth.get("username") or "master",
            nickname=auth["nickname"],
            device_id=auth["device_id"],
            platform_id=auth.get("platform", "android_bili"),
            apple_num=apple_num,
        )
    except fgo_cn.FgoError as exc:
        print(f"\n签到失败: {exc}")
        return 1
    except Exception as exc:
        print(f"\n网络或解析错误: {type(exc).__name__}: {exc}")
        return 1
    finally:
        if changed:
            save_auth(auth, from_env)

    print("\n===== 签到成功 =====")
    print(summarize(payload))
    if apple is not None:
        if apple["converted"]:
            print(f"苹果合成: {apple['converted']}/{apple['requested']} 个 ({apple['name']})")
        else:
            print(f"苹果合成: 未完成 ({'; '.join(apple['errors']) or '未知原因'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
