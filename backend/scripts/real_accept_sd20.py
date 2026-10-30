# -*- coding: utf-8 -*-
"""Seedance 2.0 提示词优化 · 真机验收（**花真钱**，必须主人点头才跑；**不进 check_all**）。

🩸 文件名故意不带 `_check`：一键自检扫的是 `*_check.py`，这条会真打方舟、真花钱。
   跑法（两种，选一种）：
     python scripts/real_accept_sd20.py           # 直调 `sd20_skill.run`（不经 HTTP）
     python scripts/real_accept_sd20.py --http    # 打跑着的后端 `/prompt/chat`（全链路）

**两种验的不是同一件事**：

| 模式 | 走到哪里 | 验什么 |
|---|---|---|
| 默认 | `sd20_skill.run` | 模型拿 skill 包能不能自己读完、按官方流程交稿 |
| `--http` | `prompt.py` → `sd20_skill` → 方舟 | 上面那些 **+ 接线**：拼 fixed、传图、写 run_log、组返回值 |

🩸 后端重启只能主人自己做，所以默认模式**不依赖后端**（直调 service），
`--http` 才要求 8911 是活的。凭据从 HKCU 读（`with_user_env.NAMES`），
不打印、不落盘。原始响应落 `D:/tmp/sd20accept/`。

判据看四样：
1. 第 1 轮是否会**先问**（官方 SKILL.md 的 Step 0），而不是直接交稿
2. `reads` 里读了哪些文件（SKILL.md 读了没、references 读了没）
3. 成品过一遍 `volc20_pe` 尺子，**红条数**（黄是建议项，不追）
4. 披露（`note`）有没有单独带出来、正文里有没有混进操作步骤
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

OUT = Path("D:/tmp/sd20accept")
OUT.mkdir(parents=True, exist_ok=True)

API = "http://127.0.0.1:8911"
USE_HTTP = "--http" in sys.argv


def _turn_http(msgs: list[dict]) -> dict:
    """走 HTTP：真正的前端路径。返回字段对齐 `AgentResult` 那几个。"""
    import httpx

    body = {"messages": msgs, "target": "sd20", "duration": 0,
            "model": "pro", "images": []}
    # 路由挂在 `/api` 前缀下（`app/main.py:39` include_router(..., prefix="/api")）
    r = httpx.post(f"{API}/api/prompt/chat", json=body, timeout=300)
    r.raise_for_status()
    j = r.json()
    if j.get("biz_code") not in (0, 1, 2):
        raise SystemExit(f"接口报错：{j.get('msg')}")
    d = j.get("data") or {}
    return {"action": d.get("action"), "question": d.get("question"),
            "prompt": d.get("prompt"), "note": d.get("note"),
            "red": d.get("red") or [], "reads": d.get("reads") or [],
            "steps": d.get("tries"), "calls": d.get("calls"),
            "tokens": d.get("tokens"), "trace": d.get("trace") or [],
            "truncated": "；".join(d.get("warnings") or [])}


def _turn_local(msgs: list[dict], fixed: list[str], images=None) -> dict:
    from app.services import sd20_skill

    got = sd20_skill.run(msgs, model="pro", fixed=fixed, images=images)
    return {"action": got.action, "question": got.question,
            "prompt": got.prompt, "note": got.note,
            "red": got.red or [], "reads": got.reads,
            "steps": got.steps, "calls": got.calls,
            "tokens": got.tokens, "trace": got.trace,
            "truncated": got.truncated or ""}


def _data_uri(p: Path) -> str:
    """图片转 data URI（方舟多模态 content 只吃这种或公网 URL）。"""
    import base64
    ext = p.suffix.lower().lstrip(".").replace("jpg", "jpeg")
    return f"data:image/{ext};base64,{base64.b64encode(p.read_bytes()).decode()}"


REF_IMG = Path("D:/tmp/ace_ref.png")

#: 每个场景：顾客原话 / 额外固定条件（素材声明）/ 追问回答 / 本轮附的图
CASES: dict[str, tuple] = {
    # 纯文生视频（真机跑通过的那条，用来对照）
    "plain": ("我想拍一个短片：一个女孩在雨夜的公交站等车。", [], "你定就行：8 秒，其他你看着办，直接写。", None),
    # 多模态参考：素材面板声明了一张参考图，图也真的挂在消息上
    "ref": ("用这张参考图里的女生，做一个她在地铁站台等车的镜头。",
            ["顾客声明的参考素材（标签就用这套，别自己编新的）：\n"
             "@图片1 —— 当参考图，锁定人/风格/场景；主角外观"],
            "8 秒，16:9，你自己定，直接写。", "img"),
    # 编辑任务：官方路径 A，一段式，不许分块标题
    "edit": ("把 @视频1 里的人换成 @图片1 里的女生，动作和背景都别动。",
             ["顾客声明的参考素材（标签就用这套，别自己编新的）：\n"
              "@视频1 —— 参考它的动作/运镜/节奏；原片\n"
              "@图片1 —— 当参考图，锁定人/风格/场景；替换成的人"],
             "8 秒，其他你定，直接写。", None),
}


def run_one(name: str, use_http: bool) -> int:
    """跑一个场景。`use_http` 时只跑 plain —— HTTP 那条路还没吃素材声明。"""
    first, extra, follow, img = CASES[name]
    prefix = f"{'http' if use_http else 'local'}_{name}"
    print(f"\n{'=' * 66}\n【{name}】{first[:56]}\n{'=' * 66}", flush=True)

    images = [_data_uri(REF_IMG)] if img else None

    # 本地模式要自己拼 fixed（HTTP 模式由 `prompt.py` 拼，正是要验的那段）。
    # 🩸 别在这里另抄一份文案 —— 抄一份就漂一份。直接问产品要。
    from app.api.prompt import SD20_HI, SD20_LO, _fixed_duration_sd20

    fixed = [_fixed_duration_sd20(0, SD20_LO, SD20_HI)] + (
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

        print("\n--- 成品 ---")
        print(got["prompt"])
        print("\n--- 披露 ---")
        print(got["note"] or "（空）")
        print("\n--- 判红 ---")
        print(got["red"] or "0 条")
        break

    print(f"\n-- {name} 用时 {time.time() - t0:.0f}s --")
    return 0


def main() -> int:
    if USE_HTTP:
        print(f"[模式] HTTP → {API}/prompt/chat（验全链路接线）", flush=True)
        if not _backend_fresh():
            print("⚠️ 后端可能是改代码之前起的 —— 这一轮验的是它当时加载的代码")
    else:
        from debug_server import inject_env
        n = inject_env()
        print(f"[模式] 直调 service；[凭据] 注入 {n} 个环境变量", flush=True)

    want = [a.split("=", 1)[1] for a in sys.argv if a.startswith("--case=")]
    names = ["plain"] if USE_HTTP else (list(CASES) if not want or want == ["all"] else want)
    bad = [n for n in names if n not in CASES]
    if bad:
        print(f"没有这个场景：{bad}（可选 {list(CASES)}）")
        return 2

    rc = 0
    for n in names:
        rc = run_one(n, USE_HTTP) or rc
    print(f"\n原始响应在 {OUT}/")
    return rc


def _backend_fresh() -> bool:
    """后端进程是不是**这轮改完代码之后**起的（只提示，不拦）。"""
    try:
        import httpx
        from pathlib import Path as _P
        r = httpx.get(f"{API}/api/health", timeout=3)
        return r.status_code == 200
    except Exception:  # noqa: BLE001
        return False


if __name__ == "__main__":
    raise SystemExit(main())
