# -*- coding: utf-8 -*-
"""H3 **手写入口**换人提示词的尺子（零费用：不调模型、不出片）。

## 为什么换尺子（2026-11-03）

旧尺子 `ruler_h3.py` 判的是 **Ref2VA 六段式**（`subject_definitions` …）。
官方换人样例 **6 条全在手册**（`h3-manual:207-213` / `:185-192`），全是自然语言；
六段式里**一条换人样例都没有**。体裁已经换成手写入口（`h3_handwrite.py`），
旧尺子判新产出必然全红 —— 那不是产出坏了，是尺子量错了体裁。

## 每条判据的官方出处

| 编号 | 判据 | 出处 |
|---|---|---|
| H1 | 必须有【参考素材说明】段 | `h3-manual:244`「完整提示词 = 参考素材说明 + 核心创意 + 画面过程说明」 |
| H2 | 每个 `@图片N` 都写了用途 | `h3-manual:248`「告诉 H3 你上传的每个素材是干什么用的…写清每个素材的用途」 |
| H3 | 用途必须是官方那几类词 | `h3-manual:248` 素材用途表 |
| H4 | 换人必须点名「谁换成谁」 | `h3-manual:213`「视频1中最后面的小孩换成 图1中的金毛狗」 |
| H5 | 不许串别家的句子 | 主人 2026-11-03「不是他的就不要串啊」＋ `MODEL-SEPARATION.md` |
| H6 | ≤7000 字符 | `h3-manual:41`「提示词上限 ≤7000 字符」 |

运行：
  python scripts/ruler_h3_handwrite.py --probes      # 每条规则一对正反样本
  python scripts/ruler_h3_handwrite.py --calib       # 当前产出必须全绿
  python scripts/ruler_h3_handwrite.py --current
  python scripts/ruler_h3_handwrite.py --sweep
  python scripts/ruler_h3_handwrite.py --exhaustive  # 单变量消融：每个开关都要有落点
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

BACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACK))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

H3_MODEL = "MiniMax-H3"

#: 官方 `h3-manual:248` 素材用途表的词（逐字）。用途句里必须命中其中之一。
OFFICIAL_USES = ("人物参考", "物体参考", "场景参考", "关键帧", "音色参考",
                 "故事版", "风格参考", "构图参考", "音频复用", "音频部分复用",
                 "动作参考", "运镜参考", "视频编辑")

#: 🩸 别家的句子。H3 手册里一条都没有，串进来就是 `no-stacking-rules` 说的自造。
FOREIGN = (
    "唯一编辑母版",              # 2.5 编辑模板
    "其他人物、道具和背景保持原样",  # 2.5 编辑模板
    "【编辑目标】", "【原视频职责】", "【时间线继承】",   # 2.5 模板段名
    "subject_definitions", "retention_analysis",       # 六段式（H3 另一体裁）
    "fully_preserved", "attribute_transfer",
)

RULES = [
    ("H1", "有【参考素材说明】段", "h3-manual:244"),
    ("H2", "每个 @图片N 都有用途句", "h3-manual:248"),
    ("H3", "素材用途用官方那几类词", "h3-manual:248"),
    ("H4", "换人点名「谁换成谁」", "h3-manual:213"),
    ("H5", "没串别家/别体裁的句子", "主人 2026-11-03"),
    ("H6", "≤7000 字符", "h3-manual:41"),
]

_PIC = re.compile(r"@图片(\d+)")


def check(text: str, chg: dict | None = None) -> list[tuple[str, str]]:
    """跑全部规则，返回 [(编号, 原因)]。空列表 = 全绿。"""
    bad: list[tuple[str, str]] = []
    chg = chg or {}
    text = text or ""

    # H1 结构
    if "【参考素材说明】" not in text:
        bad.append(("H1", "缺【参考素材说明】段（h3-manual:244 公式的第一项）"))

    # H2 每张图都有用途
    head = text.split("【", 2)
    duty = text[:text.find("\n\n")] if "\n\n" in text else text
    for n in sorted({m for m in _PIC.findall(text)}, key=int):
        if f"@图片{n}" not in duty:
            bad.append(("H2", f"@图片{n} 没有用途句（h3-manual:248 要求每个素材写清用途）"))

    # H3 用途词
    for line in duty.splitlines():
        m = _PIC.search(line)
        if m and not any(u in line for u in OFFICIAL_USES):
            bad.append(("H3", f"@图片{m.group(1)} 的用途不在官方词表里：{line.strip()[:40]}"))

    # H4 换人点名
    if chg.get("person") or chg.get("person_ids"):
        if not re.search(r"换成@图片\d+中的人物", text):
            bad.append(("H4", "勾了换人，但正文没有「…换成@图片N中的人物」（h3-manual:213）"))

    # H5 串味
    for w in FOREIGN:
        if w in text:
            bad.append(("H5", f"串了别家/别体裁的句子：{w}"))

    # H6 字数
    if len(text) > 7000:
        bad.append(("H6", f"{len(text)} 字符，超过官方上限 7000（h3-manual:41）"))

    return bad


# --------------------------------------------------------------------------- 造样本

def _people(n: int, pos: str = "unique") -> list[dict]:
    """造 n 个人。`pos="unique"` 时方位各不相同；`"dup"` 时全都 left（测指代退路）。"""
    spots = ["left", "right", "center"][:n] if pos == "unique" else ["left"] * n
    return [{"id": f"P{i + 1}", "position": spots[i],
             "desc_zh": f"黑色短发、身穿深色上衣的第{i + 1}人",
             "desc_en": f"the person number {i + 1}",
             "appearances": [{"start": 0.0, "end": 10.0}], "present": True}
            for i in range(n)]


def _mk(name, chg, *, n=1, pos="unique", picks=(0,), slots_extra=(),
        audio_ref=False, frame_all=True):
    """编一条，连上下文一起打包。编译抛错 = 生产闸的正确行为，记「闸拦」。"""
    from app.services import edit_spec

    frame = _people(n, pos)
    picked = [dict(frame[i]) for i in picks]
    slots = ["person" if k == 0 else f"person{k + 1}" for k in range(len(picks))]
    slots += list(slots_extra)
    spec = edit_spec.normalize(chg)
    try:
        text = edit_spec.compile_prompt(
            "minimax", spec, model=H3_MODEL,
            source_people=picked,
            frame_people=frame if frame_all else picked,
            desc_by_id={p["id"]: {"zh": p["desc_zh"], "en": p["desc_en"]}
                        for p in frame},
            slots=slots, audio_ref=audio_ref)
    except Exception as e:  # noqa: BLE001
        return (name, None, f"{type(e).__name__}: {e}")
    return (name, text, spec["change"])


def _judge(rows, title: str, *, expect=None) -> int:
    """返回破口数。`expect` 给定时（探针）要求刚好这么多次破口。"""
    n_bad = n_gate = 0
    for name, text, chg in rows:
        if text is None:
            n_gate += 1
            print(f"  ⏸  {name} —— 闸拦：{chg}")
            continue
        bad = check(text, chg if isinstance(chg, dict) else None)
        if bad:
            n_bad += 1
            print(f"  ❌ {name}")
            for code, why in bad:
                print(f"       {code} {why}")
    n = len(rows)
    print(f"\n{title}：{n} 组 / 破口 {n_bad} / 闸拦 {n_gate}")
    if expect is not None and n_bad != expect:
        print(f"  ⚠️ 探针预期 {expect} 次破口，实得 {n_bad} 次 —— 尺子失去鉴别力")
        return max(1, abs(n_bad - expect))
    return n_bad


# --------------------------------------------------------------------------- 五个开关

GOOD = """【参考素材说明】
@图片1 是人物参考（锁图中人物的脸和形象）。
@视频1 是视频编辑素材，对@视频1中的内容进行增删改。
@音频1 是音频复用素材，生成视频的音频直接复用@音频1。

