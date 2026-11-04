"""提示词机械体检（零模型调用）：整片矩阵扫「自相矛盾 / 没定义 / 拼接毛刺」。

为什么要这一条：2026-10-22 一天里连着翻了两类车，都不是模型不行，是**提示词自己打架**——
  ① 换人句把原片人物的衣服写进去 → 只换衣服不换脸；
  ② 换场景的同时又说「背景按原片」→ 成片背景每隔几秒翻一次；
  ③ `<Picture 5>`（边界帧）/ `<Picture 4>`（服装图）从来没进 subject_definitions。

单点断言只能防已经想到的那一条。这里改成**矩阵 + 规则**：
把通道 × 改动 × 保持 × 声音 × 边界帧的组合全编译一遍，用规则去扫，
新组合里冒出来的同类问题也会被抓住。

跑法：python scripts/prompt_lint_check.py --model volc20|volc25|h3
"""
from __future__ import annotations

import itertools
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import edit_spec  # noqa: E402

MODELS = {
    "2.0": "doubao-seedance-2-0-260128",
    "2.5": "doubao-seedance-2-5-260628",
    "H3": "MiniMax-H3",
}
PEOPLE1 = [{"id": "P1", "desc_zh": "穿红裙的女生", "desc_en": "the woman in red",
            "present": True}]
PEOPLE2 = PEOPLE1 + [{"id": "P2", "desc_zh": "戴帽子的男人", "desc_en": "the man in a hat",
                     "present": True}]
PEOPLE2_OFF = PEOPLE1 + [{"id": "P2", "desc_zh": "戴帽子的男人",
                          "desc_en": "the man in a hat", "present": False}]
DESC = {"P1": {"zh": "穿红裙的女生", "en": "the woman in red"},
        "P2": {"zh": "戴帽子的男人", "en": "the man in a hat"}}

LABEL_RE = re.compile(r"<(Picture|Subject|Video|Audio) (\d+)>")

rows: list[tuple[str, bool, str]] = []


def chk(name: str, ok, detail: str = "") -> None:
    rows.append((name, bool(ok), "" if ok else str(detail)[:220]))


def slots_for(change: dict) -> list[str]:
    """这次真正会发出去的参考图槽（顺序 = SLOT_ORDER）。"""
    slots: list[str] = []
    n_person = len([x for x in change.get("person_ids") or []] if change.get("person") else [])
    for i, slot in enumerate(edit_spec.PERSON_SLOTS):
        if i < n_person:
            slots.append(slot)
    if change.get("product") and change.get("product_has_img", True):
        slots.append("product")
    if change.get("scene") and change.get("scene_has_img", True):
        slots.append("scene")
    if change.get("wardrobe") and change.get("wardrobe_has_img", True):
        slots.append("wardrobe")
    return slots


