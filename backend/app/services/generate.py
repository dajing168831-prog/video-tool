"""镜头取样时间（原片某一镜在哪一帧取样最不容易取到切点）。

2026-11-02：静帧重绘链路（图生图 → 图生视频）已整条删除，
这里只剩 `seek_time` —— 镜头检测与其它取样路径共用。
"""
from __future__ import annotations

def seek_time(start: float | None, end: float | None,
              total: float = 0.0) -> float:
    """这一镜该在源片的第几秒抽帧 —— **一定落在片长内**。

    🩸 2026-10-25/26 两单出片失败：配方里的镜头表带着越界条目
    （`start 15.787 / end 23.994`、`start 23.994 / end 15.117`），
    按中点 19.89s 去抽一个只有 15.12s 的片子 —— ffmpeg 一帧都不出，
    `extract_frame` 抛错，整单作废。成因见 `scene._frame_times` 的注释。
    这里只做**兜底**：正常配方本来就在范围内，触发就说明上游有病，日志会喊。
    """
    s = float(start or 0.0)
    e = float(end or 0.0)
    t = s + max(0.5, e - s) / 2.0
    # 余量 0.2s：实测 `total - 0.05` 仍然取不到帧（末帧 PTS 15.0667 < 片长 15.117，
    # 按 15.067 去 seek 一帧都没有），留出一帧以上的余量才稳。
    if total > 0 and t > total - 0.2:
        return max(0.0, total - 0.2)
    return t