【核心创意】
@视频1中画面左侧的人物换成@图片1中的人物。

【画面过程说明】
替换后的人物必须严格遵循原视频的运动轨迹，保持原有的固定机位不变。
确保替换后的人物质感和光影与环境融合。"""

PROBES = [
    # (说明, 文本, change, 预期能否通过)
    ("好样本：完整三段", GOOD, {"person": True}, True),
    ("反 H1：缺参考素材说明段", GOOD.split("\n\n", 1)[1], {"person": True}, False),
    ("反 H2：图片没写用途",
     GOOD.replace("@图片1 是人物参考（锁图中人物的脸和形象）。\n", ""),
     {"person": True}, False),
    ("反 H3：用途用词不官方",
     GOOD.replace("是人物参考", "是一个差不多的人"), {"person": True}, False),
    ("反 H4：只说换人不说谁",
     GOOD.replace("@视频1中画面左侧的人物换成@图片1中的人物。",
                  "把视频里的人换掉。"), {"person": True}, False),
    ("反 H5：串了 2.5 的句子",
     GOOD + "\n其他人物、道具和背景保持原样，不参与替换或删除。", {"person": True}, False),
    ("反 H6：超 7000 字", GOOD + "啊" * 7000, {"person": True}, False),
]


def probes() -> int:
    print("== 探针自证（每条规则一对正反样本）==")
    n_bad = 0
    for name, text, chg, should_pass in PROBES:
        bad = check(text, chg)
        ok = (not bad) == should_pass
        print(("  ✅ " if ok else "  ❌ ") + name)
        if not ok:
            n_bad += 1
            print(f"      实得破口：{bad}")
    print(f"\n探针：{len(PROBES)} 条 / 不符预期 {n_bad}")
    return n_bad


def _cases():
    """生产形状的用例：单/多人、方位唯一/撞车、有/无音轨。"""
    return [
        _mk("单人换人 · 有音轨", {"change": {"person": True, "person_ids": ["P1"]}}, n=1),
        _mk("单人换人 · 无音轨", {"change": {"person": True, "person_ids": ["P1"]}},
            n=1, audio_ref=False),
        _mk("双人换人", {"change": {"person": True, "person_ids": ["P1", "P2"]}}, n=2),
        _mk("双人 · 只换一个（第三个不动）",
            {"change": {"person": True, "person_ids": ["P1"]}}, n=2),
        _mk("两人同方位（指代退回外貌）",
            {"change": {"person": True, "person_ids": ["P1", "P2"]}}, n=2, pos="dup"),
        _mk("纯文字描述换人",
            {"change": {"person": True, "person_desc": "把画面里的男人换成穿皮衣的短发女性"}}, n=1),
        _mk("换人 + 换装",
            {"change": {"person": True, "person_ids": ["P1"],
                        "wardrobe": True, "wardrobe_ids": ["P1"],
                        "wardrobe_desc_by_id": {"P1": "牛仔外套"}}}, n=1),
        _mk("只换产品",
            {"change": {"product": True, "product_target": "易拉罐",
                        "product_desc": "可口可乐"}}, n=1),
        _mk("只换场景",
            {"change": {"scene": True, "scene_desc": "带百叶窗的办公室工位"}}, n=1),
        _mk("只换风格", {"change": {"style": True, "style": "赛博朋克霓虹风"}}, n=1),
        _mk("换人 + 补充说明",
            {"change": {"person": True, "person_ids": ["P1"],
                        "extra": "画面不显示字幕。"}}, n=1),
    ]


def current() -> int:
    print("== 当前产出（生产形状的 11 种用例）==")
    return _judge(_cases(), "当前产出")


def calib() -> int:
    print("== 校准：编译器产出必须零破口 ==")
    return _judge(_cases(), "校准")


def sweep() -> int:
    print("== 多变数扫描 ==")
    rows = []
    for n in (1, 2, 3):
        for audio in (True, False):
            rows.append(_mk(
                f"{n} 人 · {'有' if audio else '无'}音轨",
                {"change": {"person": True,
                            "person_ids": [f"P{i + 1}" for i in range(n)]}},
                n=n, audio_ref=audio))
    return _judge(rows, "多变数扫描")


def exhaustive() -> int:
    """单变量消融：每个开关打开后，产出**必须变**（没变 = 开关没接线）。"""
    print("== 多维穷举：单变量消融 ==")
    base = {"change": {"person": True, "person_ids": ["P1"]}}
    n_bad = 0
    _, base_text, _ = _mk("基线", base, n=1)
    if base_text is None:
        print("  基线就被闸拦了，无法消融")
        return 1
    switches = [
        ("换装", {"wardrobe": True, "wardrobe_ids": ["P1"],
                  "wardrobe_desc_by_id": {"P1": "牛仔外套"}}),
        ("换产品", {"product": True, "product_target": "易拉罐",
                    "product_desc": "可口可乐"}),
        ("换场景", {"scene": True, "scene_desc": "带百叶窗的办公室工位"}),
        ("换风格", {"style": True, "style": "赛博朋克霓虹风"}),
        ("补充说明", {"extra": "画面不显示字幕。"}),
    ]
    for name, extra in switches:
        chg = {**base["change"], **extra}
        _, text, _ = _mk(name, {"change": chg}, n=1,
                         slots_extra=("product", "scene", "style_ref", "wardrobe"))
        if text is None:
            print(f"  ❌ {name}：被闸拦，开关没有落点")
            n_bad += 1
        elif text == base_text:
            print(f"  ❌ {name}：打开后产出一个字都没变（没落点）")
            n_bad += 1
        else:
            print(f"  ✅ {name}：产出有变化")
    # 音轨开关单独测（它不改 change，改的是 audio_ref）
    _, with_audio, _ = _mk("有音轨", base, n=1, audio_ref=True)
    _, no_audio, _ = _mk("无音轨", base, n=1, audio_ref=False)
    if with_audio and no_audio and with_audio == no_audio:
        print("  ❌ 音轨：开关打开后产出一个字都没变（没落点）")
        n_bad += 1
    else:
        print("  ✅ 音轨：产出有变化")
    print(f"\n消融：{len(switches) + 1} 个开关 / 破口 {n_bad}")
    return n_bad


def main() -> int:
    if "--probes" in sys.argv:
        return 1 if probes() else 0
    for flag, fn in (("--calib", calib), ("--current", current),
                     ("--sweep", sweep), ("--exhaustive", exhaustive)):
        if flag in sys.argv:
            return 1 if fn() else 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
