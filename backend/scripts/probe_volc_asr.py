"""探火山大模型录音文件识别：确认凭据能不能用、哪条接口通。

两种调用方式都试：
  submit   —— 异步，audio.url 必须是公网可访问的地址
  flash    —— 同步，audio.data 可以传 base64（适合我们这种音频在本机的场景）

用法：
  set VT_VOLC_API_KEY=api-key-xxxx
  python scripts/probe_volc_asr.py <audio.wav|mp3> [--url https://...]
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import uuid
from pathlib import Path

import httpx

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

BASE = "https://openspeech.bytedance.com/api/v3/auc/bigmodel"
SUBMIT = f"{BASE}/submit"
QUERY = f"{BASE}/query"
FLASH = f"{BASE}/recognize/flash"


def headers(resource_id: str, request_id: str, *, submit: bool) -> dict:
    h = {
        "X-Api-Key": os.environ.get("VT_VOLC_API_KEY", "").strip(),
        "X-Api-Resource-Id": resource_id,
        "X-Api-Request-Id": request_id,
        "Content-Type": "application/json",
    }
    if submit:
        h["X-Api-Sequence"] = "-1"
    return h


def show(tag: str, r: httpx.Response) -> None:
    print(f"  {tag}: HTTP {r.status_code}")
    for k in ("X-Api-Status-Code", "X-Api-Message", "X-Tt-Logid"):
        v = r.headers.get(k)
        if v:
            print(f"    {k}: {v}")
    body = r.text.strip()
    if body:
        print(f"    body: {body[:600]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("audio", nargs="?", default="")
    ap.add_argument("--url", default="", help="公网可访问的音频地址（测 submit 用）")
    ap.add_argument("--resource", default="volc.bigasr.auc")
    args = ap.parse_args()

    if not os.environ.get("VT_VOLC_API_KEY"):
        print("缺 VT_VOLC_API_KEY")
        return 2

    print(f"resource_id = {args.resource}")

    # ---- A. flash：base64 直传 ----
    if args.audio:
        p = Path(args.audio)
        if not p.exists():
            print(f"音频不存在: {p}")
            return 2
        raw = p.read_bytes()
        fmt = p.suffix.lstrip(".").lower().replace("wave", "wav")
        payload = {
            "user": {"uid": "video-tool-probe"},
            "audio": {"format": fmt, "data": base64.b64encode(raw).decode()},
            "request": {
                "model_name": "bigmodel",
                "show_utterances": True,
                "enable_punc": True,
                "enable_itn": True,
            },
        }
        print(f"\n[A] flash 直传 base64（{len(raw)/1024:.0f} KB, {fmt}）")
        with httpx.Client(timeout=180) as c:
            r = c.post(FLASH, headers=headers(args.resource, str(uuid.uuid4()), submit=False),
                       json=payload)
            show("flash", r)
            if r.status_code == 200:
                try:
                    d = r.json()
                    res = (d.get("result") or {})
                    print(f"    text: {res.get('text', '')[:200]}")
                    for u in (res.get("utterances") or [])[:2]:
                        words = u.get("words") or []
                        print(f"    utt {u.get('start_time')}-{u.get('end_time')}ms "
                              f"{u.get('text')} words={len(words)}")
                        for w in words[:5]:
                            print(f"      {w['start_time']}-{w['end_time']} {w['text']}")
                except Exception as e:  # noqa: BLE001
                    print("    解析响应失败:", e)

    # ---- B. submit：公网 URL ----
    if args.url:
        rid = str(uuid.uuid4())
        payload = {
            "user": {"uid": "video-tool-probe"},
            "audio": {"format": "mp3", "url": args.url},
            "request": {"model_name": "bigmodel", "show_utterances": True,
                        "enable_punc": True},
        }
        print(f"\n[B] submit 公网 URL\n    {args.url}")
        with httpx.Client(timeout=60) as c:
            r = c.post(SUBMIT, headers=headers(args.resource, rid, submit=True), json=payload)
            show("submit", r)
            if r.headers.get("X-Api-Status-Code") == "20000000":
                import time
                for _ in range(30):
                    time.sleep(2)
                    q = c.post(QUERY, headers=headers(args.resource, rid, submit=False), json={})
                    code = q.headers.get("X-Api-Status-Code")
                    print(f"    query -> {code} {q.headers.get('X-Api-Message')}")
                    if code == "20000000":
                        d = q.json()
                        print("    text:", ((d.get("result") or {}).get("text") or "")[:200])
                        break
                    if code not in ("20000001", "20000002"):
                        show("query", q)
                        break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
