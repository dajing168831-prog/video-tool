# -*- coding: utf-8 -*-
"""Seedance 2.5 提示词优化 · 真机验收（**花真钱**，必须主人点头才跑；**不进 check_all**）。

🩸 文件名故意不带 `_check`：一键自检扫的是 `*_check.py`，这条会真打方舟、真花钱。

跑法：
    python scripts/real_accept_sd25.py                # 三个场景全跑
    python scripts/real_accept_sd25.py --case=edit    # 只跑一个（plain / ref / edit）
    python scripts/real_accept_sd25.py --http --case=plain   # 走 HTTP（要先重启后端）

**和 `real_accept_sd20.py` 是两份**：三家各按各的官方标准，2.0 那份的
「必挂画质兜底」在 2.5 里是**禁止**（`sd25-pe:77`），拿它当判据会把人带错。

判据看五样：
1. 第 1 轮是否会**先问**（官方 Step 0），而不是直接交稿
2. `reads` 里读了 SKILL.md 没
3. 成品过 `ruler_sd25` 的**红条数**
4. 披露（`note`）有没有单独带出来、`素材提示：` 有没有混进正文
5. 体裁判定对不对（`free` / `tpl` / `ext` / `frame`）
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

OUT = Path("D:/tmp/sd25accept")
OUT.mkdir(parents=True, exist_ok=True)

API = "http://127.0.0.1:8911"
USE_HTTP = "--http" in sys.argv


def _turn_http(msgs: list[dict]) -> dict:
    """走 HTTP：真正的前端路径。返回字段对齐 `AgentResult` 那几个。"""
    import httpx

    body = {"messages": msgs, "target": "sd25", "duration": 0,
            "model": "pro", "images": [], "assets": []}
    r = httpx.post(f"{API}/api/prompt/chat", json=body, timeout=600)
    r.raise_for_status()
    j = r.json()
    if j.get("biz_code") not in (0, 1, 2):
        raise SystemExit(f"接口报错：{j.get('msg')}")
    d = j.get("data") or {}
    return {"action": d.get("action"), "question": d.get("question"),
            "prompt": d.get("prompt"), "note": d.get("note"),
            "red": d.get("red") or [], "yellow": d.get("yellow") or [],
            "reads": d.get("reads") or [], "genre": d.get("genre"),
            "steps": d.get("tries"), "calls": d.get("calls"),
            "tokens": d.get("tokens"), "trace": d.get("trace") or [],
            "truncated": "；".join(d.get("warnings") or [])}


def _turn_local(msgs: list[dict], fixed: list[str], images=None) -> dict:
    from app.services import sd25_skill

    got = sd25_skill.run(msgs, model="pro", fixed=fixed, images=images)
    genre = sd25_skill._genre_of(got.prompt or "") if got.action == "write" else None
    import ruler_sd25
    ctx = ruler_sd25.ctx_for(got.prompt or "", genre=genre or "free")
    rows = ruler_sd25.check(got.prompt or "", ctx) if got.prompt else []
    return {"action": got.action, "question": got.question,
            "prompt": got.prompt, "note": got.note,
            "red": got.red or [], "yellow": [x[0] for x in rows if x[1] == "黄"],
            "reads": got.reads, "genre": genre,
            "steps": got.steps, "calls": got.calls,
            "tokens": got.tokens, "trace": got.trace,
            "truncated": got.truncated or ""}


def _data_uri(p: Path) -> str:
    """图片转 data URI（方舟多模态 content 只吃这种或公网 URL）。"""
    import base64
    ext = p.suffix.lower().lstrip(".").replace("jpg", "jpeg")
    return f"data:image/{ext};base64,{base64.b64encode(p.read_bytes()).decode()}"


REF_A = Path("D:/tmp/ace_ref.png")
REF_B = Path("D:/tmp/ace_src3.png")

#: 每个场景：顾客原话 / 额外固定条件（素材声明）/ 追问回答 / 本轮附的图
CASES: dict[str, tuple] = {
    # ① 纯文生视频
    "plain": ("我想拍一个短片：一个女孩在雨夜的公交站等车，车灯扫过她的脸。",
              [], "你定就行：10 秒，其他你看着办，直接写。", None),
    # ② 多参考（两张图 + 明确分工，验 2.5 的「每份素材写职责、不采用什么」）
    "ref": ("用这两张参考图，做一个女生在旧书店翻书的镜头。",
            ["顾客声明的参考素材（标签就用这套，别自己编新的）：\n"
             "@图片1 —— 用于主体外貌（脸型、发型、气质）；不采用它的背景\n"
             "@图片2 —— 用于场景的光线与色调；不采用它的人物"],
            "10 秒，你自己定，直接写。", ("a", "b")),
    # ③ 视频编辑（官方路径：@视频1 是唯一编辑母版，五段齐全）
    "edit": ("把 @视频1 里的人换成 @图片1 里的女生，动作和背景都别动。",
             ["顾客声明的参考素材（标签就用这套，别自己编新的）：\n"
              "@视频1 —— 唯一编辑母版，动作/运镜/节奏全部沿用；不采用它的主角样貌\n"
              "@图片1 —— 用于替换后主角的外貌；不采用它的背景"],
             "10 秒，其他你定，直接写。", ("a",)),
}


def run_one(name: str, use_http: bool) -> int:
    first, extra, follow, imgs_key = CASES[name]
    prefix = f"{'http' if use_http else 'local'}_{name}"
    print(f"\n{'=' * 66}\n【{name}】{first[:56]}\n{'=' * 66}", flush=True)

    pairs = {"a": REF_A, "b": REF_B}
    images = [_data_uri(pairs[k]) for k in (imgs_key or ())] or None

    # 本地模式要自己拼 fixed（HTTP 模式由 `prompt.py` 拼，正是要验的那段）。
    # 🩸 别在这里另抄一份文案 —— 直接问产品要。
    from app.api.prompt import SD25_HI, SD25_LO, _fixed_duration_sd25

    fixed = [_fixed_duration_sd25(0, SD25_LO, SD25_HI)] + (
        list(extra) if extra else ["顾客没有声明参考素材。"])

    msgs = [{"role": "user", "content": first}]
    turn = 0
    t0 = time.time()
    while turn < 3:
        turn += 1
        print(f"\n=== 第 {turn} 轮 ===", flush=True)
        try:
            got = (_turn_http(msgs) if use_http
                   else _turn_local(msgs, fixed, images))
        except Exception as e:  # noqa: BLE001
            from app.services import skill_agent
            if isinstance(e, skill_agent.AgentError):
                print("失败：", e)
                return 1
            raise

        print(f"步数 {got['steps']} / 调用 {got['calls']} / token {got['tokens']}"
              f" / 用时 {time.time() - t0:.0f}s")
        print("读了：", got["reads"])
        if got["truncated"]:
            print("⚠️", got["truncated"])

        rec = {"turn": turn, **got}
        (OUT / f"{prefix}{turn}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")

        # 图只挂第一轮（模拟顾客一上来就传）；追问那轮不带 —— 图已在历史里
        images = None

        if got["action"] == "ask":
            print("问：", got["question"])
            msgs.append({"role": "assistant", "content": got["question"]})
            msgs.append({"role": "user", "content": follow})
            continue

        print(f"\n--- 成品（体裁 {got['genre']}）---")
        print(got["prompt"])
        print("\n--- 披露 ---")
        print(got["note"] or "（空）")
        print("\n--- 判红 ---")
        print(got["red"] or "0 条")
        if got["yellow"]:
            print("黄（建议项，不为它返工）：", got["yellow"])
        break

    print(f"\n-- {name} 用时 {time.time() - t0:.0f}s --")
    return 0


def main() -> int:
    if USE_HTTP:
        print(f"[模式] HTTP → {API}/prompt/chat（验全链路接线）", flush=True)
    else:
        from debug_server import inject_env
        n = inject_env()
        print(f"[模式] 直调 service；[凭据] 注入 {n} 个环境变量", flush=True)

    want = [a.split("=", 1)[1] for a in sys.argv if a.startswith("--case=")]
    names = ["plain"] if USE_HTTP and not want else (
        list(CASES) if not want or want == ["all"] else want)
    badn = [n for n in names if n not in CASES]
    if badn:
        print(f"没有这个场景：{badn}（可选 {list(CASES)}）")
        return 2

    rc = 0
    for n in names:
        rc = run_one(n, USE_HTTP) or rc
    print(f"\n原始响应在 {OUT}/")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