def lint(tag: str, p: str, *, model: str, spec: dict, slots: list[str],
         boundary_pic: int, audio_ref: bool, absent: set[str] | None = None,
         n_people: int = 0) -> None:
    ch = "minimax" if model.startswith("MiniMax") else "volc"
    c = spec["change"]
    pi = edit_spec.image_index(slots)

    chk(f"[{tag}] 提示词非空", bool(p.strip()))

    # ---- 拼接毛刺 ----
    for bad, why in (("the the", "重复冠词"), ("。。", "重复句号"),
                     ("；；", "重复分号"), ("  ", "双空格"),
                     ("..", "重复点号"), ("、、", "重复顿号")):
        chk(f"[{tag}] 没有{why}「{bad}」", bad not in p)

    # ---- H3：**手写入口三段式**（`h3-manual:244`）----
    # 🔓 2026-11-03 换体裁：H3 复刻从 Ref2VA 六段式改成手写入口。旧分支整段删掉，
    #   改成反过来守「六段式不许回流」—— 体裁判错是 10 月那 26 次出不了片的根因
    #   （`docs/H3-SOURCES-MINDMAP.md` §6.5：换人样例 6 条全在手册，六段式 0 条）。
    if ch == "minimax":
        # 官方 `h3-manual:244`：参考素材说明 + 核心创意 + 画面过程说明
        chk(f"[{tag}] 有【参考素材说明】段（h3-manual:244）", "【参考素材说明】" in p)
        # 反向守卫：老体裁的任何痕迹都算红（换体裁就是不许它偷偷回来）。
        for w in ("subject_definitions", "retention_analysis", "detailed_description",
                  "non_diegetic_music", "<Picture", "<Subject", "<Audio", "<Video "):
            chk(f"[{tag}] 不回流六段式「{w}」", w not in p)

        # 官方 `h3-manual:248` 的用途表 + `:284` 实际范例的冒号式：`@图片N：用途（…）`。
        head, _, body = p.partition("【参考素材说明】")
        duties = body.split("\n\n")[0]
        for slot, n in pi.items():
            if slot in (absent or set()):
                continue
            chk(f"[{tag}] 槽位 {slot}（图{n}）有用途句",
                f"@图片{n}：" in duties, duties[:200])
        chk(f"[{tag}] @视频1 有用途句（h3-manual:248）", "@视频1：" in duties,
            duties[:200])
        chk(f"[{tag}] @音频1 与实际发不发音轨一致",
            ("@音频1" in p) == audio_ref)
        # 图号不许指向没发出去的图（边界帧那张是**额外**发的一张，号在 slots 之后）。
        _lim = max(len(slots), boundary_pic or 0)
        chk(f"[{tag}] 图号不超出实际张数",
            all(1 <= int(n) <= _lim for n in re.findall(r"@图片(\d+)", p)),
            re.findall(r"@图片(\d+)", p))

        # 🩸 「不是他的就不要串啊」（主人 2026-11-03）：2.0/2.5 的模板句
        #   H3 手册里没有，混进来就是把别家的规则搬过来。
        for w in ("唯一编辑母版", "其他人物、道具和背景保持原样",
                  "色调和光线方向", "除以上明确修改对象外", "面部特征和妆造"):
            chk(f"[{tag}] 不串别家句「{w}」", w not in p)

    # ---- 只写描述、没传图：描述必须真的进提示词（接口层允许二选一）----
    for kind in ("product", "scene", "wardrobe"):
        if c.get(kind) and kind not in slots:
            d = (c.get(f"{kind}_desc") or "").strip()
            if d:
                chk(f"[{tag}] 没图时描述也进了提示词（{kind}）", d in p, d)

    # ---- 换场景 vs 保持背景：不许两头都说 ----
    if c.get("scene"):
        chk(f"[{tag}] 换场景时不说背景照原片",
            "background environment" not in p and "props and background remain unchanged" not in p
            and "背景、产品、画面布局" not in p,
            p[:200])
        # H3 手写入口的换场景句是「把@视频1中的背景场景替换为…」
        # （`h3-manual:221`「视频1窗外的场景改成图1」），比火山多一个「场景」两字。
        chk(f"[{tag}] 换场景时确实写了换背景",
            "背景替换为" in p or "背景场景替换为" in p
            or "background of <Video 1> is replaced" in p
            or "background of <Video 1> becomes" in p)
        chk(f"[{tag}] 换场景时 keep.background 被关掉",
            spec["keep"]["background"] is False)
    else:
        chk(f"[{tag}] 不换场景时不写换背景",
            "背景替换为" not in p and "背景场景替换为" not in p
            and "the background of <Video 1> is replaced" not in p)

    # ---- 范围闭环：官方**只有两种**，逐字，没有第三种（`sd25-pe:556-558`）----
    # 🩸 2026-10-22 这里原本断言「换场景时闭环句不再点名背景 / 换产品时不再点名道具」
    # —— 那是按"字面矛盾"自己发明的动态列举，官方原文里不存在这种写法。
    # `edit_spec._scope_closure()` 已回滚成官方逐字（见该函数 docstring），
    # 断言跟着回滚：只验「用的是官方那一句」，不验它删没删类别。
    if "除以上明确修改对象外" in p:
        m = re.search(r"除以上明确修改对象外，[^。]*", p)
        clause = m.group(0) if m else ""
        chk(f"[{tag}] 范围闭环是官方逐字（sd25-pe:556-558）",
            clause == "除以上明确修改对象外，@视频1中其他可见人物、道具和背景元素"
                      "保持原样，不参与替换或删除", clause)

    # ---- 光线：keep 关了就不许再说"光线跟原片" ----
    if not spec["keep"].get("lighting", True):
        chk(f"[{tag}] 关了光线保持就不说光线照原片",
            "光线、物体位置" not in p and "lighting and color tone follow" not in p,
            p[:200])

    # ---- 火山专属 ----
    if ch == "volc":
        chk(f"[{tag}] 不写「参考@视频1」", "参考@视频1" not in p and "参考视频1" not in p)
        chk(f"[{tag}] 图号不超出实际张数",
            all(int(n) <= len(slots) + (1 if boundary_pic else 0)
                for n in re.findall(r"@图片(\d+)", p)),
            re.findall(r"@图片(\d+)", p))


def build(tag: str, model: str, change: dict, keep: dict, audio: str,
          *, people=None, slots_extra: dict | None = None, boundary: int = 0,
          audio_ref: bool = False, desc: dict | None = None) -> None:
    raw = {"change": dict(change), "keep": dict(keep), "audio": audio}
    raw.update(slots_extra or {})
    spec = edit_spec.normalize(raw)
    c = spec["change"]
    slots = slots_for({**change, **(slots_extra or {})})
    ppl = people if people is not None else PEOPLE1
    p = edit_spec.compile_prompt(
        "minimax" if model.startswith("MiniMax") else "volc", spec, model=model,
        source_people=ppl, slots=slots, desc_by_id=desc or DESC, audio_ref=audio_ref,
        boundary_pic=boundary)
    absent = {slot for i, slot in enumerate(edit_spec.PERSON_SLOTS)
              if slot in slots and i < len(ppl)
              and ppl[i] and ppl[i].get("present") is False}
    lint(tag, p, model=model, spec=spec, slots=slots,
         boundary_pic=boundary, audio_ref=audio_ref, absent=absent,
         n_people=len([x for x in ppl if x]))


