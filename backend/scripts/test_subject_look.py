"""主体图的外观描述必须认得出是哪张图。

判据（全部只看效果，不看实现）：
  1. 描述和图对得上 → 提示词里写出这句外观
  2. 描述和图对不上 → 提示词退回「shown there」的纯图号写法（不许拿别人的外观去赌）
  3. 没有指纹 / 描述为空 / 文件缺失 → 同样退回纯图号写法
  4. 一句话都写不出来时，提示词里不能出现「with 。」这种断句

为什么这条必须盯着：2026-10-23 19:42 那条 H3 出片，主体定义里那句外观
（"bun … mole … black collared top"）和当时那张参考图对不上，却和原片人物很像，
出片里那个人一帧都没换。宁可少一句描述，也不能写错一句。

运行：python scripts/test_subject_look.py
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import clone_store, edit_spec, video_edit  # noqa: E402

PASS = FAIL = 0
TMP = Path(tempfile.mkdtemp(prefix="looktest_", dir="D:/tmp"))


def check(name: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}: {got!r}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want={want!r}")


def check_true(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


def make_task(name: str, image: bytes,
              desc: dict | None) -> str:
    """在 D 盘临时目录里造一个任务目录（真的按 clone_store 的路径布局）。"""
    cid = hashlib.sha1(name.encode()).hexdigest()[:32]
    d = clone_store.task_dir(cid)
    d.mkdir(parents=True, exist_ok=True)
    img = clone_store.ref_path(cid, "person")
    img.write_bytes(image)
    p = clone_store.subject_desc_path(cid)
    if desc is None:
        p.unlink(missing_ok=True)
    else:
        p.write_text(json.dumps(desc, ensure_ascii=False), encoding="utf-8")
    return cid


def compile_for(cid: str) -> str:
    """按真实路径编译一次 H3 提示词，只看主体定义那一行。"""
    img = clone_store.ref_path(cid, "person")
    spec = edit_spec.defaults()
    spec["change"]["person"] = True
    spec["change"]["person_id"] = "P2"
    look = video_edit._look_for(img)
    src = {"id": "P2", "desc_en": "young woman in a Qing-style robe",
           "position": "right"}
    return edit_spec.compile_prompt(
        "minimax", edit_spec.normalize(spec), person_asset="",
        model="MiniMax-H3-Max", source_people=[dict(src, present=True)],
        desc_by_id={"P2": src["desc_en"]}, audio_ref=False,
        slots=["person"], subject_look=look)


def subj_line(prompt: str) -> str:
    for line in prompt.splitlines():
        if line.startswith("<Subject 1> is the person in <Picture 1>"):
            return line
    return ""


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：一轮只跑一家
    from _model_gate import sel_or_exit as _sel
    _sel(only='h3')
    img = b"\x89PNG\r\n\x1a\nFAKE-IMAGE-BYTES"
    sha = hashlib.sha1(img).hexdigest()
    good = {"desc_zh": "黑色短寸，浅蓝夹克", "desc_en": "Black buzz cut, light blue jacket",
            "_image_sha1": sha}

    print("== 描述和图对得上 ==")
    cid = make_task("match", img, good)
    check("读出来的描述", video_edit._look_for(clone_store.ref_path(cid, "person")),
          {"zh": "黑色短寸，浅蓝夹克", "en": "Black buzz cut, light blue jacket"})
    line = subj_line(compile_for(cid))
    # 🩸 2026-10-24 22:35 纠正：H3 官方 `ref-en:51` 的骨架就是列具体特征
    # （`<Subject 1> is the young woman in <Picture 1>, with long dark hair,
    # a blue cardigan, …`），所以描述对得上就要写进去。
    check_true("描述对得上就写进提示词", "Black buzz cut" in line, line)
    check_true("按官方骨架写", line.startswith("<Subject 1> is the person in <Picture 1>, with "), line)

    print("== 描述和图对不上（本次修的那条）==")
    other = {"desc_zh": "发髻高挽，黑色立领", "desc_en": "Tight bun, black collared top",
             "_image_sha1": hashlib.sha1(b"another photo").hexdigest()}
    cid2 = make_task("mismatch", img, other)
    check("读出来是空", video_edit._look_for(clone_store.ref_path(cid2, "person")), {})
    line2 = subj_line(compile_for(cid2))
    check_true("提示词退回纯图号写法",
               "with the face, hairstyle, body type and clothing shown there" in line2,
               line2)
    check_true("别人的外观没混进来", "Tight bun" not in line2, line2)

    print("== 没有指纹 / 描述为空 / 文件缺失 ==")
    cid3 = make_task("nofp", img, {"desc_zh": "x", "desc_en": "y"})
    check("没有指纹按无描述处理",
          video_edit._look_for(clone_store.ref_path(cid3, "person")), {})
    cid4 = make_task("empty", img, {"desc_zh": "", "desc_en": "", "_image_sha1": sha})
    check("描述为空按无描述处理",
          video_edit._look_for(clone_store.ref_path(cid4, "person")), {})
    cid5 = make_task("file", img, None)
    check("没有描述文件按无描述处理",
          video_edit._look_for(clone_store.ref_path(cid5, "person")), {})
    check("图不存在也不崩",
          video_edit._look_for(clone_store.ref_path(cid5, "person").with_name("nope.jpg")), {})

    print("== 一句话都写不出来时，提示词不能断句 ==")
    for name, c in (("对不上", cid2), ("无文件", cid5)):
        line = subj_line(compile_for(c))
        check_true(f"{name}：不出现「with 。」", "with ." not in line, line)
        check_true(f"{name}：主体定义以句号收尾", line.endswith("."), line)

    print("== 发出去了以后，还能不能查清「当时送的是哪张图」==")
    # 🩸 两次换脸复盘都卡在这里：参考图在出片后被换成另一张，磁盘上只剩文件名。
    # 所以请求快照必须留下图的内容哈希 + 那句外观描述有没有真的写进提示词。
    work = TMP / "work"
    work.mkdir(parents=True, exist_ok=True)
    imgp = TMP / "subject_case.jpg"
    imgp.write_bytes(img)
    video_edit._write_request(
        work, 7, ch="minimax",
        plan={"model": "MiniMax-H3", "resolution": "480P",
              "look": {"zh": "黑色短寸", "en": "Black buzz cut"}},
        dur=6.0, prompt="p", video_url="file://seg.mp4",
        refs=[imgp, "asset://asset-123"], has_audio=True)
    snap = json.loads((work / "request_007.json").read_text(encoding="utf-8"))
    check("记下了参考图的内容哈希", snap["ref_sha1"][0], sha[:16])
    check("素材 ID 原样留下", snap["ref_sha1"][1], "asset://asset-123")
    check("提示词里没有这句 → 记为没用", snap["subject_look"]["used"], False)
    check("记下的是哪一句", snap["subject_look"]["text"], "Black buzz cut")

    video_edit._write_request(
        work, 8, ch="minimax",
        plan={"model": "MiniMax-H3", "resolution": "480P", "look": {}},
        dur=6.0, prompt="p", video_url="file://seg.mp4",
        refs=[imgp], has_audio=False)
    snap8 = json.loads((work / "request_008.json").read_text(encoding="utf-8"))
    check("没写描述时记为没用", snap8["subject_look"]["used"], False)
    check("没写描述时不留文字", snap8["subject_look"]["text"], "")

    shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{PASS}/{PASS + FAIL} 通过")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
