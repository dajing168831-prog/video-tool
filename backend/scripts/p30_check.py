# -*- coding: utf-8 -*-
"""复刻「逐段编辑指令」判据 —— 零费用，不调模型、不出片。

验四件事：
  1. 规格书（`clone_brief`）把原片事实摊对了（段数 / 图号 / 人 / 台词）；
  2. 硬闸（`clone_agent.check`）**有鉴别力**：每条规则都有一对「好样本放行、
     坏样本必红」的探针（`verify-ruler-before-subject`：先拿已知坏样本试尺子）；
  3. 输入签名稳定，输入一变就变；
  4. agent 交付 → 落盘 → 再跑命中缓存；agent 不给东西时**抛错**（调用方回落）。

用法： python scripts/p30_check.py --model volc25
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

BACK = Path(__file__).resolve().parents[1]
if str(BACK) not in sys.path:
    sys.path.insert(0, str(BACK))
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from _model_gate import sel_or_exit  # noqa: E402

sel_or_exit(only="volc25")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import clone_agent as A  # noqa: E402
from app.services import clone_brief as B  # noqa: E402

_n = _fail = 0


def check(name: str, got, want) -> None:
    global _n, _fail
    _n += 1
    ok = got == want
    if not ok:
        _fail += 1
    print(f"{'✅' if ok else '🔴'} {name}"
          + ("" if ok else f"\n     实际 {got!r} / 期望 {want!r}"))


# ---------------------------------------------------------------- fixture

REC = {
    "source": {"duration": 20.0, "width": 1080, "height": 1920, "fps": 30.0},
    "shots": [
        {"i": 0, "start": 0.0, "end": 8.0},
        {"i": 1, "start": 8.0, "end": 14.0},
        {"i": 2, "start": 14.0, "end": 20.0},
    ],
    # 🩸 台词只认 **ASR（`speech.segments`）** —— 那是配方里就有的那一份。
    #   出片时 `render` 会临时往 rec 里塞 `voice_lines` 并写 `speaker`，
    #   规格书若读它，预览和出片就会算出两个签名（2026-10-31 真跑踩过）。
    "voice_lines": [],
    "speech": {"lang": "zh", "segments": [
        {"start": 1.0, "end": 3.0, "text": "第一句台词"},
        {"start": 15.0, "end": 17.0, "text": "第二句台词"},
    ]},
}

INV = {
    "people": [
        {"id": "P1", "main": True, "desc_zh": "画面中央的男性，黑色短发，深色外套",
         "desc_en": "a man in the center, short black hair, dark jacket",
         "appearances": [{"start": 0.0, "end": 20.0}]},
    ],
    "_meta": {},
}

SPEC = {
    "change": {"person": True, "person_ids": ["P1"]},
    "audio": "tts",
    "resolution": "auto",
}

PLAN = {
    "ch": "volc",
    "model": "doubao-seedance-2-5-260628",
    "spec": SPEC,
    "inventory": INV,
    "slots": ["person"],
    "ordered": ["asset://p1"],
    "audio_ref": True,
    "person_ids": ["P1"],
    "person_asset": "asset://p1",
    "look": {},
}

SPANS = [(0.0, 10.0), (10.0, 20.0)]

#: 合格样本 = **照官方模板骨架填槽位**（`SKILL.md:544`），不是自己编的句式。
GOOD = """【编辑目标】编辑@视频1，只把画面中央的男性修改为@图片1中的人物。
【原视频职责】@视频1是唯一编辑母版，负责原始场景、机位、镜头运动、动作轨迹、遮挡关系和事件顺序。
【目标素材职责】@图片1用于新人物的外观，不采用图片中的背景与构图。
【编辑对象与范围】只修改画面中央的男性。不修改背景、道具与其他人物。除以上明确修改对象外，@视频1中其他可见人物、道具和背景元素保持原样，不参与替换或删除。
【时间线继承】目标人物继承原人物每次出现、运动、遮挡和离开的时点、持续时长、路径与速度变化。替换后的人物按@音频1的音色与台词说话，口型时点与它对齐。其他人物动作、镜头运动、镜头切换和事件顺序保持@视频1。"""


def main() -> int:
    print("== ① 规格书：事实摊对了 ==")
    brief = B.build(PLAN, REC, SPANS)
    check("段数 = 传进来的区间数", len(brief["segments"]), 2)
    check("段号从 1 起、与区间对齐",
          [(s["index"], s["start"], s["end"]) for s in brief["segments"]],
          [(1, 0.0, 10.0), (2, 10.0, 20.0)])
    check("第 1 段切点 = 8.0（原片镜头边界，相对段起点）",
          brief["segments"][0]["cuts"], [8.0])
    check("第 2 段切点 = 14.0（相对段起点 10.0）",
          brief["segments"][1]["cuts"], [4.0])
    check("参考图编号从 1 起、槽位对得上",
          [(r["pic"], r["slot"]) for r in brief["refs"] if r["slot"] != "audio"],
          [(0, "source"), (1, "person")])
    check("这一段带音轨 → 规格书列了 @音频1（否则 agent 会漏掉口型）",
          [(r["pic"], r["slot"]) for r in brief["refs"] if r["slot"] == "audio"],
          [(0, "audio")])
    check("第 1 段点名了 P1", brief["segments"][0]["targets"], ["P1"])
    check("第 1 段出现的人带外观描述",
          brief["segments"][0]["people"][0]["desc"], "画面中央的男性，黑色短发，深色外套")
    check("台词按时间落到对应段：第 1 段 1 句、第 2 段 1 句",
          [len(s["lines"]) for s in brief["segments"]], [1, 1])
    text = B.as_text(brief)
    check("给模型看的正文含原片时长", "20 秒" in text, True)
    check("给模型看的正文含 @图片1 的用途", "@图片1" in text, True)
    check("给模型看的正文含两段标题",
          [n for n in (1, 2) if f"### 第 {n} 段" in text], [1, 2])

    print("\n== ② 硬闸：好样本放行 ==")
    ok = [{"index": 1, "prompt": GOOD}, {"index": 2, "prompt": GOOD}]
    check("合格样本 0 红", A.check(brief, ok), [])

    print("\n== ② 硬闸：坏样本必红（成对探针）==")
    def red_of(segs):
        return A.check(brief, segs)

    check("少一段 → 报段数不对",
          any("段数对不上" in r for r in red_of(ok[:1])), True)
    check("段号错位（1 和 3）→ 报段数不对",
          any("段数对不上" in r for r in red_of(
              [{"index": 1, "prompt": GOOD}, {"index": 3, "prompt": GOOD}])), True)
    no_mark = GOOD.replace("【时间线继承】", "时间线：")
    check("缺【时间线继承】→ 红",
          any("缺段标记" in r and "时间线继承" in r for r in red_of(
              [{"index": 1, "prompt": no_mark}, {"index": 2, "prompt": GOOD}])), True)
    no_vid = GOOD.replace("@视频1", "原视频")
    check("不把原片当母版（无 @视频1）→ 红",
          any("唯一编辑母版" in r for r in red_of(
              [{"index": 1, "prompt": no_vid}, {"index": 2, "prompt": GOOD}])), True)
    ph = GOOD.replace("画面中央的男性", "<原对象>", 1)
    check("残留 <占位符> → 红",
          any("占位符" in r for r in red_of(
              [{"index": 1, "prompt": ph}, {"index": 2, "prompt": GOOD}])), True)
    badpic = GOOD.replace("@图片1", "@图片9", 1)
    check("引用不存在的图号 → 红",
          any("不存在的图号" in r for r in red_of(
              [{"index": 1, "prompt": badpic}, {"index": 2, "prompt": GOOD}])), True)
    check("空的一段 → 红",
          any("第 2 段是空的" in r for r in red_of(
              [{"index": 1, "prompt": GOOD}, {"index": 2, "prompt": "  "}])), True)

    # 🩸 口型那条的成对探针（2026-10-31 真跑翻过：实际成片口型对不上）
    brief_audio = dict(brief, refs=list(brief["refs"]) + [
        {"pic": 0, "slot": "audio", "role": "原片人声，@音频1"}])
    no_audio_ref = GOOD.replace(
        "替换后的人物按@音频1的音色与台词说话，口型时点与它对齐。", "")
    check("规格书带音频、提示词没提 @音频1 → 红",
          [r for r in A.check(brief_audio, [
              {"index": 1, "prompt": no_audio_ref},
              {"index": 2, "prompt": no_audio_ref}]) if "@音频1" in r] != [], True)
    check("写了 @音频1 的口型对齐 → 放行",
          A.check(brief_audio, [{"index": 1, "prompt": GOOD},
                                {"index": 2, "prompt": GOOD}]), [])

    print("\n== ③ 签名：输入不变就稳，输入一变就变 ==")
    s1 = A.signature(brief)
    s2 = A.signature(B.build(PLAN, REC, SPANS))
    check("同输入两次签名相同", s1, s2)
    plan2 = dict(PLAN, ordered=["asset://p2"])
    check("换参考图 → 签名变", A.signature(B.build(plan2, REC, SPANS)) != s1, True)
    plan3 = dict(PLAN, model="MiniMax-H3")
    check("换型号 → 签名变", A.signature(B.build(plan3, REC, SPANS)) != s1, True)

    # 🩸 2026-10-31 真跑翻车：出片时 `render` 会往 rec 里塞 `voice_lines`
    #   并写 `speaker`，预览/生成时没有 —— 两边签名不同，**agent 版被静默丢掉**，
    #   发出去的还是机器拼的提示词。判据：同一件事必须由同一份输入算出同一个签名。
    rec_render = dict(REC, voice_lines=[
        {"start": 1.0, "end": 3.0, "text": "第一句台词", "speaker": "P1"},
        {"start": 15.0, "end": 17.0, "text": "第二句台词", "speaker": "P1"},
    ])
    check("出片时 rec 多出 voice_lines/speaker → 签名不变",
          A.signature(B.build(PLAN, rec_render, SPANS)), s1)

    print("\n== ④ agent 交付 → 落盘 → 命中缓存 ==")
    from app.services import clone_store as store

    tmp = Path(tempfile.mkdtemp(prefix="p30_", dir="D:/tmp"))
    old_dir = store.task_dir
    store.task_dir = lambda cid: (tmp / cid)  # noqa: ARG005
    calls = {"n": 0}

    def stub(msgs):
        calls["n"] += 1
        segs = [{"index": 1, "prompt": GOOD}, {"index": 2, "prompt": GOOD}]
        return {"choices": [{"message": {"role": "assistant", "content": None,
                                         "tool_calls": [{
                                             "id": "c1", "type": "function",
                                             "function": {
                                                 "name": "deliver_segments",
                                                 "arguments": json.dumps(
                                                     {"segments": segs},
                                                     ensure_ascii=False)}}]}}],
                "usage": {"total_tokens": 10}}

    try:
        d1 = A.generate("t1", PLAN, REC, SPANS, post=stub)
        check("agent 交付 2 段", len(d1["segments"]), 2)
        check("落盘文件存在", (tmp / "t1" / A.FILENAME).is_file(), True)
        check("第一次调用 = 1 次", calls["n"], 1)
        d2 = A.generate("t1", PLAN, REC, SPANS, post=stub)
        check("同输入再跑 → 命中缓存，不再调模型", (calls["n"], d2["sig"]), (1, d1["sig"]))
        A.generate("t1", PLAN, REC, SPANS, post=stub, force=True)
        check("force=True → 重新调模型", calls["n"], 2)

        # 模型交不合格的东西：回灌一次仍不合格 → 抛错（调用方回落）
        def bad_stub(msgs):
            segs = [{"index": 1, "prompt": "随便写一句"}, {"index": 2, "prompt": "随便写一句"}]
            return {"choices": [{"message": {"role": "assistant", "content": None,
                                             "tool_calls": [{
                                                 "id": "c1", "type": "function",
                                                 "function": {
                                                     "name": "deliver_segments",
                                                     "arguments": json.dumps(
                                                         {"segments": segs},
                                                         ensure_ascii=False)}}]}}],
                    "usage": {"total_tokens": 10}}

        try:
            A.generate("t2", PLAN, REC, SPANS, post=bad_stub)
            got = "没拦住"
        except A.CloneAgentError as e:
            got = str(e)
        check("交付不合格 → 抛 CloneAgentError（调用方回落）",
              isinstance(got, str) and got != "没拦住", True)

        # 模型什么都不交
        def empty_stub(msgs):
            return {"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": []}}],
                    "usage": {"total_tokens": 1}}

        try:
            A.generate("t3", PLAN, REC, SPANS, post=empty_stub)
            got2 = "没拦住"
        except Exception as e:  # noqa: BLE001
            got2 = type(e).__name__
        check("模型不交东西 → 抛错", got2 in ("CloneAgentError", "AgentError"), True)
    finally:
        store.task_dir = old_dir
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{_n - _fail}/{_n} 通过")
    return 1 if _fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
