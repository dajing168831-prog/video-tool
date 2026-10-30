#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小红书页面抓取诊断：看看到底返回了什么（不猜）。"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

import httpx

sys.path.insert(0, r"C:/tmp/video-tool/backend")
from app.parsers.xhs_provider import (  # noqa: E402
    MOBILE_UA,
    PC_UA,
    _clean_js_json,
    _extract_state,
)

OUT = Path(r"C:/tmp/video-tool/temp")
OUT.mkdir(parents=True, exist_ok=True)


async def probe(url: str, ua: str, tag: str):
    print(f"\n===== {tag} =====")
    async with httpx.AsyncClient(
        timeout=40,
        follow_redirects=True,
        headers={
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    ) as c:
        r = await c.get(url)
    html = r.text
    print(f"status   : {r.status_code}")
    print(f"final    : {r.url}")
    print(f"len      : {len(html)}")
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    print(f"title    : {(m.group(1).strip() if m else '(无)')[:80]}")
    print(f"含 noteDetailMap : {'noteDetailMap' in html}")
    print(f"含 xsec_token    : {'xsec_token' in html}")
    print(f"含 登录          : {'登录' in html}")
    print(f"含 验证          : {'验证' in html}")
    print(f"含 __INITIAL_STATE__ : {'__INITIAL_STATE__' in html}")
    (OUT / f"xhs_{tag}.html").write_text(html, encoding="utf-8")

    st = _extract_state(html)
    if st:
        print(f"state 顶层键 : {sorted(st.keys())}")
        note = st.get("note") or {}
        if isinstance(note, dict):
            print(f"note 键      : {sorted(note.keys())}")
            dm = note.get("noteDetailMap")
            print(f"noteDetailMap: {type(dm).__name__} 条数={len(dm) if hasattr(dm, '__len__') else '?'}")
            print(f"firstNoteId  : {note.get('firstNoteId')}")
        (OUT / f"xhs_{tag}_state.json").write_text(
            json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    else:
        # 看看是不是首屏数据换了名字
        for key in ("__INITIAL_SSR_STATE__", "__NUXT__", "window.__INITIAL_STATE__"):
            print(f"  出现 {key}: {key in html}")
        idx = html.find("__INITIAL_STATE__")
        if idx >= 0:
            print("--- 该位置前后 300 字符 ---")
            print(_clean_js_json(html[max(0, idx - 60): idx + 240]))


async def main(url: str):
    await probe(url, PC_UA, "pc")
    await probe(url, MOBILE_UA, "mobile")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
