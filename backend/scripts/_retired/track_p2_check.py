"""P2 零成本验收：轨道模型 vs 旧版一次性拼装。

跑法：
    python scripts/track_p2_check.py [--cid <cid>]

验三件事，全部本地 ffmpeg，不调模型、不花钱：

  1. **等价**：同一组输入，旧 `compose()` 和轨道模型编出来的成片，
     容器时长 / 视频帧数 / 音轨采样数 / 逐帧 PSNR 必须一致。
     覆盖旧实现的三种声音分支 + 定格补时长 + 遮罩。
  2. **尺子自证**：故意做两版不一样的（换 crf、去掉字幕），
     PSNR 必须是**有限值** —— 否则上面那些"一致"就是假绿。
  3. **多片段**：把原片按时间切成 3 段交给画面轨，拼出来必须和
     "原片整条"逐帧一致 —— 证明轨道模型能直接吃掉分段素材，
     不必再先拼一个中间文件（少一代压缩）。

输出里的 PSNR：两版逐位相同时 ffmpeg 报 `inf`，这里统一记作 `inf`。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import clone_store, tracks  # noqa: E402
from app.services.media import ffmpeg_path, ffprobe_path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import legacy_compose  # noqa: E402

PASS = FAIL = 0


def check(name: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}: {got}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want={want!r}")


def check_true(name: str, cond: bool, detail="") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {name}{(' ' + detail) if detail else ''}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


# ---------------------------------------------------------------- 探针


def probe(path: Path) -> dict:
    fp = ffprobe_path()
    p = subprocess.run(
        [fp, "-v", "error", "-count_frames", "-show_entries",
         "format=duration:stream=codec_type,nb_read_frames,duration_ts,sample_rate,"
         "width,height,r_frame_rate",
         "-of", "json", str(path)],
        capture_output=True, text=True, errors="ignore", timeout=120)
    data = json.loads(p.stdout or "{}")
    out = {"duration": round(float(data.get("format", {}).get("duration") or 0), 6),
           "frames": 0, "samples": 0, "w": 0, "h": 0, "fps": 0.0}
    for s in data.get("streams") or []:
        if s.get("codec_type") == "video":
            out["frames"] = int(s.get("nb_read_frames") or 0)
            out["w"] = int(s.get("width") or 0)
            out["h"] = int(s.get("height") or 0)
            num, _, den = (s.get("r_frame_rate") or "0/1").partition("/")
            try:
                out["fps"] = round(float(num) / float(den or 1), 3)
            except (ValueError, ZeroDivisionError):
                out["fps"] = 0.0
        elif s.get("codec_type") == "audio":
            out["samples"] = int(float(s.get("duration_ts") or 0))
    return out


def psnr(a: Path, b: Path) -> float | None:
    """逐帧 PSNR（平均）。两版逐位相同 = inf。"""
    ff = ffmpeg_path()
    p = subprocess.run(
        [ff, "-hide_banner", "-i", str(a), "-i", str(b),
         "-lavfi", "[0:v][1:v]psnr", "-f", "null", "-"],
        capture_output=True, text=True, errors="ignore", timeout=600)
    m = re.findall(r"average:([0-9.]+|inf)", p.stderr or "")
    if not m:
        return None
    v = m[-1]
    return float("inf") if v == "inf" else float(v)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- 场景


def pick_render(cid: str) -> Path:
    root = clone_store.task_dir(cid) / "render"
    best = None
    for d in root.iterdir() if root.exists() else []:
        if not (d / "voice.wav").exists() or not (d / "cap.ass").exists():
            continue
        if best is None or d.stat().st_mtime > best.stat().st_mtime:
            best = d
    if best is None:
        raise SystemExit(f"任务 {cid} 下找不到同时有 voice.wav 与 cap.ass 的出片目录")
    return best


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cid", default="f01a92f793a24649982d30695f1b6d21")
    ap.add_argument("--work", default="", help="验收产物目录；留空 = 系统临时目录")
    args = ap.parse_args()

    src = clone_store.source_path(args.cid).resolve()
    rd = pick_render(args.cid)
    work = Path(args.work) if args.work else Path(
        __import__("tempfile").mkdtemp(prefix="p2check_", dir="D:/"))
    work.mkdir(parents=True, exist_ok=True)

    if not src.exists():
        raise SystemExit(f"找不到原片 {src}")
    pinfo = probe(src)
    duration, fps, total_frames = pinfo["duration"], pinfo["fps"] or 25.0, pinfo["frames"]
    print(f"== 素材：{src.name} {duration:.3f}s / 配音 {rd / 'voice.wav'} / 字幕 {rd / 'cap.ass'}")
    print(f"== 验收目录：{work}")

    voice = rd / "voice.wav"
    ass = rd / "cap.ass"

    scenes = {
        "A 配音+字幕": dict(voice=voice, ass=ass, target=duration, fps=fps),
        "B 配音+底音+遮罩": dict(voice=voice, ass=ass, bg_from=src, target=duration,
                            fps=fps, mask=(0, int(pinfo["h"] * 0.8), pinfo["w"],
                                           int(pinfo["h"] * 0.2), 0.95)),
        "C 只有原声": dict(bg_from=src, target=duration, fps=fps),
        "D 配音+定格补时长": dict(voice=voice, ass=ass, pad_to=2.0,
                            target=duration + 2.0, fps=fps),
    }

    # ---------------------------------------------------------------- 1. 等价
    for name, kw in scenes.items():
        print(f"\n== {name} ==")
        old = work / f"{name.split()[0]}_old.mp4"
        new = work / f"{name.split()[0]}_new.mp4"
        legacy_compose.compose(video=src, out=old, **kw)
        comp = tracks.from_legacy(video=src, **{**kw})
        tracks.render(comp, new)

        po, pn = probe(old), probe(new)
        check("时长一致", pn["duration"], po["duration"])
        check("视频帧数一致", pn["frames"], po["frames"])
        check("音轨采样数一致", pn["samples"], po["samples"])
        p = psnr(new, old)
        check_true("逐帧 PSNR 一致（inf = 逐位相同）", p is not None and (p == float("inf") or p >= 50.0),
                   f"= {p}")
        if sha(old) == sha(new):
            print("       文件 sha256 完全相同（比 PSNR 更强的证据）")

    # ---------------------------------------------------------------- 1b. 接线
    # 上面 A–D 验的是"轨道模型本身"；这一段验**出片链路真正调的那个入口**
    # `compose.compose()`（薄壳转发），以及它的关键字参数有没有被吞掉。
    print("== 接线：clone_pipeline 真正调的是 compose.compose，不是 tracks.render ==")
    import ast
    import inspect
    from app.services import compose as compose_shim

    src_code = (Path(__file__).resolve().parents[1]
                / "app/services/clone_pipeline.py").read_text(encoding="utf-8")
    call_kwargs: set[str] = set()
    for node in ast.walk(ast.parse(src_code)):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "compose"):
            call_kwargs |= {k.arg for k in node.keywords if k.arg}
    print(f"  出片链路传给 compose 的参数：{sorted(call_kwargs)}")
    shim_params = set(inspect.signature(compose_shim.compose).parameters)
    tracks_params = set(inspect.signature(tracks.from_legacy).parameters)
    check("compose 薄壳认得出全部参数", sorted(call_kwargs - shim_params), [])
    # 三个参数不进作品本身，别拿来要求 from_legacy 认：
    #   out   —— 产物路径，走 render(comp, out)
    #   clips / size —— P2.5 的"画面轨直接吃分段素材"，由 compose 薄壳先替换画面轨，
    #                  from_legacy 只负责把**老参数**翻译成作品
    # 尺子自己先对一遍，否则这条会永远红（假红）。
    passthrough = {"out", "clips", "size"}
    check("轨道模型认得出全部参数（out/clips/size 除外）",
          sorted(call_kwargs - tracks_params - passthrough), [])

    shim_out = work / "shim.mp4"
    compose_shim.compose(video=src, out=shim_out, ass=ass, voice=voice,
                         target=duration, fps=fps)
    check("经薄壳出的片 = 旧版成片（sha256）", sha(shim_out), sha(work / "A_old.mp4"))

    # ---------------------------------------------------------------- 2. 尺子自证
    print("\n== 尺子自证：尺子必须能判出「不一样」 ==")
    base_kw = dict(voice=voice, ass=ass, target=duration, fps=fps)
    base = work / "A_new.mp4"
    p_inf = psnr(base, work / "A_old.mp4")
    check_true("同一版自己比自己 = inf", p_inf == float("inf"), f"= {p_inf}")

    crf24 = work / "ctl_crf24.mp4"
    tracks.render(tracks.from_legacy(video=src, crf=24, **base_kw), crf24)
    p_crf = psnr(crf24, base)
    check_true("换 crf 后 PSNR 变成有限值", p_crf is not None and p_crf < float("inf"),
               f"= {p_crf:.2f} dB" if p_crf and p_crf != float("inf") else f"= {p_crf}")

    noass = work / "ctl_noass.mp4"
    tracks.render(tracks.from_legacy(video=src, **{**base_kw, "ass": None}), noass)
    p_noass = psnr(noass, base)
    check_true("去掉字幕（只改字幕轨）后 PSNR 变成有限值",
               p_noass is not None and p_noass < float("inf"),
               f"= {p_noass:.2f} dB" if p_noass and p_noass != float("inf") else f"= {p_noass}")

    # ---------------------------------------------------------------- 3. 多片段
    print("\n== 多片段：3 段直接进画面轨，不经中间文件 ==")
    # 切点落在**帧边界**上：60 秒的片子按秒切，切点会掉在帧中间，
    # 相邻两段就会抢同一帧（实测多出 2 帧）
    n1 = total_frames // 3
    b1, b2 = n1 / fps, (2 * n1) / fps
    cuts = [(0.0, b1), (b1, b2), (b2, None)]
    clips = [tracks.VideoClip(source=src, start=a, end=b, label=f"part{i}")
             for i, (a, b) in enumerate(cuts)]
    multi = tracks.Composition(
        visual=tracks.VisualTrack(clips=clips),
        audio=tracks.AudioTrack(clips=[
            tracks.AudioClip(source=voice, role="voice", label="voice")]),
        captions=tracks.CaptionTrack(ass=ass),
        duration=duration, fps=fps,
    )
    multi_out = work / "multi.mp4"
    tracks.render(multi, multi_out)
    pm, pn, po = probe(multi_out), probe(work / "A_new.mp4"), probe(work / "A_old.mp4")
    check("3 段拼出来帧数 = 单段整条", pm["frames"], pn["frames"])
    check("3 段拼出来采样数 = 单段整条", pm["samples"], pn["samples"])
    p_multi = psnr(multi_out, work / "A_new.mp4")
    check_true("3 段拼出来与整条逐帧一致", p_multi == float("inf"), f"= {p_multi}")

    # ---------------------------------------------------------------- 4. 指纹
    print("\n== 指纹：改一条轨道，只该变一条 ==")
    c0 = tracks.from_legacy(video=src, **base_kw)
    c1 = tracks.from_legacy(video=src, **{**base_kw, "ass": None})
    check("只改字幕 → 只有 captions 变", c0.changed(c1), ["captions"])
    c2 = tracks.from_legacy(video=src, **{**base_kw, "fps": fps - 5})
    check("只改帧率 → 只有 render 变", c0.changed(c2), ["render"])
    c3 = tracks.from_legacy(video=src, **{**base_kw, "bg_from": src})
    check("加了底音 → 只有 audio 变", c0.changed(c3), ["audio"])
    c4 = tracks.from_legacy(video=src, **{**base_kw, "crf": 24})
    check("只改编码参数 → 只有 render 变", c0.changed(c4), ["render"])

    print(f"\n{PASS}/{PASS + FAIL} 通过（零模型调用；产物在 {work}）")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
