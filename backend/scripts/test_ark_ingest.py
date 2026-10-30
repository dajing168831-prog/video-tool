"""素材库（asset://）的离线自检：签名、人脸判据、额度回收。

不碰网络：create_group/create_asset/get_asset/delete_group 全部用假实现。
运行：python scripts/test_ark_ingest.py
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import ark_assets, ark_ingest, face_check  # noqa: E402

PASS = FAIL = 0


def check(name: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}: {got}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want={want!r}")


def _auth(sig: str) -> str:
    return sig["Authorization"]


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：一轮只跑一家
    from _model_gate import sel_or_exit as _sel
    _sel()
    work = Path(tempfile.mkdtemp(dir="D:/tmp", prefix="ark_ingest_"))
    try:
        return _run(work)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _run(work: Path) -> int:
    print("== V4 签名 ==")
    body = b'{"Id":"asset-1"}'
    args = dict(ak="AKTEST", sk="SKTEST",
                now=datetime(2026, 10, 21, 9, 30, tzinfo=timezone.utc))
    h1 = ark_assets.sign_headers("POST", {"Action": "GetAsset",
                                         "Version": "2024-01-01"}, body, **args)
    h2 = ark_assets.sign_headers("POST", {"Action": "GetAsset",
                                         "Version": "2024-01-01"}, body, **args)
    h3 = ark_assets.sign_headers("POST", {"Action": "GetAsset",
                                         "Version": "2024-01-01"},
                                 b'{"Id":"asset-2"}', **args)
    check("同输入同签名", _auth(h1), _auth(h2))
    check("换 body 换签名", _auth(h1) == _auth(h3), False)
    # 官方文档的 Authorization 示例逐字带的这四段（content-type 少签会被判 401）
    check("鉴权头格式", bool(re.fullmatch(
        r"HMAC-SHA256 Credential=AKTEST/20261021/cn-beijing/ark/request, "
        r"SignedHeaders=content-type;host;x-content-sha256;x-date, "
        r"Signature=[0-9a-f]{64}",
        _auth(h1))), True)
    # 冻结值：这组输入下的签名已和火山官方 SDK（volcengine 1.0.229 的 SignerV4）
    # 逐字节对齐过，冻结在这里是为了防止以后"顺手改"改坏规范串
    check("签名冻结值",
          _auth(h1).rsplit("Signature=", 1)[1],
          "bbab749c00322842c3f25ba315dbeef7262e0ae24da4f67e577dce95c67f94d7")
    check("X-Content-Sha256 是 body 摘要",
          h1["X-Content-Sha256"], hashlib.sha256(body).hexdigest())
    check("X-Date 用 UTC", h1["X-Date"], "20261021T093000Z")
    q = ark_assets._canonical_query({"Version": "2024-01-01", "Action": "GetAsset"})
    check("查询串按 key 升序", q, "Action=GetAsset&Version=2024-01-01")
    q2 = ark_assets._canonical_query({"Name": "a b/c", "Action": "X"})
    check("查询串做 RFC3986 编码", q2, "Action=X&Name=a%20b%2Fc")

    print("== 列表接口的参数形状 ==")
    seen: list[tuple[str, dict]] = []
    real_call = ark_assets._call
    ark_assets._call = lambda action, body, **kw: (seen.append((action, body)),
                                                  {"Items": []})[1]
    try:
        ark_assets.list_groups()
        ark_assets.list_assets("group-1")
    finally:
        ark_assets._call = real_call
    # 官方要求 Filter.GroupType 必填，传空 Filter 会被 400 拒
    check("列组带 Filter.GroupType",
          seen[0][1].get("Filter", {}).get("GroupType"), "AIGC")
    check("列素材带组 ID",
          seen[1][1].get("Filter", {}).get("GroupIds"), ["group-1"])

    print("== 人脸判据 ==")
    face_img = work / "face.png"
    flat_img = work / "flat.png"
    import cv2
    import numpy as np

    # 直接拿真实样本不可搬，就画：有眼鼻嘴的近似人脸 vs 纯色块
    img = np.full((256, 256, 3), 200, np.uint8)
    cv2.circle(img, (128, 110), 70, (150, 170, 200), -1)
    cv2.circle(img, (100, 95), 8, (20, 20, 20), -1)
    cv2.circle(img, (156, 95), 8, (20, 20, 20), -1)
    cv2.ellipse(img, (128, 150), (22, 10), 0, 0, 180, (30, 30, 30), 2)
    cv2.imwrite(str(face_img), img)
    cv2.imwrite(str(flat_img), np.full((256, 256, 3), 128, np.uint8))
    check("模型在 → 能给出结论", face_check.detect_faces(face_img) >= 0, True)
    check("纯色图判无脸", face_check.has_face(flat_img), False)
    real = Path("data/clone/394fdd58ffa24f2ab197ca5a11e8d370/subject.jpg")
    if real.exists():
        check("真人照判有脸", face_check.has_face(real), True)

    print("== 素材库：判据 / 缓存 / 回收（假接口）==")
    ark_ingest.REG_PATH = work / "ark_assets.json"
    ark_ingest._last_stale_check = 0.0
    calls = {"group": 0, "asset": 0, "delete": 0}
    ids = {"n": 0}

    def fake_group(name, description=""):
        calls["group"] += 1
        return f"group-{calls['group']}"

    def fake_asset(group_id, url, kind="Image", name=""):
        calls["asset"] += 1
        ids["n"] += 1
        return f"asset-{ids['n']}"

    def fake_active(asset_id, **kw):
        return "Active"

    def fake_delete(gid):
        calls["delete"] += 1

    ark_assets.create_group = fake_group
    ark_assets.create_asset = fake_asset
    ark_assets.wait_active = fake_active
    ark_assets.delete_group = fake_delete
    ark_ingest.available = lambda: True
    from app.services import oss

    oss.upload = lambda p, **kw: f"https://cdn.test/{Path(p).name}"

    vid = work / "seg.mp4"
    vid.write_bytes(b"fake-video")
    r1 = ark_ingest.prepare_video(vid, "cidA")
    check("视频直接入库", r1, "asset://asset-1")
    r2 = ark_ingest.prepare_video(vid, "cidA")
    check("同单同文件命中缓存", r2, "asset://asset-1")
    check("缓存命中不重复建素材", calls["asset"], 1)

    # 🩸 2026-10-25 实测（`861efd72`）：视频入库被审核拒（CreateAsset 处理后 Failed，
    # 原因 `InputVideoSensitiveContentDetected`），但 `_ingest` 把异常吞了 →
    # error.json 写成「素材库=ok（已入素材库或不适用）」，**假绿**，真相只在日志里。
    # 判据：失败必须把原因交回调用方。
    def bad_active(_aid):
        raise ark_assets.ArkAssetError(
            "素材处理失败（Failed）：InputVideoSensitiveContentDetected")

    ark_assets.wait_active = bad_active
    seg2 = work / "seg2.mp4"
    seg2.write_bytes(b"another-video")
    rep: dict = {}
    r5 = ark_ingest.prepare_video(seg2, "cidA", report=rep)
    check("入库失败 → 返回空（调用方退回 URL）", r5, "")
    check("入库失败 → 原因写进 report（不许假绿）",
          "InputVideoSensitiveContentDetected" in str(rep.get("failed")), True)
    ark_assets.wait_active = fake_active

    before = calls["asset"]
    r3 = ark_ingest.prepare_image(flat_img, "cidA")
    check("无脸的图不入库", r3, "")
    check("无脸的图不建素材", calls["asset"], before)
    r4 = ark_ingest.prepare_image(real if real.exists() else face_img, "cidA")
    check("有脸的图入库", r4.startswith("asset://"), True)

    d = ark_ingest._load()
    check("素材与组都记了账", (len(d["assets"]), len(d["groups"])), (2, 1))
    check("组挂在 cid 上", list(d["groups"].values())[0]["cid"], "cidA")

    print("== 视频硬限制：超了就干脆不入库 ==")
    import subprocess

    from app.services.media import ffmpeg_path

    def mk(name: str, seconds: float, size: str = "720x1280") -> Path:
        p = work / name
        subprocess.run([ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i", f"color=c=blue:s={size}:d={seconds}:r=30",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(p)], check=True)
        return p

    # 区间 1.8–30.2 秒是 2026-10-21 用火山自己的接口实测出来的（网上传的 2–15 是错的）
    ok5 = ark_ingest._video_fits(mk("ok5.mp4", 5))
    check("5 秒 720p 可入库", ok5[0], True)
    ok30 = ark_ingest._video_fits(mk("ok30.mp4", 30))
    check("30 秒可入库（实测上限 30.2）", ok30[0], True)
    bad31 = ark_ingest._video_fits(mk("bad31.mp4", 31))
    check("31 秒被拦下", bad31[0], False)
    check("拦下时说明原因", "1.8–30.2s" in bad31[1], True)
    low = ark_ingest._video_fits(mk("low.mp4", 5, "320x240"))
    check("低分辨率不拦（那条没核实过）", low[0], True)

    print("== 额度：LRU 腾位置 ==")
    from app.core.config import settings

    real_cap = settings.ark_asset_max
    object.__setattr__(settings, "ark_asset_max", 2)
    try:
        # 再来一单：额度只剩 0，必须把 cidA 的老组腾掉
        ark_ingest.prepare_video(vid, "cidB")
        d = ark_ingest._load()
        check("老组被回收", d["groups"]["group-1"]["recycled"], True)
        check("老素材跟着标回收",
              all(a["recycled"] for a in d["assets"].values()
                  if a["group"] == "group-1"), True)
        check("新组仍可用", d["groups"]["group-2"]["recycled"], False)
    finally:
        object.__setattr__(settings, "ark_asset_max", real_cap)

    print("== 出片终态回收 ==")
    # 先开第三单，验"只回收自己这一单"（否则这条判据对空集恒真）
    c_vid = work / "cidC.mp4"
    c_vid.write_bytes(b"fake-video-c")
    ark_ingest.prepare_video(c_vid, "cidC")
    d = ark_ingest._load()
    g_c = [gid for gid, g in d["groups"].items() if g["cid"] == "cidC"]
    check("第三单建了新组", len(g_c), 1)
    n = ark_ingest.recycle_render("cidB")
    check("按 cid 删组", n > 0, True)
    d = ark_ingest._load()
    check("本单的组都标回收",
          all(g["recycled"] for g in d["groups"].values() if g["cid"] == "cidB"), True)
    check("别单的组不动", d["groups"][g_c[0]]["recycled"], False)

    print("== 闲置回收：1 小时节流 ==")
    c0 = calls["delete"]
    ark_ingest._last_stale_check = time.time()
    n2 = ark_ingest.recycle_stale()
    check("节流内不动手", (n2, calls["delete"]), (0, c0))

    print(f"\n{PASS}/{PASS + FAIL} 通过")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
