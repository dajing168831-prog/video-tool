#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
端到端验收（P1 判据）
=====================
按真实用户路径跑一遍：解析 → 视频代理(Range) → 音频提取 → 文件有效性。

用法:
  python e2e_check.py                       # 默认抖音样例
  python e2e_check.py --url "https://..."   # 指定链接
  python e2e_check.py --text "整段分享文案"
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import httpx

API = "http://127.0.0.1:8911"
FFMPEG = r"C:\Users\Administrator\Desktop\Jianying6.01\6.0.1.11779\ffmpeg.exe"
OUT = Path(__file__).resolve().parent.parent / "temp"

DEFAULT_TEXT = "https://www.douyin.com/video/6961737553342991651"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = ""):
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))


def probe(path: Path) -> dict:
    if not FFMPEG or not Path(FFMPEG).exists():
        return {}
    p = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path)],
                       capture_output=True, text=True, errors="ignore", timeout=60)
    info = {}
    for line in (p.stderr or "").splitlines():
        line = line.strip()
        if line.startswith("Duration:"):
            info["duration"] = line.split(",")[0].replace("Duration:", "").strip()
        if "Video:" in line:
            info["video"] = line.split("Video:")[1][:80].strip()
        if "Audio:" in line:
            info["audio"] = line.split("Audio:")[1][:80].strip()
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", default=DEFAULT_TEXT)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=180) as c:
        # R1 健康
        h = c.get(f"{API}/api/health").json()
        check("R1 服务健康 + ffmpeg 可用", h.get("data", {}).get("ffmpeg") is True,
              json.dumps(h.get("data"), ensure_ascii=False))

        # R2 解析
        r = c.post(f"{API}/api/parse", json={"text": args.text}).json()
        data = r.get("data") or {}
        ok_parse = r.get("code") == 200 and r.get("biz_code") == 0 and bool(data.get("token"))
        check("R2 解析成功", ok_parse, f"platform={data.get('platform')} title={(data.get('title') or '')[:30]}")
        if not ok_parse:
            return report()
        token = data["token"]

        # R3 文案字段
        check("R3 文案字段非空", bool(data.get("title")),
              f"title={bool(data.get('title'))} tags={len(data.get('tags') or [])} author={bool(data.get('author'))}")

        # R4 视频完整请求
        vr = c.get(f"{API}/api/file/{token}/video")
        check("R4 视频可下载", vr.status_code == 200 and len(vr.content) > 10_000,
              f"status={vr.status_code} size={len(vr.content)}")
        vpath = OUT / "e2e_video.mp4"
        vpath.write_bytes(vr.content)

        # R5 Range 支持（拖动进度条）
        rr = c.get(f"{API}/api/file/{token}/video", headers={"Range": "bytes=0-1023"})
        check("R5 视频支持 Range(206)", rr.status_code == 206, f"status={rr.status_code}")

        # R6 音频提取（静音视频属于合法情况，记为跳过而不是失败）
        ar = c.get(f"{API}/api/file/{token}/audio")
        silent = ar.status_code == 400 and "音轨" in ar.text
        check("R6 音频可提取" + ("（该视频无音轨，跳过）" if silent else ""),
              silent or (ar.status_code == 200 and len(ar.content) > 10_000),
              f"status={ar.status_code} size={len(ar.content)}")
        apath = OUT / "e2e_audio.m4a"
        if not silent:
            apath.write_bytes(ar.content)

        # R7 文件有效性
        vi = probe(vpath)
        check("R7 视频是有效媒体", bool(vi.get("video")), str(vi.get("duration", "")))
        if not silent:
            ai = probe(apath)
            check("R8 音频是有效媒体", bool(ai.get("audio")), str(ai.get("duration", "")))

    return report()


def report():
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\n=== 结果 {passed}/{total} ===")
    for name, ok, detail in results:
        if not ok:
            print(f"  ❌ {name}: {detail}")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
