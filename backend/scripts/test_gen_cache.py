"""跨次点击的生成缓存：同一提示词重跑，真的不再调模型吗？

界面上写着「同一提示词重跑不重复扣费」—— 这句话必须是**可验证的事实**，
不是文案。验法：把两个模型调用换成计数器 + 本地假产物，连点两次「出片」
（两次用不同的出片目录，就像用户点了两次），看第二次有没有再调模型。

判据成对（只有一边就会退化成另一种坏）：
  · **提示词没变** → 跨次点击必须命中缓存，不再调模型（省钱）
  · **提示词变了** → 必须重新生成（缓存绝不能挡住改动）

🩸 这条曾经是假的：缓存清单放在 `render/<rid>/` 里，而每次点「出片」
都会新建一个 rid，清单跟着新目录走 → 跨次点击永远命中不了。

🩸 2026-10-24 我曾把跨次缓存删掉，理由是"点了重跑还是一模一样的片子"。
   当天实测反证：同一提示词真跑一遍，成片与上一版 SSIM 0.95 ——
   钱花了，结果照样一样。缓存键里本来就有提示词哈希，提示词一改必然失效；
   "没变化"是提示词没改，不是缓存挡路。已恢复。

不花钱（不发任何网络请求）。

运行：python scripts/test_gen_cache.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.core.config import settings  # noqa: E402
from app.services import clone_store, generate, video_edit  # noqa: E402
from app.services.media import ffmpeg_path  # noqa: E402

PASS = FAIL = 0


def check(name: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}: {got}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want={want!r}")


def make_video(path: Path, seconds: float, w: int = 360, h: int = 640,
               src: str | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    s = src or f"color=c=navy:s={w}x{h}:d={seconds}:r=25"
    p = subprocess.run(
        [ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", s, "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)],
        capture_output=True, text=True, errors="ignore",
    )
    if p.returncode != 0 or not path.exists():
        raise SystemExit("造测试视频失败: " + (p.stderr or "")[-400:])
    return path


def make_image(path: Path, color: str = "red") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(
        [ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", f"color=c={color}:s=400x600:d=1", "-frames:v", "1", str(path)],
        capture_output=True, text=True, errors="ignore",
    )
    if p.returncode != 0:
        raise SystemExit("造测试图片失败: " + (p.stderr or "")[-400:])
    return path


def test_whole_cache() -> None:
    print("== 整片重制：连点两次「出片」，第二次不该再调视频模型 ==")
    work = Path(tempfile.mkdtemp(dir="D:/tmp", prefix="gen_cache_"))
    real_task_dir = clone_store.task_dir
    calls = {"n": 0}
    real_key = settings.ark_api_key
    real_base = settings.public_base_url
    real_url = video_edit._public_url

    # 🩸 夹具不许手抄签名（2026-10-26 已栽第二次，第一次是 `generate_audio`）：
    # 产品每给 `ark.edit_video` 加一个参数（这次是 A9 风格参考视频的 `ref_videos`），
    # 手抄的假函数就少一个 → TypeError 打断整段渲染，看着像产品坏了，其实是夹具过期。
    # 现在用 `**kw` 全收，只反过来查"产品有没有传一个真函数都不认的参数"。
    from app.services import ark as _ark
    import inspect as _inspect

    _real_params = set(_inspect.signature(_ark.edit_video).parameters) - {
        "prompt", "video_url", "out"}

    def fake_edit(prompt, *, video_url, out, **kw):
        unknown = set(kw) - _real_params
        if unknown:
            raise AssertionError(
                f"产品传了 ark.edit_video 不认识的参数：{sorted(unknown)}")
        calls["n"] += 1
        duration = kw.get("duration", -1)
        secs = duration if isinstance(duration, (int, float)) and duration > 0 else 4
        make_video(Path(out), float(secs))

    try:
        # 只要"通过配置检查"就行，不会真有网络请求
        object.__setattr__(settings, "ark_api_key", "k")
        object.__setattr__(settings, "public_base_url", "https://api.test")
        video_edit._public_url = lambda seg, cid: "https://example.test/seg.mp4"
        # 缓存目录挂到临时目录，别污染真实 data/clone
        clone_store.task_dir = lambda cid: work / "tasks" / cid
        from app.services import ark
        real_ark_edit = ark.edit_video
        ark.edit_video = fake_edit

        video = make_video(work / "src.mp4", 8.0)
        rec = {
            "source": {"duration": 8.0, "width": 360, "height": 640, "fps": 25.0,
                       "has_audio": False},
            "shots": [{"i": 0, "start": 0.0, "end": 4.0},
                      {"i": 1, "start": 4.0, "end": 8.0}],
        }
        cid = "a" * 32

        def run(tag: str, prompt: str, refs=None, spec=None):
            calls["n"] = 0
            r = video_edit.replace_whole(
                video, rec, cid=cid, prompt=prompt, refs=refs, spec=spec,
                channel="volc", model="", workdir=work / tag,
            )
            return r, calls["n"]

        r1, n1 = run("r1", "换成白色背景的直播间")
        check("第一次真的调了模型", n1 > 0, True)
        check("第一次出了成片", Path(r1["video"]).stat().st_size > 1000, True)

        r2, n2 = run("r2", "换成白色背景的直播间")
        check("第二次点击不再调模型（跨出片目录命中）", n2, 0)
        check("第二次照样有可用成片", Path(r2["video"]).stat().st_size > 1000, True)

        r3, n3 = run("r3", "换成灰色背景的直播间")
        check("换了提示词必须重新生成", n3 > 0, True)

        # 换了人物参考图但提示词没变：键里没图就会拿回旧脸
        img1 = make_image(work / "p1.jpg", "red")
        img2 = make_image(work / "p2.jpg", "blue")
        from app.services import edit_spec
        spec = edit_spec.normalize({"person": True, "person_desc": "红衣服女孩"})
        _, n4 = run("r4", "", refs={"person": img1}, spec=spec)
        _, n5 = run("r5", "", refs={"person": img1}, spec=spec)
        _, n6 = run("r6", "", refs={"person": img2}, spec=spec)
        check("同一张人物图重跑不重生成", n5, 0)
        check("换了一张人物图必须重生成", n6 > 0, True)
        check("第一次带图是生成的", n4 > 0, True)
    finally:
        clone_store.task_dir = real_task_dir
        video_edit._public_url = real_url
        object.__setattr__(settings, "ark_api_key", real_key)
        object.__setattr__(settings, "public_base_url", real_base)
        from app.services import ark
        ark.edit_video = real_ark_edit
        shutil.rmtree(work, ignore_errors=True)


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：一轮只跑一家
    from _model_gate import sel_or_exit as _sel
    _sel()
    test_whole_cache()
    print(f"\n{PASS}/{PASS + FAIL} 通过")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
