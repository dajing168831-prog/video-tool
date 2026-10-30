// 页面横向溢出诊断：找出所有超出视口右边界的元素
const puppeteer = require('puppeteer-core')

const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const URL = process.argv[2] || 'http://127.0.0.1:5180/'
const SHOT = process.argv[3] || 'D:/tmp/vt-shots/diag.png'

;(async () => {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-gpu'],
  })
  const page = await browser.newPage()
  await page.setViewport({ width: 430, height: 932, deviceScaleFactor: 2, isMobile: true, hasTouch: true })
  page.on('console', (m) => {
    if (m.type() === 'error') console.log('[console error]', m.text())
  })
  page.on('pageerror', (e) => console.log('[pageerror]', e.message))
  await page.goto(URL, { waitUntil: 'networkidle2', timeout: 40000 })
  await new Promise((r) => setTimeout(r, 2000))

  const info = await page.evaluate(() => {
    const de = document.documentElement
    const cw = de.clientWidth
    const over = []
    document.querySelectorAll('*').forEach((el) => {
      const r = el.getBoundingClientRect()
      if (r.width > 0 && r.right > cw + 1) {
        over.push({
          tag: el.tagName.toLowerCase(),
          cls: (el.className && el.className.toString()) || '',
          left: Math.round(r.left),
          right: Math.round(r.right),
          w: Math.round(r.width),
        })
      }
    })
    return {
      clientWidth: cw,
      docScrollWidth: de.scrollWidth,
      bodyScrollWidth: document.body.scrollWidth,
      htmlFontSize: getComputedStyle(de).fontSize,
      over: over.slice(0, 20),
    }
  })
  console.log(JSON.stringify(info, null, 1))
  await page.screenshot({ path: SHOT, fullPage: false })
  await browser.close()
})().catch((e) => {
  console.error('FAIL', e.message)
  process.exit(1)
})
