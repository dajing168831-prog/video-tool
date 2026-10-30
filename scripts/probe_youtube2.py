#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""YouTube 二轮探测：批量测实例 + 比较画质。"""
from __future__ import annotations

import asyncio
import json
import re

import httpx

VID = "dQw4w9WgXcQ"
URL = f"https://www.youtube.com/watch?v={VID}"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
T = 12

PIPED_FALLBACK = [
    "https://api.piped.private.coffee",
    "https://pipedapi.drgns.space",
    "https://pipedapi.leptons.xyz",
    "https://pipedapi.ducks.party",
    "https://pipedapi.nosebs.ru",
    "https://pipedapi.orangenet.cc",
    "https://pipedapi.nexrlabs.com",
    "https://pipedapi.adminforge.de",
    "https://pipedapi.kavin.rocks",
]

INVIDIOUS_FALLBACK = [
    "https://yewtu.be", "https://inv.nadeko.net", "https://invidious.nerdvpn.de",
    "https://iv.melmac.space", "https://invidious.privacyredirect.com",
    "https://invidious.f5.si", "https://inv.tux.pizza",
]

COBALT_FALLBACK = [
    "https://cobalt-api.kwiatekmiki.com",
    "https://cobalt.255x.ru",
    "https://api.dl.ixhby.dev",
    "https://cobalt-api.ayo.tf",
    "https://capi.oak.li",
]


async def list_piped(c):
    try:
        r = await c.get(
            "https://raw.githubusercontent.com/TeamPiped/documentation/main/content/docs/public-instances/index.md",
            timeout=T)
        hosts = re.findall(r"https://[a-z0-9.-]+\.[a-z]{2,}", r.text)
        hosts = [h for h in dict.fromkeys(hosts) if "pipedapi" in h or "api." in h]
        return hosts[:20] or PIPED_FALLBACK
    except Exception:  # noqa: BLE001
        return PIPED_FALLBACK


async def test_piped(c, hosts):
    print("\n===== Piped =====")
    ok = []
    for h in hosts:
        h = h.rstrip("/")
        try:
            r = await c.get(f"{h}/streams/{VID}", headers={"User-Agent": UA}, timeout=T)
            if r.status_code != 200:
                print(f"  ❌ {h:42s} {r.status_code}")
                continue
            d = r.json()
            vs = [s for s in (d.get("videoStreams") or []) if s.get("url")]
            qs = [s.get("quality") for s in vs]
            aud = len(d.get("audioStreams") or [])
            print(f"  ✅ {h:42s} 音频{aud} 画质={qs}")
            ok.append((h, d))
        except Exception as e:  # noqa: BLE001
            print(f"  ❌ {h:42s} {str(e)[:50]}")
    return ok


async def test_invidious(c, hosts):
    print("\n===== Invidious =====")
    ok = []
    for h in hosts:
        h = h.rstrip("/")
        try:
            r = await c.get(f"{h}/api/v1/videos/{VID}", headers={"User-Agent": UA}, timeout=T)
            if r.status_code != 200:
                print(f"  ❌ {h:42s} {r.status_code}")
                continue
            d = r.json()
            fm = d.get("formatStreams") or []
            ad = d.get("adaptiveFormats") or []
            print(f"  ✅ {h:42s} fmt={[f.get('resolution') for f in fm]} "
                  f"adaptive={[f.get('resolution') for f in ad][:8]}")
            ok.append((h, d))
        except Exception as e:  # noqa: BLE001
            print(f"  ❌ {h:42s} {str(e)[:50]}")
    return ok


async def test_cobalt(c, hosts):
    print("\n===== Cobalt =====")
    ok = []
    for h in hosts:
        h = h.rstrip("/")
        try:
            r = await c.post(
                h + "/", json={"url": URL, "videoQuality": "1080", "downloadMode": "auto"},
                headers={"Accept": "application/json", "Content-Type": "application/json",
                         "User-Agent": UA}, timeout=T)
            ct = r.headers.get("content-type", "")
            body = r.json() if "json" in ct else {}
            if body.get("status") in ("tunnel", "redirect") and body.get("url"):
                print(f"  ✅ {h:42s} {body.get('status')} filename={body.get('filename','')[:40]}")
                ok.append((h, body))
            else:
                print(f"  ❌ {h:42s} {r.status_code} {json.dumps(body, ensure_ascii=False)[:90]}")
        except Exception as e:  # noqa: BLE001
            print(f"  ❌ {h:42s} {str(e)[:50]}")
    return ok


async def main():
    async with httpx.AsyncClient(follow_redirects=True, verify=False) as c:
        hosts = await list_piped(c)
        print(f"Piped 候选 {len(hosts)}: {hosts[:8]}")
        p = await test_piped(c, hosts)
        await test_invidious(c, INVIDIOUS_FALLBACK)
        await test_cobalt(c, COBALT_FALLBACK)

        # 最好的 Piped 源做真实下载验证
        if p:
            h, d = p[0]
            vs = [s for s in d["videoStreams"] if s.get("format") == "MPEG_4"]
            if vs:
                u = vs[0]["url"]
                print(f"\n下载验证: {h} {u[:70]}")
                try:
                    r = await c.get(u, headers={"User-Agent": UA},
                                   timeout=60, follow_redirects=True)
                    print(f"  status={r.status_code} size={len(r.content)} "
                          f"ct={r.headers.get('content-type')}")
                except Exception as e:  # noqa: BLE001
                    print(f"  ❌ {str(e)[:100]}")


if __name__ == "__main__":
    asyncio.run(main())
