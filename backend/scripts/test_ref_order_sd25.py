# -*- coding: utf-8 -*-
"""Seedance 2.5 的**图号契约**：`@图片N` 到底是不是第 N 张 —— 零费用。

🩸 为什么单独一个文件（2026-10-28 主人第二次纠正「各家管各家」）：
   这条链**共用**（`ref_plan` / `ark.edit_body` / `_prepare`），但**断言按型号写**。
   `test_whole_wiring.py` 是跨通道接线文件，它自己的文件头写着「绿灯不能当任何
   一家已验收的证据」—— 把 2.5 的编号断言塞进去就是串联，已撤。
   这里全部用 2.5 的真实型号 id 跑，2.0 / H3 的编号归它们各自的文件。

🩸 为什么这条最要紧：前十七节判据全在问「提示词写得对不对」。真正致命的是
   **提示词全对、发过去的图全错位** —— 本地一条都不会红，只能等出了片人眼看脸
   （这条路已经判错过两次）。

覆盖：① 不重排 ② 顺序由槽位定（不看 refs 的插入顺序）③ 跳过的槽位不占图号
      ④ 图号永不超界 ⑤ 素材 ID 与本地图混用 ⑥ 端到端（真正发出去的那几个路径）

用法： python scripts/test_ref_order_sd25.py --model volc25
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BACK = Path(__file__).resolve().parents[1]
if str(BACK) not in sys.path:
    sys.path.insert(0, str(BACK))
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from _model_gate import sel_or_exit  # noqa: E402

sel_or_exit(only="volc25")

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.core.config import settings  # noqa: E402
from app.services import ark, edit_spec, video_edit  # noqa: E402
from app.services.media import ffmpeg_path  # noqa: E402

MID = "doubao-seedance-2-5-260628"
WANT = ["person", "product", "scene", "wardrobe", "style_ref"]

PASS = FAIL = 0


def check(name: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}: {got}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want={want!r}")


REC = {"source": {"duration": 8.0, "width": 360, "height": 640, "fps": 25.0},
       "shots": [{"i": 0, "start": 0.0, "end": 8.0, "dur": 8.0}]}

SPEC5 = edit_spec.normalize({
    "person": True, "person_desc": "白衬衫男人",
    "product": True, "product_desc": "陶瓷杯",
    "scene": True, "scene_desc": "咖啡馆内景",
    "wardrobe": True, "wardrobe_desc": "米色风衣",
    "style_ref": True,
})


def main() -> int:
    work = Path(tempfile.mkdtemp(dir="D:/tmp", prefix="reford25_"))
    real_key = settings.ark_api_key
    object.__setattr__(settings, "ark_api_key", "k")
    try:
        return _run(work)
    finally:
        object.__setattr__(settings, "ark_api_key", real_key)
        shutil.rmtree(work, ignore_errors=True)


def _run(work: Path) -> int:
    fake = {k: work / f"slot_{k}.jpg" for k in WANT}
    for p in fake.values():
        subprocess.run([ffmpeg_path(), "-hide_banner", "-loglevel", "error",
                        "-y", "-f", "lavfi", "-i",
                        "color=c=gray:s=400x600:d=1", "-frames:v", "1", str(p)],
                       check=True)

    print("== ① `edit_body` 只按给的顺序追加，绝不排序 ==")
    body = ark.edit_body(
        "换人", video_url="https://x/1.mp4",
        ref_images=["asset://10", "asset://2", "asset://1", "asset://3"],
        model=MID)
    imgs = [x["image_url"]["url"] for x in body["content"]
            if x.get("type") == "image_url"]
    check("混序素材 ID 不被排序（10 排在 2 前面）", imgs,
          ["asset://10", "asset://2", "asset://1", "asset://3"])
    check("content 首个元素是提示词文本", body["content"][0]["type"], "text")

    print("\n== ② 视频侧与图片侧互不串位 ==")
    body2 = ark.edit_body(
        "换人", video_url="https://x/src.mp4", ref_images=["asset://a"],
        ref_videos=["https://x/style1.mp4", "https://x/style2.mp4"], model=MID)
    check("母版 + 2 条参考视频排在所有图之前",
          [x["role"] for x in body2["content"]
           if x.get("type") in ("video_url", "image_url")],
          ["reference_video", "reference_video", "reference_video",
           "reference_image"])

    print("\n== ③ 单数 ref_image / ref_asset 追加在列表末尾（不插队）==")
    body3 = ark.edit_body(
        "换人", video_url="https://x/1.mp4",
        ref_images=["asset://a", "asset://b"],
        ref_image=work / "slot_person.jpg", ref_asset="asset://z", model=MID)
    u3 = [x["image_url"]["url"] for x in body3["content"]
          if x.get("type") == "image_url"]
    check("前两张仍是列表原序", u3[:2], ["asset://a", "asset://b"])
    check("ref_asset 排最后", u3[-1].startswith("asset://z"), True)
    check("单数 ref_image 变成 base64", u3[2].startswith("data:image/"), True)

    print("\n== ④ 顺序由 SLOT_ORDER 定，不看 refs 的插入顺序 ==")
    # 用户上传顺序 ≠ 槽位顺序：如果实现按 `refs.items()` 遍历，这里会彻底乱
    plan = video_edit._prepare(
        rec=REC, spec=SPEC5,
        refs={k: fake[k] for k in reversed(WANT)},
        channel="volc", model=MID)
    check("槽位顺序 = SLOT_ORDER", plan["slots"], WANT)
    check("ordered 与 slots 等长", len(plan["ordered"]), len(plan["slots"]))
    check("逐项对应：第 i 张就是第 i 个槽位那张图",
          [Path(x) for x in plan["ordered"]], [fake[k] for k in WANT])

    print("\n== ⑤ 跳过的槽位不占图号 ==")
    plan2 = video_edit._prepare(
        rec=REC,
        spec=edit_spec.normalize({"person": True, "person_desc": "白衬衫男人",
                                  "product": True, "product_desc": "陶瓷杯"}),
        refs={"person": work / "slot_person.jpg"},
        channel="volc", model=MID)
    check("没给图的槽位不进 slots", plan2["slots"], ["person"])
    nums2 = sorted({int(m.group(1)) for m in
                    re.finditer(r"@图片\s*(\d+)", plan2["prompt"])})
    check("提示词里没有 @图片2（不发出去的图不编号）",
          [n for n in nums2 if n > 1], [])

    print("\n== ⑥ 图号永不超界（三种组合统一扫）==")
    oob: list[str] = []
    for name, chg, refs in (
        ("只换人", {"person": True, "person_desc": "白衬衫男人"},
         {"person": work / "slot_person.jpg"}),
        ("五槽全开", None, fake),
        ("人+产品（乱序插入）",
         {"person": True, "person_desc": "白衬衫男人",
          "product": True, "product_desc": "陶瓷杯"},
         {"product": work / "slot_product.jpg",
          "person": work / "slot_person.jpg"}),
    ):
        p = video_edit._prepare(rec=REC,
                                spec=(SPEC5 if chg is None
                                      else edit_spec.normalize(chg)),
                                refs=refs, channel="volc", model=MID)
        nums = {int(m.group(1)) for m in
                re.finditer(r"@图片\s*(\d+)", p["prompt"])}
        if len(p["slots"]) != len(p["ordered"]):
            oob.append(f"{name}: slots/ordered 长度不一致")
        if nums and max(nums) > len(p["slots"]):
            oob.append(f"{name}: 提示词指到 @图片{max(nums)}，"
                       f"实际只发 {len(p['slots'])} 张")
    check("所有组合：等长且不超界", oob, [])

    print("\n== ⑦ 素材 ID 与本地图混用：位置不变、前缀剥掉 ==")
    plan3 = video_edit._prepare(
        rec=REC,
        spec=edit_spec.normalize({"person": True, "person_desc": "白衬衫男人",
                                  "product": True, "product_desc": "陶瓷杯"}),
        refs={"product": work / "slot_product.jpg"},
        subject_asset="asset-abc123", channel="volc", model=MID)
    check("素材 ID 保持第 1 张（不带 asset: 前缀）",
          [plan3["ordered"][0], Path(plan3["ordered"][1]).name],
          ["asset-abc123", "slot_product.jpg"])

    print("\n== ⑧ 端到端：整片重制真正传给模型的路径 ==")
    video = work / "src.mp4"
    subprocess.run([ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "color=c=navy:s=360x640:d=8:r=25",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)],
                   check=True)
    got: list = []

    def fake_edit(prompt, *, video_url, out, ref_images=None, **_kw):
        got.append([Path(x).name for x in (ref_images or [])])
        shutil.copy(video, out)
        return out

    from app.services import clone_store, ark_ingest

    real = (ark.edit_video, video_edit._public_url, clone_store.task_dir,
            ark_ingest.available)
    ark.edit_video = fake_edit
    video_edit._public_url = lambda seg, cid: "https://example.test/seg.mp4"
    clone_store.task_dir = lambda cid: work / "tasks" / cid
    ark_ingest.available = lambda: False
    try:
        video_edit.replace_whole(
            video, REC, cid="a1" * 16, spec=SPEC5,
            # 又一次反着给
            refs=dict(reversed(list(fake.items()))),
            channel="volc", model=MID, workdir=work / "r1")
    finally:
        (ark.edit_video, video_edit._public_url, clone_store.task_dir,
         ark_ingest.available) = real
    check("真正发出去的 5 张 = 槽位顺序", got[0] if got else [],
          [f"slot_{k}.jpg" for k in WANT])

    print(f"\n{PASS}/{PASS + FAIL} 通过")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
