"""从火山文档页的 window._ROUTER_DATA 里抽出正文 markdown。

用法: python extract_router_md.py <html文件> [输出文件]
火山文档是 SPA，但正文藏在 _ROUTER_DATA 里。找到最长的 markdown 字段就对了。
"""
from __future__ import annotations

import json
import sys


def walk(obj, hits, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            walk(v, hits, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            walk(v, hits, f"{path}[{i}]")
    elif isinstance(obj, str):
        if len(obj) > 500 and ("\n" in obj or "|" in obj):
            hits.append((len(obj), path, obj))


def main() -> None:
    src = sys.argv[1]
    html = open(src, encoding="utf-8", errors="replace").read()
    i = html.find("_ROUTER_DATA")
    if i < 0:
        print("没有 _ROUTER_DATA")
        raise SystemExit(2)
    # 有的页面是 "= {"，有的没有空格，所以从赋值号后面第一个 { 开始解
    j = html.find("{", i)
    dec = json.JSONDecoder()
    data, _ = dec.raw_decode(html[j:])
    hits: list[tuple[int, str, str]] = []
    walk(data, hits)
    hits.sort(reverse=True)
    print(f"长文本块 {len(hits)} 个", file=sys.stderr)
    out = sys.argv[2] if len(sys.argv) > 2 else src.rsplit(".", 1)[0] + ".md"
    text = "\n\n".join(t for _, _, t in hits[:6])
    open(out, "w", encoding="utf-8").write(text)
    print(f"写出 {out} ({len(text)} 字)", file=sys.stderr)


if __name__ == "__main__":
    main()
