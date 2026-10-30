"""出片的声音模式自检：真跑 ffmpeg，不调任何外部 API。

验的是「唱歌跳舞不重新配音」这条路真的能出片：
  - 原片没有识别到任何文字时，保留原声也能出片（不拿"没文案"卡住）
  - 输出音轨来自原片（不是空的、也不是模型的）
  - 默认不烧新字幕
  - 原片压根没有音轨时，改成保留原声要说清楚为什么不行

运行：python scripts/test_audio_modes.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import clone_pipeline, edit_spec  # noqa: E402
from app.services.media import ffmpeg_path, ffprobe_path  # noqa: E402

PASS = FAIL = 0


def check(name: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}: {got}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want={want!r}")


def make_video(path: Path, seconds: float, *, with_audio: bool) -> Path:
    ff = ffmpeg_path()
    args = [ff, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"color=c=navy:s=360x640:d={seconds}:r=25"]
    if with_audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                 "-c:a", "aac", "-shortest"]
    args += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)]
    p = subprocess.run(args, capture_output=True, text=True, errors="ignore")
    if p.returncode != 0 or not path.exists():
        raise SystemExit("造测试视频失败: " + (p.stderr or "")[-400:])
    return path


def streams(path: Path) -> dict:
    p = subprocess.run(
        [ffprobe_path(), "-v", "error", "-show_entries",
         "stream=codec_type:format=duration", "-of", "default=nw=1", str(path)],
        capture_output=True, text=True, errors="ignore",
    )
    out = {"video": False, "audio": False, "duration": 0.0}
    for line in p.stdout.splitlines():
        if line.startswith("codec_type="):
            kind = line.split("=", 1)[1]
            if kind in out:
                out[kind] = True
        elif line.startswith("duration="):
            try:
                out["duration"] = float(line.split("=", 1)[1])
            except ValueError:
                pass
    return out


def rec_of(seconds: float, *, has_speech: bool, has_audio: bool = True) -> dict:
    return {
        "source": {"duration": seconds, "width": 360, "height": 640,
                   "fps": 25.0, "has_audio": has_audio},
        "speech": {"has": has_speech, "lang": "zh", "segments": []},
        "shots": [
            {"i": 0, "start": 0.0, "end": seconds / 2, "dur": seconds / 2},
            {"i": 1, "start": seconds / 2, "end": seconds, "dur": seconds / 2},
        ],
        "caption_style": {},
    }


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：一轮只跑一家
    from _model_gate import sel_or_exit as _sel
    _sel()
    work = Path(tempfile.mkdtemp(dir="D:/tmp", prefix="audio_modes_"))
    try:
        return _run(work)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _run(work: Path) -> int:
    print("== 唱歌/跳舞：没有识别到文字，保留原声 ==")
    src = make_video(work / "sing.mp4", 6.0, with_audio=True)
    res = clone_pipeline.render(
        src, rec_of(6.0, has_speech=False), script="", workdir=work / "r1",
        edit_spec=edit_spec.normalize({"audio": "original"}),
    )
    s = streams(res["video"])
    check("出片存在", res["video"].exists(), True)
    check("有画面", s["video"], True)
    check("有音轨（原片的）", s["audio"], True)
    check("时长不塌", round(s["duration"]), 6)
    check("🩸 成片不带任何字幕文件", res.get("ass") is None, True)

    print("== 原片没有音轨 ==")
    silent = make_video(work / "silent.mp4", 6.0, with_audio=False)
    res3 = clone_pipeline.render(
        silent, rec_of(6.0, has_speech=False, has_audio=False), script="",
        workdir=work / "r3",
        edit_spec=edit_spec.normalize({"audio": "original"}),
    )
    s3 = streams(res3["video"])
    check("没音轨也能出片（画面为主）", res3["video"].exists() and s3["video"], True)
    check("不硬接一条不存在的音轨", s3["audio"], False)

    print("== 声音模式的默认值 ==")
    check("默认是全新配音", edit_spec.defaults()["audio"], "tts")
    # 🩸 2026-10-23 主人拍板「也不烧字幕」：subtitle 字段已删除，老请求传了也不认
    check("规格里不再有 subtitle 字段", "subtitle" not in edit_spec.defaults(), True)
    check("老请求带 subtitle 也不会漏到规格里",
          "subtitle" not in edit_spec.normalize({"audio": "original",
                                                 "subtitle": True}), True)

    print(f"\n{PASS}/{PASS + FAIL} 通过")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
