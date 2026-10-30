#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小红书解析器单独验证（不走服务，直接调 provider）。

用法:
  python test_xhs.py                        # 用默认裸链接（预期失败，看报错是否准确）
  python test_xhs.py "https://..."          # 用真实分享链接
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, r"C:/tmp/video-tool/backend")

from app.parsers.xhs_provider import XiaohongshuParser  # noqa: E402

DEFAULT = "https://www.xiaohongshu.com/explore/6411cf99000000001300b6d9"


async def main(url: str):
    p = XiaohongshuParser()
    print(f"URL: {url}")
    info = await p.parse(url)
    print("-" * 60)
    print(f"平台   : {info.platform}")
    print(f"标题   : {info.title}")
    print(f"正文   : {(info.desc or '')[:120]}")
    print(f"话题   : {info.tags}")
    print(f"作者   : {info.author}")
    print(f"封面   : {(info.cover or '')[:100]}")
    print(f"视频流 : {(info.video_url or '')[:120]}")
    print(f"图集   : {len(info.images)} 张 {info.images[:2]}")
    print(f"是视频 : {info.is_video}")


if __name__ == "__main__":
    u = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    try:
        asyncio.run(main(u))
    except Exception as e:  # noqa: BLE001
        print(f"\n[失败] {type(e).__name__}: {e}")
        sys.exit(1)
