#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用公开免费代理池实测能否解 YouTube（判据：InnerTube 返回 OK + streamingData）。

只请求公开视频的元数据，不发送任何凭据。
"""
from __future__ import annotations

import asyncio
import random

import httpx

VID = "kJQP7kiw5Fk"
KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
BODY = {
    "context": {"client": {"clientName": "ANDROID_VR", "clientVersion": "1.60.19",
                           "androidSdkVersion": 32, "hl": "en", "gl": "US"}},
    "videoId": VID, "contentCheckOk": True, "racyCheckOk": True,
}
HEADERS = {
    "User-Agent": UA,
    "Content-Type": "application/json",
    "X-YouTube-Client-Name": "28",
    "X-YouTube-Client-Version": "1.60.19",
}
SOURCES = [
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/http/data.txt",
]


async def fetch_list(c: httpx.AsyncClient) -> list[str]:
    out: list[str] = []
    for u in SOURCES:
        try:
            r = await c.get(u, timeout=30)
            for line in r.text.splitlines():
                line = line.strip()
                if line and ":" in line and not line.startswith("#"):
                    out.append(line)
        except Exception as e:  # noqa: BLE001
            print(f"  列表 {u[-40:]} 失败 {str(e)[:40]}")
    return list(dict.fromkeys(out))


async def test(hostport: str, sem: asyncio.Semaphore) -> str | None:
    async with sem:
        try:
            async with httpx.AsyncClient(proxy=f"http://{hostport}", timeout=8,
                                         follow_redirects=True) as c:
                r = await c.post(f"https://www.youtube.com/youtubei/v1/player?key={KEY}",
                                 headers=HEADERS, json=BODY)
                if r.status_code != 200:
                    return None
                d = r.json()
                ps = d.get("playabilityStatus", {})
                sd = d.get("streamingData") or {}
                if ps.get("status") == "OK" and (sd.get("formats") or sd.get("adaptiveFormats")):
                    return hostport
        except Exception:  # noqa: BLE001
            return None
    return None


async def main():
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as c:
        pool = await fetch_list(c)
    print(f"代理池 {len(pool)} 条，随机抽 400 条实测")
    random.shuffle(pool)
    sample = pool[:400]
    sem = asyncio.Semaphore(60)
    found = []
    done = 0
    for coro in asyncio.as_completed([test(h, sem) for h in sample]):
        r = await coro
        done += 1
        if done % 50 == 0:
            print(f"  已测 {done}/{len(sample)}，命中 {len(found)}")
        if r:
            found.append(r)
            print(f"  ✅ 命中 {r}")
    print(f"\n结果：{len(found)}/{len(sample)} 可用")
    for f in found:
        print("  ", f)


if __name__ == "__main__":
    asyncio.run(main())
