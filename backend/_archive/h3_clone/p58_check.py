# -*- coding: utf-8 -*-
"""「先出第 1 段，确认后再出全部」的**效果**判据（零费用，真跑整条链路）。

和 `p57_check.py` 的分工：
  · p57 = 结构/接线（参数五层透传、不拼接、continue 重建）——只看代码形状；
  · p58 = 效果（真的按段跑一遍，数"调了几次模型"）——代码形状对、行为不对也能抓。

零费用的全部理由（逐条都堵死，缺一条就会真花钱）：
  · `minimax.reference_video` 换成桩：把送进去的参考片当模型输出复制过去；
  · `video_edit._shot_looks` 返回 []：不调视觉模型；
  · `vision_plan.inventory` 固定返回源任务**已有的**盘点缓存：不重跑视觉
    （2026-11-01 实测：不堵这条，`_ensure_shot_source` 会拿新 cid 当"没看过
    这条片子"，真调一次 doubao-seed-2-1-lite，30 秒）；
  · agent 逐段指令读源任务的落盘缓存：不重跑 DeepSeek；
  · 缓存/产物全部落在临时 cid 下：**不动生产任务**。

验四件事（都是数出来的，不是"文件里有没有这句话"）：
  1. 全新任务 + max_segments=1 → 只调 1 次模型，返回 1 个片段；
  2. 同任务再跑 max_segments=0 → 第 1 段命中缓存，只调 (段数-1) 次；
  3. 只跑部分时 `replace_whole` 返回 partial=True 且**不产出 whole.mp4**；
  4. 改了提示词指纹 → 第 1 段缓存失效，必须重新调用。

🩸 第 2 条**必须重新跑 `_auto_decision`**：`clone_pipeline.render()` 每次出片
   都重算它，"继续出全部"也是一次新的出片。复用上一次的 plan 去测，
   测的是"同一个内存对象"，不是生产路径。

源任务不在（换机器/被清理）→ 打印闸话术后退 2，由 `check_all` 记作跳过，
不冒充通过。

跑法：python scripts/p58_check.py
"""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import (  # noqa: E402
    clone_pipeline as P, clone_store as store, edit_spec, h3_agent,
    minimax, video_edit, vision_plan,
)

#: 源任务：一条 18 秒、2 段、盘点认得 1 个人的真实任务（不参与生成）。
#: 缓存和产物一律落到 TEST_CID 下，这个任务本身只被**读**。
SRC = "949c0b2fb0074d59905b34574680a36f"
TEST_CID = "p58mocksession000000000000000000"
WORK = Path("D:/tmp/p58_work")
TASKS = Path("D:/tmp/p58_tasks")

CALLS: list[str] = []
#: 每次提交实际送进去的 `ref_audio`（None = 这一条请求里没有音频）。
#: 🩸 2026-11-01：`_master_audio` 的旧判定让 H3 走「音频挂在母版视频里」那条路，
#:   而 H3 官方 `ref-en:112` 明说参考视频有声音 ≠ 有 `<Audio N>` 参考 ⇒
#:   请求里一条音频都没有，提示词却写着 `<Audio 1>` 是口型参考 ⇒ 嘴型必错。
#:   这条按「真的送了什么」判，不按「代码里写了什么」判。
AUDIO: list = []
PASS = FAIL = 0


