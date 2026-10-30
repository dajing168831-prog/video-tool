"""把**真机发出去的**提示词全部导出来，供人工逐条审。

为什么要这个：`prompt_snapshot` 用的是我们自己的用例，只能证明"编译器按预期写"；
真机快照是**当时真的付了钱发出去的那段字**，审它才能发现"写出来就是这样、当时没人看"。

卖点：
  · 按型号分组，同型号的并排看，一眼看出共性；
  · 同一段请求的 `subject_look.used=False` 之类的旁证一起带上（描述没进提示词）。

用法：python scripts/dump_real_prompts.py --out <导出到哪>
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    # 🩸 不给默认值：这个脚本以前默认写到 `D:/tmp/…`，被模型分离门判成
    #   「生产代码还在引用 official/ 之外的本机资料文件」。输出路径交给调用方。
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    root = Path(__file__).resolve().parent.parent / "data" / "clone"
    groups: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for f in sorted(glob.glob(str(root / "**" / "request_*.json"), recursive=True)):
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception:
            continue
        key = f"{d.get('channel')}/{d.get('model')}/{d.get('resolution')}"
        groups[key].append((f, d))

    lines = ["# 真机发出去的提示词（逐条）\n"]
    total = 0
    for key in sorted(groups, key=lambda k: -len(groups[k])):
        items = groups[key]
        lines.append(f"\n## {key}  —— {len(items)} 段\n")
        for f, d in items:
            total += 1
            p = Path(f)
            cid = p.parts[-5] if len(p.parts) >= 5 else "?"
            rid = p.parent.parent.name if p.parent.name == "triage" else p.parent.name
            lines.append(f"### `{cid[:8]}` / `{rid[:8]}` / 段 {d.get('duration')}s / "
                         f"音轨={d.get('audio')} / 参考图 {len(d.get('ref_images') or [])} 张\n")
            look = d.get("subject_look") or {}
            if look:
                lines.append(f"> subject_look.used = **{look.get('used')}**"
                             f"（text {len(str(look.get('text') or ''))} 字符）\n")
            lines.append("```\n" + str(d.get("prompt") or "") + "\n```\n")

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"共 {total} 段，{len(groups)} 种型号组合 → {out}")
    for k in sorted(groups, key=lambda k: -len(groups[k])):
        print(f"  {len(groups[k]):>3}  {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
