# -*- coding: utf-8 -*-
"""JPG 色度采样格式转正的验收（**零费用，本机 ffmpeg 现造样本**）。

修的是什么（`OPEN-DEFECTS.md` D64-b `:677`）：
某些 JPEG 的色度采样（Y 2x2、Cb 1x1、Cr 2x1）超出解码范围，模型侧报
`invalid image: heic: decode failed`。**ffprobe 却读得出宽高** —— 于是我们放行，
用户等到出片才炸（钱和时间都白花）。修法是上传前判、转、重新探测。

被测：`media.JPEG_SAFE_PIX_FMTS` / `jpeg_needs_normalize()` / `normalize_jpeg()`
      / `scene.probe()` 的 `pix_fmt` 字段。

🩸 坏样本是**运行时现造**的：ffmpeg 造标准图 → 改 SOF0 里 Cr 的采样因子为 `0x21`
→ ffprobe 读出 `yuvj440p`。`--pix_fmt yuvj411p` 造不出来（mjpeg 编码器会自动升成 4:2:2）。

运行：python scripts/p17_check.py --model h3
"""
from __future__ import annotations

import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import _model_lock  # noqa: E402

RESULT: list[tuple[bool, str, str]] = []


def ok(name: str, detail: str = "") -> None:
    RESULT.append((True, name, detail))


def bad(name: str, detail: str) -> None:
    RESULT.append((False, name, detail))


def expect(cond: bool, name: str, detail: str = "") -> bool:
    (ok if cond else bad)(name, "" if cond else detail)
    return cond


def _make_jpg(dest: Path, w: int = 320, h: int = 240) -> bool:
    """造一张标准 JPEG（yuvj420p）。"""
    from app.services.media import ffmpeg_path
    exe = ffmpeg_path()
    if not exe:
        return False
    p = subprocess.run(
        [exe, "-y", "-v", "error", "-f", "lavfi",
         "-i", f"testsrc=size={w}x{h}:duration=1:rate=1",
         "-frames:v", "1", "-pix_fmt", "yuvj420p", "-q:v", "2", str(dest)],
        capture_output=True, text=True, errors="ignore", timeout=60)
    return p.returncode == 0 and dest.exists()


def _break_cr_sampling(path: Path) -> bool:
    """把 SOF0 里 Cr 分量的 H/V 采样改成 0x21（Y 是 2x2 → 组合成 yuvj440p）。"""
    b = bytearray(path.read_bytes())
    i = b.find(b"\xff\xc0")
    while i != -1:
        seg_len = struct.unpack(">H", bytes(b[i + 2:i + 4]))[0]
        ncomp = b[i + 9]
        if ncomp == 3 and seg_len >= 8 + 3 * ncomp:
            base = i + 10                      # 第一个分量的起点
            # 每分量 3 字节：id / H-V 采样 / 量化表 id
            third = base + 3 * 2
            b[third + 1] = 0x21
            path.write_bytes(bytes(b))
            return True
        i = b.find(b"\xff\xc0", i + 1)
    return False


def main() -> int:
    if "--model" not in sys.argv:
        print("⛔ 必须点名型号：--model h3")
        return 2
    i = sys.argv.index("--model")
    if (sys.argv[i + 1] if i + 1 < len(sys.argv) else "") != "h3":
        print("⛔ 只跑 h3 轮：--model h3")
        return 2
    _model_lock.guard("h3")

    from app.services import media, scene

    # 1–4 判据本身（纯字符串，零样本）
    expect(media.jpeg_needs_normalize("yuvj420p") is False,
           "1  标准 yuvj420p 不转（不误伤）")
    expect(media.jpeg_needs_normalize("yuvj422p") is False,
           "2  标准 yuvj422p 不转（不误伤）")
    expect(media.jpeg_needs_normalize("yuvj440p") is True,
           "3  yuvj440p 判为需要转正")
    expect(media.jpeg_needs_normalize("") is False,
           "4  没探测到格式时不判（空串不误伤）")

    # 5–7 现造样本走一遍真实链路
    with tempfile.TemporaryDirectory(dir="D:/tmp") as tmp:
        d = Path(tmp)
        good = d / "good.jpg"
        if not _make_jpg(good):
            bad("5  现造标准 JPEG", "ffmpeg 不可用或造图失败 —— 后面 3 条无法验证")
        else:
            pf_good = scene.probe(good).get("pix_fmt") or ""
            expect(pf_good in media.JPEG_SAFE_PIX_FMTS,
                   "5  scene.probe 读出标准图的 pix_fmt",
                   f"实际 {pf_good!r}")

            broken = d / "broken.jpg"
            broken.write_bytes(good.read_bytes())
            if not _break_cr_sampling(broken):
                bad("6  改坏样本", "没找到 SOF0 段，样本没造出来")
            else:
                pf_bad = scene.probe(broken).get("pix_fmt") or ""
                expect(media.jpeg_needs_normalize(pf_bad),
                       "6  坏样本被探测出来且判为需要转正",
                       f"ffprobe 读出 {pf_bad!r}")

                fixed = d / "fixed.jpg"
                done = media.normalize_jpeg(broken, fixed)
                pf_fixed = scene.probe(fixed).get("pix_fmt") if done else ""
                w0, h0 = scene.probe(broken).get("width"), scene.probe(broken).get("height")
                w1, h1 = scene.probe(fixed).get("width") if done else None, \
                    scene.probe(fixed).get("height") if done else None
                expect(done and pf_fixed in media.JPEG_SAFE_PIX_FMTS,
                       "7a 转正后格式回到安全集", f"转码成功={done} pix_fmt={pf_fixed!r}")
                expect((w0, h0) == (w1, h1) and w1,
                       "7b 转正后宽高不变", f"{w0}x{h0} -> {w1}x{h1}")

    passed = sum(1 for r in RESULT if r[0])
    for good, name, detail in RESULT:
        print(("  ✅ " if good else "  ❌ ") + name)
        if not good and detail:
            print("       " + detail)
    print(f"\nJPG 采样转正验收：通过 {passed} / {len(RESULT)}，红 {len(RESULT) - passed}")
    return 0 if passed == len(RESULT) else 1


if __name__ == "__main__":
    sys.exit(main())