def check(name: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want={want!r}")


def fake_reference_video(video, *, prompt, out, **kw):
    """模型桩：把送进来的参考片原样当成"生成结果"。零成本、可数次数。"""
    CALLS.append(Path(out).name)
    AUDIO.append(kw.get("ref_audio"))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(video, out)
    return Path(out)


def main() -> int:
    # 🩸 任务只能读一次：下面会把 `store.task_dir` 切到临时目录，切完再 load
    #   就指向临时 cid，读回来是 None。
    task = store.load(SRC)
    if not task:
        print("本脚本只验有真实任务数据的环境（源任务不在：换机器或被清理）")
        return 2

    _subject = store.subject_path(SRC)
    _refs = {s: store.ref_path(SRC, s) for s in store.REF_SLOTS
             if store.ref_path(SRC, s).exists()}
    _video = store.source_path(SRC)
    # 🩸 盘点必须在切 task_dir **之前**读出来：`vision_plan.inventory` 靠
    #   `clone_store.task_dir(cid)` 找缓存文件，切完就读不到 → 返回空盘点 →
    #   `_span_plan` 直接返回 {} → 整条测试在"没有人要换"的空集上跑绿。
    _inv = P._inventory_or_none(SRC)
    if not (_inv or {}).get("people"):
        print("本脚本只验有可用视觉盘点的环境（源任务盘点是空的，测不了换人路径）")
        return 2

    minimax.reference_video = fake_reference_video
    video_edit._shot_looks = lambda cid, rec: []
    vision_plan.inventory = lambda cid, video=None, **kw: _inv
    TASKS.mkdir(parents=True, exist_ok=True)
    store.task_dir = lambda cid: (TASKS / cid)
    _orig_cached = h3_agent.cached
    h3_agent.cached = lambda cid, plan, rec, spans: _orig_cached(SRC, plan, rec, spans)

    rec = task["recipe"]
    r = task["renders"][-1]
    spec = edit_spec.normalize(r["edit"])
    subject = _subject
    refs = _refs
    video = _video

    def mkplan():
        """生产同款：`clone_pipeline.render()` 每次出片都重算这一份。"""
        return P._auto_decision(
            video, dict(rec), spec=spec,
            regen_prompt=r.get("regen_prompt") or "",
            regen_shots=r.get("regen_shots") or None,
            regen_channel="minimax", regen_model="MiniMax-H3-Lite",
            subject_image=subject if subject.exists() else None,
            subject_asset=r.get("subject_asset") or "", refs=refs,
            inventory=_inv,
            style_video=P._style_video_of(SRC, spec))

    d1 = mkplan()
    plan, spans = d1["plan"], d1["spans"]
    print(f"段数 = {len(spans)}  盘点 "
          f"{len((plan.get('inventory') or {}).get('people') or [])} 人 / "
          f"{len((plan.get('inventory') or {}).get('shots') or [])} 镜   "
          f"phash = {plan.get('phash')}")
    if len(spans) < 2:
        print("本脚本只验多段任务（这条源片只有 1 段，验不了「先出一段」）")
        return 2

    shutil.rmtree(WORK, ignore_errors=True)
    shutil.rmtree(TASKS / TEST_CID, ignore_errors=True)
    work = WORK / "triage"

    print("\n== ① 全新任务 + 只出前 1 段 ==")
    CALLS.clear()
    t0 = time.time()
    clips = video_edit.replace_spans(
        video, dict(rec), spans, cid=TEST_CID, plan=plan, spec=spec, refs=refs,
        prompt=r.get("regen_prompt") or "", inventory=_inv,
        workdir=work, max_segments=1)
    check("只调 1 次模型", len(CALLS), 1)
    check("只返回 1 个片段", len(clips), 1)
    check("片段文件真的存在", Path(clips[0]).exists(), True)
    # 🩸 原声模式必须**单独**把音频当 reference_audio 送进去。参考视频里就算带
    #   音轨也不算音频参考（H3 官方 `ref-en:112`）—— 只靠母版 = 模型没东西可跟。
    if video_edit._audio_track(spec, video, work) is not None:
        check("**原声模式的音频真的送进了模型**（不是只挂在母版视频里）",
              bool(AUDIO and AUDIO[-1] is not None), True)
    else:
        print("  ··  源片没有可提取的音轨，音频那条判据跳过（不算通过）")
    print(f"  用时 {time.time() - t0:.1f}s  提交 = {CALLS}")

    print("\n== ② 同任务继续出全部（第 1 段应命中缓存）==")
    d2 = mkplan()
    plan2, spans2 = d2["plan"], d2["spans"]
    check("**生产重算的 plan 指纹与上一次相同**（否则缓存天然对不上）",
          plan2.get("phash"), plan.get("phash"))
    check("重算的段数相同", spans2, spans)
    CALLS.clear()
    t0 = time.time()
    clips2 = video_edit.replace_spans(
        video, dict(rec), spans, cid=TEST_CID, plan=plan2, spec=spec, refs=refs,
        prompt=r.get("regen_prompt") or "", inventory=_inv,
        workdir=work, max_segments=0)
    check("返回全部段", len(clips2), len(spans))
    check("**第 1 段没重复调模型**（调用数 = 段数-1）", len(CALLS), len(spans) - 1)
    print(f"  用时 {time.time() - t0:.1f}s  实际提交 = {CALLS}")

    print("\n== ③ 只跑部分时绝不拼接 ==")
    whole = WORK / "whole"
    shutil.rmtree(whole, ignore_errors=True)
    CALLS.clear()
    r2 = video_edit.replace_whole(
        video, dict(rec), cid=TEST_CID, spec=spec, refs=refs,
        subject_image=subject if subject.exists() else None,
        channel="minimax", model="MiniMax-H3-Lite",
        inventory=_inv, workdir=WORK, max_segments=1)
    check("返回 partial=True", r2.get("partial"), True)
    check("给了 preview 片段", bool(r2.get("preview")), True)
    check("**没有产出 whole.mp4**（缺段不拼）", (whole / "whole.mp4").exists(), False)

    print("\n== ④ 改提示词 → 第 1 段缓存必须失效 ==")
    plan3 = dict(plan2)
    CALLS.clear()
    plan3["phash"] = (plan2.get("phash") or "") + "-changed"
    video_edit.replace_spans(
        video, dict(rec), spans[:1], cid=TEST_CID, plan=plan3, spec=spec,
        refs=refs, prompt=r.get("regen_prompt") or "", inventory=_inv,
        workdir=WORK / "changed", max_segments=1)
    check("改了指纹就重新调模型（不拿旧结果糊弄）", len(CALLS), 1)

    print(f"\n{PASS}/{PASS + FAIL} 通过   全程花费 = ¥0（模型/视觉/agent 全是桩或读缓存）")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
