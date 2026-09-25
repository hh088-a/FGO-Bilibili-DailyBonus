# -*- coding: utf-8 -*-
"""FGO 国服(B服) 登录/签到协议实现。

链路: gamedata(member) -> logintomembercenter -> login -> toplogin
协议参考(公开研究):
  - Chaldea  https://github.com/chaldea-center/chaldea (AGPL-3.0)
  - fgo-cn-toplogin-extractor  https://github.com/AkatuRegumi/fgo-cn-toplogin-extractor (AGPL-3.0)
仅供个人账号使用。
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import time
import uuid
from collections import OrderedDict
from typing import Any
from urllib.parse import unquote

import requests

# ---- B站 TV 端 OAuth(扫码登录用) ----
TV_APPKEY = "4409e2ce8ffd12b8"
TV_APPSEC = "59b43e04ad6965f34319062b478f83dd"
TV_AUTH_URL = "https://passport.bilibili.com/x/passport-tv-login/qrcode/auth_code"
TV_POLL_URL = "https://passport.bilibili.com/x/passport-tv-login/qrcode/poll"
BILI_NAV_URL = "https://api.bilibili.com/x/web-interface/nav"

# ---- FGO 国服元数据 ----
CHALDEA_GAMETOP_URLS = (
    "https://data-cn.chaldea.center/gametop.json",
    "https://data.chaldea.center/gametop.json",
)
FGO_CONFIG_URL = "https://static.biligame.com/config/fgo.config.js"

DEVELOPMENT_AUTH_CODE = "aK8mTxBJCwZyxBjNJSKA5xCWL7zKtgZEQNiZmffXUbyQd5aLun"
FUNNY_KEY = "B5UI78B3486A7B48IB9AUF8E8P97CPI9"
DEFAULT_UNITY = "2022.3.62f2"
TIMEOUT = (12, 35)
APPLE_SHOP_ID = 13000000  # 主界面 AP 加号: 树苗+40AP -> 青铜果实 (shoppurchase)
APPLE_COST = 40           # 一次合成消耗 AP (另需树苗)
AP_RECOVER_SECONDS = 300  # AP 每 300 秒回复 1 点 (已实测确认)

PLATFORMS: dict[str, dict[str, Any]] = {
    "android_bili": {
        "label": "安卓 B服",
        "host": "https://le1-bili-fate.bilibiligame.net",
        "rkchannel": 24,
        "cPlat": 3,
        "uPlat": 3,
        "is_android": True,
        "os": "Android OS 7.1.2 / API-25 (N2G48C/4565141)",
        "ptype": "vivo V1938CT",
    },
    "ios_bili": {
        "label": "iOS B服",
        "host": "https://le1-ios-fate.bilibiligame.net",
        "rkchannel": 996,
        "cPlat": 2,
        "uPlat": 2,
        "is_android": False,
        "os": "iPadOS 15.2",
        "ptype": "iPad7,3",
    },
}


class FgoError(RuntimeError):
    pass


# ================= B站扫码授权 =================

def _sign_tv(params: dict[str, Any]) -> dict[str, str]:
    p = {k: str(v) for k, v in params.items()}
    query = "&".join(f"{k}={p[k]}" for k in sorted(p))
    p["sign"] = hashlib.md5((query + TV_APPSEC).encode("utf-8")).hexdigest()
    return p


def _passport_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
    })
    return s


def create_qr() -> tuple[str, str]:
    """申请扫码登录二维码, 返回 (auth_code, qr_url)。"""
    params = _sign_tv({"appkey": TV_APPKEY, "local_id": 0, "ts": int(time.time())})
    r = _passport_session().post(TV_AUTH_URL, data=params, timeout=TIMEOUT)
    r.raise_for_status()
    payload = r.json()
    if payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
        raise FgoError(f"二维码申请失败: code={payload.get('code')} message={payload.get('message')}")
    data = payload["data"]
    auth_code, qr_url = str(data.get("auth_code") or ""), str(data.get("url") or "")
    if not auth_code or not qr_url:
        raise FgoError("二维码响应缺少 auth_code/url")
    return auth_code, qr_url


def poll_qr(auth_code: str, status_cb=None, timeout_seconds: int = 180) -> dict[str, Any]:
    """轮询扫码结果, 成功返回 {mid, username, access_token, refresh_token, expires_at}。"""
    sess = _passport_session()
    deadline = time.time() + timeout_seconds
    last_code = None
    while time.time() < deadline:
        time.sleep(2)
        params = _sign_tv({
            "appkey": TV_APPKEY, "auth_code": auth_code,
            "local_id": 0, "ts": int(time.time()),
        })
        r = sess.post(TV_POLL_URL, data=params, timeout=TIMEOUT)
        r.raise_for_status()
        result = r.json()
        code = result.get("code")
        if code != last_code:
            if status_cb:
                if code in (86039, 86101):
                    status_cb("等待扫码…")
                elif code == 86090:
                    status_cb("已扫码, 等待手机端确认…")
                elif code == 86038:
                    raise FgoError("二维码已过期, 请重试")
                elif code != 0:
                    status_cb(f"等待授权: code={code}")
            last_code = code
        if code != 0:
            continue

        payload = result.get("data")
        if not isinstance(payload, dict):
            raise FgoError("扫码成功响应缺少 data")
        token_info = payload.get("token_info") if isinstance(payload.get("token_info"), dict) else payload
        token = str(token_info.get("access_token") or "")
        refresh = str(token_info.get("refresh_token") or "")
        mid = int(token_info.get("mid") or 0)
        expires_in = int(token_info.get("expires_in") or 0)
        if not token or mid <= 0:
            raise FgoError("扫码成功但缺少 access_token/mid")

        username = ""
        cookies = {}
        ci = payload.get("cookie_info")
        if isinstance(ci, dict) and isinstance(ci.get("cookies"), list):
            cookies = {str(c["name"]): str(c["value"]) for c in ci["cookies"]
                       if isinstance(c, dict) and c.get("name")}
        if cookies:
            try:
                nav = requests.get(BILI_NAV_URL, cookies=cookies,
                                   headers={"User-Agent": "Mozilla/5.0"}, timeout=TIMEOUT)
                nd = nav.json()
                if nd.get("code") == 0:
                    username = str(nd["data"].get("uname") or "")
            except Exception:
                pass
        return {
            "mid": mid,
            "username": username,
            "access_token": token,
            "refresh_token": refresh,
            "expires_at": int(time.time()) + expires_in if expires_in > 0 else 0,
        }
    raise FgoError("等待扫码超时")


# ================= FGO 协议 =================

def refresh_access_token(access_token: str, refresh_token: str) -> dict[str, Any]:
    """刷新 B站 access_token。成功返回 {access_token, refresh_token, expires_at}。

    注意: 刷新成功后旧 token 立即失效, 调用方必须立刻保存新 token。
    """
    params = _sign_tv({
        "appkey": TV_APPKEY,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "ts": int(time.time()),
    })
    r = _passport_session().post(
        "https://passport.bilibili.com/api/oauth2/refreshToken",
        data=params, timeout=TIMEOUT,
    )
    r.raise_for_status()
    payload = r.json()
    if payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
        raise FgoError(f"token 刷新失败: code={payload.get('code')} message={payload.get('message')}")
    data = payload["data"]
    return {
        "access_token": str(data["access_token"]),
        "refresh_token": str(data.get("refresh_token") or refresh_token),
        "expires_at": int(time.time()) + int(data.get("expires_in") or 0),
    }


def parse_fgo_payload(data: Any) -> dict[str, Any]:
    if isinstance(data, dict):
        return data
    if isinstance(data, bytes):
        data = data.decode("utf-8", errors="replace")
    s = str(data).strip()
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    try:
        obj = json.loads(base64.b64decode(unquote(s).strip()).decode("utf-8"))
        if isinstance(obj, dict):
            return obj
    except Exception as exc:
        raise FgoError(f"无法解码 FGO 响应: {exc}") from exc
    raise FgoError("FGO 响应不是 JSON 对象")


def response_detail(payload: dict[str, Any], nid: str) -> dict[str, Any]:
    for item in payload.get("response") or []:
        if not isinstance(item, dict):
            continue
        if item.get("nid", "") == nid:
            code = str(item.get("resCode", ""))
            if code not in ("", "00"):
                raise FgoError(f"FGO {nid or 'login'} 失败: resCode={code} detail={item.get('fail')}")
            success = item.get("success")
            return success if isinstance(success, dict) else item
    errors = [f"{x.get('nid')}:{x.get('resCode')}" for x in payload.get("response") or []
              if isinstance(x, dict) and str(x.get("resCode", "")) not in ("", "00")]
    raise FgoError(f"FGO 响应中找不到 {nid!r}, error_codes={errors}")


def _response_usk(payload: dict[str, Any]) -> str | None:
    """从 ac.php 响应提取下一轮会话种子 (response[].usk 或 userGame.usk)。"""
    for item in payload.get("response") or []:
        if isinstance(item, dict) and item.get("usk"):
            return str(item["usk"])
    updated = (payload.get("cache") or {}).get("updated") or {}
    for game in updated.get("userGame") or []:
        if isinstance(game, dict) and game.get("usk"):
            return str(game["usk"])
    return None


def _next_usk(seed: str) -> str:
    """会话种子 -> 下一次请求的 usk (与 sgusk->usk 同一公式)。"""
    return hashlib.md5((FUNNY_KEY + seed).encode("utf-8")).hexdigest()


def _purchase_result(payload: dict[str, Any]) -> dict[str, Any]:
    """解析 shoppurchase 响应 (错误响应 nid 可能不是 purchase, 实测为 "0")。"""
    items = [x for x in payload.get("response") or [] if isinstance(x, dict)]
    for item in items:
        if item.get("nid") == "purchase":
            code = str(item.get("resCode", ""))
            success = item.get("success") or {}
            return {
                "ok": code in ("", "00"),
                "code": code,
                "name": str(success.get("purchaseName") or ""),
                "num": int(success.get("PurchaseNum") or 0),
                "fail": item.get("fail") or {},
            }
    for item in items:
        code = str(item.get("resCode", ""))
        if code not in ("", "00"):
            fail = item.get("fail") or {}
            detail = " ".join(str(fail.get("detail") or fail.get("message") or "").split())
            return {"ok": False, "code": code, "name": "", "num": 0,
                    "fail": detail or fail or "未知错误"}
    return {"ok": False, "code": "missing", "name": "", "num": 0,
            "fail": "响应中找不到结果"}


def ap_state(payload: dict[str, Any]) -> dict[str, int]:
    """从 toplogin/shoppurchase 响应计算 AP 状态。

    公式(已用游戏内显示标定, 2026-09-26, actMax=141 时显示 14, 公式给出 14):
        AP = actMax - ceil((actRecoverAt - serverTime) / 300)
    actRecoverAt 为 AP 回满时刻; 已回满(actRecoverAt<=now)时 AP=actMax。
    返回 {ap, act_max, act_recover_at, server_time}。
    """
    cache = payload.get("cache") or {}
    server_time = int(cache.get("serverTime") or time.time())
    replaced = cache.get("replaced") or {}
    game = (replaced.get("userGame") or [{}])[0] if replaced.get("userGame") else {}
    act_max = int(game.get("actMax") or 0)
    recover_at = int(game.get("actRecoverAt") or 0)
    if act_max <= 0:
        raise FgoError("响应中缺少 actMax, 无法计算 AP")
    if recover_at <= server_time:
        ap = act_max
    else:
        delta = recover_at - server_time
        ap = act_max - -(-delta // AP_RECOVER_SECONDS)  # ceil
        ap = max(0, ap)
    return {"ap": ap, "act_max": act_max, "act_recover_at": recover_at,
            "server_time": server_time}


def fetch_game_top() -> dict[str, Any]:
    last_exc: Exception | None = None
    for url in CHALDEA_GAMETOP_URLS:
        try:
            r = requests.get(url, timeout=TIMEOUT)
            r.raise_for_status()
            cn = r.json().get("CN")
            if isinstance(cn, dict):
                try:
                    rr = requests.get(FGO_CONFIG_URL, timeout=TIMEOUT)
                    m = re.search(r"FateGO_(\d+\.\d+\.\d+)_", rr.text) or \
                        re.search(r'"latest_version"\s*:\s*"(\d+\.\d+\.\d+)"', rr.text)
                    if m:
                        cn["appVer"] = m.group(1)
                except Exception:
                    pass
                return cn
        except Exception as exc:
            last_exc = exc
    raise FgoError(f"无法获取国服版本元数据: {last_exc}")


def _game_headers(unity_ver: str, platform: dict[str, Any]) -> dict[str, str]:
    if platform["is_android"]:
        ua = f"UnityPlayer/{unity_ver} (UnityWebRequest/1.0, libcurl/8.10.1-DEV)"
    else:
        ua = "fatego/20 CFNetwork/1327.0.4 Darwin/21.2.0"
    return {
        "Content-Type": "application/x-www-form-urlencoded",
        "Connection": "keep-alive",
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate",
        "X-Unity-Version": unity_ver,
        "User-Agent": ua,
    }


def toplogin(access_token: str, mid: int, username: str, nickname: str,
             device_id: str, platform_id: str = "android_bili",
             apple_num: int = 0, apple_min_ap: int = 0, log_cb=print) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """执行完整登录链, 返回 (toplogin 响应 payload, 苹果合成结果 apple_num=0 时为 None)。"""
    platform = PLATFORMS[platform_id]
    cn = fetch_game_top()
    app_ver = str(cn.get("appVer") or "").strip()
    data_ver = int(cn.get("dataVer") or 0)
    unity_ver = str(cn.get("unityVer") or DEFAULT_UNITY)
    if not app_ver or data_ver <= 0:
        raise FgoError(f"版本元数据异常: {cn}")

    host = platform["host"]
    rkchannel, cplat, uplat = platform["rkchannel"], platform["cPlat"], platform["uPlat"]
    os_name, ptype = platform["os"], platform["ptype"]
    log_cb(f"连接 {platform['label']}, 当前版本 FGO {app_ver}")

    sess = requests.Session()
    headers = _game_headers(unity_ver, platform)
    app_start = time.monotonic() - 30.0

    def post(url, form):
        r = sess.post(url, data=form, headers=headers, timeout=TIMEOUT)
        r.raise_for_status()
        return r

    # 1/4 gamedata
    log_cb("1/4 获取 gamedata…")
    member = OrderedDict([
        ("deviceid", ""), ("t", "22360"), ("v", "1.0.1"), ("s", "1"),
        ("mac", "00000000000000E0"), ("os", ""), ("ptype", ""), ("imei", "aaaaa"),
        ("username", "lv9999"), ("type", "login"), ("password", "111111"),
        ("rksdkid", "1"), ("rkchannel", rkchannel), ("cPlat", cplat), ("uPlat", uplat),
        ("appVer", app_ver), ("dateVer", data_ver), ("lastAccessTime", int(time.time())),
        ("developmentAuthCode", DEVELOPMENT_AUTH_CODE), ("idempotencyKey", str(uuid.uuid4())),
        ("version", data_ver), ("dataVer", data_ver),
    ])
    s = response_detail(parse_fgo_payload(post(f"{host}//rongame_beta/rgfate/60_member/member.php", member).text), "gamedata")
    data_ver = int(s.get("version", data_ver))
    date_ver = data_ver

    # 2/4 B站授权校验
    log_cb("2/4 验证 Bilibili 授权…")
    lm = OrderedDict([
        ("deviceid", ""), ("t", "22360"), ("v", "1.0.1"), ("s", "1"),
        ("mac", "00000000000000E0"), ("os", ""), ("ptype", ""), ("imei", "aaaaa"),
        ("rksdkid", "1"), ("username", username),
    ])
    if platform["is_android"]:
        lm["bundleid"] = "com.bilibili.fatego"
    lm.update(OrderedDict([
        ("type", "token"), ("rkuid", mid), ("access_token", access_token),
        ("rkchannel", rkchannel), ("cPlat", cplat), ("uPlat", uplat),
        ("appVer", app_ver), ("dateVer", data_ver), ("lastAccessTime", int(time.time())),
        ("developmentAuthCode", DEVELOPMENT_AUTH_CODE), ("idempotencyKey", str(uuid.uuid4())),
        ("version", data_ver), ("dataVer", data_ver),
    ]))
    s = response_detail(parse_fgo_payload(post(f"{host}/rongame_beta/rgfate/60_member/logintomembercenter.php", lm).text), "login_to_membercenter")
    rguid, rgusk = str(s["rguid"]), str(s["rgusk"])
    data_ver = int(s.get("dataVer", data_ver))
    date_ver = int(s.get("dateVer", data_ver))
    time.sleep(2)

    # 3/4 建立游戏会话
    log_cb("3/4 建立 FGO 会话…")
    gl = OrderedDict([
        ("deviceid", device_id), ("os", os_name), ("ptype", ptype),
        ("rgsid", 1001), ("rguid", rguid), ("rgusk", rgusk), ("idfa", ""),
        ("v", "1.0.1"), ("mac", "0"), ("imei", ""), ("type", "login"),
        ("nickname", nickname), ("rkchannel", rkchannel), ("cPlat", cplat), ("uPlat", uplat),
        ("assetbundleFolder", ""), ("appVer", app_ver), ("dateVer", date_ver),
        ("lastAccessTime", int(time.time())), ("developmentAuthCode", DEVELOPMENT_AUTH_CODE),
        ("idempotencyKey", str(uuid.uuid4())), ("userAgent", 1), ("t", 20399),
        ("s", 1), ("rksdkid", 1), ("dataVer", data_ver),
    ])
    s = response_detail(parse_fgo_payload(post(f"{host}/rongame_beta/rgfate/60_1001/login.php", gl).text), "")
    sguid = str(s["sguid"])
    sgtype = s.get("sgtype", 2)
    sgtag = str(s.get("sgtag", ""))
    resolved_nickname = str(s.get("nickname") or nickname)
    usk = hashlib.md5((FUNNY_KEY + str(s["sgusk"])).encode("utf-8")).hexdigest()
    time.sleep(5)

    # 4/4 toplogin (即每日签到)
    log_cb("4/4 TopLogin 签到…")
    client_local = time.monotonic() - app_start
    url = (f"{host}/rongame_beta/rgfate/60_1001/ac.php"
           f"?_userId={sguid}&_key=toplogin&_clientLocalTime={client_local:.5f}")
    form = OrderedDict([
        ("nickname", resolved_nickname), ("sgtype", sgtype), ("sgtag", sgtag),
        ("ac", "action"), ("key", "toplogin"), ("deviceid", device_id),
        ("os", os_name), ("ptype", ptype), ("usk", usk), ("umk", ""),
        ("rgsid", 1001), ("rkchannel", rkchannel), ("cPlat", cplat), ("uPlat", uplat),
        ("userId", sguid), ("appVer", app_ver), ("dateVer", date_ver),
        ("lastAccessTime", int(time.time())), ("developmentAuthCode", DEVELOPMENT_AUTH_CODE),
        ("idempotencyKey", str(uuid.uuid4())), ("userAgent", 1), ("dataVer", data_ver),
    ])
    payload = parse_fgo_payload(post(url, form).text)
    response_detail(payload, "login")
    log_cb("TopLogin 完成")

    # 5/5 可选: AP -> 青铜果实 合成 (树苗+40AP, usk 每次响应轮换)
    apple: dict[str, Any] | None = None
    if apple_num > 0:
        apple = {"requested": apple_num, "converted": 0, "name": "", "errors": [],
                 "ap_before": None, "ap_after": None}
        try:
            st = ap_state(payload)
            apple["ap_before"] = st["ap"]
            log_cb(f"当前 AP: {st['ap']}/{st['act_max']}")
        except FgoError as exc:
            log_cb(f"AP 检测失败: {exc}")
            st = None
        if st is not None and apple_min_ap > 0 and st["ap"] < apple_min_ap:
            apple["errors"].append(f"AP={st['ap']} < {apple_min_ap}, 未达合成阈值")
            log_cb(f"苹果合成跳过: AP={st['ap']} < {apple_min_ap}")
            return payload, apple
        log_cb(f"苹果合成 ×{apple_num}…")
        seed = _response_usk(payload)
        if seed:
            usk = _next_usk(seed)
        if not seed:
            log_cb("提示: toplogin 响应未含 usk 种子, 尝试沿用当前 usk")
        est_ap = st["ap"] if st is not None else None
        for i in range(apple_num):
            if est_ap is not None and i > 0:
                if apple_min_ap > 0 and est_ap < apple_min_ap:
                    apple["errors"].append(f"AP={est_ap} < {apple_min_ap}, 停止继续合成")
                    break
                if est_ap < APPLE_COST:
                    apple["errors"].append(f"AP={est_ap} < {APPLE_COST}, AP 不足")
                    break
            client_local = time.monotonic() - app_start
            buy_url = (f"{host}/rongame_beta/rgfate/60_1001/ac.php"
                       f"?_userId={sguid}&_key=shoppurchase&_clientLocalTime={client_local:.5f}")
            buy = OrderedDict([
                ("ac", "action"), ("key", "shoppurchase"), ("deviceid", device_id),
                ("os", os_name), ("ptype", ptype), ("usk", usk), ("umk", ""),
                ("rgsid", 1001), ("rkchannel", rkchannel), ("cPlat", cplat), ("uPlat", uplat),
                ("userId", sguid), ("appVer", app_ver), ("dateVer", date_ver),
                ("lastAccessTime", int(time.time())), ("developmentAuthCode", DEVELOPMENT_AUTH_CODE),
                ("idempotencyKey", str(uuid.uuid4())), ("userAgent", 1), ("dataVer", data_ver),
                ("id", APPLE_SHOP_ID), ("num", 1),
            ])
            buy_payload = parse_fgo_payload(post(buy_url, buy).text)
            result = _purchase_result(buy_payload)
            if not result["ok"]:
                log_cb("合成响应诊断: " + json.dumps(
                    buy_payload.get("response"), ensure_ascii=False)[:500])
                apple["errors"].append(f"resCode={result['code']} {result['fail']}")
                break
            apple["converted"] += 1
            apple["name"] = result["name"] or apple["name"]
            if est_ap is not None:
                est_ap = max(0, est_ap - APPLE_COST)
                apple["ap_after"] = est_ap
            next_seed = _response_usk(buy_payload)
            if next_seed:
                usk = _next_usk(next_seed)
            time.sleep(1.5)
        if apple["converted"]:
            log_cb(f"苹果合成完成: {apple['converted']}/{apple_num}")
        else:
            log_cb(f"苹果合成未完成: {'; '.join(apple['errors']) or '未知'}")
    return payload, apple
