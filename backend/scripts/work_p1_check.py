"""P1 零成本验收：词级投影 + 口型判定 + 改动局部性。

跑法：
    python scripts/work_p1_check.py [--timeline <cid>] [--plan <cid>]

验的是四件事（全部本地计算，且脚本会把所有付费调用替换成"一调就报错"）：
  1. 原文投影：每个字都继承原时间，投影窗口覆盖原片首字到末字；
  2. 改一句：只有那一句标记 changed，其他句子的窗口一个字都不动；
  3. 口型：没说话的镜头 lip=False，说话的镜头 lip=True；
  4. plan：同输入 → 复用；改词 → 只有那段变成请求，理由写清"台词变了"。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import (ark, clone_store, edit_spec, generate,  # noqa: E402
                          minimax, timeline, video_edit, work)

PASS = FAIL = 0


def check(name: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}: {got}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want={want!r}")


def pick(prefix: str) -> str:
    from app.core.config import settings

    hits = list(Path(settings.clone_dir).glob(prefix + "*"))
    if not hits:
        raise SystemExit(f"找不到任务：{prefix}")
    return hits[0].name


def _same(a: dict, b: dict) -> bool:
    return abs(float(a["start"]) - float(b["start"])) < 1e-6 \
        and abs(float(a["end"]) - float(b["end"])) < 1e-6


def _segment_to_edit(base: list[dict]) -> int:
    """挑一个不太短、不太长的句子来改 —— 太短改不动，太长会触发重新断行。"""
    for n, s in enumerate(base):
        if 4 <= len(s["text"]) <= 9:
            return n
    return len(base) // 2


def _swap_two(text: str) -> str:
    for i in range(len(text) - 1):
        if text[i] != text[i + 1]:
            return text[:i] + text[i + 1] + text[i] + text[i + 2:]
    return text


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：一次只跑一家。
    from _model_gate import sel_or_exit
    sel_or_exit()

    ap = argparse.ArgumentParser()
    ap.add_argument("--timeline", default="f01a92f7", help="用哪个任务验词级投影")
    ap.add_argument("--plan", default="89c228cc", help="用哪个任务验 plan 联动")
    args = ap.parse_args()

    # 🛑 付费调用一律变成异常：这套验收必须证明"一分钱没花"
    def boom(*a, **kw):
        raise AssertionError("付费接口被调用了！P1 验收必须零费用")

    paid = (ark.edit_video, minimax.reference_video,
            video_edit.replace_spans)
    ark.edit_video = minimax.reference_video = boom
    video_edit.replace_spans = boom
    try:
        return _run(pick(args.timeline), pick(args.plan))
    finally:
        (ark.edit_video, minimax.reference_video,
         video_edit.replace_spans) = paid


def _run(cid_t: str, cid_p: str) -> int:
    w = work.build(cid_t)
    src_text = timeline.source_text(w)
    base = timeline.project(w, src_text)
    print(f"== 词级投影 {cid_t[:8]}：{len(base['segments'])} 句 / "
          f"{len((w['evidence']['speech'] or {}).get('segments') or [])} 个语音段 ==")

    check("原文投影没有任何改动标记", base["changed_segments"], [])
    starts = [s["start"] for s in base["segments"]]
    check("句子按时间先后排列", starts == sorted(starts), True)
    chars = timeline.source_chars(w)
    first_ch = min(c["s"] for c in chars)
    last_ch = max(c["e"] for c in chars)
    check("首句起点 = 原片第一个字", abs(base["segments"][0]["start"] - first_ch) < 0.01, True)
    check("末句终点 = 原片最后一个字", abs(base["segments"][-1]["end"] - last_ch) < 0.01, True)

    # ---- 改动局部性 ----
    k = _segment_to_edit(base["segments"])
    seg = base["segments"][k]
    pos = src_text.find(seg["text"])
    print(f"  改第 {k} 句（{seg['start']:.2f}-{seg['end']:.2f}s，{len(seg['text'])} 字）")

    swapped = _swap_two(seg["text"])
    edited = src_text[:pos] + swapped + src_text[pos + len(seg["text"]):]
    p2 = timeline.project(w, edited)
    check("换两个字：只标记这一句", p2["changed_segments"], [k])
    check("换两个字：句子数不变", len(p2["segments"]), len(base["segments"]))
    others_same = all(_same(a, b) for j, (a, b) in enumerate(zip(base["segments"], p2["segments"]))
                      if j != k and j < len(p2["segments"]))
    check("换两个字：其他句子窗口不动", others_same, True)

    # 加两个字：句子会重新断行，所以逐句比窗口没有意义；
    # 真正要守的性质是**没改的字，时间一个字都不动**（锚定保持）。
    longer = seg["text"][:2] + "增加" + seg["text"][2:]
    edited2 = src_text[:pos] + longer + src_text[pos + len(seg["text"]):]
    base_t = timeline.align_times(w, src_text)
    new_t = timeline.align_times(w, edited2)
    p = len(timeline._norm(src_text[:pos]))          # 归一化后，这一句的起点
    shift = len(timeline._norm("增加"))
    ins = p + 2                                      # 这一句前两个字原样保留，插在第 3 位
    check("插入位置对得上", new_t[ins]["c"], "增")
    head_same = all(abs(base_t[i]["s"] - new_t[i]["s"]) < 1e-6
                    and abs(base_t[i]["e"] - new_t[i]["e"]) < 1e-6
                    for i in range(ins))
    tail_same = all(abs(base_t[i]["s"] - new_t[i + shift]["s"]) < 1e-6
                    and abs(base_t[i]["e"] - new_t[i + shift]["e"]) < 1e-6
                    for i in range(ins, len(base_t)))
    check("加字前：前面的字时间不动", head_same, True)
    check("加字后：后面的字时间不动（锚定保持）", tail_same, True)

    # ---- 口型 ----
    inv = work._load_inventory(cid_t)
    shots = w["evidence"]["shots"]
    lips = [timeline.lip_dependent(w, [s["start"], s["end"]], inv) for s in shots]
    print(f"  镜头口型标记：{lips[:10]}")
    check("有不跟嘴型的镜头", False in lips, True)
    check("有跟嘴型的镜头", True in lips, True)
    first_lip_false = next((s for s, v in zip(shots, lips) if not v), None)
    if first_lip_false and k > 3:
        before = timeline.text_for_span(w, src_text, [first_lip_false["start"], first_lip_false["end"]])
        after = timeline.text_for_span(w, edited, [first_lip_false["start"], first_lip_false["end"]])
        check("改后段的词，不影响前段的台词", before == after, True)

    # ---- plan 联动 ----
    wp = work.build(cid_p)
    text_p = timeline.source_text(wp)
    spec = edit_spec.normalize({"change": {"person": True}, "audio": "tts",
                                "resolution": "480p"})
    intent = {"mode": "whole", "channel": "volc",
              "model": "doubao-seedance-2-0-mini-260615",
              "edit": spec, "script": text_p}
    units = work._desired_units(cid_p, wp, intent)
    check("整片只有一个单元", len(units), 1)
    u = units[0]
    inv_p = work._load_inventory(cid_p)
    lip = timeline.lip_dependent(wp, u["span"], inv_p)
    words = timeline.text_for_span(wp, text_p, u["span"])
    refs = work._ref_files(cid_p, spec["change"])
    sha = work.sha256_file(clone_store.source_path(cid_p))
    key = work._unit_key(intent, spec, u, sha, refs, lip, words)
    fake = {"id": "fake:seg_001", "render": "fake", "mode": "whole",
            "engine": u["engine"], "span": u["span"], "lip": lip,
            "sig": work._sig(key), "key": key, "output": "", "sha256": "",
            "stale_refs": []}
    w2 = json.loads(json.dumps(wp))
    w2["assets"] = [fake]

    p_same = work.plan(cid_p, w2, intent)
    check("同台词 → 全部复用", p_same["totals"]["request_units"], 0)

    one_word = text_p[:-1] + ("X" if text_p[-1:] != "X" else "Y")
    p_word = work.plan(cid_p, w2, {**intent, "script": one_word})
    check("改词 → 这一段要重新生成", p_word["totals"]["request_units"], 1)
    check("理由写明是台词变了", "台词变了" in (p_word["requests"][0]["why"]), True)

    print(f"\n{PASS}/{PASS + FAIL} 通过（零费用，未调用任何模型接口）")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
