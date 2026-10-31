# -*- coding: utf-8 -*-
"""Seedance 2.5 延长（B5）判据 —— 零费用，不出片。

🩸 2026-10-28：`test_extend.py` 锁死 `only="volc20"`，**2.5 的延长从没被测过**。
   而 2.5 的延长提示词是**自己一套官方模板**（`sd25-pe:651-697` 六句），
   不是 2.0 那一句 —— 两家混着测就等于没测。

本文件只验 2.5（`doubao-seedance-2-5-260628`）。2.0 的延长归 `test_extend.py`。

覆盖：空内容拦截 / 秒数夹取（2.5 上限 30）/ 方向归一 / 官方六句模板 /
      **用户 content 里的台词与符号**（`sd25-pe:141` 引号转 `{}`、
      `:867` 四个合法符号原样保留）/ 换行合并 / 接缝 0 帧 / 适配器接线。

用法： python scripts/test_extend_sd25.py --model volc25
"""
from __future__ import annotations

import re
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

from app.services import clone_store as store  # noqa: E402
from app.services import extend as X  # noqa: E402
from app.services import models  # noqa: E402

MID = "doubao-seedance-2-5-260628"

_fail = 0
_n = 0


def check(name: str, got, want) -> None:
    global _fail, _n
    _n += 1
    ok = got == want
    if not ok:
        _fail += 1
    print(f"{'✅' if ok else '🔴'} {name}"
          + ("" if ok else f"\n     实际 {got!r} / 期望 {want!r}"))


def _run(**kw):
    """调一次 `extend.run`，把 `store.render_dir` 指到临时目录（零污染）。"""
    tmp = Path(tempfile.mkdtemp(prefix="ext25_", dir="D:/tmp"))
    old = store.render_dir
    store.render_dir = lambda cid, rid: (tmp / rid)  # noqa: ARG005
    try:
        return X.run(base=tmp / "没有这个文件.mp4", progress=None, **kw)
    finally:
        store.render_dir = old
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)


def _prompt(direction: str, content: str) -> str:
    """走**适配器**（生产入口），不直接调 `volc25._extend_prompt`。"""
    return models.adapter_for(model=MID).extend_prompt(direction, content)


