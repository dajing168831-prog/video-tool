"""探测方舟账号能用哪些视频模型，以及 Seedance 2.0 是否已开通。

判断办法：故意发一个参数不全的请求。
  - 404 / "does not exist" / "no access"  -> 模型不存在或没开通
  - 400 但抱怨的是参数（duration/ratio/content）-> 模型可用，只是我们没给全
这样一次探测不花钱（不会真的开始生成）。
"""
from __future__ import annotations

import json
import os
import sys
import winreg

import httpx

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "https://ark.cn-beijing.volces.com/api/v3"


def user_env(name: str) -> str:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as k:
            v, _ = winreg.QueryValueEx(k, name)
            return str(v)
    except OSError:
        return ""


KEY = os.environ.get("VT_ARK_API_KEY") or user_env("VT_ARK_API_KEY")
if not KEY:
    print("没有 VT_ARK_API_KEY")
    raise SystemExit(2)
H = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

CANDIDATES = [
    "doubao-seedance-2-0-pro-260101",
    "doubao-seedance-2-0-260101",
    "doubao-seedance-2-0-pro-fast-260101",
    "doubao-seedance-2-0-lite-260101",
    "doubao-seedance-2-0-pro-251015",
    "doubao-seedance-1-0-pro-fast-251015",
    "doubao-seedance-1-0-pro-250528",
    "doubao-seedance-1-0-lite-t2v-250428",
]


def main() -> None:
    # 先看看有没有列模型的接口
    try:
        r = httpx.get(f"{BASE}/models", headers=H, timeout=20)
        print(f"[GET /models] HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:  # noqa: BLE001
        print(f"[GET /models] 失败: {e}")

    for m in CANDIDATES:
        body = {"model": m, "content": []}  # 空 content 必定 400，但能区分"模型不存在"
        try:
            r = httpx.post(f"{BASE}/contents/generations/tasks", headers=H, json=body, timeout=30)
            txt = (r.text or "").replace("\n", " ")[:220]
            print(f"{m:42s} HTTP {r.status_code}  {txt}")
        except Exception as e:  # noqa: BLE001
            print(f"{m:42s} 异常 {e}")
        print("-" * 100)


if __name__ == "__main__":
    main()
