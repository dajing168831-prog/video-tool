# -*- coding: utf-8 -*-
"""H3 转换路由的验收（**零费用、零模型调用**）。

被测：`app/services/h3_convert_route.py` —— 顾客提交什么素材 → 走哪个模式 →
用哪把尺子。纯规则，所以每条判据都能拿假素材直接喂。

🩸 这条线为什么值得单独建尺子：模式判错不是"效果差一点"。
2026-10-29 实测，把两张角色设定图当成 I2VA 的首帧发出去，结果
16:9 被吞成 adaptive、分镜被压成 6 镜、运镜语法坏掉（lite 6/14、pro 11/14）。

判据分三类：
  A. 六个模式的判定（含官方的互斥硬边界）
  B. 画幅 / 时长按模式、按型号分叉
  C. 判不了的情形必须"不猜" —— 返回空模式 + 要问顾客的问题
  D. 全组合穷举：任何一个合法素材组合，都必须给出模式或说明为什么给不出

🩸 最后一条是防「真空真」：只测我想到的几种组合，等于只测了交集。
这里把角色组合**全部**跑一遍（640 组），一个都不许落到"模式空、又没问题、又没提问"。

运行：python scripts/p19_check.py --model h3
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import _model_lock  # noqa: E402

RESULT: list[tuple[bool, str, str]] = []


def ok(name: str, detail: str = "") -> None:
    RESULT.append((True, name, detail))


def bad(name: str, detail: str) -> None:
    RESULT.append((False, name, detail))


def expect(cond: bool, name: str, detail: str = "") -> bool:
    (ok if cond else bad)(name, "" if cond else detail)
    return cond


def main() -> int:
    if "--model" not in sys.argv:
        print("⛔ 必须点名型号：--model h3")
        return 2
    i = sys.argv.index("--model")
    if (sys.argv[i + 1] if i + 1 < len(sys.argv) else "") != "h3":
        print("⛔ 只跑 h3 轮：--model h3")
        return 2
    _model_lock.guard("h3")

    from app.services import h3_convert_route as rt

    A = rt.Asset

    # ---------------------------------------------------------------- A 六种模式
    r = rt.route([])
    expect(r["mode"] == "t2va" and r["guide"] == "base" and r["ruler"] == "ruler_h3_base",
           "A1 什么都不传 → 文生视频，走三字段和 base 尺子",
           f"mode={r['mode']!r} guide={r['guide']!r} ruler={r['ruler']!r}")

    r = rt.route([A("image", "first_frame")])
    expect(r["mode"] == "i2va" and r["ruler"] == "ruler_h3_base",
           "A2 一张图当首帧 → 图生视频（首帧），仍走三字段",
           f"mode={r['mode']!r} ruler={r['ruler']!r}")

    r = rt.route([A("image", "last_frame")])
    expect(r["mode"] == "l2va",
           "A3 一张图当尾帧 → 图生视频（尾帧）", f"mode={r['mode']!r}")

    r = rt.route([A("image", "first_frame"), A("image", "last_frame")])
    expect(r["mode"] == "fl2va" and r["guide"] == "base",
           "A4 首帧 + 尾帧 → 首尾帧模式，仍走三字段",
           f"mode={r['mode']!r} guide={r['guide']!r}")

    r = rt.route([A("image", "reference_image")])
    expect(r["mode"] == "r2va" and r["guide"] == "ref"
           and r["ruler"] == "ruler_h3_handwrite",
           "A5 人物/风格参考图 → 参考模式，走手写入口和 ref 尺子",
           f"mode={r['mode']!r} guide={r['guide']!r} ruler={r['ruler']!r}")

    r = rt.route([A("video")])                      # 没标角色，靠 normalize 补
    expect(r["mode"] == "r2va" and r["notes"],
           "A6 只传一段视频（没标用途）→ 补成参考视频，走参考模式",
           f"mode={r['mode']!r} notes={r['notes']!r}")

    # 官方硬边界：`:212-214` 互斥，两个方向都要拦
    r = rt.route([A("image", "first_frame"), A("image", "reference_image")])
    expect(r["mode"] == "" and r["problems"],
           "A7 首帧 + 参考图 → 混用被拦（正向）",
           f"mode={r['mode']!r} problems={r['problems']!r}")

    r = rt.route([A("image", "reference_image"), A("video")])
    expect(r["mode"] == "r2va" and not r["problems"],
           "A8 参考图 + 参考视频 → 不算混用，应当放行",
           f"mode={r['mode']!r} problems={r['problems']!r}")
    # ↑ 这一条是成对探针的"另一边"：只有 A7 绿、A8 也绿，才说明拦住的是
    #   「帧 + 参考」这组，而不是把所有多素材都拦了。

    # ---------------------------------------------------------------- B 画幅 / 时长
    r = rt.route([])
    expect(r["ratio"]["required"] is True and r["ratio"]["adaptive"] is False,
           "B1 文生视频：画幅必填、不能 adaptive",
           f"{r['ratio']!r}")

    r = rt.route([A("image", "first_frame")])
    expect(r["ratio"]["adaptive"] is True and r["ratio"]["allowed"] == ["adaptive"],
           "B2 图生视频：恒 adaptive，填别的会被忽略",
           f"{r['ratio']!r}")

    r = rt.route([A("image", "reference_image")], model="MiniMax-H3")
    expect(r["ratio"]["adaptive"] is True and "16:9" in r["ratio"]["allowed"],
           "B3 参考模式（H3）：可 adaptive 也可显式指定",
           f"{r['ratio']!r}")

    r = rt.route([A("image", "reference_image")], model="MiniMax-H3-Lite")
    expect(r["ratio"]["adaptive"] is False and r["ratio"]["required"] is True,
           "B4 参考模式（H3-Lite）：不支持 adaptive，必须显式指定",
           f"{r['ratio']!r}")

    expect(rt.route([], model="MiniMax-H3")["duration"] == (4, 15),
           "B5 H3 时长 4–15")
    expect(rt.route([], model="MiniMax-H3-Max")["duration"] == (5, 15),
           "B6 H3-Max 时长 5–15（不支持 4 秒）",
           f"实际 {rt.route([], model='MiniMax-H3-Max')['duration']!r}")

    # ---------------------------------------------------------------- C 判不了不猜
    r = rt.route([A("image")])                      # 一张图但没说用途
    expect(r["mode"] == "" and r["questions"],
           "C1 一张图没标用途 → 不给模式，先问顾客",
           f"mode={r['mode']!r} questions={r['questions']!r}")

    r = rt.route([A("image", "reference_image")] * 10)
    expect(bool(r["problems"]),
           "C2 参考图 10 张 → 超上限被拦（官方 ≤9）",
           f"problems={r['problems']!r}")

    many = [A("image", "reference_image")] * 9 + [A("video")] * 3 + [A("audio")] * 3
    r = rt.route(many)
    expect(any("12" in p for p in r["problems"]),
           "C3 图 9 + 视频 3 + 音频 3 = 15 个 → 混用上限 12 被拦",
           f"problems={r['problems']!r}")

    r = rt.route([A("video", "reference_video", seconds=20.0)])
    expect(bool(r["problems"]),
           "C4 参考视频单段 20 秒 → 超 2–15 秒被拦",
           f"problems={r['problems']!r}")

    r = rt.route([A("video", "reference_video", seconds=3.0)])
    expect(not r["problems"],
           "C5 参考视频单段 3 秒 → 正常放行（成对探针的另一边）",
           f"problems={r['problems']!r}")

    for bad_call, name in (
        (lambda: rt.route([], model="MiniMax-HX"), "C6 未知型号"),
        (lambda: A("image", "第一帧"), "C7 非法 role"),
        (lambda: A("audio_xx"), "C8 非法素材类型"),
    ):
        try:
            bad_call()
            bad(name + " → 应当报错，实际没报")
        except ValueError:
            ok(name + " → 报错")

    # ---------------------------------------------------------------- D 全组合穷举
    # 角色组合：首帧 0/1、尾帧 0/1、参考图 0..9、参考视频 0..3、参考音频 0..3
    # = 2×2×10×4×4 = 640 组。任何一组都必须落到「有模式」或「有问题」或「有待问」。
    holes, total = [], 0
    for nf, nl, ni, nv, na in itertools.product(range(2), range(2),
                                                range(10), range(4), range(4)):
        assets = ([A("image", "first_frame")] * nf
                  + [A("image", "last_frame")] * nl
                  + [A("image", "reference_image")] * ni
                  + [A("video", "reference_video", 3.0)] * nv
                  + [A("audio", "reference_audio", 3.0)] * na)
        total += 1
        rr = rt.route(assets)
        if not rr["mode"] and not rr["problems"] and not rr["questions"]:
            holes.append((nf, nl, ni, nv, na))
        if rr["mode"] and (rr["guide"] == "ref") != (rr["mode"] == "r2va"):
            holes.append(("guide错配", nf, nl, ni, nv, na, rr["mode"], rr["guide"]))
    expect(total == 640 and not holes,
           f"D1 全组合穷举：{total} 组素材组合全部给出结论",
           f"漏了 {len(holes)} 组，前几个：{holes[:5]}")

    # ---------------------------------------------------------------- E 尺子
    sys.path.insert(0, str(ROOT / "scripts"))
    import ruler_h3_base  # noqa: E402
    import ruler_h3_handwrite  # noqa: E402

    nb, nr = len(ruler_h3_base.RULES), len(ruler_h3_handwrite.RULES)
    expect(nb > 0 and nr > 0, "E1 两把尺子都能读到",
           f"base={nb} ref={nr}")
    # 🔓 2026-11-03 复刻换体裁：ref 从六段式换成手写入口三段式。
    expect(rt.GUIDES["base"]["ruler"] == "ruler_h3_base"
           and rt.GUIDES["ref"]["ruler"] == "ruler_h3_handwrite",
           "E2 选尺子只认模块名：三字段→base，手写入口→ref",
           f"{rt.GUIDES!r}")
    # 🩸 只锁「两把尺子是两把、不互相引用」，不锁条数 —— 条数会随官方复核变，
    #    写死数字只会制造假红（`vacuous-truth-false-green` 的姐妹坑）。
    src_base = (ROOT / "scripts" / "ruler_h3_base.py").read_text(encoding="utf-8")
    src_ref = (ROOT / "scripts" / "ruler_h3_handwrite.py").read_text(encoding="utf-8")
    expect("import ruler_h3_handwrite" not in src_base
           and "import ruler_h3_base" not in src_ref,
           "E3 两把尺子互不引用",
           "有互相 import，两把尺子已经混了")

    # ---------------------------------------------------------------- K 官方 skill 原文真进了产品
    # 🩸 2026-10-29 主人：「你装在我本地！！！起到的作用和效果是我想要的吗？」
    # 官方 skill 的 workflow 是「读 references/*.txt 照它写」（`SKILL.md:12-13`）。
    # 以前产品喂给 agent 的是我手抄的 13 / 19 条摘要 —— agent 一次都没读过原文。
    # 这一组钉住：三个调用点的 system prompt 必须含官方原文。
    import hashlib as _hl
    import json as _js
    from pathlib import Path as _P

    from app.services import h3_official as _off

    _sk = _off.skill()
    expect("Identify the input mode" in _sk,
           "K1 SKILL.md 原文进了产品并能读出来")

    _b = _off.system_prompt("base")
    _r = _off.system_prompt("ref")
    expect("Zoom In" in _b and "integrated_multimodal_description" in _b,
           "K2 三字段那路的 prompt 含 base-en 全文（运镜闭集 + 三字段名）")
    expect("Zoom In" in _r and "subject_definitions" in _r,
           "K3 六段式含 base-en + ref-en 全文"
           "（ref-en:213-218 明写镜头写法沿用 base，只传 ref 会丢运镜闭集）")
    # 判据用 ref-en **独有**的一句（`ref-en:284`）。不能拿 `subject_definitions` 判 ——
    # 那个词 SKILL.md 第 27 行介绍 Ref2VA 时就有，三字段带上 SKILL.md 必然出现。
    expect("summarizes ambience and physical sounds across the full video" not in _b,
           "K3b 三字段那路没掺 ref-en 正文（两把尺子互不引用）")

    # 工程内原文必须与 MANIFEST 记录一致 —— 防「两份各说各话」
    _man = _P(r"D:/tmp/official/h3/MANIFEST.json")
    if _man.exists():
        _m = _js.loads(_man.read_text(encoding="utf-8"))
        _want = {f["path"]: f["sha256"] for f in _m["files"] if f.get("sha256")}
        for _n in ("base-en.txt", "ref-en.txt"):
            _got = _hl.sha256((_off.DIR / _n).read_bytes()).hexdigest()
            expect(_got == _want.get(_n),
                   f"K5 工程内的 {_n} 与 MANIFEST 登记的 sha256 一致",
                   f"工程 {_got[:12]} / MANIFEST {str(_want.get(_n))[:12]}")
    else:
        ok("K5 MANIFEST 不在本机 → 跳过比对（部署机上不适用）")

    passed = sum(1 for r in RESULT if r[0])
    for good, name, detail in RESULT:
        print(("  ✅ " if good else "  ❌ ") + name)
        if not good and detail:
            print("       " + detail)
    print(f"\nH3 转换路由验收：通过 {passed} / {len(RESULT)}，红 {len(RESULT) - passed}"
          f"（base 尺子 {nb} 条；ref 尺子 {nr} 条，两把都只锁「互不引用」，条数现读不写死）")
    return 0 if passed == len(RESULT) else 1


if __name__ == "__main__":
    sys.exit(main())
