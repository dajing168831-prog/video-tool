"""手写脚本导入 —— 用户自己写好口播稿，一句一镜切开，**跳过剧本生成**直接进分镜/出片。

出处（逐行对照）：
  · 竞品 `src/lib/script-import.ts:16-81`
      - `estimateDurationSec`：中日韩 5 字/秒、拉丁 14 字/秒，夹 2–15 秒（`:17-27`）
      - `splitNarration`：句末标点 `。！？!?\\n` 切句 → 单句超 100 字再按 `，,；;、` 切 → 最多 40 镜
        （`:18-62`）
      - `splitNarrationIntoShots`：首镜 hook / 末镜 cta / 其余 demo，`description` 与
        `voiceover` 都填原句（`:30-36`、`:73-77`）
  · 竞品 `src/app/api/project/[id]/import-script/route.ts:33-70`：切不出分镜报 422；
    存入 scripts 表并置为当前版本（版本号 = 现有最大 + 1）。

**三处必须改（不改就跑不通，逐条写明理由）**：
  1. 单镜时长竞品 2–15 秒，我们分镜硬约束是 **4–15 秒**（`output_storyboard.md`「硬性约束」/
     `drama_format.py:116-117` C12）→ 下限抬到 4。短片段的"少说了一秒"由后续 TTS 实际时长兜底，
     和竞品注释里「durations are planning estimates」同一口径。
  2. 竞品分镜没有 `product` 字段（它靠素材匹配），我们分镜必须标商品出镜（C8 ≥ 一半）。
     手写稿没有这个标注，默认**全部 true** —— 项目本身就是商品短剧、商品图整包随片带，
     用户上分镜页还能改。这是补字段，不是替顾客改文案。
  3. 景别/运镜竞品给 `camera: "static"`、无景别；我们两栏都进提示词 → 补中性值「中景 / 固定」。

**不许做的**：不改写用户文案、不补台词、不猜卖点。切分只是排版。
"""
from __future__ import annotations

import re

#: 句末标点（竞品 `script-import.ts:18` 逐字）
SENTENCE_DELIM = re.compile(r"[。！？!?\n]+")
#: 次级标点（竞品 `:20`）
SUBCLAUSE_DELIM = re.compile(r"[，,；;、]+")
#: 单镜字数上限（竞品 `:22`）
MAX_CHARS_PER_SHOT = 100
#: 最多几镜（竞品 `:24`）
MAX_SHOTS = 40
#: 我们单镜时长区间（C12），竞品是 2–15
MIN_SEC, MAX_SEC = 4, 15

_CJK = re.compile(r"[一-鿿぀-ヿ가-힯]")


def has_cjk(text: str) -> bool:
    return bool(_CJK.search(text or ""))


def estimate_duration_sec(text: str) -> float:
    """竞品 `:26-27`：CJK 5 字/秒、拉丁 14 字/秒，四舍五入后夹区间。"""
    cps = 5 if has_cjk(text) else 14
    sec = round(len(text or "") / cps)
    return float(min(MAX_SEC, max(MIN_SEC, sec)))


def split_narration(text: str) -> list[str]:
    """竞品 `:30-62`：先按句末标点切，超长句再按次级标点累积切，最多 40 段。"""
    sentences = [s.strip() for s in SENTENCE_DELIM.split(text or "")]
    pieces: list[str] = []
    for sent in sentences:
        if not sent:
            continue
        if len(sent) <= MAX_CHARS_PER_SHOT:
            pieces.append(sent)
            continue
        buf = ""
        for sub in SUBCLAUSE_DELIM.split(sent):
            sub = sub.strip()
            if not sub:
                continue
            # +1 是拼接时补的那个「，」，保证拼完不越界（竞品 `:49-53`）
            if buf and len(buf) + 1 + len(sub) > MAX_CHARS_PER_SHOT:
                pieces.append(buf)
                buf = sub
            else:
                buf = f"{buf}，{sub}" if buf else sub
        if buf:
            pieces.append(buf)
    return pieces[:MAX_SHOTS]


def split_into_shots(text: str) -> list[dict]:
    """切成分镜（我们的 schema）。首 hook / 末 cta / 其余 demo（竞品 `:64-81`）。"""
    pieces = split_narration(text)
    n = len(pieces)
    shots = []
    for i, p in enumerate(pieces, 1):
        if i == 1:
            kind, purpose = "hook", "钩子：用这句开场抓住人"
        elif i == n:
            kind, purpose = "cta", "行动号召：给出下一步"
        else:
            kind, purpose = "demo", "演示：推进故事"
        shots.append({
            "id": i,
            "duration": estimate_duration_sec(p),
            "framing": "中景",
            "camera": "固定",
            "description": p,
            "dialogue": p,
            "product": True,
            "purpose": f"{kind}｜{purpose}",
        })
    return shots


def plan(text: str) -> dict:
    """切分结果 + 汇总。切不出东西时 `shots` 为空（调用方按竞品 `route.ts:35` 报 422）。"""
    shots = split_into_shots(text)
    return {
        "shots": shots,
        "count": len(shots),
        "total_seconds": round(sum(s["duration"] for s in shots), 1),
    }


#: 竞品导进来的脚本在 scripts 表里 `styleType: "custom"`（`import-script/route.ts:59`）
STYLE_TYPE = "custom"
