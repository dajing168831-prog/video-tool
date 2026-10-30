"""把编译好的 H5 起成局域网可访问的静态服务。

存在的理由只有一个：**改了前端却看不到变化**。
`python -m http.server` 不发缓存头，浏览器就按自己的启发式决定要不要复用 index.html，
于是每次重编都要人手动 Ctrl+Shift+R —— 漏做一次就会以为"功能没做"。

规则只有两条，都跟着事实走：
  · index.html 每次都要问服务器（no-cache）—— 它引用的 chunk 名字是带哈希的；
  · /assets/ 下的文件名带哈希，内容变了名字就变 → 可以放心让浏览器长期缓存。

用法：python scripts/serve_h5.py [端口] [绑定地址]
"""
from __future__ import annotations

import functools
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "frontend" / "app" / "dist" / "build" / "h5"


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        path = self.path.split("?")[0]
        if path in ("", "/") or path.endswith(".html"):
            self.send_header("Cache-Control", "no-cache, must-revalidate")
        elif "/assets/" in path:
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        super().end_headers()

    def log_message(self, fmt: str, *args) -> None:  # 不刷屏
        pass


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8920
    bind = sys.argv[2] if len(sys.argv) > 2 else "0.0.0.0"
    if not (DIST / "index.html").exists():
        print(f"找不到 {DIST / 'index.html'}，先跑 npm run build:h5", file=sys.stderr)
        return 1
    handler = functools.partial(Handler, directory=str(DIST))
    srv = ThreadingHTTPServer((bind, port), handler)
    print(f"H5 静态服务：{DIST}  ← http://{bind}:{port}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
