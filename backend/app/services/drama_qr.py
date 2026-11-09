"""店铺二维码（E3）—— 本地生成可扫的 PNG，零生成费、零第三方服务。

出处：clipforge `src/lib/shop-link.ts:1-45`（UTM 组装）、`src/lib/shop-qr.ts:1-41`
（尺寸/边距/颜色/容错等级 M）。**逻辑逐字照抄，只有两处本地化**：

1. 🩸 竞品的 PNG 靠 `qrcode` 库的 PIL/PyPNG 写入器 —— 本机 venv **两者都没装**。
   这里自己写 PNG（zlib + struct，约 30 行），只要求 `qrcode` 内核算矩阵。
2. 默认 `utm_campaign` 用本项目名 `product-drama`（竞品写死自家品牌 `clipforge`）。

二维码**本身不拦**（私域/印刷是正当用途）；是否允许**烧进成片**由
`drama_platform.get_off_site_qr_policy(platform)` 按平台判——抖音是 block。
"""
from __future__ import annotations

import math
import re
import struct
import zlib
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

import qrcode

#: 默认活动名（本地化：竞品是自带品牌名）
DEFAULT_CAMPAIGN = "product-drama"
#: 尺寸与边距（竞品 `shop-qr.ts:15-21`）
DEFAULT_SIZE = 512
MIN_SIZE, MAX_SIZE = 128, 2048
DEFAULT_MARGIN = 2
#: 容错等级（竞品 `shop-qr.ts:38`）
ERROR_LEVEL = qrcode.ERROR_CORRECT_M

_HEX = re.compile(r"^#?[0-9a-fA-F]{6}$")


class QrError(ValueError):
    pass


def build_shop_link(shop_url: str | None, *, platform: str | None = None,
                    affiliate_code: str | None = None,
                    campaign: str | None = None) -> str:
    """给店铺链接挂 UTM（竞品 `shop-link.ts:24-45` 逐字口径）。

    保留原有 query/hash；空值、非 http(s)、解析不了 → 返回 ""（调用方直接跳过）。
    """
    raw = (shop_url or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
    except ValueError:
        return ""
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return ""
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    plat = (platform or "").strip().lower()
    if plat:
        query["utm_source"] = plat
    query["utm_medium"] = "short_video"
    query["utm_campaign"] = (campaign or "").strip() or DEFAULT_CAMPAIGN
    aff = (affiliate_code or "").strip()
    if aff:
        query["aff"] = aff
    return urlunsplit((parts.scheme, parts.netloc, parts.path,
                       urlencode(query), parts.fragment))


# ---------------------------------------------------------------------------
# 纯 Python PNG 写入（无 PIL / 无 PyPNG）
# ---------------------------------------------------------------------------
def _chunk(tag: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def _rgb(hex_color: str, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    text = (hex_color or "").strip()
    if not _HEX.match(text):
        return fallback
    text = text.lstrip("#")
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def matrix_png(matrix: list[list[bool]], out: Path, *, box: int, margin: int,
               dark: tuple[int, int, int] = (0, 0, 0),
               light: tuple[int, int, int] = (255, 255, 255)) -> tuple[int, int]:
    """把 0/1 矩阵写成 PNG。返回 (宽, 高)。"""
    modules = len(matrix)
    side_modules = modules + margin * 2
    side = side_modules * box
    rows: list[bytes] = []
    for y in range(side):
        my = y // box - margin
        row = bytearray(b"\x00")  # filter type 0
        for x in range(side):
            mx = x // box - margin
            on = 0 <= my < modules and 0 <= mx < modules and matrix[my][mx]
            row.extend(dark if on else light)
        rows.append(bytes(row))
    raw = b"".join(rows)
    ihdr = struct.pack(">IIBBBBB", side, side, 8, 2, 0, 0, 0)  # 8bit RGB
    blob = (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(raw, 9))
            + _chunk(b"IEND", b""))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(blob)
    return side, side


def generate(shop_url: str, out: Path, *, platform: str | None = None,
             affiliate_code: str | None = None, campaign: str | None = None,
             size: int = DEFAULT_SIZE, margin: int = DEFAULT_MARGIN,
             dark: str = "#000000", light: str = "#FFFFFF") -> str:
    """生成二维码 PNG，返回**实际编码进去的 URL**（UTM 后的）。

    链接无效 → 抛 `QrError`（没东西可编码，不许画一张空码）。
    """
    link = build_shop_link(shop_url, platform=platform,
                           affiliate_code=affiliate_code, campaign=campaign)
    if not link:
        raise QrError("无效的商品链接，无法生成二维码")
    side_px = min(MAX_SIZE, max(MIN_SIZE, int(round(size or DEFAULT_SIZE))))
    margin = max(0, int(round(margin)))
    qr = qrcode.QRCode(error_correction=ERROR_LEVEL,
                       border=margin, box_size=1)
    qr.add_data(link)
    qr.make(fit=True)
    matrix = [[bool(v) for v in row] for row in qr.get_matrix()]
    # qrcode 的 get_matrix 已经含 border；这里再按「整数像素/模块」放大到目标尺寸附近。
    # 🩸 只做整数除法会让实际尺寸**掉到请求值以下**（128 → 123），所以两头都要兜：
    #    低于下限就向上取整，超过上限就向下取整。
    modules = max(1, len(matrix))
    box = max(1, side_px // modules)
    if box * modules < MIN_SIZE:
        box = math.ceil(MIN_SIZE / modules)
    if box * modules > MAX_SIZE:
        box = max(1, MAX_SIZE // modules)
    out = Path(out)
    matrix_png(matrix, out, box=box, margin=0,
               dark=_rgb(dark, (0, 0, 0)), light=_rgb(light, (255, 255, 255)))
    return link
