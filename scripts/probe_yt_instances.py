#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""最后一轮免费探测：全量扫 Invidious / Piped 实例，用「被封锁的视频」做判据。

判据：返回标题 + 可下载流 = 通。只测 kjQP7kiw5Fk（本机直连必失败的那条）。
"""
from __future__ import annotations

import asyncio
import re

import httpx

VID = "kJQP7kiw5Fk"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
T = 12


async def collect(c: httpx.AsyncClient) -> tuple[list[str], list[str]]:
    inv, piped = [], []
    try:
        r = await c.get("https://api.invidious.io/instances.json?sort_by=health", timeout=20)
        for item in r.json():
            host, meta = item[0], item[1]
            if meta.get("type") == "https":
                inv.append(f"https://{host}")
    except Exception as e:  # noqa: BLE001
        print("invidious api 列表失败", str(e)[:60])
    # 补：文档里的实例（API 列表被过滤过，这里补全）
    try:
        r = await c.get(
            "https://raw.githubusercontent.com/iv-org/documentation/master/docs/instances.md",
            timeout=20)
        for h in re.findall(r"https://([a-z0-9.-]+\.[a-z]{2,})", r.text):
            bad = ("github", "raw.", "invidious.io", "docs.", "redirect", "wiki")
            if not any(b in h for b in bad):
                inv.append("https://" + h)
        inv = list(dict.fromkeys(inv))
    except Exception as e:  # noqa: BLE001
        print("invidious 文档列表失败", str(e)[:60])
    try:
        r = await c.get(
            "https://raw.githubusercontent.com/TeamPiped/documentation/main/content/docs/public-instances/index.md",
            timeout=20)
        for h in re.findall(r"https://[a-z0-9.-]+\.[a-z]{2,}", r.text):
            if ("pipedapi" in h or "api." in h) and h not in piped:
                piped.append(h)
    except Exception as e:  # noqa: BLE001
        print("piped 列表失败", str(e)[:60])
    return inv[:40], piped[:40]


async def test_inv(c: httpx.AsyncClient, host: str, sem: asyncio.Semaphore):
    async with sem:
        try:
            r = await c.get(f"{host}/api/v1/videos/{VID}", headers={"User-Agent": UA}, timeout=T)
            if r.status_code != 200:
                return None
            d = r.json()
            title = d.get("title") or ""
            fm = [f for f in (d.get("formatStreams") or []) if f.get("url")]
            ad = [f for f in (d.get("adaptiveFormats") or []) if f.get("url")]
            if title and (fm or ad):
                return (host, "invidious", title[:40], [f.get("resolution") for f in fm])
        except Exception:  # noqa: BLE001
            return None
    return None


async def test_piped(c: httpx.AsyncClient, host: str, sem: asyncio.Semaphore):
    async with sem:
        try:
            r = await c.get(f"{host}/streams/{VID}", headers={"User-Agent": UA}, timeout=T)
            if r.status_code != 200:
                return None
            d = r.json()
            title = d.get("title") or ""
            vs = [s for s in (d.get("videoStreams") or []) if s.get("url")]
            if title and vs:
                return (host, "piped", title[:40], [s.get("quality") for s in vs])
        except Exception:  # noqa: BLE001
            return None
    return None


async def main():
    async with httpx.AsyncClient(follow_redirects=True, verify=False, timeout=T) as c:
        inv, piped = await collect(c)
        print(f"Invidious 候选 {len(inv)} | Piped 候选 {len(piped)}")
        sem = asyncio.Semaphore(12)
        tasks = [test_inv(c, h, sem) for h in inv] + [test_piped(c, h, sem) for h in piped]
        results = [r for r in await asyncio.gather(*tasks) if r]
        print(f"\n可用 {len(results)} 个：")
        for host, kind, title, q in results:
            print(f"  ✅ [{kind:9s}] {host:45s} {title}  {q}")


if __name__ == "__main__":
    asyncio.run(main())
