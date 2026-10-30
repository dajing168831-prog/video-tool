import httpx
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
u = "https://www.tiktok.com/@tatumcrae/video/7107337212743830830"
with httpx.Client(timeout=25, follow_redirects=True, headers={"User-Agent": UA}) as c:
    r = c.get("https://www.tiktok.com/oembed", params={"url": u})
    print("status:", r.status_code)
    print("headers:", dict(r.headers))
    print("body[:500]:", r.text[:500].replace("\n"," "))
