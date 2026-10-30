#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""YouTube 免费解析源探测（不猜，全实测）。

测四类候选：
  A. yt-dlp 换 player_client（看 bot 校验能不能绕）
  B. Piped 公共实例（开源 YouTube 前端，自带 API）
  C. Invidious 公共实例（同上）
  D. Cobalt 公共实例（开源下载器）
  E. 第三方聚合 API

用法: python probe_youtube.py [video_url]
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys

import httpx

URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
VID = URL.split("v=")[-1].split("&")[0] if "v=" in URL else URL.rsplit("/", 1)[-1]
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)
TIMEOUT = 15
YTDLP = r"D:/venvs/video-tool/Scripts/yt-dlp.exe"


# ---------------------------------------------------------------- A. yt-dlp
def test_ytdlp():
    print("\n===== A. yt-dlp 换客户端 =====")
    clients = ["tv", "web_safari", "ios", "android_vr", "web_embedded", "mweb"]
    for cli in clients:
        cmd = [
            YTDLP, "--no-warnings", "--skip-download", "--print",
            "%(title)s | %(duration)s | %(ext)s",
            "--extractor-args", f"youtube:player_client={cli}",
            URL,
        ]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True,
                               errors="ignore", timeout=60)
            out = (p.stdout or "").strip().splitlines()
            if p.returncode == 0 and out:
                print(f"  ✅ {cli:14s} {out[-1][:90]}")
            else:
                err = (p.stderr or "").strip().splitlines()
                print(f"  ❌ {cli:14s} {(err[-1] if err else 'fail')[:100]}")
        except subprocess.TimeoutExpired:
            print(f"  ⏱ {cli:14s} 超时")


# ---------------------------------------------------------------- 实例列表
async def get_json(c: httpx.AsyncClient, url: str):
    r = await c.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


async def test_piped(c):
    print("\n===== B. Piped 实例 =====")
    hosts: list[str] = []
    try:
        data = await get_json(c, "https://piped-instances.kavin.rocks/")
        for item in data:
            api = item.get("api_url") or ""
            if api.startswith("http"):
                hosts.append(api.rstrip("/"))
    except Exception as e:  # noqa: BLE001
        print(f"  实例列表取不到: {str(e)[:80]}")
        hosts = ["https://pipedapi.kavin.rocks", "https://pipedapi.adminforge.de",
                 "https://api.piped.private.coffee", "https://pipedapi.reallyaweso.me"]
    print(f"  候选 {len(hosts)} 个")
    for h in hosts[:12]:
        try:
            d = await get_json(c, f"{h}/streams/{VID}")
            title = d.get("title") or ""
            vs = [s for s in (d.get("videoStreams") or []) if s.get("url")]
            aud = [s for s in (d.get("audioStreams") or []) if s.get("url")]
            print(f"  ✅ {h:45s} {title[:40]} 视频{len(vs)} 音频{len(aud)}")
        except Exception as e:  # noqa: BLE001
            print(f"  ❌ {h:45s} {str(e)[:60]}")


async def test_invidious(c):
    print("\n===== C. Invidious 实例 =====")
    hosts: list[str] = []
    try:
        data = await get_json(c, "https://api.invidious.io/instances.json?sort_by=health")
        for item in data:
            host, meta = item[0], item[1]
            if meta.get("api") and meta.get("type") == "https":
                hosts.append(f"https://{host}")
    except Exception as e:  # noqa: BLE001
        print(f"  实例列表取不到: {str(e)[:80]}")
    print(f"  候选 {len(hosts)} 个")
    for h in hosts[:12]:
        try:
            d = await get_json(c, f"{h}/api/v1/videos/{VID}")
            title = d.get("title") or ""
            fmt = d.get("formatStreams") or []
            adaptive = d.get("adaptiveFormats") or []
            print(f"  ✅ {h:45s} {title[:36]} fmt{len(fmt)} adaptive{len(adaptive)}")
        except Exception as e:  # noqa: BLE001
            print(f"  ❌ {h:45s} {str(e)[:60]}")


async def test_cobalt(c):
    print("\n===== D. Cobalt 实例 =====")
    hosts: list[str] = []
    try:
        data = await get_json(c, "https://instances.cobalt.best/api/instances.json")
        for item in data:
            if item.get("api_online") and not item.get("turnstile"):
                hosts.append((item.get("url") or "").rstrip("/"))
    except Exception as e:  # noqa: BLE001
        print(f"  实例列表取不到: {str(e)[:80]}")
        hosts = ["https://cobalt-api.kwiatekmiki.com", "https://api.cobalt.tools"]
    print(f"  候选 {len(hosts)} 个")
    for h in hosts[:12]:
        try:
            r = await c.post(
                h + "/",
                json={"url": URL, "videoQuality": "720", "downloadMode": "auto"},
                headers={"Accept": "application/json", "Content-Type": "application/json",
                         "User-Agent": UA},
                timeout=TIMEOUT,
            )
            body = r.json() if "json" in r.headers.get("content-type", "") else {}
            status = body.get("status")
            if status in ("tunnel", "redirect", "stream") and body.get("url"):
                print(f"  ✅ {h:40s} status={status} url={body['url'][:60]}")
            else:
                print(f"  ❌ {h:40s} {r.status_code} {json.dumps(body, ensure_ascii=False)[:100]}")
        except Exception as e:  # noqa: BLE001
            print(f"  ❌ {h:40s} {str(e)[:60]}")


async def test_aggregator(c):
    print("\n===== E. 第三方聚合 =====")
    try:
        r = await c.post("https://video.zacao.top/api/parse", json={"url": URL},
                         headers={"User-Agent": UA}, timeout=TIMEOUT)
        print(f"  zacao: {r.status_code} {r.text[:200]}")
    except Exception as e:  # noqa: BLE001
        print(f"  zacao: ❌ {str(e)[:80]}")


async def main():
    async with httpx.AsyncClient(follow_redirects=True) as c:
        await test_piped(c)
        await test_invidious(c)
        await test_cobalt(c)
        await test_aggregator(c)
    test_ytdlp()


if __name__ == "__main__":
    print(f"目标视频: {URL}  (id={VID})")
    asyncio.run(main())
