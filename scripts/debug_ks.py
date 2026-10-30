import asyncio
import fake_useragent
from parse_video_py.utils import create_async_client

URL = "https://v.kuaishou.com/Ke2ZpdGR"

async def main():
    ua = fake_useragent.UserAgent(os="iOS").random
    async with create_async_client(follow_redirects=False) as c:
        r1 = await c.get(URL, headers={"User-Agent": ua, "Referer": "https://v.kuaishou.com/"})
    loc = r1.headers.get("location", "")
    print("step1:", r1.status_code, "loc:", loc[:100])
    print("step1 headers:", dict(r1.headers))
    async with create_async_client(follow_redirects=True) as c:
        r2 = await c.get(loc, headers=r1.headers, cookies=r1.cookies)
    print("step2:", r2.status_code, "len:", len(r2.text))
    print("has INIT_STATE:", "INIT_STATE" in r2.text)
    print("has __APOLLO:", "__APOLLO" in r2.text)
    print("head:", r2.text[:200].replace("\n", " "))

asyncio.run(main())
