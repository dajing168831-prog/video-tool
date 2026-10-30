// 历史页验证：解析 → 返回首页 → 历史 tab → 点第一条 → 回到结果页
const puppeteer = require('puppeteer-core')
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const LINK = process.argv[2] || 'https://www.bilibili.com/video/BV1SknF6KE5g'

async function tapText(page, text, sel = 'uni-button, button') {
  const box = await page.evaluate((t, s) => {
    const hit = Array.from(document.querySelectorAll(s)).find((el) => (el.textContent || '').trim().includes(t))
    if (!hit) return null
    const r = hit.getBoundingClientRect()
    return { x: r.x + r.width / 2, y: r.y + r.height / 2 }
  }, text, sel)
  if (!box) throw new Error(`找不到：${text}`)
  await page.mouse.click(box.x, box.y)
}

;(async () => {
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] })
  const page = await browser.newPage()
  await page.setViewport({ width: 430, height: 932, deviceScaleFactor: 2, isMobile: true, hasTouch: true })
  page.on('pageerror', (e) => console.log('[pageerror]', e.message))
  await page.goto('http://127.0.0.1:5180/', { waitUntil: 'networkidle2' })
  await sleep(1000)

  await page.click('textarea')
  await page.type('textarea', LINK, { delay: 30 })
  await tapText(page, '开始解析')
  await page.waitForFunction(() => location.href.includes('pages/result'), { timeout: 120000 })
  console.log('A 解析完成')

  // 返回
  await page.goBack()
  await sleep(1500)
  console.log('B 返回后 URL:', page.url())

  // 历史 tab
  await tapText(page, '历史', 'uni-tabbar *')
  await sleep(1500)
  console.log('C 历史页 URL:', page.url())
  const txt = await page.evaluate(() => document.body.innerText.replace(/\n+/g, ' | '))
  console.log('C 历史页内容:', txt.slice(0, 300))
  await page.screenshot({ path: 'D:/tmp/vt-shots/h1-history.png' })

  // 点第一条
  const itemBox = await page.evaluate(() => {
    const el = document.querySelector('uni-view.item, .item')
    if (!el) return null
    const r = el.getBoundingClientRect()
    return { x: r.x + r.width / 2, y: r.y + r.height / 2 }
  })
  if (itemBox) await page.mouse.click(itemBox.x, itemBox.y)
  await sleep(3000)
  console.log('D 点历史后 URL:', page.url())
  console.log('D 内容:', (await page.evaluate(() => document.body.innerText.replace(/\n+/g, ' | '))).slice(0, 250))
  await page.screenshot({ path: 'D:/tmp/vt-shots/h2-detail.png' })

  await browser.close()
  console.log('DONE')
})().catch((e) => { console.error('FAIL', e.message); process.exit(1) })
