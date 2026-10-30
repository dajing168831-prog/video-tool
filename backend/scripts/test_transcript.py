# -*- coding: utf-8 -*-
"""口播文案（语音转写）的自检 —— **零模型调用、零费用**。

喂的是假 ASR，验的是我们自己的四件事：
  1. 段落化（停顿够长才换段）
  2. 缓存（转过就不再花第二次钱）
  3. 四类拒绝要说人话（图集 / 超长 / 静音 / ASR 报错）
  4. 接口接线（GET 只读缓存、POST 才识别；解析接口不碰 ASR）

跑法：python scripts/test_transcript.py
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.core.config import settings  # noqa: E402
from app.services import storage, transcript  # noqa: E402

PASS = FAIL = 0
TOKEN = "a" * 32


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}: {got}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want={want!r}")


class FakeASR:
    """假 ASR：不发请求，按给定脚本返回。"""

    def __init__(self, segs=None, has=True, lang="zh", boom=None):
        self.segs, self.has, self.lang, self.boom = segs or [], has, lang, boom
        self.calls = 0

    def transcribe(self, audio, **_kw):
        self.calls += 1
        if self.boom:
            raise self.boom
        return {"has": self.has, "lang": self.lang,
                "segments": [dict(s) for s in self.segs]}


SEGS = [
    {"start": 0.2, "end": 1.6, "text": "第一句话。"},
    {"start": 1.7, "end": 3.0, "text": "紧接着第二句。"},
    {"start": 5.5, "end": 7.0, "text": "隔了三秒另起一段。"},
]


def main() -> int:
    real_temp = settings.temp_dir
    tmp = Path(tempfile.mkdtemp(dir="D:/tmp", prefix="tr_"))
    object.__setattr__(settings, "temp_dir", tmp)
    try:
        print("== 段落化 ==")
        check("停顿 <1.2s 接在同一段",
              transcript.build_text(SEGS),
              "第一句话。紧接着第二句。\n隔了三秒另起一段。")
        check("空输入 → 空文本", transcript.build_text([]), "")
        check("空句被跳过",
              transcript.build_text([{"start": 0, "end": 1, "text": "  "}]), "")

        print("== 缓存 ==")
        d = storage.task_dir(TOKEN)
        d.mkdir(parents=True, exist_ok=True)
        # 造一条"音轨"，免得去抽音频（真 ASR 也不读它）
        storage.audio_path(TOKEN).write_bytes(b"fake")
        meta_v = {"is_video": True, "duration": 7.0}
        fake = FakeASR(SEGS)
        first = asyncio.run(transcript.get_or_make(TOKEN, meta_v, asr=fake))
        check("首次识别调用次数", fake.calls, 1)
        check("落盘 cached=False", first["cached"], False)
        check("字数不含空白", first["chars"], len(first["text"].replace("\n", "")))
        second = asyncio.run(transcript.get_or_make(TOKEN, meta_v, asr=fake))
        check("第二次读缓存、不再调用", fake.calls, 1)
        check("缓存标记 cached=True", second["cached"], True)
        again = asyncio.run(transcript.get_or_make(TOKEN, meta_v, asr=fake,
                                                   refresh=True))
        check("refresh=1 才重跑", (fake.calls, again["cached"]), (2, False))

        print("== 四类拒绝（都要说人话，不许返回空文本冒充成功）==")
        def err_of(**kw):
            t = kw.pop("token", "b" * 32)
            storage.task_dir(t).mkdir(parents=True, exist_ok=True)
            # 造一条"音轨"：这些用例要验的是 ASR 的反应，不是抽音频
            storage.audio_path(t).write_bytes(b"fake")
            fake2 = FakeASR(**kw)
            try:
                asyncio.run(transcript.get_or_make(t, {"is_video": True,
                                                       "duration": 7.0}, asr=fake2))
                return ""
            except transcript.TranscriptError as e:
                return str(e)

        check("图集 → 拒",
              _try(lambda: asyncio.run(transcript.get_or_make(
                  "c" * 32, {"is_video": False}, asr=FakeASR())))[:6], "图集没有音频")
        check("超长 → 拒",
              _try(lambda: asyncio.run(transcript.get_or_make(
                  "d" * 32, {"is_video": True, "duration": 3600},
                  asr=FakeASR())))[:4], "视频 6")
        check("静音（ASR 说没人声）→ 拒", err_of(has=False)[:6], "没检测到人声")
        from app.services.providers.asr import ASRError

        check("ASR 抛错 → 翻成人话",
              err_of(boom=ASRError("识别失败 HTTP 500"))[:13], "识别失败 HTTP 500")

        print("== 接线 ==")
        from app.main import app

        # 🩸 新版 FastAPI 把 include_router 挂成懒加载对象，`app.routes` 里
        # 拿不到子路由的 path（实测 7 个全是 /docs 这类）。用 openapi 取，
        # 它会把所有路由真正解析出来。
        _paths = app.openapi().get("paths", {})
        check("transcript 路由已注册",
              "/api/task/{token}/transcript" in _paths, True)
        _methods = set(_paths.get("/api/task/{token}/transcript", {}))
        check("GET/POST 都在", ("get" in _methods, "post" in _methods),
              (True, True))
        import inspect

        from app.api import routes

        src = inspect.getsource(routes.parse)
        check("解析阶段不碰 ASR", ("transcript" in src), False)

        # 端到端一枪：真走 handler，只把 ASR 换掉（零费用）
        import json

        import app.services.providers.asr as asr_mod

        tk = "e" * 32
        td = storage.task_dir(tk)
        td.mkdir(parents=True, exist_ok=True)
        (td / "meta.json").write_text(
            json.dumps({"is_video": True, "duration": 7.0}), encoding="utf-8")
        storage.audio_path(tk).write_bytes(b"fake")
        asr_mod.get_asr = lambda *_a, **_k: FakeASR(SEGS)
        from fastapi.testclient import TestClient

        _c = TestClient(app)
        _r = _c.post(f"/api/task/{tk}/transcript").json()
        check("POST 端到端成功", (_r["code"], _r["biz_code"]), (200, 0))
        check("返回的文案非空", bool((_r.get("data") or {}).get("text")), True)
        _r2 = _c.get(f"/api/task/{tk}/transcript").json()
        check("GET 只读缓存拿到同一份",
              (_r2.get("data") or {}).get("text") == (_r.get("data") or {}).get("text"),
              True)
        _r3 = _c.post("/api/task/" + "f" * 32 + "/transcript").json()
        check("不存在的任务 → 404 业务码", _r3["biz_code"], 404)
    finally:
        object.__setattr__(settings, "temp_dir", real_temp)

    print(f"\n{PASS}/{PASS + FAIL} 通过")
    return 1 if FAIL else 0


def _try(fn):
    try:
        fn()
        return ""
    except transcript.TranscriptError as e:
        return str(e)


if __name__ == "__main__":
    raise SystemExit(main())
