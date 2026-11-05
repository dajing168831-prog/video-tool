"""出片彩排：在**真实任务**上把整条出片链路跑一遍，模型调用全部换成本地假实现。

为什么要有这个
--------------
出片是真金白银：生图、图生视频、视频编辑、配音，每一步都计费。
以前只能"点了才知道错"，一个参数传错就是一次钱。

这个脚本把火山 / MiniMax / TTS 替换成本地 ffmpeg 造的假产物，
**其余全是真代码**：分诊、提示词编译、参考图组装、时间轴拼装、合成、质量门。
所以"点了就报错""参考图没发出去""成片时长不对"这类问题，在花钱之前就能发现。

不花钱：整个过程零网络请求（`_public_url` 也换成了假地址）。

隔离：把任务复制到临时目录再跑（`VT_CLONE_DIR` 指向临时目录），
不动用户数据，也不复用已有缓存 —— 否则会命中上一次的缓存，模型调用根本不发生。

用法：
    python scripts/rehearse_render.py                 # 拿最近一个已分析的任务
    python scripts/rehearse_render.py --cid <cid>     # 指定任务
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.core.config import settings  # noqa: E402
# 🧊 2026-11-03 复刻下架 H3：`minimax`（出片客户端 + IR）随执行链归档。
from app.services import (ark, clone_pipeline, edit_spec, generate,  # noqa: E402
                          triage, video_edit)
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


def dur_of(p: Path) -> float:
    r = subprocess.run([ffprobe_path(), "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1", str(p)], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if line.startswith("duration="):
            return float(line.split("=")[1])
    return 0.0


def cut(src: Path, out: Path, start: float, dur: float) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y",
                    "-ss", f"{start:.3f}", "-i", str(src), "-t", f"{max(0.5, dur):.3f}",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                    "-an", str(out)], check=True, capture_output=True)
    return out


class FakeTTS:
    """假配音：按字数造一段正弦波，长度接近真实 TTS。"""

    ext = ".mp3"

    def synth(self, text: str, out: Path, *, voice: str = "",
              rate: int = 0, dialect: str = "",
              fidelity: bool = False) -> None:
        # 签名必须跟真供应商一致（`providers/tts.py:40/117` 都收 dialect）——
        # 🩸 2026-10-28：少这个形参，整条排练在合成第一句时 TypeError。
        # 🩸 2026-11-05：`fidelity`（口音还原）同上，流水线现在恒传它。
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        seconds = max(1.0, len(text) * 0.19)
        subprocess.run([ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i", f"sine=frequency=220:duration={seconds}",
                        str(out)], check=True, capture_output=True)


def latest_analyzed() -> str:
    root = Path(settings.clone_dir)
    best = ("", 0.0)
    for d in root.iterdir() if root.exists() else []:
        f = d / "task.json"
        if not f.exists():
            continue
        try:
            t = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if t.get("recipe") and t.get("state") == "analyzed":
            if f.stat().st_mtime > best[1]:
                best = (d.name, f.stat().st_mtime)
    return best[0]


def prepare(cid: str, root: Path) -> tuple[str, Path, dict]:
    """把任务复制到临时目录，返回 (新 cid, 任务目录, 配方)。"""
    src = Path(settings.clone_dir) / cid
    new = "ab" * 16
    dst = root / new
    dst.mkdir(parents=True)
    for name in ("subject.jpg", "ref_product.jpg", "ref_scene.jpg", "ref_wardrobe.jpg"):
        if (src / name).exists():
            shutil.copy2(src / name, dst / name)
    if (src / "inventory").exists():
        shutil.copytree(src / "inventory", dst / "inventory")
    try:
        (dst / "source.mp4").hardlink_to(src / "source.mp4")
    except Exception:
        shutil.copy2(src / "source.mp4", dst / "source.mp4")
    task = json.loads((src / "task.json").read_text(encoding="utf-8"))
    task["id"] = new
    (dst / "task.json").write_text(json.dumps(task, ensure_ascii=False), encoding="utf-8")
    (dst / "cover.img").parent.mkdir(parents=True, exist_ok=True)
    return new, dst, task["recipe"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cid", default="", help="要彩排的任务号；留空 = 最近一个已分析的任务")
    args = ap.parse_args()

    cid = args.cid or latest_analyzed()
    if not cid:
        print("没有已分析的任务，先跑一次分析（或传 --cid）")
        return 2

    root = Path(tempfile.mkdtemp(dir="D:/tmp", prefix="rehearse_"))
    # 人脸检测模型跟着 clone_dir 的**父目录**走（见 `identity.MODELS`）：
    # 任务目录要多套一层，模型才和真实布局一样落在 …/models
    tasks_root = root / "clone"
    tasks_root.mkdir()
    models = Path(settings.clone_dir).parent / "models"
    if models.exists():
        shutil.copytree(models, root / "models")
    new_cid, task_dir, rec = prepare(cid, tasks_root)
    video = task_dir / "source.mp4"
    refs = {}
    for slot, name in (("person", "subject.jpg"), ("product", "ref_product.jpg"),
                       ("scene", "ref_scene.jpg"), ("wardrobe", "ref_wardrobe.jpg")):
        if (task_dir / name).exists():
            refs[slot] = task_dir / name

    orig_clone_dir = settings.clone_dir
    object.__setattr__(settings, "clone_dir", tasks_root)
    real = (ark.edit_video, video_edit._public_url, settings.ark_api_key)
    seen: dict = {}
    calls: list[dict] = []

    # 🩸 不要替换 `video_edit.replace_spans` 本身：分段续接（边界帧、按段换人、
    # 缓存键）全在 `_gen_spans` 里 —— 连它一起换掉，等于把要验的代码也假掉了。
    # 只换最底下的模型调用，分段的真实逻辑照跑。

    # 🧊 2026-11-03：`fake_ref_video`（MiniMax 出片桩）随 H3 下架删除。
    def fake_edit_video(prompt, *, video_url, out, ref_image=None, ref_images=None,
                        ref_asset="", ref_audio=None, model="", resolution="720p",
                        duration=0.0, **_):
        seen.update(model_prompt=prompt,
                    model_imgs=[Path(x).name for x in (ref_images or [])])
        calls.append(dict(seen))
        return cut(video, out, 0.0, min(float(duration) or 6.0, dur_of(video)))

    # 🧊 2026-11-03：`fake_context_ir`（H3-Context-IR 桩）随改写器归档删除。
    ark.edit_video = fake_edit_video
    video_edit._public_url = lambda seg, cid: "https://example.test/seg.mp4"
    object.__setattr__(settings, "ark_api_key", "k")

    src_total = float((rec.get("source") or {}).get("duration") or 0)
    # 文案长度按原片估：0.19 秒/字（和假 TTS 的口径一致，免得被"差太多"拦下）
    script = "这是一段用于彩排的占位文案，" * max(1, int(src_total / 0.19 / 14))
    script = script[: max(8, int(src_total / 0.19))]
    work = root / "out"

    def spec(**kw):
        base = {k: False for k in ("person", "product", "scene", "wardrobe")}
        base.update(kw)
        return edit_spec.normalize({**base, "audio": "original"})

    def run(tag: str, **kw):
        seen.clear()
        calls.clear()
        return clone_pipeline.render(video, rec, workdir=work / tag, progress=None, **kw)

    try:
        print(f"== 彩排任务 {cid[:8]}（{src_total:.2f}s）==")
        have_person = "person" in refs
        if have_person:
            print("== 1. 智能重制 + 换人 + 保留原声 ==")
            r = run("r1", script=None, cid=new_cid, mask_bottom=True, regen_mode="auto",
                    # 🩸 多人画面必须点名换谁（`_prepare` 的多人闸门拦得住），
                    #    彩排走的是同一条真链路，所以也得给。
                    edit_spec=spec(person=True, person_ids=["P1"]), refs=refs,
                    subject_image=refs["person"])
            # 🩸 2026-11-02 分诊只剩 keep / video：`still_shots()` / `audio_mode` /
            #    `speech_spans` 全部随静帧档删除。判据改成「没勾镜头 = 全部重制」。
            disp = triage.decide(rec.get("shots") or [], None)
            check("没勾镜头时整条走视频重制",
                  set(disp.values()), {"video"})
            # 🩸 2026-10-22 真实翻车点：第 2 段开头 3 秒原片人物回灌。
            # 根因是边界帧没进 subject_definitions。这里在真链路上把它钉住。
            #
            # ⚠️ 判据必须跟**实际切到哪儿**走，不能写死"第 2 段一定带边界帧"：
            # 这个样本 11.7s 处原本就有一刀，段接缝正好落在切镜上 —— 那种接缝
            # **故意不带**边界帧（旧场景的尾帧会把画面往回拽）。换一个样本、
            # 换一个上限，"第几段带"就变了（2026-10-22 第二次因写死样本假红）。
            dec = json.loads((work / "r1" / "decisions.json").read_text(encoding="utf-8"))
            spans = [(float(a), float(b)) for a, b in dec["spans"]]
            # 🩸 T2（2026-10-23）：必须用**产品同一把尺**。产品判"接缝在切点上"
            # 走的是 `_at_shot_cut`（±0.08s 容差），这里原来用 `round(b,3) in starts`
            # 精确相等 —— 10.1s 的接缝距真实切点 0.05s，产品认定"在切点上"（判定
            # 正确：不带边界帧），测试却判成"不在"，是**假红**。
            at_cut = [video_edit._at_shot_cut(rec, float(b)) for _, b in spans[:-1]]
            check("每一段都调了一次模型", len(calls), len(spans))
            check("第 1 段只发人物图", (calls[0]["model_imgs"] if calls else []),
                  ["subject.jpg"])
            check("第 1 段不写首帧句",
                  "is the first frame of the target video"
                  in (calls[0]["model_prompt"] if calls else ""), False)
            check("结果页如实报了有没有边界帧", r["regen_meta"]["boundary"],
                  any(not c for c in at_cut))
            print(f"       （段数 {len(spans)}；接缝在镜头切点上 = {at_cut}）")
            for n, seam_cut in enumerate(at_cut, start=2):
                imgs = calls[n - 1]["model_imgs"] if len(calls) >= n else []
                prompt = calls[n - 1]["model_prompt"] if len(calls) >= n else ""
                has_bf = any("boundary" in str(x) for x in imgs)
                where = "落在原片切镜上" if seam_cut else "落在镜头中间"
                check(f"第 {n} 段接缝{where} → 边界帧 {has_bf}", has_bf, not seam_cut)
                check(f"第 {n} 段首帧句与接缝一致",
                      "<Picture 2> is the first frame of the target video" in prompt,
                      not seam_cut)
                # 🩸 2026-10-23（E5 查出的判据过期）：官方 `ref-en:134` 的 task type
                # 是**多项用 ` + ` 连**的枚举，实际产出可能是
                # `[video editing + reference generation + audio reuse + keyframe completion]`。
                # 原来按整串 `[video editing + keyframe completion]` 精确匹配，
                # 多一项就假红。改成"取方括号里的项，再看有没有这一项"。
                _m = re.match(r"^\[([^\]]+)\]", prompt.split("summary:", 1)[-1].lstrip())
                _typs = [x.strip() for x in _m.group(1).split("+")] if _m else []
                check(f"第 {n} 段任务类型与接缝一致",
                      "keyframe completion" in _typs, not seam_cut)
            check("成片有内容", Path(r["video"]).stat().st_size > 10_000, True)
            check("成片时长没跑偏", abs(dur_of(r["video"]) - src_total) < 1.0, True)

            print("== 3. 整片重制 + 换人 ==")
            # 同 r1：多人画面必须点名换谁，否则被 `_prepare` 的多人闸门拦下
            sp = edit_spec.normalize({"person": True, "person_ids": ["P1"],
                                      "audio": "tts"})
            r3 = run("r3", script=script, cid=new_cid, mask_bottom=True,
                     regen_mode="whole", edit_spec=sp, refs=refs,
                     subject_image=refs["person"], tts=FakeTTS(), allow_stretch=True)
            check("整片重制第 1 段只发人物图",
                  calls[0]["model_imgs"] if calls else [], ["subject.jpg"])
            # 同一条规矩：接缝落在原片切镜上就不带边界帧。
            # 整片重制的分段由 `plan_spans` 给出（这里验的是边界帧有没有按规则跟上，
            # 分段本身归 test_plan_preview / test_whole_wiring 管）
            plan3 = video_edit.prepare(rec, prompt="", spec=sp, refs=refs,
                                       subject_image=refs["person"], channel="auto",
                                       model="")
            spans3, _moved3 = video_edit.plan_spans(video, rec, plan3)
            # 同 T2：与产品同一把尺（±0.08s）
            at3 = [video_edit._at_shot_cut(rec, float(b)) for _, b in spans3[:-1]]
            print(f"       （整片重制段数 {len(spans3)}；接缝在切点上 = {at3}）")
            for n, seam_cut in enumerate(at3, start=2):
                imgs3 = calls[n - 1]["model_imgs"] if len(calls) >= n else []
                has_bf3 = any("boundary" in str(x) for x in imgs3)
                check(f"整片重制第 {n} 段边界帧与接缝一致", has_bf3, not seam_cut)
            check("提示词非空", bool(seen.get("model_prompt")), True)
            check("整片重制成片有内容", Path(r3["video"]).stat().st_size > 10_000, True)
        else:
            print("（这个任务没传人物图，跳过换人相关彩排）")

        print("== 4. 只换配音不换画面 ==")
        r4 = run("r4", script=script, cid=new_cid, mask_bottom=True, regen_mode="auto",
                 edit_spec=edit_spec.normalize({"audio": "tts"}),
                 tts=FakeTTS(), allow_stretch=True)
        check("画面全部用原片", r4.get("replaced_shots", 0), 0)
        check("成片有内容", Path(r4["video"]).stat().st_size > 10_000, True)
        # 🩸 2026-10-23 主人拍板「也不烧字幕」：不再产出字幕轨
        check("不带字幕轨", bool(r4.get("ass")), False)

    finally:
        ark.edit_video, video_edit._public_url = real[:2]
        object.__setattr__(settings, "ark_api_key", real[2])
        object.__setattr__(settings, "clone_dir", orig_clone_dir)
        shutil.rmtree(root, ignore_errors=True)

    print(f"\n{PASS}/{PASS + FAIL} 通过（零费用，未调用任何付费接口）")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
