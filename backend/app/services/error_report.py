"""一次失败 → 一个 json，**把查错要用的东西全放进去**。

🩸 为什么要有这个文件（2026-10-23 主人原话：「把报错数据写清楚！不然老是
来来回回查」）：
以前出片失败只留一行
    「第 1 段生成失败：创建编辑任务失败 HTTP 400: {...}」
—— 看不出是哪一段、多长、走的是 asset:// 还是公网 URL、素材库是不是先拒过、
请求 id 是多少。要查清得回头翻 uvicorn 日志，而日志一重启就被覆盖。

落盘位置：`<workdir>/errors/<stage>_<timestamp>.json`
同一份内容也会**拼进异常消息**（只放关键几项），让界面上直接能看。
"""
from __future__ import annotations

import json
import logging
import time
import traceback
from pathlib import Path

log = logging.getLogger(__name__)

# 段区间/提示词这类长字段保留到这个长度；超出只截断显示，json 里放全文
_SHOW = 160


def _short(v, n: int = _SHOW) -> str:
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
    return s if len(s) <= n else s[:n] + "…"


def dump(workdir, *, stage: str, **fields) -> Path:
    """把一个阶段的失败证据写成 json，返回路径。自身绝不抛错。"""
    try:
        d = Path(workdir) / "errors"
        d.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        p = d / f"{stage}_{ts}.json"

        err = fields.pop("error", None)
        rec: dict = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "stage": stage}
        rec.update({k: v for k, v in fields.items()})

        # 异常对象拆成三段：类型 / 消息 / 它自带的 detail（原始响应体）
        if isinstance(err, BaseException):
            rec["error"] = {
                "type": type(err).__name__,
                "message": str(err),
                "detail": getattr(err, "detail", None) or {},
                "traceback": traceback.format_exc()[-4000:],
            }
        elif err is not None:
            rec["error"] = err

        p.write_text(json.dumps(rec, ensure_ascii=False, indent=2, default=str),
                     encoding="utf-8")
        return p
    except Exception as e:  # noqa: BLE001
        log.warning("错误证据落盘失败（不影响主流程）：%s", e)
        return Path("")


def brief(rec_path: Path, **kv) -> str:
    """拼进异常消息的那一小段：只放**看一眼就知道往哪查**的字段。"""
    bits = []
    for k, v in kv.items():
        if v in (None, "", [], {}):
            continue
        bits.append(f"{k}={_short(v, 60)}")
    s = "｜" + " ".join(bits) if bits else ""
    if rec_path:
        s += f"｜完整证据: {rec_path}"
    return s
