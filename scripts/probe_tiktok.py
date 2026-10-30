import json, sys
import httpx

urls = [l.strip() for l in open(r'C:/tmp/video-tool/temp/tt_urls.txt', encoding='utf-8') if l.strip()]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"

alive = []
with httpx.Client(timeout=25, follow_redirects=True, headers={"User-Agent": UA}) as c:
    for u in urls:
        try:
            r = c.get("https://www.tiktok.com/oembed", params={"url": u})
            if r.status_code == 200 and r.headers.get("content-type","").startswith("application/json"):
                d = r.json()
                alive.append((u, d.get("title","")[:60], d.get("author_name","")))
                print(f"[OK ] {u}\n      {d.get('author_name')} | {d.get('title','')[:60]}")
            else:
                print(f"[DEAD] {r.status_code} {u}")
        except Exception as e:
            print(f"[ERR ] {u} {str(e)[:80]}")

print(f"\n有效 {len(alive)}/{len(urls)}")
open(r'C:/tmp/video-tool/temp/tt_alive.txt','w',encoding='utf-8').write('\n'.join(u for u,_,_ in alive))
