"""取一条样本视频到本地，供复刻链路调试。

用法（在 backend/ 下）：
    python scripts/fetch_sample.py "<视频链接>" <输出目录>

只做"解析 + 下载"两件事，复用现有 parsers，不产生新逻辑。
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.routes import PARSERS  # noqa: E402  （解析器注册表在 routes 里）
from app.parsers.base import detect_platform  # noqa: E402
from app.services import media  # noqa: E402


async def main(url: str, outdir: Path) -> None:
    platform = detect_platform(url)
    print("platform:", platform)
    parser = PARSERS.get(platform)
    if parser is None:
        raise SystemExit(f"不支持的平台: {platform}")

    info = await parser.parse(url)
    print("title :", getattr(info, "title", "")[:60])
    print("is_video:", info.is_video)

    outdir.mkdir(parents=True, exist_ok=True)
    dest = outdir / "source.mp4"
    await media.download(info.video_url, dest)
    print("saved :", dest, dest.stat().st_size, "bytes")
    print("probe :", media.probe_duration(dest))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    asyncio.run(main(sys.argv[1], Path(sys.argv[2])))
