# -*- coding: utf-8 -*-
"""F5 调试用的后端启动器（VSCode `.vscode/launch.json`）。

跟 `scripts/with_user_env.py` 的区别：
  · `with_user_env.py` 用 `subprocess` 转调一条命令 —— 调试器只挂在最外层，
    F5 的断点进不去 `app/` 里的业务代码；
  · 这里把 HKCU 里的凭据**注入当前进程**，再 **in-process** 起 uvicorn，
    所以 F5 能直接在 `app/api/clone.py` 之类的地方断点。

🩸 变量名单不在本文件重复维护：直接复用 `with_user_env.NAMES`。
   以前抄两份，加一个 key 就得改两个地方，漏一个就是"配了但不生效"。
🩸 凭据只在进程环境里，不打印、不落盘。

用法：
    F5（推荐）  → .vscode/launch.json 的「▶ 后端 (uvicorn 8911)」
    命令行      → python scripts/debug_server.py [port]
"""
from __future__ import annotations

import os

import sys
import winreg
from pathlib import Path

BACK = Path(__file__).resolve().parents[1]
for p in (BACK, BACK / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from with_user_env import NAMES  # noqa: E402


def inject_env() -> int:
    """把 HKCU\\Environment 里的凭据塞进当前进程，返回注入了几个。"""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment")
    except OSError:
        print("[debug] 读不到 HKCU\\Environment —— 凭据不会注入，出片会失败")
        return 0
    n = 0
    with key:
        for name in NAMES:
            try:
                os.environ[name] = winreg.QueryValueEx(key, name)[0]
                n += 1
            except FileNotFoundError:
                continue
    return n


def free_port(port: int) -> None:
    """杀掉占着这个端口的旧后端 —— 否则 uvicorn 绑不上，F5 直接报 10048。

    🩸 2026-10-28：**不要在这里用 `subprocess` 调 netstat/taskkill**。
      实测 F5 下卡死在 `[debug] 已注入 13 个环境变量` 之后不再打印 ——
      debugpy 附加时子进程管道会被拦住，命令永远不返回，用户看到的就是
      "F5 起来了但没有日志"。改用 psutil 直接读连接表 + 结束进程，全程不走子进程。
    """
    try:
        import psutil
    except Exception as e:  # noqa: BLE001
        print(f"[debug] 没有 psutil（{e}）：端口被占用的话请先停掉旧后端", flush=True)
        return
    me = os.getpid()
    try:
        conns = psutil.net_connections(kind="tcp")
    except Exception as e:  # noqa: BLE001
        print(f"[debug] 读连接表失败（忽略）：{e}", flush=True)
        return
    for c in conns:
        if not c.laddr or c.laddr.port != port:
            continue
        if c.status != psutil.CONN_LISTEN or not c.pid or c.pid == me:
            continue
        try:
            psutil.Process(c.pid).kill()
            print(f"[debug] 已结束占用 {port} 的旧进程 {c.pid}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[debug] 结束进程 {c.pid} 失败（{e}）", flush=True)


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8911
    n = inject_env()
    os.environ.setdefault("VT_CLONE_WORKERS", "4")
    print(f"[debug] 已注入 {n} 个环境变量；端口 {port}", flush=True)
    free_port(port)
    print("[debug] 正在导入 uvicorn 与 app.main…", flush=True)
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
