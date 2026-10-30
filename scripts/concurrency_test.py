#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""并发实测：模拟 N 个用户同时解析+下载，看后端是否真的并行、瓶颈在哪。

用法: python concurrency_test.py [并发数] [平台样例]
"""
from __future__ import annotations

import asyncio
import sys
import time

import httpx

API = "http://127.0.0.1:8911"
SAMPLES = {
    "twitter": "https://x.com/TopHeroes_/status/2001950365332455490",
    "instagram": "https://www.instagram.com/reel/Chunk8-jurw/",
}


async def one(c: httpx.AsyncClient, text: str, idx: int) -> dict:
    t0 = time.monotonic()
    r = await c.post(f"{API}/api/parse", json={"text": text})
    d = r.json()
    t_parse = time.monotonic() - t0
    if d.get("biz_code") != 0:
        return {"idx": idx, "ok": False, "err": d.get("msg"), "parse": t_parse}

    token = d["data"]["token"]
    t1 = time.monotonic()
    v = await c.get(f"{API}/api/file/{token}/video")
    t_dl = time.monotonic() - t1
    return {"idx": idx, "ok": v.status_code == 200, "size": len(v.content),
            "parse": t_parse, "download": t_dl, "total": time.monotonic() - t0}


async def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    key = sys.argv[2] if len(sys.argv) > 2 else "twitter"
    url = SAMPLES[key]

    async with httpx.AsyncClient(timeout=600) as c:
        print(f"串行基线：1 个任务")
        base = await one(c, url, 0)
        print(f"  解析 {base['parse']:.1f}s 下载 {base['download']:.1f}s "
              f"合计 {base['total']:.1f}s size={base.get('size', 0)}")

        print(f"\n并发 {n} 个任务：")
        t0 = time.monotonic()
        results = await asyncio.gather(*[one(c, url, i) for i in range(n)])
        wall = time.monotonic() - t0
        for r in results:
            if r["ok"]:
                print(f"  #{r['idx']} 解析 {r['parse']:.1f}s 下载 {r['download']:.1f}s "
                      f"合计 {r['total']:.1f}s size={r['size']}")
            else:
                print(f"  #{r['idx']} 失败: {r.get('err')}")
        okn = sum(1 for r in results if r["ok"])
        print(f"\n总耗时 {wall:.1f}s | 成功 {okn}/{n} | 单任务平均吞吐 "
              f"{okn / wall:.2f} 个/秒 | 等效加速比 {_speedup(base['total'], wall, n):.2f}x")


def _speedup(one_time: float, wall: float, n: int) -> float:
    return (one_time * n) / wall if wall > 0 else 0


if __name__ == "__main__":
    asyncio.run(main())
