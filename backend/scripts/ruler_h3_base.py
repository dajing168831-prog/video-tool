# -*- coding: utf-8 -*-
"""H3 创作模式（T2VA / I2VA / FL2VA / L2VA）提示词尺子 —— 零费用、零模型调用。

**与 `ruler_h3.py`（Ref2VA 六段式）并列、互不引用。**
标准文档：`docs/PROMPT-AUDIT-H3-BASE.md`（规则编号 B1–B36，本文件规则号与之 1:1 对齐）。

官方依据：`D:/tmp/official/h3/base-en.txt`（222 行）。
🩸 两把尺子不能合并：同一家模型，这两种模式的规则**方向相反** ——
风格句这里写在 `[Shot 1]` **之内**（`base-en:78`），六段式写在 `[Shot 1]` **之前**
（`ref-en:230`）。合成一把必然抄错一边。

用法：
    python scripts/ruler_h3_base.py --calib     # 官方 4 份案例校准（红必须 0）
    python scripts/ruler_h3_base.py --probes    # 每条规则一对正反样本
    python scripts/ruler_h3_base.py --current   # 量我们现在编译出来的
    python scripts/ruler_h3_base.py --sweep     # 多变数组合（生产形状）

🩸 校准语料是 `base-en.txt §5` 的 **4 个官方完整案例**，一个模式一份 ——
**从官方文件里现读**，不在本文件里重打一遍（重打就可能抄错，而"抄错的尺子"比没有尺子更糟）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACK))
sys.path.insert(0, str(BACK / "scripts"))

from app.services.models import h3_base_compile as hbc   # noqa: E402

BASE_EN = Path("D:/tmp/official/h3/base-en.txt")

from app.services.models.h3_base import (  # noqa: F401
    RULES,
    check,
)


# ---------------------------------------------------------------- 官方案例
CASE_MODES = ("t2va", "i2va", "fl2va", "l2va")
CASE_NAMES = ("Case 1 · T2VA", "Case 2 · I2VA", "Case 3 · FL2VA", "Case 4 · L2VA")


def official_cases() -> list[tuple[str, str, dict]]:
    """从 `base-en.txt §5` 现读 4 个官方完整案例（一个模式一份）。

    🩸 不从本文件里重打 —— 重打就有抄错的风险，而"抄错的尺子"比没有尺子更糟。
    """
    if not BASE_EN.exists():
        return []
    txt = BASE_EN.read_text(encoding="utf-8")
    i = txt.find("## 5. Cases")
    if i < 0:
        return []
    blocks = re.findall(r"```text\n(.*?)```", txt[i:], re.S)
    out = []
    for k, b in enumerate(blocks[:4]):
        out.append((CASE_NAMES[k], b.strip(), {"mode": CASE_MODES[k]}))
    return out


def calib() -> int:
    rows = official_cases()
    if not rows:
        print("!! 一份官方案例都没读到 —— 不许当通过")
        return 2
    n_red = 0
    for name, p, ctx in rows:
        vs = check(p, ctx)
        red = [v for v in vs if v[1] == "红"]
        yellow = [v for v in vs if v[1] == "黄"]
        n_red += len(red)
        mark = "红" if red else ("黄" if yellow else "绿")
        print(f"\n[{mark}] {name}（适用 {len(RULES)} 条规则）")
        for v in vs:
            print(f"     {v[1]} {v[0]} {v[2]} ← {v[3]}｜{v[4][0][:100]}")
    print(f"\n官方语料校准：{len(rows)} 条，红 {n_red} 条"
          f"（{len(rows) * len(RULES)} 条规则-示例判定）")
    return 0 if n_red == 0 else 1


# ---------------------------------------------------------------- 正反样本
def _case(k: int) -> str:
    rows = official_cases()
    return rows[k][1] if len(rows) > k else ""


def probes() -> int:
    """每条规则一对（坏样本必须响、好样本必须不响）。

    样本一律从**官方案例**改一个地方得来 —— 不自己写一段新提示词当样本，
    否则测的是"我写得对不对"，不是"尺子认不认官方形状"。
    """
    c1, c2, c3, c4 = (_case(0), _case(1), _case(2), _case(3))
    P: list[tuple[str, str, str, dict]] = []

    def add(rid, bad, good, ctx):
        P.append((rid, bad, good, ctx))

    t = {"mode": "t2va"}
    add("B1", c1.replace("\n\nnon_diegetic_music: A soft acoustic-guitar pattern", ""),
        c1, t)
    add("B2", c1.replace("[Shot 1] Live-action", "Live-action"), c1, t)
    add("B3", c1.replace("The doorbell rings once", "门铃响了一声"), c1, t)
    add("B4", c1 + " " + ("word " * 1500), c1, t)
    add("B5", hbc.instruction_line("i2va") + "\n\n" + c1, c1, t)
    add("B6", c2.replace("at 0.00 seconds into the target video",
                         "at 0.5 seconds into the target video"), c2,
        {"mode": "i2va"})
    add("B7", c3.replace("8.00-second mark", "8-second mark"), c3, {"mode": "fl2va"})
    add("B8", c4.replace("<Picture 1> (from [Shot 1])",
                         "Picture 1 (from Shot 1)"), c4, {"mode": "l2va"})
    add("B9", c2.replace("is fully referenced.\n\n", "is fully referenced.\n"), c2,
        {"mode": "i2va"})
    add("B10", c1.replace("[Shot 2] At 00:05.000,", "[Shot 2]"), c1, t)
    add("B11", c1.replace("the camera cuts to", "the camera jumps to"), c1, t)
    # 🩸 2026-10-30：B12「运镜只取官方 20 个词」**已撤回**（自造规则）。
    #   官方 §4.3 那张表表头是「Available Expression」，全节没有"只能"的措辞，
    #   反而写着 `write camera movement as natural English`（`base-en:117`/`ref-en:219`）。
    #   同一天两次误红（`uses a tracking shot` / `The camera tracks the dog`）。
    #   存档：`docs/_archive/b12-withdrawn-2026-10-30.md`
    add("B13", c1.replace("with small amplitude", "with tiny amplitude"), c1, t)
    add("B14", c1.rstrip() + " Push In, small amplitude.", c1, t)
    # 官方原句是 `…at slow speed as the middle-aged baker …`；把 `as` 去掉 = 连接词丢失
    add("B28", c1.replace("at slow speed as the middle-aged baker",
                          "at slow speed the middle-aged baker"), c1, t)
    add("B15", c1.replace("Live-action, cinematic,", "Soft and gentle,"), c1, t)
    add("B17", c1.replace("(S1)", "(S2)", 1), c1, t)
    add("B19", c1.replace("(S1) places a fresh loaf on the wooden counter and says: <d>",
                          " places a fresh loaf on the wooden counter and says: <d>"),
        c1, t)
    add("B21", c1.replace("and says: <d>", "and says in an off-screen voiceover: <d>"),
        c1, t)
    add("B22", c1.replace("the camera cuts to a close-up of steam rising from the sliced "
                          "bread while the baker's final words carry over from the "
                          "previous shot.",
                          "the camera cuts to a close-up of steam rising from the sliced "
                          "bread.<scenetrans>"),
        c1, t)
    add("B24", c1.replace(
        "Wooden shutters scrape open over a quiet street as trays clink softly inside "
        "the bakery.",
        "Wooden shutters scrape open. Trays clink softly. A doorbell rings. A step "
        "sounds. A knife slices bread."), c1, t)
    add("B25", c1.replace(
        "A soft acoustic-guitar pattern at a moderate tempo, joined by sparse "
        "upright-bass notes and a gentle fade at the end.",
        "Guitar plays. Bass enters. A fade begins. Silence follows."), c1, t)
    add("B26", c1.replace(
        "Wooden shutters scrape open over a quiet street as trays clink softly inside "
        "the bakery. The doorbell rings once, followed by light footsteps and the "
        "crisp sound of bread being sliced.", "N/A"), c1, t)

    ok = 0
    for rid, bad, good, ctx in P:
        if bad == good:                    # 锚串失效 → 这条压根没测到，不许算过
            print(f"!! {rid}  坏样本和好样本一模一样 —— 锚串失效，这条没测到")
            continue
        fired_bad = any(v[0] == rid for v in check(bad, ctx))
        fired_good = any(v[0] == rid for v in check(good, ctx))
        hit = fired_bad and not fired_good
        ok += 1 if hit else 0
        print(f"{'ok ' if hit else '!! '}{rid}  坏样本{'响' if fired_bad else '哑'} / "
              f"好样本{'误响' if fired_good else '不响'}")
    print(f"\n规则自证：{ok}/{len(P)}（官方案例 {len(official_cases())} 份）")
    return 0 if ok == len(P) else 1


# ---------------------------------------------------------------- 当前输出
def _spec(mode: str) -> dict:
    return {
        "mode": mode,
        "duration": 5,
        "ratio": "16:9",
        "style": "Live-action, cinematic",
        "shots": [{
            "cut": None,
            "body": "a medium-wide shot frames a baker opening the shutters of a "
                    "small street bakery before sunrise",
            "camera": {"type": "Push In", "amplitude": "small", "speed": "slow",
                       "target": "toward the wooden counter"},
            "dialogue": [{"who": "the middle-aged baker", "lang": "zh",
                          "text": "第一炉面包好了。"}],
        }],
        "soundscape": "Wooden shutters scrape open over a quiet street. Trays clink "
                      "softly inside the bakery.",
        "music": "A soft acoustic-guitar pattern at a moderate tempo.",
    }


def params_check() -> int:
    """请求参数（B28–B35）：这些不是正文，但顾客照填，错一条提交就失败。"""
    n = 0
    cases = [
        ("T2VA 必须给具体比例", "t2va", {"ratio": ""}, lambda p: p["ratio"] != "adaptive"),
        ("T2VA 不许 adaptive", "t2va", {"ratio": "adaptive"}, lambda p: p["ratio"] != "adaptive"),
        ("I2VA 恒 adaptive", "i2va", {"ratio": "16:9"}, lambda p: p["ratio"] == "adaptive"),
        ("时长夹在 4–15", "t2va", {"duration": 99}, lambda p: p["duration"] == 15),
        ("时长下限 4", "t2va", {"duration": 1}, lambda p: p["duration"] == 4),
        ("Max 档下限 5", "t2va", {"duration": 1},
         lambda p: p["duration"] == 5),
    ]
    for label, mode, over, ok in cases:
        sp = _spec(mode)
        sp.update(over)
        model = "MiniMax-H3-Max" if "Max" in label else "MiniMax-H3"
        got = hbc.request_params(sp, model=model)
        good = ok(got)
        n += 0 if good else 1
        print(f"  {'✅' if good else '❌'} {label}：{got['ratio']} / {got['duration']}s")
    print(f"  {'✅' if n == 0 else '❌'} 请求参数：6 项（不通过 {n}）")
    return n


def show(title: str, rows: list[tuple]) -> int:
    print("=" * 78)
    print(title)
    n_red = 0
    for name, p, ctx in rows:
        vs = check(p, ctx)
        red = [v for v in vs if v[1] == "红"]
        n_red += len(red)
        mark = "红" if red else ("黄" if vs else "绿")
        print(f"\n  [{mark}] {name}")
        for v in vs:
            print(f"      {v[1]} {v[0]} {v[2]} ← {v[3]}｜{v[4][0][:100]}")
    print(f"\n{n_red} 条红")
    return n_red


def current_cases() -> list[tuple]:
    rows = []
    for mode in hbc.MODES_LIVE:
        sp = _spec(mode)
        text = hbc.compile_prompt(sp)
        rows.append((f"{mode.upper()} 编译产出", text, {"mode": mode}))
    return rows


def sweep() -> int:
    """生产形状组合：模式 × 运镜 × 有无台词 × 有无配乐（全部本地编译）。"""
    rows = []
    for mode in hbc.MODES_LIVE:
        for cam in ("", "Push In", "Static Shot", "Tracking Shot"):
            for dlg in (True, False):
                sp = _spec(mode)
                if cam:
                    sp["shots"][0]["camera"]["type"] = cam
                else:
                    sp["shots"][0].pop("camera")
                if not dlg:
                    sp["shots"][0].pop("dialogue")
                try:
                    text = hbc.compile_prompt(sp)
                except Exception as e:      # noqa: BLE001
                    rows.append((f"{mode}/{cam or '-'}/{'dlg' if dlg else '-'}",
                                 f"编译失败：{e}", {"mode": mode}))
                    continue
                rows.append((f"{mode} / 运镜={cam or '无'} / 台词={'有' if dlg else '无'}",
                             text, {"mode": mode}))
    n_red = show(f"多变数扫描（H3 创作模式）：{len(rows)} 个组合（零模型调用）", rows)
    n_par = params_check()
    print(f"\n  总红 {n_red} 条｜参数不通过 {n_par} 项")
    return 0 if n_red == 0 and n_par == 0 else 1


def exhaustive() -> int:
    """全维度穷举：模式 × 镜头数 × 运镜（闭集 20 + 无）× 台词形态 × 有无风格。

    分母 = 2 × 2 × 21 × 4 × 2 = **672** 个组合，全部本地编译、零模型调用。
    「破口」= 编译抛错，或编译出来判红。黄不算破口（风格缺失是建议级）。
    """
    cam_list = ("",) + tuple(hbc.CAMERA_PHRASES.values())
    dlg_list = ("none", "one", "two", "voiceover")
    style_list = (True, False)
    want = len(hbc.MODES_LIVE) * 2 * len(cam_list) * len(dlg_list) * len(style_list)

    n = bad = 0
    first_bad: list[str] = []
    for mode in hbc.MODES_LIVE:
        for shots_n in (1, 2):
            for cam in cam_list:
                for dlg in dlg_list:
                    for with_style in style_list:
                        n += 1
                        spec = _exhaustive_spec(mode, shots_n, cam, dlg, with_style)
                        label = (f"{mode}/{shots_n}镜/运镜={cam or '无'}/"
                                 f"台词={dlg}/风格={'有' if with_style else '无'}")
                        try:
                            out = hbc.compile(spec)
                        except Exception as e:            # noqa: BLE001
                            bad += 1
                            if len(first_bad) < 5:
                                first_bad.append(f"{label} → 编译抛错：{e}")
                            continue
                        reds = [v for v in check(out["text"], {"mode": mode})
                                if v[1] == "红"]
                        if reds:
                            bad += 1
                            if len(first_bad) < 5:
                                first_bad.append(
                                    f"{label} → {reds[0][0]} {reds[0][2]}｜"
                                    f"{reds[0][4][0][:80]}")
    print("=" * 78)
    print(f"H3 创作模式全维度穷举：{n}/{want} 个组合（零模型调用、零费用）")
    for x in first_bad:
        print(f"   ✗ {x}")
    print(f"   破口 {bad} 条")
    if n != want:
        print(f"!! 只跑了 {n} 个，应跑 {want} 个 —— 空集/少集不算通过")
        return 2
    return 0 if bad == 0 else 1


def _exhaustive_spec(mode, shots_n, cam, dlg, with_style) -> dict:
    shots = []
    for i in range(shots_n):
        # 第 2 镜起写**名词短语** —— 编译器会在前面加 `the camera cuts to `
        # （契约见 `h3_base_compile.compile_prompt` 的 docstring）。
        sh: dict = {"body": ("a wide shot frames an empty street at dawn" if i == 0
                             else "a close-up of a hand on a door handle")}
        if i:
            sh["cut"] = 3.0 * i
        if cam:
            sh["camera"] = {"type": cam, "amplitude": "small", "speed": "slow"}
        shots.append(sh)
    if dlg == "one":
        shots[0]["dialogue"] = [{"who": "a man", "lang": "zh", "text": "早安。"}]
    elif dlg == "two":
        shots[0]["dialogue"] = [{"who": "a man", "lang": "zh", "text": "早安。"}]
        shots[-1].setdefault("dialogue", []).append(
            {"who": "a woman", "lang": "zh", "text": "早。"})
    elif dlg == "voiceover":
        shots[0]["dialogue"] = [{"who": "a man", "lang": "zh", "text": "我记得。",
                                 "voiceover": True}]
    return {
        "mode": mode,
        "duration": max(4, int(3 * shots_n + 1)),
        "ratio": "16:9",
        "style": "Live-action, cinematic" if with_style else "",
        "shots": shots,
        "soundscape": "Street ambience continues throughout.",
        "music": "",
    }


def main() -> int:
    from _model_lock import guard
    guard("h3")
    if "--exhaustive" in sys.argv:
        return exhaustive()
    if "--calib" in sys.argv:
        return calib()
    if "--probes" in sys.argv:
        return probes()
    if "--current" in sys.argv:
        return 0 if show("现在我们编译出来的 H3 创作模式输出",
                         current_cases()) == 0 else 1
    if "--sweep" in sys.argv:
        return sweep()
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
