"""P7 验收：作品库（复刻历史）—— 出的片找得回来、多版本挑得了。

产品上的一句话：**花过钱出的每一版，都在「历史 → 复刻作品」里，随时重播、换版、继续改。**

这条链有三段，断哪一段用户都会觉得"白做了"：
  1. 前端真的去取复刻历史（`/clone/history` 早就有接口，之前没人调）；
  2. 卡片上要显示的东西后端真的给了（创建时间、每版时长、质检结论）；
  3. 点进去的跳转参数能落到真实存在的成片上（不是拼一个假 URL）。

跑法：python scripts/p7_check.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import clone_store  # noqa: E402

FRONT = ROOT.parent / "frontend" / "app" / "src"
HIST = (FRONT / "pages" / "history" / "history.vue").read_text(encoding="utf-8")
RES = (FRONT / "pages" / "clone" / "result.vue").read_text(encoding="utf-8")

rows: list[tuple[str, bool, str]] = []


def chk(name: str, ok: bool, detail: str = "") -> None:
    rows.append((name, bool(ok), detail))


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：一轮只跑一家
    from _model_gate import sel_or_exit as _sel
    _sel()
    # ---- 1. 前端真的去取 ------------------------------------------------
    chk("1.1 历史页引用了复刻历史接口", "cloneHistory" in HIST and "loadClones" in HIST,
        "接口存在但没人调 = 作品等于丢了")
    chk("1.2 有「复刻作品」这个入口", "复刻作品" in HIST and "tab === 'clone'" in HIST,
        "tabBar 只有三个页签，作品库挂在「历史」里")
    chk("1.3 onShow 会去拉（回到页面就能看到新出的版本）",
        re.search(r"onShow\(\)\s*\{[^}]*loadClones", HIST, re.S) is not None,
        "只在 onLoad 拉，出完片回来还是旧列表")

    # ---- 2. 后端给的字段够不够画卡片 -------------------------------------
    items = clone_store.history(200)
    with_render = [it for it in items if it.get("renders")]
    done = [r for it in with_render for r in it["renders"] if r.get("state") == "done"]

    # 🩸 防空转：一份带成片的任务都没有时，下面这些字段检查会"对空集合成立"，
    # 那是假绿。所以这里先把"尺子有没有东西可量"单独判一条。
    chk("2.1 尺子自证：服务器上真有带成片的作品可量",
        bool(done), f"{len(items)} 个任务 / {len(done)} 版成片")

    chk("2.2 每个任务都带 created_at（卡片要显示时间、列表要排序）",
        bool(items) and all(it.get("created_at") for it in items),
        f"{sum(1 for it in items if it.get('created_at'))}/{len(items)}")

    fields_ok = all(
        ("created_at" in r) and ("duration" in r) and ("qc_ok" in r)
        for it in with_render for r in it["renders"]
    )
    chk("2.3 每版都带 created_at / duration / qc_ok",
        bool(with_render) and fields_ok,
        f"{len(with_render)} 个作品、{sum(len(it['renders']) for it in with_render)} 版")

    # ---- 3. 点进去能落到真成片上 -----------------------------------------
    # 🩸 只量**出完的**版本：卡片取的是「最新一版能播的」封面，
    # 失败的版本本来就没有封面、界面也不会去请求它 —— 拿 renders[-1] 量是量错对象。
    bad_cover = []
    for it in with_render:
        for r in it["renders"]:
            if r.get("state") != "done":
                continue
            if not (clone_store.render_dir(it["id"], r["id"]) / "cover.jpg").exists():
                bad_cover.append(it["id"][:8])
    chk("3.1 出完的版本都有封面文件（卡片不会一片灰）",
        bool(done) and not bad_cover,
        "缺封面：" + ",".join(sorted(set(bad_cover))) if bad_cover else f"{len(done)} 版全有")

    chk("3.1b 一版成片都没有时，卡片退回原片封面",
        "cloneFileUrl(c.id, 'srccover')" in HIST,
        "否则这类作品在库里是个空框")

    chk("3.2 卡片跳转参数和后端路由对得上",
        "`/pages/clone/result?cid=${c.id}&rid=${r.id}`" in HIST
        and "/pages/clone/diagnose?cid=${c.id}" in HIST,
        "result 看片、diagnose 继续改")

    # 前端认识的渲染状态，必须是后端真的写过的 —— 多写一个就是"永远不亮的灯"
    allowed = {"queued", "rendering", "done", "failed"}
    used = set(re.findall(r"state === '([a-z]+)'", HIST))
    chk("3.3 前端判的状态值都在后端值域里", used <= allowed,
        f"前端用到 {sorted(used)}")

    # ---- 4. 页内换版本 ----------------------------------------------------
    chk("4.1 成片页能直接切版本（不用退回列表再点）",
        "switchVersion" in RES and "cloneDetail" in RES,
        "同一作品多版并排比")
    chk("4.2 只把出完的版本列进切换条",
        re.search(r"filter\(\(r\) => r\.state === 'done'\)", RES) is not None,
        "出片中的版本放进去会点出 404")

    ok = sum(1 for _n, o, _d in rows if o)
    for n, o, d in rows:
        print(f"{'PASS' if o else 'FAIL'}  {n}" + (f"  [{d}]" if d else ""))
    print(f"\n{ok}/{len(rows)} 通过")
    return 0 if ok == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
