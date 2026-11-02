"""换画面结构化规格的自检 —— **跨型号共用的那一段**（不发网络请求、不花钱）。

这里只放**不属于任何一家**的规则：默认值、normalize、图片编号、通道判定、
槽位编号、分辨率、静帧重绘、混剪提示词。三个型号各自的自检在
`test_edit_spec_sd20.py` / `test_edit_spec_sd25.py` / `test_edit_spec_h3.py`。

运行入口只有一个：`python scripts/test_edit_spec.py --model <型号>`
（它会先跑本文件，再跑点名的那一家）。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import edit_spec  # noqa: E402

PASS = FAIL = 0


def check(name: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}: {got}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want={want!r}")


# ---- 跨型号共用的输入 --------------------------------------------------------
p = edit_spec.normalize({"person": True})
no_person = edit_spec.normalize({"product": True, "scene": True})
only_face = edit_spec.normalize({"person": True})
ppl2 = [{"id": "P1", "present": True, "desc_zh": "穿红裙的女生",
         "desc_en": "the woman in red"},
        {"id": "P2", "present": True, "desc_zh": "穿蓝衬衫的男生",
         "desc_en": "the man in blue"}]
p1 = {"id": "P1", "present": True, "desc_en": "the woman in a red dress"}
p2 = {"id": "P2", "present": True, "desc_en": "the man in a black suit"}
ex = edit_spec.normalize({"person": True, "extra": "画面更亮一点"})


def run() -> None:
    print("== 默认值 ==")
    d = edit_spec.defaults()
    check("默认没有任何换项", edit_spec.has_change(d), False)
    check("默认保什么全开", all(d["keep"].values()), True)
    check("默认声音=tts", d["audio"], "tts")
    # 成片直接发出去，不做「AI 生成」角标 —— 这个开关已整个删掉，不再有这回事
    check("角标概念已移除", "watermark" in d, False)

    print("== normalize ==")
    flat = edit_spec.normalize({"person": True, "person_desc": "白衬衫女孩",
                                "keep": {"camera": False}, "audio": "mix"})
    check("扁平写法进 change", flat["change"]["person"], True)
    check("扁平写法描述保留", flat["change"]["person_desc"], "白衬衫女孩")
    check("keep 只改指名项", flat["keep"]["camera"], False)
    check("keep 其余仍开", flat["keep"]["motion"], True)
    check("声音 mix", flat["audio"], "mix")
    nested = edit_spec.normalize({"change": {"product": True, "product_desc": "咖啡杯"}})
    check("嵌套写法进 change", nested["change"]["product"], True)
    check("不认的风格退回空", edit_spec.normalize({"style": "赛博朋克"})["change"]["style"], "")
    check("不认的声音退回 tts", edit_spec.normalize({"audio": "nope"})["audio"], "tts")
    # 前端就算还传老字段也不能凭空造出角标
    check("老字段传进来也不加角标", "watermark" in edit_spec.normalize({"watermark": True}), False)
    check("垃圾输入不报错", edit_spec.normalize("xxx")["change"]["person"], False)

    print("== 图片编号 ==")
    # 🩸 编号按**真的发出去的槽位**算，不按"用户勾了哪些"：勾了没给图的槽位会被跳过，
    # 号一旦按勾选算，提示词就会指着一张不存在的图（见 video_edit._prepare）。
    sp = edit_spec.normalize({"person": True, "product": True, "scene": True})
    slots_all = [s for s, _ in edit_spec.ref_order(sp, person_asset="asset-1")]
    check("素材ID占人物=图片1", edit_spec.image_index(slots_all),
          {"person": 1, "product": 2, "scene": 3})
    check("本地人物图也是图片1",
          edit_spec.image_index([s for s, _ in edit_spec.ref_order(sp)]),
          {"person": 1, "product": 2, "scene": 3})
    check("不换人时产品=图片1",
          edit_spec.image_index([s for s, _ in edit_spec.ref_order(no_person)]),
          {"product": 1, "scene": 2})
    check("场景没图就只剩人物占 1 号", edit_spec.image_index(["person"]),
          {"person": 1})

    print("== 通道判定 ==")
    check("有 asset → asset", edit_spec.subject_kind(p, person_asset="x"), "asset")
    check("本地人物图 → file", edit_spec.subject_kind(p), "file")
    check("只换产品 → none", edit_spec.subject_kind(no_person), "none")

    print("== 多槽位编号 ==")
    both = edit_spec.normalize({"product": True, "scene": True,
                                "product_desc": "咖啡杯", "scene_desc": "街边"})
    bp = edit_spec.compile_prompt("volc", both)
    check("产品拿图1", "产品替换为@图片1" in bp, True)
    check("场景拿图2", "背景替换为@图片2" in bp, True)


    print("== 分辨率 ==")
    check("指定合法档位就照用", edit_spec.resolution_for("volc", edit_spec.normalize({"resolution": "1080p"}), auto="720p"), "1080p")
    check("火山收到 2K → 降到 1080p", edit_spec.resolution_for("volc", edit_spec.normalize({"resolution": "2K"}), auto="720p"), "1080p")
    check("MiniMax 收到 1080p → 升到 2K", edit_spec.resolution_for("minimax", edit_spec.normalize({"resolution": "1080p"}), auto="768P"), "2K")
    check("认不出的档位退回 auto", edit_spec.resolution_for("volc", edit_spec.normalize({"resolution": "8K"}), auto="720p"), "720p")
