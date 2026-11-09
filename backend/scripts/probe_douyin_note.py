"""抖音图文（note）解析冒烟探针。

背景（2026-11-05 修了两处）：
1. 图文分享链解析必报 `KeyError: 'videoInfoRes'` —— 不是图文不支持，是回退 HTML
   时换了新 client 没带 ttwid（拿到不含内容的精简 SSR），且分享链被硬拼成
   `share/video/{id}`（图文应落在 `share/note/{id}`）。
2. 图片出来是 webp 字节却顶着 `.jpg` 文件名 —— 候选 URL 里本来就有 `.jpeg`，
   但 `_get_no_webp_url` 用 `endswith(".webp")` 判断，带签名 query 时永远不成立。

两处补丁都在 `vendor/parse-video-py/src/parse_video_py/parser/douyin.py`。

用法：
    python scripts/probe_douyin_note.py https://v.douyin.com/xxxxxx/

绿 = images 非空 **且** 第一张图真的是 JPEG/PNG（不是 webp）
红 = 抛异常 / images 为空 / 图片是 webp
需要联网。抖音分享短链会过期，红了先确认链接本身还能打开。
"""
import argparse
import asyncio
import sys

import httpx

UA = (
    "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
)


def _magic(b: bytes) -> str:
    if b.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if b.startswith(b"\x89PNG"):
        return "PNG"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "WEBP"
    return "?"


async def run(url: str) -> int:
    from parse_video_py.parser.douyin import DouYin

    try:
        info = await DouYin().parse_share_url(url)
    except Exception as e:  # noqa: BLE001
        print(f"RED  {type(e).__name__}: {e}")
        return 1

    n = len(info.images or [])
    print(f"title={info.title[:50]!r}")
    print(f"author={info.author.name!r} video_url={info.video_url[:50]!r}")
    print(f"images={n}")
    if n == 0:
        print("RED  images 为空")
        return 1

    img = info.images[0]
    ext = img.url.split("?")[0].rsplit(".", 1)[-1]
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=40) as c:
            r = await c.get(img.url, headers={"User-Agent": UA})
        kind = _magic(r.content)
    except Exception as e:  # noqa: BLE001
        print(f"RED  图片下载失败 {type(e).__name__}: {e}")
        return 1
    print(f"image[0] ext={ext} ctype={r.headers.get('content-type')} "
          f"bytes={len(r.content)} magic={kind}")
    if kind == "WEBP":
        print("RED  图片是 webp（下载下来打不开）")
        return 1

    print(f"GREEN images={n} 首图={kind}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url", help="抖音图文分享链接")
    args = ap.parse_args()
    return asyncio.run(run(args.url))


if __name__ == "__main__":
    sys.exit(main())
