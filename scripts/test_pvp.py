import asyncio, sys
from parse_video_py import parse_video_share_url

URLS = [
    "https://www.douyin.com/video/6961737553342991651",
    "https://www.bilibili.com/video/BV1SknF6KE5g",
    "https://www.xiaohongshu.com/explore/6411cf99000000001300b6d9",
]

async def main():
    for u in URLS:
        print("="*60)
        print("URL:", u)
        try:
            r = await asyncio.wait_for(parse_video_share_url(u), timeout=30)
            if r is None:
                print("  结果: None")
                continue
            print("  author :", getattr(r, "author", None))
            print("  title  :", (getattr(r, "title", "") or "")[:80])
            print("  video  :", (getattr(r, "video_url", "") or "")[:100])
            print("  images :", len(getattr(r, "images", None) or []))
        except Exception as e:
            print("  FAIL:", type(e).__name__, str(e)[:200])

asyncio.run(main())
