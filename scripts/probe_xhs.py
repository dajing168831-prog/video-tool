import json, re
html = open(r'C:/tmp/video-tool/temp/xhs.html', encoding='utf-8', errors='ignore').read()
m = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*</script>', html, re.S)
if not m:
    print("未匹配 __INITIAL_STATE__"); raise SystemExit
raw = m.group(1)
# 小红书用 undefined 而不是 null
raw = raw.replace('undefined', 'null')
try:
    d = json.loads(raw)
except Exception as e:
    print("JSON 解析失败:", e); print(raw[:300]); raise SystemExit

note = d.get('note') or {}
print("顶层 keys:", list(d.keys())[:12])
print("note keys:", list(note.keys())[:12])
ndm = note.get('noteDetailMap') or {}
print("noteDetailMap 条数:", len(ndm))
for k, v in list(ndm.items())[:2]:
    print("  noteId:", k)
    n = (v or {}).get('note') or {}
    print("  note fields:", list(n.keys())[:15])
    print("  type:", n.get('type'), "| title:", (n.get('title') or '')[:40])
    video = n.get('video') or {}
    if video:
        print("  video keys:", list(video.keys())[:10])
        media = video.get('media') or {}
        print("  video.media keys:", list(media.keys())[:8])
        stream = media.get('stream') or {}
        for st in ('h264','h265','av1'):
            arr = stream.get(st) or []
            if arr:
                print(f"  stream.{st}[0].masterUrl:", (arr[0].get('masterUrl') or '')[:110])
