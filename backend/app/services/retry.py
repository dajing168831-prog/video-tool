"""厂商接口的重试：只重试"可以再来一次"的错误。

多人同时测的时候最容易撞的是这两类：
  429  并发/频率超限 —— 服务端**明确没收下**这单，重试不会重复扣费
  5xx  网关抖动 —— 同上

所以这里**只重试 HTTP 状态码**，不重试网络超时/连接异常：
请求可能已经到达对方并建了任务，盲目重发等于花两次钱。超时一律原样抛出去。

400/401/403 是参数或权限问题，重试一百次结果一样，立刻抛。
"""
from __future__ import annotations

import logging
import time

log = logging.getLogger(__name__)

RETRY_STATUS = {429, 500, 502, 503, 504}
# 退避：2s → 4s → 8s → 16s。厂商的并发上限通常按秒/分钟滑动，20 秒足够让出坑位
_BACKOFF = (2.0, 4.0, 8.0, 16.0)


def post(client, url: str, **kw):
    """POST 并重试可恢复的错误。调用方自己判断 r.status_code。"""
    last = None
    for i, wait in enumerate((0.0,) + _BACKOFF):
        if wait:
            log.warning("接口 %s 可重试错误 %s，%.0fs 后重试（第 %d 次）",
                        url, getattr(last, "status_code", "?"), wait, i)
            time.sleep(wait)
        try:
            r = client.post(url, **kw)
        except Exception as e:  # noqa: BLE001
            # 网络层异常不重试：请求可能已经被对方收下
            log.warning("接口 %s 请求异常（不重试）：%s", url, e)
            raise
        if r.status_code not in RETRY_STATUS:
            return r
        last = r
    return last
