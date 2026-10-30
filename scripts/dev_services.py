#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
开发依赖服务管理（PostgreSQL + Redis）
======================================
用 DETACHED_PROCESS 启动，进程独立于调用它的 shell，
不会被任务生命周期误杀。

用法:
  python dev_services.py start|stop|status
"""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

PG_HOME = Path(r"D:\apps\pgsql\pgsql\bin")
PG_DATA = Path(r"D:\apps\pgsql\data")
PG_LOG = Path(r"D:\apps\pgsql\pg.log")
REDIS_HOME = Path(r"D:\apps\redis\Redis-8.10.2-Windows-x64-msys2")
REDIS_LOG = Path(r"D:\apps\redis\redis.log")

DETACHED = 0x00000008  # DETACHED_PROCESS
NEW_GROUP = 0x00000200  # CREATE_NEW_PROCESS_GROUP


def port_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.5)
        return s.connect_ex((host, port)) == 0


def spawn(cmd, log_path: Path):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    f = open(log_path, "ab")
    subprocess.Popen(
        cmd,
        stdout=f,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=DETACHED | NEW_GROUP,
        close_fds=True,
    )


def start_pg():
    if port_open(5432):
        print("PostgreSQL 已在运行 (5432)")
        return True
    # 清理残留 pid（强制终止后常见）
    pidfile = PG_DATA / "postmaster.pid"
    if pidfile.exists():
        try:
            pid = int(pidfile.read_text().splitlines()[0])
            os.kill(pid, 9)
        except Exception:
            pass
        try:
            pidfile.unlink()
        except Exception:
            pass
        time.sleep(1)
    print("启动 PostgreSQL ...")
    # pg_ctl 的 -l 已经写 PG_LOG，stdout 必须写另一个文件，否则文件被占用启动失败
    spawn(
        [str(PG_HOME / "pg_ctl.exe"), "-D", str(PG_DATA), "-l", str(PG_LOG), "start"],
        PG_LOG.parent / "pg_ctl.out.log",
    )
    for _ in range(20):
        time.sleep(1)
        if port_open(5432):
            print("PostgreSQL OK (5432)")
            return True
    print("PostgreSQL 启动失败，看日志:", PG_LOG)
    return False


def start_redis():
    if port_open(6379):
        print("Redis 已在运行 (6379)")
        return True
    print("启动 Redis ...")
    spawn(
        [str(REDIS_HOME / "redis-server.exe"), "--port", "6379",
         "--save", "", "--appendonly", "no"],
        REDIS_LOG,
    )
    for _ in range(10):
        time.sleep(1)
        if port_open(6379):
            print("Redis OK (6379)")
            return True
    print("Redis 启动失败，看日志:", REDIS_LOG)
    return False


def stop_pg():
    subprocess.run(
        [str(PG_HOME / "pg_ctl.exe"), "-D", str(PG_DATA), "-m", "fast", "stop"],
        capture_output=True,
    )
    print("PostgreSQL 已停止")


def stop_redis():
    cli = REDIS_HOME / "redis-cli.exe"
    subprocess.run([str(cli), "-p", "6379", "shutdown"], capture_output=True)
    print("Redis 已停止")


def status():
    print(f"PostgreSQL 5432: {'UP' if port_open(5432) else 'DOWN'}")
    print(f"Redis      6379: {'UP' if port_open(6379) else 'DOWN'}")


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    if action == "start":
        ok1 = start_pg()
        ok2 = start_redis()
        sys.exit(0 if (ok1 and ok2) else 1)
    elif action == "stop":
        stop_pg()
        stop_redis()
    else:
        status()
