"""多人换人：**每个人的换人句能不能互不相同** —— 穷举判据（零费用、零模型调用）。

为什么要有这条
--------------
一句「把人物换成图N里的人」在多人画面里没有唯一解。判据不是"句子长得不一样"
（两句只差 `@图片1`/`@图片2` 也算不一样，但模型照样分不清），而是
**剥掉图号/主体号之后，指代必须仍然互不相同**。

两家官方给的定位手段只有两种，按优先级：
  1. **方位** —— 火山 `sd2-pe:72`（"多人未指明谁在左/右"是病灶）、
     `:153` 的写法；MiniMax `ref-en:246`（首次出镜写 position）；
  2. **外观** —— `sd2-pe` §1 的 2–3 个静态特征、`ref-en` 的 subject_definitions。

方位来自盘点 `position`（九宫格，上下分屏用 top/bottom）。

本脚本回答的问题
----------------
「哪些盘点结果会导致四家写不出可区分的指代？」——答案是**方位与外观同时失效时**。
只要盘点给出了外观描述，即使方位相同也不会重复（方位是加分项，不是必需项）。

跑法：python scripts/identifiability_check.py --model volc20|volc25|h3
"""
from __future__ import annotations

import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import edit_spec  # noqa: E402

POS9 = ["top-left", "top", "top-right", "left", "center", "right",
        "bottom-left", "bottom", "bottom-right"]

# 盘点结果的形态（夹具，不是剧情）
SHAPES = {
    "方位各不同": lambda n: POS9[:n],
    "全同方位(同侧同框)": lambda n: ["left"] * n,
    "全 unknown": lambda n: ["unknown"] * n,
    "没有 position 字段(老盘点)": lambda n: [None] * n,
}
DESCS = {
    "描述各不同": lambda n: [f"第{i + 1}号人物穿的独特服装" for i in range(n)],
    "全同描述(长得像)": lambda n: ["穿黑T恤的男人"] * n,
    "无描述(盘点失败)": lambda n: [""] * n,
}
DESCS_EN = {
    "描述各不同": lambda n: [f"person number {i + 1} in a distinct outfit" for i in range(n)],
    "全同描述(长得像)": lambda n: ["a man in a black t-shirt"] * n,
    "无描述(盘点失败)": lambda n: [""] * n,
}

# 🩸 2026-10-26（D28）：以前一次跑四家（2.0/2.5/H3/静帧），跟「一个一个模型分开执行」
# 冲突，而且 H3 那列的抽取正则没验证过 —— 一跑就是 48 组「抽到 0 句」的红字噪声，
# 把一整个 2.5 轮次带跑偏。现在**默认只跑火山 2.0**，别家必须 `--model` 点名。
CHANNELS = [("volc20", "火山2.0", "volc", "doubao-seedance-2-0-260128"),
            ("volc25", "火山2.5", "volc", "doubao-seedance-2-5-260628"),
            ("h3", "H3", "minimax", "MiniMax-H3")]
ALL_KEYS = [c[0] for c in CHANNELS] + ["still"]


def _strip_ids(s: str) -> str:
    """剥掉图号/主体号再比。

    🩸 不剥就是假绿：两句只差 `@图片1`/`@图片2` 会被判成"不同"，
    但模型看到的仍然是一模一样的指代 —— 这是本脚本第一次跑就踩到的坑。
    """
    s = re.sub(r"@图片\d+", "@图片", s)
    s = re.sub(r"<Subject \d+>", "<Subject>", s)
    s = re.sub(r"<Picture \d+>", "<Picture>", s)
    # 🩸 必须去大小写：H3 的 `_ucfirst` 把**第一句**首字母大写、后面几句小写，
    # 两句本来一模一样的指代就靠 `The`/`the` 被判成"不同"（第八次同源假绿 ——
    # 写 probe_h3.py 时踩过同一个坑，当时没回填到这里）。
    return s.strip().lower()


def _people(n: int, poses, descs) -> list[dict]:
    out = []
    for i in range(n):
        p = {"id": f"P{i + 1}", "present": True,
             "desc_zh": descs[i], "desc_en": descs[i],
             # 🩸 2026-10-26（D39）：**必须给时间轴**。`_gate_single_frame` 靠
             # `_coappear` 判同框，没有 `appearances` 就判成"从没同框" →
             # 闸静默放行 → "只换第 1 个"那一批全是空跑（空集恒真=假绿）。
             "appearances": [{"start": 0.0, "end": 5.0}]}
        if poses[i] is not None:
            p["position"] = poses[i]
        out.append(p)
    return out


