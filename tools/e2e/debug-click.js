// 诊断：点「开始解析」后到底发生了什么
const puppeteer = require('puppeteer-core')
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const URL = 'http://127.0.0.1:5180/'
const LINK = 'https://www.douyin.com/video/6961737553342991651'

;(async () => {
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] })
  const page = await browser.newPage()
  await page.setViewport({ width: 430, height: 932, deviceScaleFactor: 2, isMobile: true, hasTouch: true })
  page.on('console', (m) => console.log(`[console.${m.type()}]`, m.text()))
  page.on('pageerror', (e) => console.log('[pageerror]', e.message))
  page.on('request', (r) => { if (r.url().includes('8911')) console.log('[req]', r.method(), r.url()) })
  page.on('requestfailed', (r) => console.log('[reqfail]', r.url(), r.failure() && r.failure().errorText))
  page.on('response', (r) => { if (r.url().includes('8911')) console.log('[res]', r.status(), r.url()) })

  await page.goto(URL, { waitUntil: 'networkidle2', timeout: 40000 })
  await sleep(1200)

  await page.click('textarea')
  await page.type('textarea', LINK, { delay: 10 })
  await sleep(500)
  console.log('textarea value:', await page.$eval('textarea', (el) => el.value))

  // 用真实鼠标点击 uni-button 的中心
  const box = await page.evaluate(() => {
    const els = Array.from(document.querySelectorAll('uni-button, button'))
    const hit = els.find((el) => (el.textContent || '').trim().includes('开始解析'))
    if (!hit) return null
    const r = hit.getBoundingClientRect()
    return { x: r.x + r.width / 2, y: r.y + r.height / 2, text: hit.textContent.trim(), tag: hit.tagName }
  })
  console.log('button box:', JSON.stringify(box))
  if (box) await page.mouse.click(box.x, box.y)

  await sleep(3000)
  await page.screenshot({ path: 'D:/tmp/vt-shots/dbg1.png' })
  console.log('body after click:', (await page.evaluate(() => document.body.innerText.replace(/\n+/g, ' | '))).slice(0, 300))
  await sleep(20000)
  await page.screenshot({ path: 'D:/tmp/vt-shots/dbg2.png' })
  console.log('url:', page.url())
  console.log('body after 23s:', (await page.evaluate(() => document.body.innerText.replace(/\n+/g, ' | '))).slice(0, 400))
  await browser.close()
})().catch((e) => { console.error('FAIL', e.message); process.exit(1) })
