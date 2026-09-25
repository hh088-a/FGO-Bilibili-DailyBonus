# -*- coding: utf-8 -*-
"""B站扫码登录助手: 获取 FGO B服签到所需的 access_token。

用法:
    python login_qr.py run "御主名" [平台]      # 一步到位: 显示二维码 -> 扫码 -> 保存凭据
    python login_qr.py request "御主名" [平台]  # 仅生成二维码(qr.png)与临时状态
    python login_qr.py poll                     # 等待扫码结果并保存凭据(配合 request 使用)

平台: android(默认, 安卓B服) 或 ios(iOS B服)
凭据保存到 auth.json (等同账号密码, 请勿分享/提交)。
"""
import json
import os
import sys

import qrcode

import fgo_cn

AUTH_FILE = "auth.json"
PENDING_FILE = "pending_qr.json"
QR_PNG = "qr.png"
PLATFORMS = {"android": "android_bili", "ios": "ios_bili"}


def parse_platform(value: str | None) -> str:
    if not value:
        return "android_bili"
    p = PLATFORMS.get(value.lower())
    if not p:
        raise SystemExit(f"未知平台 {value!r}, 可选: android / ios")
    return p


def do_request(nickname: str, platform: str) -> int:
    auth_code, qr_url = fgo_cn.create_qr()
    qr = qrcode.QRCode(border=1)
    qr.add_data(qr_url)
    qr.make()
    qr.make_image().save(QR_PNG)
    with open(PENDING_FILE, "w", encoding="utf-8") as f:
        json.dump({"auth_code": auth_code, "nickname": nickname, "platform": platform, "qr_url": qr_url}, f)
    print(f"二维码已保存到 {QR_PNG}, 请用手机 Bilibili App 扫码并确认")
    print(f"链接: {qr_url}\n")
    qr.print_ascii(invert=True)
    return 0


def do_poll(timeout: int = 180) -> int:
    try:
        with open(PENDING_FILE, encoding="utf-8") as f:
            pending = json.load(f)
    except FileNotFoundError:
        print(f"找不到 {PENDING_FILE}, 请先运行 request")
        return 1

    def show(msg):
        print(f"  [{msg}]", flush=True)

    try:
        info = fgo_cn.poll_qr(pending["auth_code"], status_cb=show, timeout_seconds=timeout)
    except fgo_cn.FgoError as exc:
        print(f"登录失败: {exc}")
        return 1

    import secrets
    data = {
        "platform": pending.get("platform", "android_bili"),
        "mid": info["mid"],
        "username": info["username"],
        "nickname": pending["nickname"],
        "access_token": info["access_token"],
        "refresh_token": info.get("refresh_token", ""),
        "expires_at": info["expires_at"],
        "device_id": secrets.token_hex(16),
    }
    with open(AUTH_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.remove(PENDING_FILE)
    print(f"登录成功! B站账号: {info['username']} (mid={info['mid']})")
    print(f"凭据已保存到 {AUTH_FILE} —— 请勿分享或提交到仓库。")
    return 0


def do_run(nickname: str, platform: str) -> int:
    auth_code, qr_url = fgo_cn.create_qr()
    print("请用手机 Bilibili App 扫码:\n")
    print(f"  {qr_url}\n")
    qr = qrcode.QRCode(border=1)
    qr.add_data(qr_url)
    qr.print_ascii(invert=True)
    with open(PENDING_FILE, "w", encoding="utf-8") as f:
        json.dump({"auth_code": auth_code, "nickname": nickname, "platform": platform, "qr_url": qr_url}, f)
    return do_poll()


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cmd = sys.argv[1]
    if cmd == "request" and len(sys.argv) >= 3:
        return do_request(sys.argv[2], parse_platform(sys.argv[3] if len(sys.argv) > 3 else None))
    if cmd == "poll":
        return do_poll()
    if cmd == "run" and len(sys.argv) >= 3:
        return do_run(sys.argv[2], parse_platform(sys.argv[3] if len(sys.argv) > 3 else None))
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
