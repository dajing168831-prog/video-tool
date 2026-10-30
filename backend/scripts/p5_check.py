"""P5 验收：旧层下线（零模型调用、不联网、不花钱）。

P5 的验收（`docs/ROUTE-2A-PLAN.md` / `docs/FEATURE-MAP.md`）：
  ① 六个保留开关、四个档位、隐式缓存的**对外暴露**全部收掉；
  ② `FEATURE-MAP.md` 里"自造"的每一行都有归属（保留 / 替换 / 删除）；
  ③ 说明书里不再有"名不副实"条目。

只验能机械判定的部分：
  K 六开关：请求体没有 keep；不带 keep 编译出来的提示词与"全保"逐字节相同。
  M 四档：对外文档只写 auto；界面上四个名字一个都不剩。
  A 复用：键带配音内容 → 改词必须换键；音色进 plan 签名。
  F 说明书：自造行都有归属；§5 已清零且界面话术到位。

跑法：python scripts/p5_check.py
"""
from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.api import clone as api  # noqa: E402
from app.services import edit_spec, video_edit, work  # noqa: E402

FRONT = ROOT.parent / "frontend" / "app" / "src"
DOCS = ROOT.parent / "docs"

rows: list[tuple[str, bool, str]] = []


def chk(name: str, ok: bool, detail: str = "") -> None:
    rows.append((name, bool(ok), detail))


# ---------------------------------------------------------------------------
# K 六开关：对外收掉，内部行为不变
# ---------------------------------------------------------------------------

def phase_k() -> None:
    fields = set(api.EditIn.model_fields)
    chk("K1 请求体不再有「保什么」六个开关", "keep" not in fields,
        f"EditIn 字段 {len(fields)} 个，无 keep")
    chk("K2 KeepIn 模型已删除", not hasattr(api, "KeepIn"), "api.clone 里没有 KeepIn")

    base = {"change": {"person": True, "person_id": "P1"}, "audio": "tts"}
    with_keep = {**base, "keep": {k: True for k in edit_spec.KEEP_LABELS}}
    a = edit_spec.normalize(base)
    b = edit_spec.normalize(with_keep)
    pa = edit_spec.compile_prompt("volc", a, slots=["person"], model="")
    pb = edit_spec.compile_prompt("volc", b, slots=["person"], model="")
    chk("K3 不下发 keep 与全保编译出的提示词逐字相同", pa == pb and bool(pa),
        f"{len(pa)} 字符")

    vue = (FRONT / "pages" / "clone" / "diagnose.vue").read_text(encoding="utf-8")
    chk("K4 前端不再下发 keep，开关样式已删",
        "keep:" not in vue and ".keep-grid" not in vue and "toggleKeep" not in vue,
        "数据/载荷/样式三处都没有")


# ---------------------------------------------------------------------------
# M 四档：对外只剩"每镜由系统定"
# ---------------------------------------------------------------------------

def phase_m() -> None:
    desc = api.RenderIn.model_fields["regen_mode"].description or ""
    chk("M1 接口文档不再把 shots/whole 写成用户选项",
        "auto" in desc and "shots" not in desc and "whole" not in desc, desc)

    def scan(words: tuple[str, ...]) -> list[str]:
        """按"会被渲染出去"的口径找词：注释行不算。"""
        hits = []
        for name in ("diagnose.vue", "progress.vue"):
            text = (FRONT / "pages" / "clone" / name).read_text(encoding="utf-8")
            for word in words:
                for m in re.finditer(word, text):
                    line = text[:m.start()].count("\n") + 1
                    src = text.splitlines()[line - 1].strip()
                    if src.startswith("//") or src.startswith("<!--"):
                        continue
                    hits.append(f"{name}:{line} {word}")
        return hits

    hits = scan(("智能重制", "混剪", "整片重制"))
    chk("M2 界面上四个档位名字一个不剩", not hits, "、".join(hits) or "0 处")
    # 尺子自证：同一把尺子必须找得到界面上确实还在的词，否则"0 处"只是没扫到
    chk("M3 尺子自证：同一扫描方式能找到界面上的「换什么」", bool(scan(("换什么",))),
        f"{len(scan(('换什么',)))} 处")

    # 兼容不许误伤：老值仍然被接受（老客户端 / 历史回放），只是不再宣传
    ok = True
    try:
        api.RenderIn(script="x", regen_mode="shots")
        api.RenderIn(script="x", regen_mode="whole")
    except Exception:  # noqa: BLE001
        ok = False
    chk("M4 老客户端传 shots/whole 仍然可用（不静默破坏）", ok, "兼容值保留")


# ---------------------------------------------------------------------------
# A 复用：键必须跟着"这条配音"走
# ---------------------------------------------------------------------------

