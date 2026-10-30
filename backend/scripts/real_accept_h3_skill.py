# -*- coding: utf-8 -*-
"""H3 提示词优化 · 真机验收（**花真钱**，必须主人点头才跑；**不进 check_all**）。

🩸 文件名故意不带 `_check`：一键自检扫的是 `*_check.py`，这条会真打方舟、真花钱。

**为什么直调 service 而不打后端**：后端重启只能主人自己做，跑着的进程可能是改代码
之前起的。这条脚本 `import h3_skill` 直接跑**当前工作区的代码**，验的就是刚改的东西。
（要走 HTTP 全链路，用同目录的 `real_accept_h3.py`，那个要求后端是新的。）

验三条，全部走 `h3_skill.run`（agent 自己 list_skills → read_skill → 交稿）：

| # | 验什么 | 看什么 |
|---|---|---|
| A | 体裁挑选 + 启动问询 | `reads` 里选对了包；第一轮 `ask` 一次列了几项 |
| B | 六段式（带参考素材） | 出 `subject_definitions`；判据红几条 |
| C | `@图片1` 标签（本轮修的那条） | 判据认不认 Hub 写法，会不会静默跳过 |

原始响应落 `D:/tmp/h3accept/`。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

BACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACK))
sys.path.insert(0, str(BACK / "scripts"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import logging  # noqa: E402

logging.disable(logging.INFO)

OUT = Path("D:/tmp/h3accept")
OUT.mkdir(parents=True, exist_ok=True)
MODEL = "pro"
#: D 那条用的参考图（AI 生成的人像，不涉及真人肖像）
REF_IMG = Path("D:/tmp/ace_ref.png")


def _data_uri(p: Path) -> str:
    """图片转 data URI。方舟多模态 content 只吃这种或公网 URL。"""
    import base64
    ext = p.suffix.lower().lstrip(".").replace("jpg", "jpeg")
    return f"data:image/{ext};base64,{base64.b64encode(p.read_bytes()).decode()}"


def _turn(msgs: list[dict], fixed: list[str], images=None) -> dict:
    from app.services import h3_skill

    got = h3_skill.run(msgs, model=MODEL, fixed=fixed, images=images)
    return {"action": got.action, "question": got.question,
            "prompt": got.prompt, "note": got.note,
            "red": got.red or [], "reads": got.reads,
            "steps": got.steps, "calls": got.calls, "tokens": got.tokens,
            "trace": got.trace, "truncated": got.truncated or ""}


def run_case(tag: str, first: str, fixed: list[str], follow: str,
             images=None) -> dict:
    """跑一条：先发顾客原话，`ask` 就追一轮，然后把结果打全。

    `images` 只在**第一轮**挂（模拟顾客一上来就传参考图）；追问那一轮不再带 ——
    图已经在历史里了，重复挂会变成"又发了一遍素材"。
    """
    msgs = [{"role": "user", "content": first}]
    print(f"\n{'=' * 66}\n【{tag}】{first[:60]}\n{'=' * 66}")
    t0 = time.time()
    got = _turn(msgs, fixed, images)
    print(f"第 1 轮：action={got['action']} 步={got['steps']} "
          f"调用={got['calls']} token={got['tokens']} 用时={time.time() - t0:.0f}s")
    print(f"  读了：{got['reads']}")

    if got["action"] == "ask":
        q = got["question"] or ""
        print(f"  ❓提问（{len(q)} 字）：\n{q}")
        msgs += [{"role": "assistant", "content": q},
                 {"role": "user", "content": follow}]
        got2 = _turn(msgs, fixed)
        got["tokens"] += got2["tokens"]
        got["reads"] = list(dict.fromkeys(got["reads"] + got2["reads"]))
        print(f"第 2 轮：action={got2['action']} 步={got2['steps']} "
              f"调用={got2['calls']} token={got2['tokens']}")
        got = {**got2, "tokens": got["tokens"], "reads": got["reads"],
               "q1": q, "q1_len": len(q)}

    p = got.get("prompt") or ""
    print(f"  成品 {len(p)} 字 ｜ 判据红 {len(got['red'])} ｜ 总 token {got['tokens']}")
    if got["red"]:
        for r in got["red"]:
            print(f"    ❌ {r}")
    if got["truncated"]:
        print(f"  ⚠️ {got['truncated']}")
    print(f"  开头：{p[:160]!r}")

    (OUT / f"{tag}.json").write_text(
        json.dumps(got, ensure_ascii=False, indent=1), encoding="utf-8")
    return got


def main() -> int:
    from debug_server import inject_env
    n = inject_env()
    print(f"[凭据] 注入 {n} 个环境变量；模型 {MODEL}；结果落 {OUT}", flush=True)

    total = {"tokens": 0}

    # ---------------------------------------------------------------- A 体裁
    # 顾客原话，不是提示词。挑的是**强制启动问询**的那个包（minimalist `:24`
    # 「一次性确认商品款式情况、目标时长、画幅比例、苹果风模板和画面文案方式」），
    # 好看出 ask_user 现在会列几项。
    a = run_case(
        "A-genre",
        "做一条极简风格的产品广告，卖一款白色无线耳机，讲戴上之后的安静感。",
        ["目标片长：还没定，由你在对话里问。官方单段 4–15 秒。"],
        "10 秒，16:9，款式就一款白色，别的你定，直接给我成品。",
    )
    total["tokens"] += a["tokens"]
    print(f"  ▶ 选包：{a['reads']}")

    # ---------------------------------------------------------------- B 六段
    b = run_case(
        "B-ref",
        "用这张参考图里的女生，做一个她在地铁站台等车的镜头，电影感。",
        ["顾客声明的参考素材（标签就用这套）：\n"
         "<Picture 1> —— 主角外观参考\n"
         "目标片长：还没定，由你在对话里问。"],
        "8 秒，16:9，你自己定，直接给我成品。",
    )
    total["tokens"] += b["tokens"]
    bp = b.get("prompt") or ""
    print(f"  ▶ 六段式：{'subject_definitions' in bp} ｜ 标签语法："
          f"{'<Picture' if '<Picture' in bp else ('@图片' if '@图片' in bp else '无')}")

    # ---------------------------------------------------------------- C @写法
    # 本轮修的那条：顾客照界面上的写法说「@图片1」，模型可能原样照抄。
    # 不管它最后写哪种，判据都必须**真的跑**，不能因为认不出模式而静默跳过。
    c = run_case(
        "C-at",
        "把 @图片1 里的人换成 @图片2 里的女人，动作和背景都别动。",
        ["顾客声明的参考素材（标签就用这套）：\n"
         "@图片1 —— 原片里的女主\n"
         "@图片2 —— 换成她\n"
         "目标片长：还没定，由你在对话里问。"],
        "6 秒，16:9，你自己定，直接给我成品。",
    )
    total["tokens"] += c["tokens"]
    cp = c.get("prompt") or ""
    from app.services import h3_skill
    print(f"  ▶ 成品用的标签：{'<Picture' if '<Picture' in cp else ('@图片' if '@图片' in cp else '无')}"
          f" ｜ 判据判的模式：{h3_skill._mode_of(cp)} ｜ 红 {len(c['red'])}")

    # ---------------------------------------------------------------- D 第一次带图
    # 🩸 本轮修的那条：顾客**第一次就给参考图**、还没出过稿 —— 以前前端把这种
    #   请求全塞进 `/prompt/revise`，他那句原话被当成「已有的 H3 提示词」去改。
    #   现在走对话路出稿，图跟着对话走。
    #   关键判据不是"出了六段式"，而是**模型有没有真看到图**：让它描述图里的
    #   具体细节（发型、衣服、背景），说得出=图真挂上了，说不出一=还在空谈。
    d = run_case(
        "D-first-with-image",
        "用这张参考图里的女生，做一个她在地铁站台等车的镜头，电影感。",
        ["目标片长：还没定，由你在对话里问。"],
        "8 秒，16:9，你自己定，直接给我成品。",
        images=[_data_uri(REF_IMG)],
    )
    total["tokens"] += d["tokens"]
    dp = d.get("prompt") or ""
    # 这几样是图里真实存在的：马尾、白色上衣、浅蓝天空。模型写得出来才叫看见了。
    seen = [w for w in ("ponytail", "white top", "white shirt", "pale blue",
                        "light blue", "blue sky") if w in dp.lower()]
    print(f"  ▶ 图里细节命中：{seen or '一个都没提到 —— 图可能没挂上'}")
    print(f"  ▶ 六段式：{'subject_definitions' in dp} ｜ 标签："
          f"{'<Picture' if '<Picture' in dp else ('@图片' if '@图片' in dp else '无')}")

    print(f"\n{'=' * 66}\n合计 token：{total['tokens']}（pro）｜ 明细 {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
