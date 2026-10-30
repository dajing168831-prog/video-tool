"""抓火山引擎文档正文。

文档页是 SSR，正文藏在 window._ROUTER_DATA 里（MDContent 字段）。
直接 curl 拿到的是外壳，必须把这层 JSON 拆出来。

用法：
  python tools/fetch_volc_doc.py <docid> [--lib 82379] [--out path.md]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


def fetch(libid: str, docid: str) -> str:
    url = f"https://www.volcengine.com/docs/{libid}/{docid}"
    req = urllib.request.Request(url, headers={"Accept": "text/html"})
    html = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "replace")
    m = re.search(r"window\._ROUTER_DATA\s*=\s*(\{.*?\});?\s*</script>", html, re.S)
    if not m:
        raise SystemExit(f"没找到 _ROUTER_DATA（页面长度 {len(html)}）")
    data = json.loads(m.group(1))

    def walk(o, path=""):
        if isinstance(o, dict):
            for k, v in o.items():
                yield from walk(v, f"{path}/{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                yield from walk(v, f"{path}/{i}")
        else:
            yield path, o

    for p, v in walk(data):
        if isinstance(v, str) and p.endswith("/MDContent") and len(v) > 200:
            return v
    raise SystemExit("没找到正文")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("docid")
    ap.add_argument("--lib", default="82379")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    md = fetch(a.lib, a.docid)
    if a.out:
        Path(a.out).write_text(md, encoding="utf-8")
        print(f"saved {a.out} ({len(md)} chars)")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
