# -*- coding: utf-8 -*-
"""Skill 执行器 —— 让**模型自己调工具去读官方 skill 包**，而不是我们把原文拼进 system。

## 为什么换掉「把 skill 拼进 system」

2026-10-30 验证（`D:/tmp/probe_agent_skill.py` / `_skill2.py`，真机 9 次调用）：

| | 拼进 system | 模型自己读 |
|---|---|---|
| 谁决定读哪份 | **人**（已经漏过：2.0 漏 8 份里的 1 份、H3 漏 9 个里的 8 个） | 模型按 SKILL.md 指路 |
| system 大小 | 46,495 字符，每次全付 | 几百字符 |
| 跨 skill | 做不到 | 实测：产品广告流程走完，自己切到 `h3-prompt-writing` 读 `ref-en.txt` |
| 问了几个问题 | 1 个 | 7 个（官方 Start Gate 全部） |

## 这个文件**不含任何一家的内容**

只做三件事：列目录、读文件、跑循环。哪家的 skill、提示词怎么写，
全在调用方传进来的 `root` 目录里。所以两家都能用，也都不会把它变成某一家的私有件。

## 输出协议用**工具**表达，不用文本标记

以前靠 `<<<ASK>>>` / `<<<PROMPT>>>` 这组文本标记区分"要问"还是"交付"，
实测漏过一次（官方 Step 4 的披露段模型没写）。工具是结构化的，漏不了。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from app.services import ark_chat

#: 一次对话最多走多少步（模型一次 tool_calls 算一步）
MAX_STEPS = 12
#: 一次对话的 token 上限。实测一个完整产品广告流程约 5.1 万，8 万留余量。
MAX_TOKENS = 80_000
#: 一次对话最多读多少个文件（防死循环反复读）
MAX_READS = 30
#: 单个 skill 文件大小上限
MAX_FILE_BYTES = 400_000


class AgentError(ValueError):
    """执行失败。消息直接给顾客看，写人话。"""


@dataclass
class AgentResult:
    action: str = ""                 # "ask" | "write"
    question: str = ""
    prompt: str = ""
    note: str = ""
    red: list = field(default_factory=list)
    steps: int = 0
    calls: int = 0
    tokens: int = 0
    reads: list = field(default_factory=list)
    trace: list = field(default_factory=list)   # 前端进度用
    truncated: str = ""                          # 超上限时说明原因


# ---------------------------------------------------------------- skill 包

def _frontmatter(text: str) -> dict:
    """抢 SKILL.md 的 frontmatter（name / description / trigger-words）。"""
    out: dict = {}
    if not text.startswith("---"):
        return out
    parts = text.split("---", 2)
    if len(parts) < 3:
        return out
    for ln in parts[1].splitlines():
        if ":" in ln and not ln.startswith((" ", "\t", "#")):
            k, v = ln.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def list_skills(root: Path) -> list[dict]:
    """扫 root 下每个 skill 包的 SKILL.md，取它的自我介绍。"""
    rows = []
    for d in sorted(root.iterdir()):
        md = d / "SKILL.md"
        if not d.is_dir() or not md.exists():
            continue
        fm = _frontmatter(md.read_text(encoding="utf-8", errors="replace"))
        rows.append({
            "name": fm.get("name") or d.name,
            "path": f"{d.name}/SKILL.md",
            "description": " ".join((fm.get("description") or "").split())[:600],
            "triggers": fm.get("metadata", ""),
        })
    return rows


class SkillFS:
    """只能读 `root` 目录内的文件。路径穿越、超大文件一律拒。"""

    def __init__(self, root: Path):
        self.root = root.resolve()
        if not self.root.is_dir():
            raise AgentError(f"skill 包目录不存在：{root}")
        self.reads: list[str] = []

    def read(self, rel: str) -> str:
        p = (self.root / rel).resolve()
        try:
            p.relative_to(self.root)             # 越界直接抛
        except ValueError:
            return "错误：只能读 skill 包目录里的文件"
        if not p.is_file():
            here = self._hint(rel)
            return "错误：没有这个文件。" + (f"这个 skill 下有：{here}" if here else "")
        if p.stat().st_size > MAX_FILE_BYTES:
            return f"错误：文件太大（{p.stat().st_size} 字节）"
        self.reads.append(rel)
        return p.read_text(encoding="utf-8", errors="replace")

    def _hint(self, rel: str) -> str:
        base = (self.root / rel.split("/")[0])
        if not base.is_dir():
            return ""
        files = [str(x.relative_to(self.root)) for x in base.rglob("*") if x.is_file()]
        return ", ".join(files[:30])


# ---------------------------------------------------------------- 工具定义

TOOLS = [
    {"type": "function", "function": {
        "name": "list_skills",
        "description": "列出所有可用的官方 skill（名字 + 适用场景）。第一次动手前先看这个。",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "read_skill",
        "description": "读某个 skill 包里的文件，例如 'xxx-generator/SKILL.md'。"
                       "SKILL.md 里提到要读参考文件时，用这个继续读。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "相对 skill 根目录的路径"}},
            "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "ask_user",
        "description": "向用户提问，然后等回答。一次最多问 3 个。信息够了就别问。",
        "parameters": {"type": "object", "properties": {
            "question": {"type": "string",
                         "description": "给用户看的问题，用正常说话的语气；"
                                        "有选项就每个选项单独一行、以「- 」开头"}},
            "required": ["question"]},
    }},
    {"type": "function", "function": {
        "name": "deliver_prompt",
        "description": "交付最终成品。调用后本次任务结束。写完提示词就该调用它。",
        "parameters": {"type": "object", "properties": {
            "prompt": {"type": "string",
                       "description": "完整提示词正文。从第一句开始，不要标题、不要说明文字"},
            "note": {"type": "string",
                     "description": "给用户看的说明：你替他补全了什么、改了什么。"
                                    "用人话，不要术语。没有就留空"}},
            "required": ["prompt"]},
    }},
]


# ---------------------------------------------------------------- 执行

def _post(messages: list[dict], *, model: str, key: str,
          timeout: float = 300.0) -> dict:
    body = {"model": model, "messages": messages, "tools": TOOLS,
            "tool_choice": "auto", "temperature": 0.2}
    try:
        return ark_chat.post(body, key=key, timeout=timeout)
    except ark_chat.ArkError as e:
        raise AgentError(str(e)) from e


def _clean(messages: list[dict]) -> list[dict]:
    out = []
    for m in messages or []:
        role = (m or {}).get("role")
        text = ((m or {}).get("content") or "").strip()
        if role in ("user", "assistant") and text:
            out.append({"role": role, "content": text})
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out


def run(root: Path, *, system: str, messages: list[dict], model: str, key: str,
        judge=None, max_steps: int = MAX_STEPS, max_tokens: int = MAX_TOKENS,
        post=None, on_step=None) -> AgentResult:
    """跑一轮 agent 对话。

    `post` 可注入桩（`post(messages)`，零费用测试）。
    `judge` 是交付前的判据：返回非空列表就带着问题让模型改一次。
    `on_step` 是每一步的回调（前端进度用）。
    """
    hist = _clean(messages)
    if not hist:
        raise AgentError("没有收到任何对话内容")
    if hist[-1]["role"] != "user":
        raise AgentError("最后一轮不是顾客说的话")

    fs = SkillFS(root)
    msgs: list[dict] = [{"role": "system", "content": system}] + hist
    res = AgentResult(trace=[{"t": 0, "stage": "start", "text": "开始"}])
    t0 = time.time()
    judged_once = False

    def step(stage: str, text: str) -> None:
        res.trace.append({"t": round(time.time() - t0, 1),
                          "stage": stage, "text": text})
        if on_step:
            on_step(stage, text)

    for n in range(1, max_steps + 1):
        res.steps = n
        if res.tokens >= max_tokens:
            res.truncated = f"token 已到上限（{res.tokens}/{max_tokens}）"
            break
        d = (post(msgs) if post else
             _post(msgs, model=model, key=key))
        res.calls += 1
        res.tokens += (d.get("usage") or {}).get("total_tokens") or 0
        try:
            msg = d["choices"][0]["message"]
        except Exception as e:                          # noqa: BLE001
            raise AgentError(f"生成响应结构异常：{e}") from e

        tcs = msg.get("tool_calls") or []
        if not tcs:
            # 模型没调工具直接说话 —— 当成交付（别让它的话白说）
            text = (msg.get("content") or "").strip()
            if not text:
                raise AgentError("模型这一轮什么都没给")
            res.action, res.prompt = "write", text
            res.truncated = res.truncated or "模型没有按工具协议交付，直接当正文收了"
            step("deliver", "模型直接给了正文")
            break

        msgs.append(msg)
        stop = False
        for tc in tcs:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            out, kind = "", "tool"

            if name == "list_skills":
                rows = list_skills(root)
                out = json.dumps(rows, ensure_ascii=False, indent=1)
                step("list", f"看到 {len(rows)} 个 skill")

            elif name == "read_skill":
                rel = str(args.get("path") or "")
                if len(fs.reads) >= MAX_READS:
                    out = f"错误：这次对话已经读了 {MAX_READS} 个文件，不再读了"
                else:
                    out = fs.read(rel)
                step("read", f"读 {rel}（{len(out)} 字符）")

            elif name == "ask_user":
                q = str(args.get("question") or "").strip()
                if not q:
                    out = "错误：问题不能为空"
                else:
                    res.action, res.question = "ask", q
                    step("ask", "向顾客提问")
                    stop = True
                    out = "已把问题发给用户，等回答"

            elif name == "deliver_prompt":
                p = str(args.get("prompt") or "").strip()
                if not p:
                    out = "错误：prompt 不能为空"
                else:
                    # 🩸 `judge` 只返回**红**（结构/字段/必挂件那种硬伤）；
                    # 黄是建议项，为了它反复烧钱不值。而且只回灌**一次** —— 判据不判死。
                    red = judge(p) if judge is not None else []
                    if red and not judged_once:
                        judged_once = True
                        out = ("\n".join(f"- [{r[0]}] {r[1]}（官方出处 {r[2]}）：{r[3]}"
                                         for r in red)
                               + "\n\n请按上面的问题改一遍，再调 deliver_prompt 交。")
                        step("judge", f"判到 {len(red)} 条红，回灌重试")
                    else:
                        res.action, res.prompt = "write", p
                        res.note = str(args.get("note") or "").strip()
                        res.red = red
                        step("deliver", f"交付 {len(p)} 字符")
                        stop = True
                        out = "已交付"
            else:
                out = f"错误：没有这个工具 {name}"

            msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": out})

        if stop:
            break
    else:
        res.truncated = res.truncated or f"走到步数上限（{max_steps} 步）"

    if res.action != "write" and res.action != "ask":
        raise AgentError(
            f"这次没能交出提示词（{res.truncated or '模型没有交付'}），请换个说法再试")

    res.reads = fs.reads
    res.trace.append({"t": round(time.time() - t0, 1), "stage": "end",
                      "text": "完成"})
    if on_step:
        on_step("end", "完成")
    return res

