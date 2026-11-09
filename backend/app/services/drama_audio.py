"""BGM 上传与混音策略（D2）—— 纯策略，不发请求。

出处：clipforge `src/lib/audio-mix.ts:1-18`（**逐字抽规则**）+
`src/app/api/project/[id]/bgm/route.ts:1-45`（上传白名单 / 20MB 上限）。
混音滤镜本身在 `drama_compose.py`，这里只管「音量该是多少、要不要闪避」，
免得两个地方各写一套数。

🩸 为什么默认 0.18 而不是 1：这是带货口播片，人声第一；BGM 是垫底，
    用户能调但只能在 [0.05, 0.40] 之间调（竞品同一组上下限）。
"""
from __future__ import annotations

from pathlib import Path

#: 竞品 `audio-mix.ts:2-4`
DEFAULT_BGM_VOLUME = 0.18
MIN_BGM_VOLUME = 0.05
MAX_BGM_VOLUME = 0.4

#: 竞品 `bgm/route.ts:8`（MIME）+ `:18`（扩展名）
ALLOWED_MIME = {"audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav",
                "audio/aac", "audio/mp4", "audio/x-m4a"}
ALLOWED_EXT = {".mp3", ".wav", ".aac", ".m4a"}
MAX_BYTES = 20 * 1024 * 1024

#: 尾音淡出默认 3 秒（竞品 `composer.ts:330`：防止 aloop 被硬切）
DEFAULT_FADE_OUT = 3.0


def normalize_volume(value, fallback: float = DEFAULT_BGM_VOLUME) -> float:
    """把音量夹进安全区间并保留两位（竞品 `audio-mix.ts:6-12`）。"""
    try:
        base = float(value)
    except (TypeError, ValueError):
        base = float(fallback)
    if not (base == base) or base in (float("inf"), float("-inf")):
        base = DEFAULT_BGM_VOLUME
    safe = min(MAX_BGM_VOLUME, max(MIN_BGM_VOLUME, base))
    return round(safe * 100) / 100


def resolve_mix(volume=None, duck=None, *, has_voice: bool) -> dict:
    """返回该用的 `{volume, duck}`（竞品 `audio-mix.ts:14-18`）。

    闪避**只在对白轨存在时**才有意义；没有对白就强制关掉，
    否则 sidechain 的 key 不存在，滤镜图会直接报错。
    """
    return {
        "volume": normalize_volume(volume),
        "duck": bool(has_voice and (duck is not False)),
    }


def ext_ok(filename: str | None, content_type: str | None = None) -> bool:
    """扩展名与 MIME **任一命中**即可（竞品 `bgm/route.ts:19-22`：
    有些上传拿不到准确 MIME，只卡 MIME 会把正常文件拒掉）。"""
    ext = Path(str(filename or "")).suffix.lower()
    mime = (content_type or "").split(";")[0].strip().lower()
    return ext in ALLOWED_EXT or mime in ALLOWED_MIME
