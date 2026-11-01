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
    sel_or_exit()
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

    print("\n== ⑤ 前端 ==")
    front = ROOT.parent / "frontend" / "app" / "src"
    req = (front / "api" / "request.js").read_text(encoding="utf-8")
    dia = (front / "pages" / "clone" / "diagnose.vue").read_text(encoding="utf-8")
    res = (front / "pages" / "clone" / "result.vue").read_text(encoding="utf-8")
    check("request.js 有 maxSegments", "maxSegments" in req, True)
    check("不传时请求体不含 max_segments（老请求形状不变）",
          "maxSegments > 0 ? { max_segments: maxSegments }" in req, True)
    check("诊断页有「先出第 1 段」入口", "先出第 1 段看看" in dia, True)
    check("只有多段时才给这个按钮", "canPreviewOne" in dia, True)
    check("结果页有「继续出全部」", "continueAll" in res and "cloneRenderContinue" in res, True)

    print(f"\n{PASS}/{PASS + FAIL} 通过")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