CHANGES = {
    "换人": {"person": True, "person_ids": ["P1"]},
    "换产品": {"product": True, "product_target": "蓝色马克杯",
               "product_target_en": "the blue mug"},
    "换场景": {"scene": True},
    "换装": {"wardrobe": True},
    # 接口层允许「传图 或 写一句描述」，只写描述时描述必须进提示词
    "换产品(只描述)": {"product": True, "product_desc": "蓝色马克杯",
                       "product_has_img": False},
    "换场景(只描述)": {"scene": True, "scene_desc": "雨夜街头",
                       "scene_has_img": False},
    "换装(只描述)": {"wardrobe": True, "wardrobe_desc": "米色风衣",
                     "wardrobe_has_img": False},
    "全换": {"person": True, "person_ids": ["P1"], "product": True,
             "product_target_en": "the blue mug", "scene": True, "wardrobe": True},
}
KEEPS = {
    "全保持": {},
    "不保背景": {"background": False},
    "不保光线": {"lighting": False},
    "啥都不保": {k: False for k in edit_spec.KEEP_LABELS},
}


def main() -> int:
    import _model_lock

    # 🩸 必须点名型号（2026-10-26）：以前一个命令把三家矩阵全扫一遍，
    # 改一家的判据会连带把别家的结果一起换掉。现在一轮只扫点名的那一家。
    if "--model" not in sys.argv:
        lock = _model_lock.current()
        print("⛔ 必须点名型号：--model volc20|volc25|h3")
        print(f"   当前锁：{_model_lock.MODELS.get(lock, lock) if lock else '（无）'}")
        return 2
    i = sys.argv.index("--model")
    sel = sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
    if sel not in _model_lock.MODELS:
        print("用法：--model volc20|volc25|h3")
        return 2
    _model_lock.guard(sel)
    LABEL = {"volc20": "2.0", "volc25": "2.5", "h3": "H3"}[sel]
    one = [(LABEL, MODELS[LABEL])]

    for (mlabel, model), (clabel, change), (klabel, keep) in itertools.product(
            one, CHANGES.items(), KEEPS.items()):
        build(f"{mlabel}/{clabel}/{klabel}", model, change, keep, "original",
              audio_ref=False)
        build(f"{mlabel}/{clabel}/{klabel}/配音", model, change, keep, "tts",
              audio_ref=True)

    if sel == "h3":
        # 多人 / 缺席 / 边界帧
        build("H3/双人/配音", MODELS["H3"],
              {"person": True, "person_ids": ["P1", "P2"]}, {}, "tts",
              people=PEOPLE2, audio_ref=True)
        build("H3/双人/一人缺席", MODELS["H3"],
              {"person": True, "person_ids": ["P1", "P2"]}, {}, "tts",
              people=PEOPLE2_OFF, audio_ref=True)
        PEOPLE2_PUNCT = [dict(x, **{"present": True}) for x in PEOPLE2]
        build("H3/描述带句号", MODELS["H3"],
              {"person": True, "person_ids": ["P1", "P2"]}, {}, "tts",
              people=PEOPLE2_PUNCT, audio_ref=True,
              desc={"P1": {"zh": "穿红裙的女生。", "en": "the woman in red."},
                    "P2": {"zh": "戴帽子的男人。", "en": "the man in a hat."}},
              boundary=3)
        build("H3/双人边界帧点名所有在场主体", MODELS["H3"],
              {"person": True, "person_ids": ["P1", "P2"]}, {}, "original",
              people=PEOPLE2, boundary=3)
        build("H3/边界帧", MODELS["H3"], {"person": True, "person_ids": ["P1"]}, {},
              "original", boundary=3)
        build("H3/边界帧+场景", MODELS["H3"],
              {"person": True, "person_ids": ["P1"], "scene": True}, {},
              "original", boundary=3)
    elif sel == "volc25":
        # 🩸 2026-10-22 实测（任务 a47631b0）：视觉盘点给的是**整句**描述，
        # 末尾带句号；拼进模板就成了「…bottle. in <Video 1> is replaced by…」
        # 「…酒瓶。（这句…）」。所有内嵌位置必须先去标点。
        PEOPLE2_PUNCT = [dict(x, **{"present": True}) for x in PEOPLE2]
        build("2.5/描述带句号", MODELS["2.5"],
              {"person": True, "person_ids": ["P1", "P2"]}, {}, "tts",
              people=PEOPLE2_PUNCT, audio_ref=True,
              desc={"P1": {"zh": "穿红裙的女生。", "en": "the woman in red."},
                    "P2": {"zh": "戴帽子的男人。", "en": "the man in a hat."}})
        # 🩸 2026-10-23：画面内文字能力下线，「2.0/画面文字」这条用例随之删除。
        build("2.5/风格", MODELS["2.5"], {"person": True, "person_ids": ["P1"],
                                          "style": "anime"}, {}, "original")
    print(f"本次只扫 {LABEL}")

    ok = sum(1 for _, v, _ in rows if v)
    for name, v, detail in rows:
        if not v:
            print(f"  FAIL {name}  [{detail}]")
    print(f"\n{ok}/{len(rows)} 通过（零模型调用）")
    return 0 if ok == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
