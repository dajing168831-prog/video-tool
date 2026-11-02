# -*- coding: utf-8 -*-
"""「先出第 1 段，确认后再出全部」的判据（`max_segments`）。

判什么（都是**行为/结构**，不是"文件里有没有这句话"）：
  1. 参数能从 API 模型一路传到最底层 `_gen_spans`（五层签名都认）；
  2. 只跑部分时**绝不拼接** —— 拼接函数必须在预览返回之后才可能被调用；
  3. `/continue` 接口存在且能把预览单重建成完整单；
  4. `max_segments` 默认 0 = 老行为，不传就是全出。

⚠️ 不验「真跑一段花多少钱、命中缓存省多少钱」—— 那要真调模型（花钱），
   由主人放行后单独跑。这里只保证代码路径对。

跑法：python scripts/p57_check.py --model volc25
"""
from __future__ import annotations

import inspect
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))   # scripts/ 里的型号闸
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from _model_gate import sel_or_exit  # noqa: E402

PASS = FAIL = 0


def check(name: str, got, want) -> None:
    global PASS, FAIL
    ok = got == want
    if ok:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want={want!r}")


def has_param(fn, p: str) -> bool:
    return p in inspect.signature(fn).parameters


def main() -> int:
    # 🩸 只验 2.5 这一轮：下面第 `⑥` 段会真算一遍预览，用的是 2.5 的型号
    #   （`--model h3` 跑这条 = 拿别家的型号报绿，闸门必须先拦住）。
    sel_or_exit(only="volc25")
    from app.api import clone as api
    from app.services import clone_jobs, clone_pipeline, video_edit

    print("== ① 参数一路透传（五层）==")
    f = api.RenderIn.model_fields["max_segments"]
    check("API 模型有 max_segments", f is not None, True)
    check("默认 0 = 走老行为", f.default, 0)
    for mod, name in [(clone_jobs.submit_render, "submit_render"),
                      (clone_jobs._render, "_render"),
                      (clone_pipeline.render, "clone_pipeline.render"),
                      (video_edit.replace_spans, "replace_spans"),
                      (video_edit.replace_whole, "replace_whole"),
                      (video_edit._gen_spans, "_gen_spans")]:
        check(f"{name} 收 max_segments", has_param(mod, "max_segments"), True)

    print("\n== ② 只跑部分时绝不拼接 ==")
    src = inspect.getsource(video_edit.replace_whole)
    # 预览返回必须出现在 _concat 调用**之前**；否则就是"拼了个残缺成片"。
    i_prev = src.find("if max_segments and len(pieces) < len(spans):")
    i_concat = src.find("_concat(pieces, out, work)")
    check("replace_whole 里有预览分支", i_prev >= 0, True)
    check("_concat 在预览分支之后（部分时先返回）",
          i_prev >= 0 and i_concat > i_prev, True)
    check("预览分支标记 partial=True", '"partial": True' in src[i_prev:i_prev + 900], True)

    src_p = inspect.getsource(clone_pipeline.render)
    i_prev_p = src_p.find("if max_segments and wants_change:")
    i_done_p = src_p.find('_p(progress, "done", 100)')
    check("render 有预览分支", i_prev_p >= 0, True)
    check("预览分支在「done/100%」之前返回", i_prev_p < i_done_p, True)
    check("预览分支写 out.mp4（下载接口才取得到）",
          '_out_prev = workdir / "out.mp4"' in src_p, True)

    print("\n== ③ 底层真停：第 N+1 段不进循环体 ==")
    src_g = inspect.getsource(video_edit._gen_spans)
    i_break = src_g.find("if max_segments and n > max_segments:")
    i_body = src_g.find("need = max(0.5, b - a)")
    check("_gen_spans 有 break", i_break >= 0, True)
    check("break 在段体之前（不会先花钱再判）",
          i_break >= 0 and 0 < i_body - i_break < 400, True)

    print("\n== ④ 继续出全部 ==")
    routes = {r.path for r in api.router.routes}
    check("有 /continue 接口",
          "/clone/{cid}/render/{rid}/continue" in routes, True)
    src_c = inspect.getsource(api.clone_render_continue)
    check("只接受 partial 单", 'src.get("partial")' in src_c, True)
    check("重跑时 max_segments=0（出全部）", "max_segments=0" in src_c, True)
    # 输入字段要带走：型号/通道/规格 —— 缺一个就会出成另一个东西。
    # 判据看的是"有没有被剔除"，不是"源码里有没有这个词"：
    # `_OUTPUT_ONLY` 是唯一剔除名单，输入字段只要不在里面就会原样复制过去。
    _drop = src_c.split("_OUTPUT_ONLY = ")[1].split("}")[0]
    for k in ("regen_channel", "regen_model", "edit", "script", "mask_bottom"):
        check(f"continue 不会丢掉 {k}", f'"{k}"' in _drop, False)

    print("\n== ⑤ 确认框按前 N 段报数 ==")
    # 🩸 2026-11-01 主人截图：点「先出第 1 段看看」，弹窗还写「视频模型：2 段 / 共
    #   18.067 秒」。根因不是文案错，是 `/plan` 压根没把 max_segments 传下去，
    #   预览一路按全片算。这里既验接线（源码），也验行为（真算一遍，零费用）。
    src_api = (ROOT / "app" / "api" / "clone.py").read_text(encoding="utf-8")
    i_plan = src_api.find("async def clone_plan")
    seg_plan = src_api[i_plan:src_api.find("@router.post", i_plan)]
    check("/plan 把 max_segments 透传给预览",
          "max_segments=int(body.max_segments or 0)" in seg_plan, True)
    check("/prompts 不截断（要写全片逐段指令）",
          "with_agent=True" in src_api[src_api.find("async def clone_prompts"):
                                       src_api.find("@router.post",
                                                    src_api.find("async def clone_prompts"))],
          True)
    check("preview_render 收 max_segments",
          has_param(clone_pipeline.preview_render, "max_segments"), True)

    # 48 秒 = 8 个有动作的镜头 → 2.5 的 30s 上限切出 2 段（判据不依赖真实视频文件）
    _sh = 6.0
    rec = {
        "source": {"duration": _sh * 8, "fps": 30.0, "width": 1080,
                   "height": 1920, "has_audio": True},
        "shots": [{"i": i, "start": i * _sh, "end": (i + 1) * _sh,
                   "motion": 2.4, "text": f"第{i + 1}句"} for i in range(8)],
        "speech": {"lang": "zh", "segments": [
            {"start": i * _sh + 1, "end": i * _sh + 3, "text": f"台词{i + 1}"}
            for i in range(8)]},
    }
    _spec = {"change": {"person": True, "person_ids": ["P1"]},
             "audio": "original"}
    _kw = dict(script=None, edit_spec=_spec,
               refs={"person": Path("nope.jpg")}, regen_channel="volc",
               regen_model="doubao-seedance-2-5-260628")
    full = clone_pipeline.preview_render(Path("unused.mp4"), rec, **_kw)
    one = clone_pipeline.preview_render(Path("unused.mp4"), rec,
                                        max_segments=1, **_kw)
    check("全片按 2 段报", full["change"]["video_calls"], 2)
    check("全片不标 partial", full["change"].get("partial"), None)
    check("只出 1 段 → 视频模型按 1 段报", one["change"]["video_calls"], 1)
    check("标了 partial", one["change"].get("partial"), True)
    check("整片总量另存（界面写「整片共 N 段」）",
          one["change"].get("total_video_calls"), 2)
    check("逐段提示词也只给这 1 段", len(one["segments"]), 1)
    check("合同按片段时长算（不是整片时长）",
          one["contract"]["duration"], one["change"]["video_seconds"])
    check("成对的下半：全片合同仍是整片时长",
          full["contract"]["duration"], full["change"]["video_seconds"])

    print("\n== ⑥ 前端 ==")
    front = ROOT.parent / "frontend" / "app" / "src"
    req = (front / "api" / "request.js").read_text(encoding="utf-8")
    dia = (front / "pages" / "clone" / "diagnose.vue").read_text(encoding="utf-8")
    res = (front / "pages" / "clone" / "result.vue").read_text(encoding="utf-8")
    # 探针的输入状态：照主人截图那一屏的真实数据写（4 段视频要重生成、面板没点开）
    states = [
        {"name": "截图场景", "self": {"wantRegen": True, "peek": None, "reuse": {"requests": [
            {"engine": "video"}, {"engine": "video"},
            {"engine": "video"}, {"engine": "video"}]}}},
        {"name": "单段", "self": {"wantRegen": True, "peek": None,
                                  "reuse": {"requests": [{"engine": "video"}]}}},
        {"name": "全是静帧", "self": {"wantRegen": True, "peek": None, "reuse": {"requests": [
            {"engine": "still"}, {"engine": "still"},
            {"engine": "still"}, {"engine": "still"}]}}},
        {"name": "不换画面", "self": {"wantRegen": False, "peek": None, "reuse": None}},
        {"name": "清单未就绪", "self": {"wantRegen": True, "peek": None, "reuse": None}},
    ]
    tmp_dir = ROOT / "temp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    states_path = tmp_dir / "_p57_front_states.json"
    states_path.write_text(json.dumps(states, ensure_ascii=False), encoding="utf-8")
    check("确认框认 partial（只出前 N 段时按 N 段说）", "c.partial" in dia, True)
    check("提示词可选（H5 全局 user-select:none 会挡住划选)",
          'class="peek-text" selectable' in dia, True)
    check("request.js 有 maxSegments", "maxSegments" in req, True)
    check("不传时请求体不含 max_segments（老请求形状不变）",
          "maxSegments > 0 ? { max_segments: maxSegments }" in req, True)
    check("诊断页有「先出第 1 段」入口", "先出第 1 段看看" in dia, True)
    # 🩸 2026-11-02 主人截图问「分段的按键哪里去了」：按钮的代码在、界面上就是不出现。
    #   以前这里只查 `"canPreviewOne" in dia` —— 文件里写着这个名字就算绿，等于没验。
    #   改成把这个计算属性**真跑一遍**（`_front_cond_probe.js` 直接执行 `.vue` 里的
    #   函数体，依赖的 computed 按同名求值），逐状态看它给不给按钮。
    probe = subprocess.run(
        ["node", str(ROOT / "scripts" / "_front_cond_probe.js"),
         str(front / "pages" / "clone" / "diagnose.vue"),
         "canPreviewOne", str(states_path)],
        capture_output=True, text=True, encoding="utf-8")
    if probe.returncode != 0:
        check("计算属性探针能跑（取不到函数=红，不许静默放过）", probe.stderr.strip(), "")
    else:
        got = {x.get("name"): x.get("got") for x in json.loads(probe.stdout)}
        check("主人截图那个状态（4 段视频、提示词面板没点开）要给按钮",
              got.get("截图场景"), True)
        check("只有 1 段视频不给按钮", got.get("单段"), False)
        check("4 段全是静帧重绘不给按钮（max_segments 只管视频段）",
              got.get("全是静帧"), False)
        check("不换画面不给按钮", got.get("不换画面"), False)
        check("复用清单还没算出来不给按钮", got.get("清单未就绪"), False)
    check("结果页有「继续出全部」", "continueAll" in res and "cloneRenderContinue" in res, True)

    print(f"\n{PASS}/{PASS + FAIL} 通过")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
