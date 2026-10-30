#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P0 解析能力矩阵探测
====================
对给定 URL 列表逐个探测：
  1. 平台识别
  2. yt-dlp 元信息提取（标题/时长/作者）
  3. 可用流检查（是否有视频流 / 音频流）
  4. 文案字段可得性
输出：probe-result.json + 控制台表格

用法:
  python probe_parsers.py urls.txt
  python probe_parsers.py --url "https://..."
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    import yt_dlp
except ImportError:
    sys.exit("缺少 yt-dlp：pip install yt-dlp")

OUT = Path(__file__).resolve().parent.parent / "docs" / "probe-result.json"

PLATFORM_PATTERNS = [
    ("douyin", r"douyin\.com|iesdouyin\.com"),
    ("kuaishou", r"kuaishou\.com|chenzhongtech\.com"),
    ("xiaohongshu", r"xiaohongshu\.com|xhslink\.com"),
    ("bilibili", r"bilibili\.com|b23\.tv"),
    ("tiktok", r"tiktok\.com"),
    ("youtube", r"youtube\.com|youtu\.be"),
    ("instagram", r"instagram\.com"),
    ("twitter", r"twitter\.com|x\.com"),
]


def detect_platform(url: str) -> str:
    for name, pat in PLATFORM_PATTERNS:
        if re.search(pat, url, re.I):
            return name
    return "unknown"


def probe_one(url: str) -> dict:
    platform = detect_platform(url)
    result = {
        "url": url,
        "platform": platform,
        "ok": False,
        "title": "",
        "duration": None,
        "uploader": "",
        "has_video": False,
        "has_audio": False,
        "desc_len": 0,
        "tags": [],
        "error": "",
        "elapsed": 0.0,
    }
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": 20,
        "extract_flat": False,
    }
    t0 = time.time()
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info.get("_type") == "playlist":
                entries = info.get("entries") or []
                info = entries[0] if entries else {}
            result.update(
                ok=True,
                title=info.get("title") or "",
                duration=info.get("duration"),
                uploader=info.get("uploader") or info.get("channel") or "",
                desc_len=len(info.get("description") or ""),
                tags=info.get("tags") or [],
            )
            formats = info.get("formats") or []
            result["has_video"] = any(
                f.get("vcodec") not in (None, "none") for f in formats
            )
            result["has_audio"] = any(
                f.get("acodec") not in (None, "none") for f in formats
            )
    except Exception as e:
        result["error"] = str(e).splitlines()[0][:300]
    result["elapsed"] = round(time.time() - t0, 2)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?", help="每行一个 URL 的文本文件")
    ap.add_argument("--url", action="append", default=[], help="直接指定 URL，可多次")
    args = ap.parse_args()

    urls = list(args.url)
    if args.file:
        for line in Path(args.file).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    if not urls:
        sys.exit("没有 URL：传一个文件或 --url")

    results = []
    for u in urls:
        r = probe_one(u)
        results.append(r)
        status = "OK " if r["ok"] else "FAIL"
        print(
            f"[{status}] {r['platform']:12s} "
            f"V={int(r['has_video'])} A={int(r['has_audio'])} "
            f"desc={r['desc_len']:4d} {r['elapsed']:5.1f}s  {u[:70]}"
        )
        if r["error"]:
            print(f"        └ {r['error']}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n结果已写入 {OUT}")

    # 汇总
    print("\n=== 按平台汇总 ===")
    by = {}
    for r in results:
        d = by.setdefault(r["platform"], {"n": 0, "ok": 0})
        d["n"] += 1
        d["ok"] += int(r["ok"])
    for p, d in sorted(by.items()):
        print(f"{p:14s} {d['ok']}/{d['n']}")


if __name__ == "__main__":
    main()