def _volc_h3_clauses(ch: str, model: str, n: int, ppl: list[dict],
                     pick_n: int | None = None) -> list[str]:
    """`pick_n` = 这次**只换前几个人**（画面里仍然有 `n` 个人）。

    🩸 2026-10-26（D39）：以前只会全员换，于是"只换一个"这条支路的闸
    从来没被这个脚本量过 —— 2.0 的 D27 / 2.5 的 D28 / H3 的 D39 是同一个形状。
    """
    k = pick_n or n
    rows = {f"person{i + 1}" if i else "person": True for i in range(k)}
    spec = edit_spec.normalize(rows)
    slots = list(edit_spec.PERSON_SLOTS[:k])
    text = edit_spec.compile_prompt(ch, spec, model=model, slots=slots,
                                    source_people=ppl[:k],
                                    desc_by_id={p["id"]: {"zh": p["desc_zh"],
                                                          "en": p["desc_en"]}
                                                for p in ppl})
    if ch == "minimax":
        # 🩸 D31：指认句在 `subject_definitions` 里（`<Subject N> is … replaced by …`），
        # 以前却去 `detailed_description` 里找「同一行既有 replaced by 又有
        # The target video is an edited」—— 现行输出里根本没有这种行，所以
        # 每次都是「抽到 0 句」。改成认定义段，两种写法都收：
        #   `… in <Video 1>, and is replaced by <Subject 2>.`
        #   `… in <Video 1> that is replaced by <Subject 2>.`
        line = [x for x in text.splitlines()
                if x.strip().startswith("<Subject") and "replaced by <Subject" in x]
        # 🩸 首句是 `The person…`（大写 T），正则不写 [Tt] 会漏掉第一句 ——
        # 第二次跑就是这么假绿的（5 人只抽到 4 句）。
        got = re.findall(r"([Tt]he person\b.*?is replaced by <Subject \d+>)",
                         "\n".join(line))
        # 🩸 只换一个人时"句数互异"恒真（本来就只有 1 句），那条判据量不到东西。
        # 真正该问的是：**这句里有没有定位词**。编译器的两种写法：
        #   有定位 → `… is the person on the left in <Video 1>, and is replaced by …`
        #   没定位 → `… is the person in <Video 1> that is replaced by …`
        has_loc = bool(line) and not any(" that is replaced by" in x for x in line)
        return [_strip_ids(x) for x in got], has_loc
    # 🩸 2026-10-26（修 D41）：这里原来是 `return [_strip_ids(x) for x in got], True`
    # 后面跟着 `idx = …` 两行**永远执行不到的**代码 —— `got` 只在 minimax 分支里赋过值，
    # 火山 2.0/2.5 一进来就 `UnboundLocalError`。我加 H3 分支时只跑了 `--model h3`，
    # 另一家直接崩了都没发现。**共用脚本加分支，改完必须把每个分支都走到**。
    idx = {slot: i + 1 for i, slot in enumerate(slots)}
    # 🩸 2026-10-28：`_clauses` 不再有 `edit_task` 开关 —— 句式口径由各家的
    #   `Dialect` 提供。判据按型号取那一家自己的方言（本来就是一轮只跑一家）。
    from app.services.models import volc20_compile, volc25_compile
    _dialect = (volc25_compile.CL25 if (model and "2-5" in model)
                else volc20_compile.CL20)
    cl = edit_spec._clauses(ch, spec["change"], idx, dialect=_dialect,
                            people=ppl, desc_by_id=None)
    # 第二位（"有没有定位词"）只有 H3 量：H3 的两种写法一眼能分
    # （`is the person on the left …` vs `the person in <Video 1> that is replaced by`）。
    # 火山 2.0 的定位词**不在换人句里**：换人句的宾语是 `<主体N>`，定位词写在
    # 前面那句定义里（「将@视频1中画面中央的人物定义为<主体1>」）。拿换人句的
    # 字面去量"有没有定位词"只会恒假 —— 火山的这两个形状由
    # `ruler_sd20/sd25 --sweep` 各自守着。
    return [_strip_ids(x) for x in cl[:n]], None


