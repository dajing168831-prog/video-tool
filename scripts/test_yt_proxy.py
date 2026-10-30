#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""换出口前先测：这条代理到底能不能解 YouTube。

用法:
  python test_yt_proxy.py --proxy "socks5://user:pass@1.2.3.4:1080"
  python test_yt_proxy.py --proxy "http://user:pass@1.2.3.4:8080" --url "https://youtu.be/xxx"

判据（三条全过才算能用）:
  P1 代理出口 IP 不是机房段（能查到 IP）
  P2 被本机直连封锁的视频能解析出标题
  P3 用同一个出口真下 2MB 片段（证明流地址没被 IP 绑定打回）
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

YTDLP = [sys.executable, "-m", "yt_dlp", "--no-warnings", "--no-playlist"]
# 本机直连必失败、用来做判据的视频
BLOCKED = "https://www.youtube.com/watch?v=kJQP7kiw5Fk"


def run(cmd: list[str], timeout: int = 180) -> tuple[int, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, errors="ignore",
                       timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


async def check_egress(proxy: str) -> str:
    async with httpx.AsyncClient(proxy=proxy, timeout=30) as c:
        r = await c.get("https://ipinfo.io/json")
        d = r.json()
    return f"{d.get('ip')} | {d.get('city')}, {d.get('country')} | {d.get('org')}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--proxy", required=True, help="http:// 或 socks5:// 代理地址")
    ap.add_argument("--url", default=BLOCKED)
    args = ap.parse_args()
    proxy = args.proxy

    results: list[tuple[str, bool, str]] = []

    def check(name, ok, detail=""):
        results.append((name, ok, detail))
        print(f"[{'PASS' if ok else 'FAIL'}] {name}  {detail}")

    # P1 出口
    try:
        egress = asyncio.run(check_egress(proxy))
        check("P1 代理可用", True, egress)
    except Exception as e:  # noqa: BLE001
        check("P1 代理可用", False, str(e)[:120])
        return report(results)

    # P2 解析
    t0 = time.time()
    code, out = run(YTDLP + ["--proxy", proxy, "-J", "--skip-download", args.url])
    elapsed = time.time() - t0
    info = {}
    if code == 0 and out.strip():
        try:
            info = json.loads(out)
        except Exception:  # noqa: BLE001
            pass
    ok2 = bool(info.get("title"))
    check("P2 能解析被封锁视频", ok2,
          f"{info.get('title', '')[:40]} 耗时 {elapsed:.1f}s" if ok2 else out.strip()[-160:])
    if not ok2:
        return report(results)

    # P3 真下 2MB
    with tempfile.TemporaryDirectory() as td:
        dest = Path(td) / "probe.mp4"
        t0 = time.time()
        code, out = run(YTDLP + [
            "--proxy", proxy,
            "-f", "bv*[height<=720]+ba/b[height<=720]/b",
            "--download-sections", "*0-10",
            "--force-keyframes-at-cuts",
            "--merge-output-format", "mp4",
            "-o", str(dest), args.url,
        ], timeout=300)
        elapsed = time.time() - t0
        size = dest.stat().st_size if dest.exists() else 0
        check("P3 能真下载片段", code == 0 and size > 100_000,
              f"{size / 1024 / 1024:.1f}MB 耗时 {elapsed:.1f}s"
              if code == 0 else out.strip()[-160:])

    return report(results)


def report(results):
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n=== 结果 {passed}/{len(results)} ===")
    if passed == len(results):
        print("✅ 这条出口可用：设置 VT_YOUTUBE_PROXY=<proxy> 即可启用 YouTube")
    else:
        print("❌ 这条出口不可用，换一条再测（不要先买）")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