def main() -> int:
    print("== 空内容：花钱之前拦住 ==")
    for label, c in (("空字符串", ""), ("纯空格", "   "), ("换行+空格", "\n\t  ")):
        try:
            _run(cid="__probe__", rid="r1", direction="back", seconds=5,
                 content=c, model=MID, resolution="720p", with_audio=False)
            got = "没拦住"
        except RuntimeError as e:  # noqa: PERF203
            got = str(e)
        check(f"内容{label} → 当场拒绝",
              "续出来的这段里发生什么" in got, True)

    print("\n== 秒数：2.5 单段上限 30 ==")
    check("60s 被收到 30s", X.clamp_seconds(60, MID), 30)
    # 🩸 下限是 **4s 不是 2s**：`extend.MIN_SEC = 2` 只是"延长段至少 2s 才有意义"，
    #   真正生效的是 `max(MIN_SEC, spec["min_sec"])` —— 2.5 的 `min_sec` 是 4
    #   （单段 4–30s）。第一版判据写成 2，是尺子错不是产品错。
    check("1s 被抬到 2.5 自己的下限 4s", X.clamp_seconds(1, MID), 4)
    check("5s 原样", X.clamp_seconds(5, MID), 5)

    print("\n== 方向与官方六句模板 ==")
    back = _prompt("back", "她转身走进电梯")
    front = _prompt("front", "她从电梯里走出来")
    check("向后：触发关键词「向后延长@视频1」",
          "向后延长@视频1" in back, True)
    check("向前：触发关键词「向前延长@视频1」",
          "向前延长@视频1" in front, True)
    check("未知方向按向后处理",
          "向后延长@视频1" in _prompt("sideways", "x"), True)
    # 官方 `sd25-pe:643`「同一主体始终只有一个连续实例，不得复制、分裂或生成
    # 第二个相同主体」+ `:645`「最终 Prompt **必须明确写出**上述单一实例和拓扑
    # 要求，不能只在内部分析中检查后省略」→ 两个方向都必须带这句。
    both = [("向后", back), ("向前", front)]
    check("两个方向都写了「同一主体…不重复、不分裂」",
          [n for n, p in both if "同一主体" in p and "不重复、不分裂" in p],
          ["向后", "向前"])
    check("两个方向都写了「保持…连续」",
          [n for n, p in both if "延长过程中保持人物身份与服装" in p],
          ["向后", "向前"])
    check("向前多写「只属于原视频后续的…不得提前出现」",
          ("只属于原视频后续的角色" in front,
           "只属于原视频后续的角色" in back), (True, False))
    # 官方模板里的 `<主体姿态与朝向>` 是**槽位占位符**，`sd25-pe:324` 要求全部替换
    check("占位符尖括号没有漏进提示词",
          [n for n, p in both if re.search(r"<[^<>]{2,}>", p)], [])

    print("\n== 用户 content：台词与符号（官方 `sd25-pe:141` / `:867`）==")
    # ① 带引号的台词 → `{}`：官方原文「用户只给出带引号的台词片段…最终对白
    #    只能写成 `{你一个外人}`」
    check("裸引号 + 说话动作 → 转 {}",
          "男人转身说{你好啊}然后走开" in _prompt("back", '男人转身说"你好啊"然后走开'),
          True)
    check("中文弯引号同样转 {}",
          "她低声说{别走}" in _prompt("back", "她低声说“别走”，然后关灯"), True)
    # ② 名词引用不该被标成台词（标了模型会念出来）
    check("没有说话动作的引号 → 只去引号、不标 {}",
          '把标题改成限时优惠' in _prompt("back", '把标题改成"限时优惠"')
          and "{限时优惠}" not in _prompt("back", '把标题改成"限时优惠"'), True)
    # ③ 用户自己打的 `{}` 原样保留（官方符号表就是这么用的）
    check("手打 {} 原样保留",
          "男人说{你好啊}" in _prompt("back", "男人说{你好啊}然后走开"), True)
    # ④ `【】` 字幕 / `<>` 音效 / `()` 音乐 都是官方合法符号，一个都不许清
    keep = [
        ("字幕", "画面上出现【三年后】三个字", "【三年后】"),
        ("音效", "远处传来<玻璃碎裂>的声音", "<玻璃碎裂>"),
        ("音乐", "背景响起（钢琴曲）", "（钢琴曲）"),
    ]
    for name, c, tok in keep:
        check(f"{name}标记原样保留", tok in _prompt("back", c), True)

    print("\n== 换行：模板整句插入，不能把句子切断 ==")
    multi = _prompt("back", "第一行\n第二行")
    check("换行被并成逗号", "第一行，第二行" in multi, True)
    check("没有残留换行插在模板句中间",
          any("\n第" in ln for ln in multi.splitlines()), False)
    check("多行全文都在（没丢内容）",
          ("第一行" in multi and "第二行" in multi), True)

    print("\n== 接缝：2.5 官方说拼接处无痕迹，不裁帧 ==")
    check("2.5 接缝裁帧 = (0, 0)", X.seam_frames(MID), (0, 0))

    print("\n== 适配器接线：2.5 真指向自己的延长实现 ==")
    ad = models.adapter_for(model=MID)
    check("extend_prompt / extend_submit 都接上了",
          (ad.extend_prompt is not None, ad.extend_submit is not None),
          (True, True))
    check("extend_transition 为真（2.5 支持两段视频补全）",
          bool(ad.caps.extend_transition), True)

    print("\n== 参考图：延长能带图（官方 `sd25-guide:93`「@image1 的角色从天而降」）==")
    # ① 请求体：图片按给的顺序追加在待延长视频之后，不排序、不去重
    from app.services import ark

    body = ark.extend_body(
        "向后延长@视频1。" + "随后，@图片1的女人入画。", video_url="https://x/s.mp4",
        ref_images=["asset://b", "asset://a"], model=MID)
    got = [x["image_url"]["url"] for x in body["content"]
           if x.get("type") == "image_url"]
    check("请求体里图片顺序 = 给的顺序（不排序）", got,
          ["asset://b", "asset://a"])
    check("待延长视频永远是第 1 条",
          [x["type"] for x in body["content"]][:2], ["text", "video_url"])

    # ② 提交层：`_extend_submit` 真的把图透传到 `ark.extend_video`
    from app.services import video_edit as _ve
    from app.services.models import volc25 as _v25

    seen_img: list = []
    real_xv, real_url = ark.extend_video, _ve._public_url

    def fake_xv(prompt, *, video_url, out, ref_images=None, **_kw):
        seen_img.append(list(ref_images or []))
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_bytes(b"x")
        return Path(out)

    ark.extend_video = fake_xv
    _ve._public_url = lambda seg, cid: "https://example.test/s.mp4"
    try:
        _v25._extend_submit(
            prompt="向后延长@视频1。", ref_src=Path("D:/tmp/不存在.mp4"),
            seg=Path(tempfile.mkdtemp(dir="D:/tmp", prefix="ext25s_")) / "o.mp4",
            model=MID, resolution="720p", seconds=5, with_audio=False,
            cid="x", ref_images=[Path("a.jpg"), Path("b.jpg")])
    finally:
        ark.extend_video, _ve._public_url = real_xv, real_url
    check("2.5 提交层把 2 张图原序透传出去", seen_img, [[Path("a.jpg"),
                                                          Path("b.jpg")]])

    # ③ 🩸 2026-10-31：原来这里测「2.0 的延长不支持带图 → 当场拒绝」。2.0 的适配器
    #   已随复刻视频下架归档、不再注册 ⇒ 传它的 ID 会回落成 2.5（**支持**带图），
    #   这条断言没有承载型号了，而且回落路径会走到读文件把脚本崩掉。
    #   2.5 带图的正向行为由上面两条（原序透传 / 视频永远第 1 条）覆盖。
    #   ⚠️ 将来若再有型号声明「延长不支持带图」，这条要按那个型号恢复。

    print("\n== 预设续法：只有 2.5 有（`sd25-pe:528` 的四个类别）==")
    modes = models.adapter_for(model=MID).caps.extend_modes
    check("2.5 的四个续法键", sorted(modes),
          ["action", "pause", "reaction", "scene"])
    check("每个都有一句可填进模板的话",
          [k for k, v in modes.items() if not str(v).strip()], [])
    # 🩸 官方 `:528`「只能延长动作过程、反应、停顿或场景过渡…**不得新增人物、
    #   主线事件或故事结果**」—— 四句话里出现"新增/加入/出现一个新"就是违规
    check("四句话里没有「新增事件」这种越界表述",
          [k for k, v in modes.items()
           if any(w in v for w in ("新增", "新人物", "新事件", "突然出现"))], [])
    for k, txt in modes.items():
        p = _prompt("back", txt)
        check(f"续法 {k} 能拼进延长模板", txt in p, True)

    # 别家一个都没有 → 前端不显示这一块，界面回到自由文本框
    # （旧 2.0 型号已下架、回落到 2.5，不再算「别家」）
    for other in ("MiniMax-H3-Max",):
        check(f"{other} 没有预设续法",
              dict(models.adapter_for(model=other).caps.extend_modes), {})

    # 未知续法：必须当场说清楚，不许悄悄当成"没写内容"
    try:
        _run(cid="__probe__", rid="r_mode", direction="back", seconds=5,
             content="", content_mode="不存在的续法", model=MID,
             resolution="720p", with_audio=False)
        bad_mode = "没拦住"
    except RuntimeError as e:
        bad_mode = str(e)
    check("未知续法 → 当场拒绝", "没有「不存在的续法」这种续法" in bad_mode, True)

    # 自己写的内容优先：content 非空时 mode 整个忽略
    try:
        _run(cid="__probe__", rid="r_mode2", direction="back", seconds=5,
             content="她转身走进电梯", content_mode="action", model=MID,
             resolution="720p", with_audio=False)
        pri = "居然跑完了"
    except Exception as e:  # noqa: BLE001
        pri = f"{type(e).__name__}: {e}"
    check("有内容 → 过的不是续法那道闸",
          "续法" not in pri, True)

    print(f"\n{_n - _fail}/{_n} 通过")
    return 1 if _fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