def _still_clauses(n: int, ppl: list[dict]) -> list[str]:
    rows = {f"person{i + 1}" if i else "person": True for i in range(n)}
    spec = edit_spec.normalize(rows)
    text = edit_spec.still_prompt(spec, list(edit_spec.PERSON_SLOTS[:n]), people=ppl)
    return [_strip_ids(x) for x in
            re.findall(r"把([^；。]*?)换成图[^里]*里的人", text)]


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：一次只跑一家。
    # 🩸 闸门会把 `--model X` 从 sys.argv 里吃掉（免得下游 argparse 报未知参数），
    # 所以这里用它的返回值当默认值 —— 别指望 args.model 还能读到用户点的那个。
    from _model_gate import sel_or_exit
    sel = sel_or_exit(extra=("still",))

    import argparse

    ap = argparse.ArgumentParser()
    # `all`（四家一起跑）已按「一轮只跑一家」删除：点名 `all` 会被闸门直接拒绝。
    ap.add_argument("--model", default=sel, choices=ALL_KEYS,
                    help="只跑这一家（默认 = 本轮点名的型号）")
    args = ap.parse_args()
    want = {args.model}

    from app.services import video_edit
    from app.services.video_edit import EditError

    print(f"本次只跑：{'、'.join(sorted(want))}（其余需另起一轮点名）")

    # 🩸 四道闸各判各的（2026-10-23 拆开）：同一份盘点，四家结论本来就可以不同 ——
    # 火山 2.0/2.5/静帧读 `desc_zh`，H3 读 `desc_en`；2.5 还多一层职责行。
    gates = {
        "火山2.0": video_edit.require_identifiable_volc20,
        "火山2.5": video_edit.require_identifiable_volc25,
        "H3": video_edit.require_identifiable_h3,
        "静帧": video_edit.require_identifiable_still,
    }

    def gate_pass(tag: str, ppl: list[dict], slots: list[str]) -> bool:
        # 🩸 2026-10-29（D70）：2.0 的闸在**生产**里由适配器把编译器那把尺传进来
        #   （`models/volc20.py:_gate` 传 `sd20_locator` + `sd20_multi_locator`）。
        #   这里不传 = 量的是另一个闸 —— 会继续报"闸放行但输出重复"的假红。
        kw = {}
        if tag == "火山2.0":
            from app.services.models.volc20_compile import (sd20_locator,
                                                            sd20_multi_locator)
            kw = {"locator": sd20_locator, "locator_multi": sd20_multi_locator}
        try:
            gates[tag]({"people": ppl}, slots, **kw)
            return True
        except EditError:
            return False

    rows = []
    for n in (1, 2, 3, 5):
        for sname, sfn in SHAPES.items():
            poses = sfn(n)
            for dname, dfn in DESCS.items():
                zh = dfn(n)
                en = DESCS_EN[dname](n)
                ppl_zh = _people(n, poses, zh)
                ppl_en = _people(n, poses, en)
                slots = list(edit_spec.PERSON_SLOTS[:n])
                for key, tag, ch, model in CHANNELS:
                    if key not in want:
                        continue
                    ppl = ppl_en if ch == "minimax" else ppl_zh
                    got, _loc = _volc_h3_clauses(ch, model, n, ppl)
                    rows.append((n, sname, dname, tag, len(got), len(set(got)),
                                 gate_pass(tag, ppl, slots), len(got) == n))
                if "still" in want:
                    got = _still_clauses(n, ppl_zh)
                    rows.append((n, sname, dname, "静帧", len(got), len(set(got)),
                                 gate_pass("静帧", ppl_zh, slots), len(got) == n))

    # 🩸 只换画面里的第 1 个（画面仍有 n 个人）—— 与上面"全员都换"是两个形状：
    # 2.0 的 D27、2.5 的 D28、H3 的 D39 都是这条支路上漏判出来的。
    for n in (2, 3, 5):
        for sname, sfn in SHAPES.items():
            poses = sfn(n)
            for dname, dfn in DESCS.items():
                zh = dfn(n)
                en = DESCS_EN[dname](n)
                ppl_zh = _people(n, poses, zh)
                ppl_en = _people(n, poses, en)
                slots = [edit_spec.PERSON_SLOTS[0]]
                for key, tag, ch, model in CHANNELS:
                    # 只跑 H3：这个形状（画面 n 个人、只换第 1 个）是 H3 的 D39 漏判出来的，
                    # 而"有没有定位词"只有 H3 能如实量（见 `_volc_h3_clauses` 末段）。
                    # 火山的同一个形状由 `ruler_sd20 / ruler_sd25 --sweep` 各自守着。
                    if key not in want or key != "h3":
                        continue
                    ppl = ppl_en if ch == "minimax" else ppl_zh
                    got, has_loc = _volc_h3_clauses(ch, model, n, ppl, pick_n=1)
                    # 只换一个时"互异"恒真（就 1 句）→ 这一列改记**有没有定位词**
                    rows.append((n, sname + "·只换第1个", dname, tag,
                                 1, 1 if has_loc else 0,
                                 gate_pass(tag, ppl, slots), len(got) == 1))

    # 三块结论分开算，别混成一个数：
    #   extract —— 抽到的句数不等于人数：尺子可能根本没抽到（空集恒真，见下）
    #   dup     —— 编译器写出了重复指代
    #   mismatch—— **闸的结论和编译器实际输出对不上**：这一项才是本脚本补上的
    #              （放行却重复 = 闸漏放 / 假绿；拦截却互异 = 闸误伤 / 假红）
    extract = [r for r in rows if not r[7]]
    dup = [r for r in rows if r[4] != r[5]]
    # 一致的定义：放行(True) ⇔ 输出互异(True)；拦截(False) ⇔ 输出重复(False)。
    # 🩸 这里第一版写成了 `==`，把"放行+互异"（正确）全报成了不一致 —— 判据自己错。
    # 🩸 2026-10-26（D39）：**只换一个**的行不能套这条 —— 那时输出只有 1 句，
    # 被换的那个人在正文里根本不出现（没被换的人不会写进 prompt），
    # 所以"拦截但看起来互异"不是误伤。那一批只查一个方向：
    #   **闸放行 ⇔ 定义行里真的有定位词**（放行却写不出定位词 = 漏放、假绿）。
    _single = [r for r in rows if "·只换第1个" in r[1]]
    mismatch = [r for r in rows
                if r[7] and "·只换第1个" not in r[1] and (r[6] != (r[4] == r[5]))]
    mismatch += [r for r in _single if r[7] and r[6] and r[5] == 0]

    if "h3" in want:
        h3 = [r for r in rows if r[3] == "H3"]
        ok_ext = sum(1 for r in h3 if r[7])
        print("H3 列：抽取已按 `subject_definitions` 的现行写法校准（D31），"
              f"{ok_ext}/{len(h3)} 组抽到的句数 = 应换人数。")

    print(f"{'人数':<6}{'方位':<26}{'描述':<24}{'通道':<10}{'句数':<6}{'互异':<6}{'闸'}")
    for r in dup:
        print(f"{r[0]:<6}{r[1]:<26}{r[2]:<24}{r[3]:<10}{r[4]:<6}{r[5]:<6}"
              f"{'放行' if r[6] else '拦截'}")
    combos = sorted({(r[1], r[2]) for r in dup})
    # 🩸 退出码只认「真问题」：`dup` 全被闸拦住 = **设计如此**（闸就是为它建的），
    # 不算失败；`mismatch`（闸漏放/误伤）和 `extract`（抽不到=无法结论）才红。
    # 以前把 dup 也算失败 → 每次默认运行都红，红噪声把一整轮带跑偏。
    print(f"\n{len(rows) - len(dup)}/{len(rows)} 互异"
          f"（{len(dup)} 组会写出重复指代，其中"
          f"{sum(1 for r in dup if not r[6])} 组已被闸拦住）")
    if dup and all(not r[6] for r in dup):
        print("✅ 所有重复指代的形态都在出片前被闸拦住 —— 这是设计，不是缺陷。")
    if combos:
        print("会重复的盘点形态：")
        for a, b in combos:
            print(f"  · 方位={a}  描述={b}")
        # 🩸 2026-10-29（D70）：原来这行写「只要盘点给了外观描述就不重复」——
        #   同一份输出里的表就把它否了（"描述各不同"那几行照样重复）。
        #   「描述不同」不等于「能指认」：编译器要的是**带人物中心词的短语**。
        print("\n结论：**编译器取不出定位词**时才会重复 —— 方位不唯一，"
              "且描述里凑不出可用于指认的人物短语"
              "（典型是以服装开头、没有「男子/女性」这类中心词的盘点）。"
              "两段描述字面不同也没用。")

    if extract:
        print(f"\n🩸 抽取失败 {len(extract)} 组（抽到的句数 ≠ 人数）——"
              f" 这些组不能下结论，空集恒真：")
        for r in extract[:5]:
            print(f"  · {r[0]}人 {r[1]} {r[2]} {r[3]} → 抽到 {r[4]} 句")

    if mismatch:
        print(f"\n❌ 闸与编译器对不上 {len(mismatch)} 组：")
        for r in mismatch:
            kind = "闸放行但输出重复（漏放）" if r[6] else "闸拦截但输出互异（误伤）"
            print(f"  · {r[0]}人 {r[1]} {r[2]} {r[3]} → {kind}")
    else:
        print("\n✅ 四道闸的结论与编译器实际输出全部一致。")

    return 0 if not (mismatch or extract) else 1


if __name__ == "__main__":
    sys.exit(main())
