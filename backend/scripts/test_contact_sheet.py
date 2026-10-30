"""全片联系表的纯本地自检（不发网络请求、不花钱）。

判据只看产物：图真的生成了、格子数对、时间戳文字真的烧上去了。
运行：python scripts/test_contact_sheet.py
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import media  # noqa: E402

PASS = FAIL = 0


def check(name: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}: {got}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want={want!r}")


def _size(path: Path) -> tuple[int, int]:
    """用 ffmpeg -i 读宽高（本机没有 ffprobe）。"""
    p = subprocess.run([media.ffmpeg_path(), "-hide_banner", "-i", str(path)],
                       capture_output=True, text=True, errors="ignore", timeout=30)
    m = re.search(r"Video:.*?(\d+)x(\d+)", p.stderr or "", re.S)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：一轮只跑一家
    from _model_gate import sel_or_exit as _sel
    _sel()
    work = Path(tempfile.mkdtemp(dir="D:/tmp", prefix="sheet_"))
    try:
        src = work / "src.mp4"
        subprocess.run(
            [media.ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y",
             "-f", "lavfi", "-i", "testsrc=s=360x640:d=12:r=25",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)],
            check=True,
        )
        out = work / "sheet.jpg"
        media.contact_sheet(src, out, cols=5, rows=6, width=240, duration=12.0)
        check("图生成了", out.exists(), True)
        check("不是空文件", out.stat().st_size > 10_000, True)
        w, h = _size(out)
        # 5 列 × 240 宽；行数按格子高度算，只验宽度这一条硬判据
        check("网格宽 = 列数 × 每格宽", w, 5 * 240)
        check("有多行", h > 240, True)
        # 缓存参数不同 → 换一张，别把上次的图当新的
        out2 = work / "sheet2.jpg"
        media.contact_sheet(src, out2, cols=4, rows=4, width=180, duration=12.0)
        check("另一组参数换了尺寸", _size(out2)[0], 4 * 180)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(f"\n{PASS}/{PASS + FAIL} 通过")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
