"""用 Windows 用户级环境变量跑一条命令。

为什么需要它：凭据只存在 HKCU 的用户环境变量里（不落项目文件），
但当前 shell 是更早启动的，看不到后来写入的变量。这个脚本从注册表读出来
塞进子进程环境，密钥既不出现在命令行里、也不落盘。

用法：
  python scripts/with_user_env.py <任意命令...>
"""
from __future__ import annotations

import os
import subprocess
import sys
import winreg

NAMES = [
    "VT_VOLC_API_KEY", "VT_ASR_PROVIDER", "VT_TTS_PROVIDER",
    "VT_VOLC_ASR_RESOURCE", "VT_VOLC_TTS_RESOURCE", "VT_VOLC_TTS_SPEAKER",
    "VT_VOLC_UID", "VT_ENABLED_PLATFORMS", "VT_CLONE_WORKERS",
    # 代理出口（2026-10-29 开放 X 时加：X 必须走代理，见 config.py:70）
    "VT_PROXY", "VT_YOUTUBE_PROXY",
    "VT_ARK_API_KEY", "VT_ARK_IMAGE_MODEL", "VT_ARK_VIDEO_MODEL",
    "VT_CLONE_MAX_REGEN",
    # 双通道换画面
    "MINIMAX_API_KEY", "VT_MINIMAX_API_KEY", "VT_MINIMAX_BASE",
    "VT_MINIMAX_VIDEO_MODEL", "VT_MINIMAX_RESOLUTION",
    "VT_ARK_VIDEO_EDIT_MODEL", "VT_PUBLIC_BASE_URL", "VT_URL_SECRET",
    "VT_SOURCE_URL_TTL", "VT_CLONE_CHANNEL",
    # OSS（火山参考视频的公网地址走这里）
    "VT_OSS_ENDPOINT", "VT_OSS_BUCKET", "VT_OSS_ACCESS_KEY_ID",
    "VT_OSS_ACCESS_KEY_SECRET", "VT_OSS_PUBLIC_BASE", "VT_OSS_PREFIX",
    "VT_OSS_ACL",
]


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    env = dict(os.environ)
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment")
    except OSError:
        key = None
    if key is not None:
        for n in NAMES:
            try:
                env[n] = winreg.QueryValueEx(key, n)[0]
            except FileNotFoundError:
                continue
    return subprocess.call(sys.argv[1:], env=env)


if __name__ == "__main__":
    raise SystemExit(main())
