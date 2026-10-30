"""P15 验收：无缝转场（B7，两段视频补全间隙）。

零模型调用、不花钱：请求体是纯函数，切分/接缝是纯计算，`make_seam` 用桩。

  S1 请求体    —— 2.5 声明 omni_reference_task_type=reference；2.0 没有（成对）
  S2 内容顺序  —— text → 视频1 → 视频2；duration=4；不出音频；ratio=adaptive
  S3 提示词    —— 照抄官方骨架（`seedance-25-guide.md:1337`），槽位可换、留空不留坑
  S4 切分      —— split_by_marks 总时长守恒、不产生 0 长度片段（**预留、未接入**）
  S5 接缝替换  —— 前后各让 2 秒 + 中间插 4 秒，**总时长不变**；段太短跳过并记账（同上）
  S6 缓存键    —— 同素材同参数同键；换提示词/换位置/换型号换键
  S7 边界      —— 0 和总长两端不补；N 段最多 N-1 个接缝
  S8 接线      —— **出片侧一个字段都不许留**（2026-10-25 主人拍板只留延长链路）；
                  延长链路 `ExtendIn` / `extend.run` 保留，但**前端入口已下架**
                  （2026-10-28 主人拍板：只做复刻，不做延长）

  🩸 范围：B7 **只接在延长链路**（原片 ↔ AI 续写段那一个接缝）。出片链路不接：
  复刻要像原片，而原片的硬切就是原片的剪法；重绘段 ↔ 原片段的接缝另有 B6 尾帧锁定。
  S4/S5 测的是 `transition.patch` 那一组「预留但没调用方」的代码，不许当成已上线能力。

官方出处：
  `seedance-25-guide.md:69`（视频无缝转场）、`:1337`（句式）
  `seedance-20-guide.md:988-1000`（轨道补齐，≤3 段 / 总 ≤15s）
  `volc-api:458`（reference 任务 ratio/duration 无限制）、`:588`（duration 下限 4s）

跑法：python scripts/p15_check.py --model volc20|volc25|h3
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import ark, edit_spec, transition  # noqa: E402

FRONT = ROOT.parent / "frontend" / "app" / "src"

M25 = "doubao-seedance-2-5-260628"
M20 = "doubao-seedance-2-0-fast-260128"

rows: list[tuple[str, bool, str]] = []

# 🚦 必须点名型号（2026-10-26）：一轮只跑一家。
from _model_gate import sel_or_exit as _sel_or_exit
SEL = _sel_or_exit()


def chk(name: str, ok, detail: str = "") -> None:
    rows.append((name, bool(ok), detail if not ok else ""))


TMP = Path(tempfile.mkdtemp(prefix="p15_", dir="D:/tmp"))


def _mk(name: str, data: bytes = b"STUB") -> Path:
    p = TMP / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def body_of(model: str, **kw) -> dict:
    base = dict(video_a="https://x.test/a.mp4", video_b="https://x.test/b.mp4",
                model=model)
    base.update(kw)
    return ark.transition_body(transition.seam_prompt(), **base)


def roles(b: dict) -> list[str]:
    return [c.get("role") for c in (b.get("content") or [])
            if c.get("type") == "video_url"]


# ---------------------------------------------------------------------------
# S1 请求体

if SEL == "volc25":
    b25 = body_of(M25)
    chk("S1 2.5 显式声明 reference 任务（`volc-api:458`）",
        b25.get("omni_reference_task_type") == "reference",
        str(b25.get("omni_reference_task_type")))
elif SEL == "volc20":
    b20 = body_of(M20)
    chk("S1 2.0 不带 omni_reference_task_type（该字段只支持 2.5）",
        "omni_reference_task_type" not in b20, str(b20.keys()))

# ---------------------------------------------------------------------------
# S2 内容顺序与固定参数

if SEL == "volc25":
    b25 = body_of(M25)
    chk("S2 两段都是 reference_video", roles(b25) == ["reference_video"] * 2, str(roles(b25)))
    con = b25.get("content") or []
    chk("S2 第一项是文本、后两项按 视频1→视频2 顺序",
        con[0].get("type") == "text"
        and "a.mp4" in str((con[1].get("video_url") or {}).get("url"))
        and "b.mp4" in str((con[2].get("video_url") or {}).get("url")),
        str(con)[:160])
    chk("S2 时长 4 秒（官方下限，`volc-api:588`）",
        b25.get("duration") == 4, str(b25.get("duration")))
    chk("S2 不出音频（成片声音来自 TTS/原片，模型那条会被丢掉）",
        b25.get("generate_audio") is False, str(b25.get("generate_audio")))
    chk("S2 比例自适应（接缝两侧跟原片同规格）",
        b25.get("ratio") == "adaptive", str(b25.get("ratio")))
elif SEL == "volc20":
    b20 = body_of(M20)
    chk("S2 2.0 时长 4 秒（官方下限，`volc-api:588`）",
        b20.get("duration") == 4, str(b20.get("duration")))
    chk("S2 两段时长都超上限时按型号收口（2.0 上限 15）",
        ark.transition_body(transition.seam_prompt(), video_a="u1", video_b="u2",
                            model=M20, duration=99).get("duration") == 15, "")

# ---------------------------------------------------------------------------
# S3 提示词骨架

p0 = transition.seam_prompt()
chk("S3 骨架含官方三处（衔接起来 / 无缝自然地衔接转场到@视频2 / 不要改变上传的两个视频）",
    "衔接起来" in p0 and "无缝自然地衔接转场到@视频2" in p0
    and "不要改变上传的两个视频" in p0, p0[:160])
p1 = transition.seam_prompt("镜头快速横移带走")
chk("S3 给了描述就进槽位", "镜头快速横移带走" in p1, p1[:160])
chk("S3 留空不留空槽（不出现两个连续逗号或空括号）",
    "，，" not in p0 and "（）" not in p0 and "{desc}" not in p0, p0)
chk("S3 描述末尾标点被吃掉（不出现「。，」）",
    "。，" not in transition.seam_prompt("横移带走。"), transition.seam_prompt("横移带走。"))

# ---------------------------------------------------------------------------
# S4 切分：总时长守恒

def c(src: str, start: float, end: float) -> dict:
    return {"source": src, "start": start, "end": end, "freeze": 0.0,
            "label": "x", "kind": "source"}


clips0 = [c("/v/a.mp4", 0.0, 5.0), c("/v/b.mp4", 10.0, 18.0)]
segs = transition.split_by_marks(clips0, [5.0, 8.0, 13.0, 99.0])
tot0 = sum(transition.clip_dur(x) for x in clips0)
tot1 = sum(transition.clip_dur(x) for x in segs)
chk("S4 切分后总时长守恒", abs(tot0 - tot1) < 1e-6, f"{tot0} vs {tot1}")
chk("S4 落在片段边界上/片段外的 mark 被忽略（5.0 不切、99 不切）",
    len(segs) == 3, str(len(segs)))
chk("S4 没有 0 长度片段", all(transition.clip_dur(x) > 0 for x in segs), str(segs))
chk("S4 切开后源文件不变、只改 start/end",
    segs[0]["source"] == "/v/a.mp4" and segs[-1]["source"] == "/v/b.mp4", "")

# ---------------------------------------------------------------------------
# S5 接缝替换：前后各让 2 秒、中间插 4 秒、总时长不变

_real_make = transition.make_seam
_calls: list[tuple[float, float]] = []


def _fake_make(prev, prev_end, nxt, nxt_start, **kw):
    _calls.append((round(float(prev_end), 3), round(float(nxt_start), 3)))
    return _mk(f"seam_{len(_calls)}.mp4")


transition.make_seam = _fake_make

clips1 = [c("/v/a.mp4", 0.0, 6.0), c("/v/b.mp4", 0.0, 6.0), c("/v/c.mp4", 0.0, 6.0)]
out1, info1 = transition.patch(clips1, workdir=TMP / "w1", model=M25)
chk("S5 三段落 → 补了两个接缝、插进两段过渡（共 5 段）",
    len(out1) == 5 and info1["patched"] == 2, f"{len(out1)}/{info1['patched']}")
tot_before = sum(transition.clip_dur(x) for x in clips1)
tot_after = sum(transition.clip_dur(x) for x in out1)
chk("S5 总时长不变（配音轨不需要重新对齐）",
    abs(tot_before - tot_after) < 1e-6, f"{tot_before} vs {tot_after}")
chk("S5 前段让出 2 秒、后段让进 2 秒",
    abs(transition.clip_dur(out1[0]) - 4.0) < 1e-6
    and abs(out1[2]["start"] - 2.0) < 1e-6, f"{out1[0]}/{out1[2]}")
chk("S5 插入的过渡段长 4 秒、标成 seam",
    abs(transition.clip_dur(out1[1]) - 4.0) < 1e-6 and out1[1]["kind"] == "seam", "")
chk("S5 接缝两侧取的是真实素材位置（前段末 / 后段首）",
    _calls and _calls[0] == (6.0, 0.0), str(_calls))

# 段太短：1.0 秒的段落让不出 2 秒
_calls.clear()
clips2 = [c("/v/a.mp4", 0.0, 1.0), c("/v/b.mp4", 0.0, 6.0)]
out2, info2 = transition.patch(clips2, workdir=TMP / "w2", model=M25)
chk("S5 前段太短 → 这一处不补，进 skipped（不压成闪帧）",
    info2["patched"] == 0 and any(s["why"] == "前段太短" for s in info2["skipped"]),
    str(info2))
chk("S5 没补就不动素材（片段原样保留）",
    len(out2) == 2 and abs(transition.clip_dur(out2[0]) - 1.0) < 1e-6, str(out2))

# 超上限
clips3 = [c(f"/v/{i}.mp4", 0.0, 6.0) for i in range(5)]
out3, info3 = transition.patch(clips3, workdir=TMP / "w3", model=M25, max_seams=2)
chk("S5 超上限的部分不静默吞掉（记账里写明）",
    info3["patched"] == 2 and info3["total"] == 4
    and any(s["why"] == "超过上限" for s in info3["skipped"]), str(info3))

# 生成失败不拖垮整片
def _boom(*a, **kw):
    raise RuntimeError("模拟平台失败")


# 第一处失败、第二处成功：整片不许因此崩，失败的退回硬接、成功的照补
_seq = {"n": 0}


def _fail_once(prev, prev_end, nxt, nxt_start, **kw):
    _seq["n"] += 1
    if _seq["n"] == 1:
        raise RuntimeError("模拟平台失败")
    return _fake_make(prev, prev_end, nxt, nxt_start, **kw)


transition.make_seam = _fail_once
out4, info4 = transition.patch(clips1, workdir=TMP / "w4", model=M25)
chk("S5 单处生成失败 → 该处保持硬接，其余照补（不整片失败）",
    info4["patched"] == 1 and len(out4) == 4, f"{info4['patched']}/{len(out4)}")
chk("S5 失败原因写进记账（不静默）",
    any("生成失败" in s["why"] for s in info4["skipped"]), str(info4["skipped"])[:160])
chk("S5 失败那一处不侵占素材（总时长仍不变）",
    abs(sum(transition.clip_dur(x) for x in out4) - tot_before) < 1e-6,
    str(sum(transition.clip_dur(x) for x in out4)))

transition.make_seam = _real_make

# ---------------------------------------------------------------------------
# S6 缓存键

fa, fb = _mk("fa.mp4", b"AAA"), _mk("fb.mp4", b"BBB")
pr = transition.seam_prompt()
k1 = transition._seam_key(fa, 5.0, fb, 0.0, pr, M25)
k2 = transition._seam_key(fa, 5.0, fb, 0.0, pr, M25)
chk("S6 同素材同参数 → 同键（重跑不重复扣费）", k1 == k2, f"{k1}/{k2}")
chk("S6 换提示词 → 换键",
    k1 != transition._seam_key(fa, 5.0, fb, 0.0, transition.seam_prompt("横移"), M25), "")
chk("S6 换取用位置 → 换键",
    k1 != transition._seam_key(fa, 4.0, fb, 0.0, pr, M25), "")
chk("S6 换型号 → 换键",
    k1 != transition._seam_key(fa, 5.0, fb, 0.0, pr, M20), "")

# ---------------------------------------------------------------------------
# S6b 真 ffmpeg：定长 + 成片里换接缝画面（不联网、不调模型）

import subprocess  # noqa: E402

from app.services.media import ffmpeg_path  # noqa: E402
from app.services.scene import probe  # noqa: E402

FF = ffmpeg_path()


def _synth(dest: Path, seconds: float, color: str) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        [FF, "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", f"color=c={color}:s=320x180:r=30:d={seconds}",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
         "-c:v", "libx264", "-crf", "28", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", str(dest)],
        capture_output=True, text=True, errors="ignore", timeout=120)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "")[-300:])
    return dest


if FF:
    short = _synth(TMP / "short.mp4", 3.0, "red")
    fitted = transition._fit_duration(short, TMP / "fitted.mp4", 4.0)
    have = float((probe(fitted) or {}).get("duration") or 0)
    chk("S6b 生成段比 4 秒短 → 冻帧补到正好 4 秒",
        abs(have - 4.0) < 0.12, f"{have:.3f}s")

    long_src = _synth(TMP / "long.mp4", 8.0, "blue")
    seam_clip = _synth(TMP / "seam4.mp4", 4.0, "green")
    dest = transition.replace_seam_in_file(
        long_src, seam_at=4.0, seam=seam_clip, dest=TMP / "patched.mp4")
    info = probe(dest) or {}
    chk("S6b 成片换接缝画面后总时长不变（音轨沿用）",
        abs(float(info.get("duration") or 0) - 8.0) < 0.15,
        f"{info.get('duration')}")
    chk("S6b 换完仍有音轨（不是把声音丢了）",
        bool(info.get("has_audio")), str(info.get("has_audio")))
    try:
        transition.replace_seam_in_file(long_src, seam_at=0.5,
                                        seam=seam_clip, dest=TMP / "bad.mp4")
        near_edge = False
    except ValueError:
        near_edge = True
    chk("S6b 接缝贴着片头 → 拒绝（会吃掉整段）", near_edge, "")
else:
    chk("S6b 找不到 ffmpeg，跳过合成验证", False, "ffmpeg_path() 为空")

# ---------------------------------------------------------------------------
# S7 边界

_calls.clear()
one, info_one = transition.patch([c("/v/a.mp4", 0.0, 6.0)], workdir=TMP / "w5")
chk("S7 只有一段 → 没有接缝，什么都不补（不报错）",
    len(one) == 1 and info_one["total"] == 0 and info_one["patched"] == 0, str(info_one))
chk("S7 空列表不炸", transition.patch([], workdir=TMP / "w6")[1]["total"] == 0, "")

# ---------------------------------------------------------------------------
# S8 接线

from app.api.clone import EditIn, ExtendIn  # noqa: E402

# 🩸 2026-10-25 主人拍板：**只留延长链路**。出片侧一个字段都不许留 ——
# 留了就是「配了没反应」，比没有更糟。
md = EditIn(**{"transition": True}).model_dump()
chk("S8 出片规格里没有 transition（配了没反应比没有更糟）",
    "transition" not in md and "transition_desc" not in md, str(list(md)))
chk("S8 规格默认值里也没有（编辑规格不认这个开关）",
    "transition" not in edit_spec.defaults(), str(list(edit_spec.defaults())))
chk("S8 normalize 也不会把它捡回来",
    "transition" not in edit_spec.normalize({"transition": True}), "")

chk("S8 ExtendIn 有 transition / transition_desc（延长那一个接缝）",
    ExtendIn(**{"content": "x", "transition": True}).model_dump().get("transition") is True, "")
chk("S8 ExtendIn 默认直接接（不补）",
    ExtendIn(**{"content": "x"}).model_dump().get("transition") is False, "")

cp_src = (ROOT / "app" / "services" / "clone_pipeline.py").read_text(
    encoding="utf-8", errors="ignore")
chk("S8 出片链路没有接（不许自己把原片剪辑点揉成过渡）",
    "_tr.patch(" not in cp_src and 'spec.get("transition")' not in cp_src, "")

ex_src = (ROOT / "app" / "services" / "extend.py").read_text(encoding="utf-8", errors="ignore")
chk("S8 延长链路接上了（make_seam + replace_seam_in_file）",
    "make_seam" in ex_src and "replace_seam_in_file" in ex_src, "")
chk("S8 延长没开开关时还是老的裁帧硬拼（stitch 原样保留）",
    "if with_transition:" in ex_src and "def stitch(" in ex_src, "")

diag = (FRONT / "pages" / "clone" / "diagnose.vue").read_text(
    encoding="utf-8", errors="ignore")
res = (FRONT / "pages" / "clone" / "result.vue").read_text(
    encoding="utf-8", errors="ignore")
chk("S8 出片页**没有**这个开关（用户不用理解什么叫接缝）",
    "接缝补过渡" not in diag and "onTransition" not in diag, "")
# 🩸 2026-10-28 主人拍板：**延长整个下架**（本项目只做复刻；延长出来的是
#   「接着往下编」，会让成片偏离原片）。这条反过来守：结果页不许再有延长入口。
#   后端 `extend.py` 与三家 `_extend_prompt` **保留不动** —— 那是「这家模型能
#   延长」的能力记录，不是产品界面。要恢复入口只需在前端加回卡片。
chk("S8 结果页**没有**延长入口（2026-10-28 延长下架）",
    "延长这条片子" not in res and "startExtend" not in res, "")

# ---------------------------------------------------------------------------
bad = [r for r in rows if not r[1]]
for name, ok, detail in rows:
    print(("  ok   " if ok else "  FAIL ") + name
          + (f"  [{detail[:220]}]" if not ok else ""))
print(f"\n{len(rows) - len(bad)}/{len(rows)} 通过（零模型调用）")
sys.exit(1 if bad else 0)
