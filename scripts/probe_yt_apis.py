#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探测第三方「公开解析接口」——这些站点浏览器里能用，说明它们的出口能过 YouTube。"""
from __future__ import annotations

import asyncio
import json
import re

import httpx

VID = "kJQP7kiw5Fk"
URL = f"https://www.youtube.com/watch?v={VID}"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
H = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}
T = 25


def has_media(text: str) -> bool:
    return bool(re.search(r"https?://[^\s\"']*(googlevideo|\.mp4|\.m4a|\.webm)", text))


async def probe(c: httpx.AsyncClient, name: str, fn):
    try:
        r = await fn()
        body = r.text or ""
        ok = r.status_code == 200 and has_media(body)
        print(f"  {'✅' if ok else '❌'} {name:22s} {r.status_code} "
              f"media={has_media(body)} len={len(body)} {body[:110]!r}")
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ {name:22s} {type(e).__name__}: {str(e)[:80]}")


async def main():
    async with httpx.AsyncClient(follow_redirects=True, timeout=T, headers=H) as c:
        print("== 第三方公开接口 ==")
        await probe(c, "vevioz", lambda: c.get(f"https://api.vevioz.com/api/button/videos/{VID}"))
        await probe(c, "yout.com", lambda: c.get(f"https://yout.com/api/v1/videos/{VID}"))
        await probe(c, "yt5s", lambda: c.post("https://yt5s.io/api/ajaxSearch",
                                              data={"q": URL, "vt": "mp4"}))
        await probe(c, "y2mate", lambda: c.post("https://www.y2mate.com/mates/analyzeV2/ajax",
                                                data={"k_query": URL, "k_page": "home",
                                                      "hl": "en", "q_auto": "0"}))
        await probe(c, "ssyoutube", lambda: c.post("https://ssyoutube.com/api/convert",
                                                   data={"url": URL}))
        await probe(c, "cobalt-old", lambda: c.post("https://co.wuk.sh/api/json",
                                                    json={"url": URL}))
        await probe(c, "savefrom", lambda: c.get(f"https://en.savefrom.net/api/home?url={URL}"))
        await probe(c, "9convert", lambda: c.get(
            f"https://9convert.com/api/ajaxSearch/index?query={URL}&vt=mp4"))


if __name__ == "__main__":
    asyncio.run(main())
