"""画面 Look 预设（14 种全局光线色调）—— 纯数据。

出处：clipforge `src/lib/look-presets.ts`，数据由 `scripts/import_clipforge_presets.py`
原样抽成 `app/data/look_presets.json`（**不是重打一遍**，避免抄错字）。

为什么要有：一条片子里每一镜的光线必须是同一个，否则接起来像拼的。
每个预设给两段提示词（竞品原设计，`look-presets.ts:15-18`）：
  - `image`：加到**关键帧出图**提示词后面（光 + 色调 + 背景 + 景深）
  - `motion`：加到**图生视频**提示词后面的**短**光锚（动效提示词要镜头主导，长风格块会稀释动作）
  - `opener`：只有 `real` 组的预设才有，**前置**在图生视频提示词最前面
    （竞品实测：前置的"相机身份"短语比中段的画质词更能把模型推向手机实拍分布）
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data" / "look_presets.json"

#: 「不指定全局 Look」的哨兵值（竞品 `look-presets.ts:43`）
LOOK_NONE = "none"


@lru_cache(maxsize=1)
def _all() -> tuple[dict, ...]:
    return tuple(json.loads(DATA.read_text(encoding="utf-8")))


def all_presets() -> list[dict]:
    return list(_all())


def get(look_id: str | None) -> dict | None:
    if not look_id or look_id == LOOK_NONE:
        return None
    for p in _all():
        if p.get("id") == look_id:
            return p
    return None


def valid(look_id: str | None) -> bool:
    return get(look_id) is not None


def image_suffix(look_id: str | None) -> str:
    """加到关键帧出图提示词后面的那段（竞品 `lookImageSuffix`）。"""
    p = get(look_id)
    return str(((p or {}).get("image") or {}).get("zh") or "")


def motion_prefix(look_id: str | None) -> str:
    """前置在图生视频提示词最前面（只有 real 组有）。"""
    p = get(look_id)
    return str(((p or {}).get("opener") or {}).get("zh") or "")


def motion_suffix(look_id: str | None) -> str:
    """加到图生视频提示词后面（短光锚）。"""
    p = get(look_id)
    return str(((p or {}).get("motion") or {}).get("zh") or "")


def look_of_doc(doc: dict) -> str:
    """从项目文档取全局 Look id；没选模板 = 空串（= 不加任何风格词）。

    出图（`drama_grid.prompt`）与出片（`drama_film.build_prompt`）共用这一份 ——
    两处各写一遍会慢慢写岔。
    """
    tpl = ((doc or {}).get("template") or {}).get("template") or {}
    look = str(tpl.get("look") or "")
    return look if valid(look) else ""


def public() -> list[dict]:
    """给界面的列表：id / 名称 / 示例文字（出图那段，用来预览）。"""
    return [{"id": p.get("id"),
             "name": (p.get("name") or {}).get("zh") or p.get("id"),
             "sample": ((p.get("image") or {}).get("zh") or "")[:60],
             "group": p.get("group") or "styled"} for p in _all()]
