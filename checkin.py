# -*- coding: utf-8 -*-
"""FGO B服每日签到: 执行 toplogin 并输出账号/奖励摘要。

用法:
    python checkin.py           # 读取 auth.json (本地) 或环境变量 FGO_AUTH_JSON (CI)

token 剩余有效期不足 30 天时自动刷新;
凭据有变化时会写回 auth.json (本地) 或生成 updated_auth.json (CI, 供更新 secret)。
"""
import base64
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import fgo_cn

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

AUTH_FILE = "auth.json"
UPDATED_FILE = "updated_auth.json"
REFRESH_THRESHOLD = 30 * 86400  # 剩余不足 30 天则刷新

_START = time.time()


def log(msg: str) -> None:
    """带时间戳的单行日志。"""
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def log_cb(msg: str) -> None:
    """传给 fgo_cn 的日志回调。"""
    log(msg)


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


def publish_report(report: str) -> None:
    """可选地推送到 Telegram，并写入私有 GitHub 日志仓库。"""
    token = os.environ.get("FGO_LOG_PAT", "").strip()
    owner = os.environ.get("FGO_LOG_OWNER", "").strip()
    repo = os.environ.get("FGO_LOG_REPO", "FGO-Bilibili-DailyBonusLog").strip()
    if token and owner:
        now = datetime.now(timezone(timedelta(hours=8)))
        path = now.strftime("%Y/%m/%d.log")
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            current = __import__("requests").get(url, headers=headers, timeout=20)
            payload = {
                "message": f"签到日志 {path}",
                "content": base64.b64encode((report + "\n").encode("utf-8")).decode("ascii"),
            }
            if current.ok and current.json().get("sha"):
                payload["sha"] = current.json()["sha"]
                old = base64.b64decode(current.json().get("content", "")).decode("utf-8")
                payload["content"] = base64.b64encode((old.rstrip("\n") + "\n" + report + "\n").encode("utf-8")).decode("ascii")
            response = __import__("requests").put(url, headers=headers, json=payload, timeout=20)
            response.raise_for_status()
            print("日志已写入 GitHub 私有仓库")
        except Exception as exc:
            print(f"GitHub 日志上传失败: {type(exc).__name__}: {exc}")

    bot = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_ADMIN_ID", "").strip()
    if bot and chat_id and bot != "nullvalue" and chat_id != "nullvalue":
        try:
            response = __import__("requests").post(
                f"https://api.telegram.org/bot{bot}/sendMessage",
                data={"chat_id": chat_id, "text": report}, timeout=20,
            )
            response.raise_for_status()
            print("Telegram 通知已发送")
        except Exception as exc:
            print(f"Telegram 通知失败: {type(exc).__name__}: {exc}")


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
        log(f"找不到 {AUTH_FILE} 且未设置 FGO_AUTH_JSON, 请先运行  python login_qr.py  扫码登录")
        return 1

    try:
        apple_num = max(0, int(os.environ.get("FGO_APPLE_NUM") or 0))
    except ValueError:
        apple_num = 0
    raw_min_ap = (os.environ.get("FGO_APPLE_AP_MIN") or "120").strip().lower()
    if raw_min_ap in ("max", "full", "满"):
        apple_min_ap = -1  # -1 = AP 满了才合成
        ap_min_txt = "max(AP满了才合成)"
    else:
        try:
            apple_min_ap = max(0, int(raw_min_ap))
        except ValueError:
            apple_min_ap = 120
        ap_min_txt = str(apple_min_ap)
    log(f"开始签到: 御主={auth.get('nickname', '?')} 平台={auth.get('platform', 'android_bili')} "
        f"苹果合成={'关' if apple_num <= 0 else f'{apple_num}个/阈值{ap_min_txt}'}")

    changed = False
    remaining = int(auth.get("expires_at") or 0) - time.time()

    if remaining <= 60:
        log("B站 access_token 已过期, 请重新运行  python login_qr.py  扫码")
        return 1

    if remaining < REFRESH_THRESHOLD and auth.get("refresh_token"):
        log(f"token 剩余 {remaining / 86400:.0f} 天, 执行自动刷新…")
        try:
            new = fgo_cn.refresh_access_token(auth["access_token"], auth["refresh_token"])
        except fgo_cn.FgoError as exc:
            log(f"自动刷新失败(将继续用现有 token 尝试签到): {exc}")
        else:
            auth.update(new)
            changed = True
            log("刷新成功, 新有效期 180 天")
    else:
        log(f"token 剩余有效期 {remaining / 86400:.0f} 天")

    try:
        payload, apple = fgo_cn.toplogin(
            access_token=auth["access_token"],
            mid=int(auth["mid"]),
            username=auth.get("username") or "master",
            nickname=auth["nickname"],
            device_id=auth["device_id"],
            platform_id=auth.get("platform", "android_bili"),
            apple_num=apple_num,
            apple_min_ap=apple_min_ap,
            log_cb=log_cb,
        )
    except fgo_cn.FgoError as exc:
        log(f"签到失败: {exc}")
        return 1
    except Exception as exc:
        log(f"网络或解析错误: {type(exc).__name__}: {exc}")
        return 1
    finally:
        if changed:
            save_auth(auth, from_env)

    print()
    print("===== 签到成功 =====")
    print(summarize(payload))
    if apple is not None:
        if apple.get("ap_before") is not None:
            tail = f" (AP {apple['ap_before']}" + (
                f"→{apple['ap_after']})" if apple.get("ap_after") is not None else ")")
        else:
            tail = ""
        if apple["converted"]:
            print(f"苹果合成: {apple['converted']} 个 ({apple['name']}){tail}")
        elif apple["errors"] and "未达合成阈值" in apple["errors"][0]:
            eta = apple.get("eta_seconds")
            eta_txt = ""
            if eta:
                h, m = divmod(round(eta / 60), 60)
                eta_txt = f", 约 {h}小时{m}分钟后达到阈值" if h else f", 约{m}分钟后达到阈值"
            print(f"苹果合成: 跳过, {apple['errors'][0]}{eta_txt}")
        else:
            print(f"苹果合成: 未完成 ({'; '.join(apple['errors']) or '未知原因'}){tail}")
    report_lines = [
        f"FGO B服签到 - {datetime.now(timezone(timedelta(hours=8))):%Y-%m-%d %H:%M:%S}",
        "状态: 成功",
        f"御主: {auth.get('nickname', '?')}",
        summarize(payload),
    ]
    if apple is not None:
        report_lines.append(f"苹果合成: {apple.get('converted', 0)} 个")
    publish_report("\n".join(report_lines))
    log(f"完成, 耗时 {time.time() - _START:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
