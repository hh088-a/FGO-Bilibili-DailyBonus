# -*- coding: utf-8 -*-
"""CI 辅助: 把 updated_auth.json 写回仓库 secret FGO_AUTH_JSON。

需要环境变量:
    GITHUB_REPOSITORY  owner/repo  (Actions 自动提供)
    FGO_UPDATE_PAT     具备 repo 权限的 Personal Access Token
"""
import base64
import json
import os
import sys

import requests
from nacl import encoding, public

UPDATED_FILE = "updated_auth.json"


def main() -> int:
    if not os.path.exists(UPDATED_FILE):
        print("凭据无变化, 跳过 secret 更新")
        return 0

    repo = os.environ["GITHUB_REPOSITORY"]
    pat = os.environ["FGO_UPDATE_PAT"]
    with open(UPDATED_FILE, encoding="utf-8") as f:
        secret_value = f.read()

    headers = {
        "Authorization": f"token {pat}",
        "Accept": "application/vnd.github+json",
    }
    # 1. 获取仓库公钥
    r = requests.get(f"https://api.github.com/repos/{repo}/actions/secrets/public-key",
                     headers=headers, timeout=20)
    r.raise_for_status()
    key_info = r.json()

    # 2. sealed box 加密
    pk = public.PublicKey(key_info["key"].encode(), encoding.Base64Encoder())
    sealed = public.SealedBox(pk).encrypt(secret_value.encode("utf-8"))
    encrypted = base64.b64encode(sealed).decode()

    # 3. 更新 secret
    r = requests.put(
        f"https://api.github.com/repos/{repo}/actions/secrets/FGO_AUTH_JSON",
        headers=headers, timeout=20,
        json={"encrypted_value": encrypted, "key_id": key_info["key_id"]},
    )
    r.raise_for_status()
    print("secret FGO_AUTH_JSON 已更新")
    return 0


if __name__ == "__main__":
    sys.exit(main())
