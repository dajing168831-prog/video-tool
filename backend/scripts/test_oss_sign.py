"""用阿里云官方 SDK（oss2）交叉验证我们的 OSS V1 签名实现。

为什么要对：签名错的表现就是 403 SignatureDoesNotMatch，而真实凭据只能试一次；
先用 SDK 在本地对死，把"凭据对不对"和"算法对不对"两个变量拆开。

oss2 只在跑这个测试时需要，运行时不依赖。
    python scripts/test_oss_sign.py
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import oss as mine  # noqa: E402

try:
    import oss2
    from oss2.http import Request
except ImportError:
    print("未安装 oss2，跳过交叉验证（pip install oss2 后重跑）")
    raise SystemExit(2)

AK_ID, AK_SEC, BUCKET = "testAK", "testSECRET", "dajinggl-img"
DATE = "Tue, 21 Oct 2026 04:00:00 GMT"
CT = "video/mp4"

CASES = [
    ("单个 x-oss 头", "uploads/a.mp4", {"x-oss-cache-control": "public, max-age=31536000"}),
    ("无 x-oss 头", "uploads/b.mp4", {}),
    ("两个 x-oss 头（验证字典序）", "uploads/c.mp4", {
        "x-oss-cache-control": "public, max-age=31536000",
        "x-oss-object-acl": "public-read",
    }),
    ("值里带逗号和空格", "uploads/d e.mp4", {"x-oss-cache-control": "public, max-age=1, s-maxage=2"}),
]


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：一轮只跑一家
    from _model_gate import sel_or_exit as _sel
    _sel()
    auth = oss2.Auth(AK_ID, AK_SEC)
    ok = 0
    for name, key, hdrs in CASES:
        h = dict(hdrs)
        h["Date"] = DATE
        h["Content-Type"] = CT
        req = Request("PUT", f"https://{BUCKET}.oss-cn-guangzhou.aliyuncs.com/{key}",
                      headers=h, data=b"")
        sts = auth._ProviderAuth__get_string_to_sign(req, BUCKET, key)
        official = base64.b64encode(
            hmac.new(AK_SEC.encode(), sts.encode(), hashlib.sha1).digest()
        ).decode()
        our = mine._sign("PUT", key, CT, DATE, AK_ID, AK_SEC, BUCKET, hdrs).split(":", 1)[1]
        same = official == our
        ok += same
        print(f"  {'ok  ' if same else 'FAIL'} {name}")
        if not same:
            ours = (f"PUT\n\n{CT}\n{DATE}\n"
                    f"{mine._canonical_oss_headers(hdrs)}/{BUCKET}/{key}")
            print(f"    官方 StringToSign: {sts!r}")
            print(f"    我们 StringToSign: {ours!r}")
    print(f"\n{ok}/{len(CASES)} 与官方 SDK 一致")
    return 0 if ok == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
