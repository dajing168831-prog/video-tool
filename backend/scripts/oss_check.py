"""OSS 连通性自检：传一个探测文件，再从公网取回来。

跑法（凭据在 Windows 用户环境变量里，不落文件）：
    python scripts/with_user_env.py python scripts/oss_check.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.core.config import settings  # noqa: E402
from app.services import oss  # noqa: E402

print("endpoint   :", settings.oss_endpoint)
print("bucket     :", settings.oss_bucket)
print("public base:", settings.oss_public_base)
print("key id     :", (settings.oss_access_key_id[:6] + "…") if settings.oss_access_key_id else "(未配)")
print("key secret :", "已配" if settings.oss_access_key_secret else "(未配)")
print()

if not oss.available():
    print("❌ OSS 未配置，缺 VT_OSS_ACCESS_KEY_ID / VT_OSS_ACCESS_KEY_SECRET")
    raise SystemExit(2)

res = oss.check()
if res.get("ok"):
    print(f"✅ 上传并读取成功: {res['url']}  (HTTP {res['status']})")
else:
    print(f"❌ 失败: {res.get('error') or res}")
    raise SystemExit(1)