def phase_a() -> None:
    k1 = video_edit._seg_key("volc", "abc123", 0.0, 5.01, au_mark=":na")
    chk("A1 保留原声的键与历史格式一致（不白花一次钱）",
        k1 == "volc:abc123:0.00-5.01:na", k1)

    k2 = video_edit._seg_key("volc", "abc123", 0.0, 5.01, audio_sig=":0a1b2c")
    k3 = video_edit._seg_key("volc", "abc123", 0.0, 5.01, audio_sig=":9f8e7d")
    chk("A2 配音变了 → 键必须变（改词不许命中旧口型）", k2 != k3,
        f"{k2} vs {k3}")

    k4 = video_edit._seg_key("volc", "abc123", 0.0, 5.01, audio_sig=":0a1b2c")
    chk("A3 同样的输入 → 键逐字相同（不然永远不复用）", k2 == k4, k2)

    parsed = work._parse_manifest_key(k2)
    chk("A4 带配音哈希的键仍能解析出时间段", parsed.get("span") == [0.0, 5.01],
        str(parsed.get("span")))

    base = {"mode": "whole", "channel": "volc", "model": "",
            "edit": edit_spec.normalize({"change": {"person": False}, "audio": "tts",
                                         "extra": "换成黄昏"})}
    spec = base["edit"]
    unit = {"span": [0.0, 5.0], "engine": "video", "prompt": "p",
            "channel": "volc", "model": "m", "resolution": "720p"}
    a = work._unit_key({**base, "voice": "v1"}, spec, unit, "sha", {}, True, "hi")
    b = work._unit_key({**base, "voice": "v2"}, spec, unit, "sha", {}, True, "hi")
    c = work._unit_key({**base, "voice": "v1"}, spec, unit, "sha", {}, True, "hi")
    chk("A5 音色进了出片前那份清单的签名（换音色不能承诺复用）",
        work._sig(a) != work._sig(b) and work._sig(a) == work._sig(c),
        f'{a["voice"]} / {b["voice"]}')


# ---------------------------------------------------------------------------
# F 说明书：自造行有归属，名不副实清零
# ---------------------------------------------------------------------------

def phase_f() -> None:
    doc = (DOCS / "FEATURE-MAP.md").read_text(encoding="utf-8")
    made = [ln for ln in doc.splitlines()
            if "自造" in ln and ln.startswith("|") and "归属" not in ln]
    owned = [ln for ln in made
             if re.search(r"自造[^|]*(·\s*(保留|替换|删除))", ln)]
    chk("F1 每条「自造」都写明了归属（保留/替换/删除）",
        len(made) == len(owned), f"{len(owned)}/{len(made)}")

    chk("F2 §5 名不副实清单已清零并留了处置记录",
        "名不副实清单（P5 已清零）" in doc and "未结项 = 0" in doc,
        "8 条逐条给了处置")

    diag = (FRONT / "pages" / "clone" / "diagnose.vue").read_text(encoding="utf-8")
    res = (FRONT / "pages" / "result" / "result.vue").read_text(encoding="utf-8")
    # 🩸 2026-10-26 主人禁令：「任何形态的『再传一张 / 脸太小换半身照』提示都不许出现」。
    # 所以这条判据**反过来**——界面上既不许有「锁长相」这种无证据的承诺，
    # 也不许有「脸太小/近景最准/自动裁大头照」这类会把人引回「要不要两张」的说法。
    # 只看**给用户看的 imgHint 文案**（注释里写禁令依据不算违规）。
    _hints = "\n".join(ln for ln in diag.splitlines() if "imgHint" in ln or "别传三视图" in ln)
    _banned = ("锁长相", "近景最准", "小脸", "自动裁", "大头照", "全身照", "再传一张")
    chk("F3 人物参考图提示不承诺、不劝补第二张",
        not any(t in _hints for t in _banned),
        "命中：" + "、".join(t for t in _banned if t in _hints))
    chk("F4 单价没配时不报金额（不许写「预估 ¥0」）",
        "单价未配置" in diag and "缺单价" not in diag, "费用：单价未配置，这里不出金额")
    chk("F5 「提取文案」改名为「复制作品文案」",
        "复制作品文案" in res, "按钮文案")


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：一轮只跑一家
    from _model_gate import sel_or_exit as _sel
    _sel()
    phase_k()
    phase_m()
    phase_a()
    phase_f()
    ok = sum(1 for _n, o, _d in rows if o)
    for n, o, d in rows:
        print(f"{'PASS' if o else 'FAIL'}  {n}" + (f"  [{d}]" if d else ""))
    print(f"\n{ok}/{len(rows)} 通过")
    return 0 if ok == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
