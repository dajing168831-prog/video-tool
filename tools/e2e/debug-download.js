// 诊断 H5 下载按钮
const puppeteer = require('puppeteer-core')
const fs = require('fs')
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const LINK = process.argv[2] || 'https://www.bilibili.com/video/BV1SknF6KE5g'
const DL = 'D:/tmp/vt-shots/downloads'

;(async () => {
  fs.mkdirSync(DL, { recursive: true })
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] })
  const page = await browser.newPage()
  await page.setViewport({ width: 430, height: 932, deviceScaleFactor: 2, isMobile: true, hasTouch: true })
  page.on('console', (m) => console.log(`[c.${m.type()}]`, m.text()))
  page.on('pageerror', (e) => console.log('[pageerror]', e.message))
  page.on('response', async (r) => {
    if (r.url().includes('/api/file/')) console.log('[res]', r.status(), r.url().slice(-40))
  })

  const client = await page.createCDPSession()
  await client.send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: DL, eventsEnabled: true })
  client.on('Browser.downloadWillBegin', (e) => console.log('[download begin]', e.suggestedFilename))
  client.on('Browser.downloadProgress', (e) => console.log('[download progress]', e.state, e.receivedBytes))

  await page.goto('http://127.0.0.1:5180/', { waitUntil: 'networkidle2' })
  await sleep(1000)
  await page.click('textarea')
  await page.type('textarea', LINK, { delay: 30 })
  const b = await page.evaluate(() => {
    const el = Array.from(document.querySelectorAll('uni-button')).find((e) => (e.textContent || '').includes('开始解析'))
    const r = el.getBoundingClientRect()
    return { x: r.x + r.width / 2, y: r.y + r.height / 2 }
  })
  await page.mouse.click(b.x, b.y)
  await page.waitForFunction(() => location.href.includes('pages/result'), { timeout: 120000 })
  await sleep(2500)

  // 直接测 fetch + blob 是否可行
  const probe = await page.evaluate(async () => {
    const token = location.href.split('?')[0]
    const m = performance.getEntriesByType('resource').map((e) => e.name).filter((u) => u.includes('/api/file/'))
    const url = m[0] || ''
    try {
      const r = await fetch(url)
      const bl = await r.blob()
      return { url: url.slice(-40), ok: r.ok, status: r.status, size: bl.size, type: bl.type }
    } catch (e) {
      return { url: url.slice(-40), err: e.message }
    }
  })
  console.log('PROBE fetch blob:', JSON.stringify(probe))

  // 点保存视频
  const vb = await page.evaluate(() => {
    const el = Array.from(document.querySelectorAll('uni-button')).find((e) => (e.textContent || '').trim().includes('保存视频'))
    if (!el) return null
    const r = el.getBoundingClientRect()
    return { x: r.x + r.width / 2, y: r.y + r.height / 2 }
  })
  console.log('保存视频坐标:', JSON.stringify(vb))
  const vurl = await page.evaluate(() => {
    const el = document.querySelector('video')
    return el ? el.currentSrc || el.src : ''
  })
  console.log('video src:', vurl)
  await page.mouse.click(vb.x, vb.y)
  for (let i = 0; i < 18; i++) {
    await sleep(5000)
    const txt = await page.evaluate(() => document.body.innerText.replace(/\n+/g, ' | '))
    console.log(`[${(i + 1) * 5}s] files=${JSON.stringify(fs.readdirSync(DL))} tail=${txt.slice(-60)}`)
    if (fs.readdirSync(DL).length) break
  }
  await page.screenshot({ path: 'D:/tmp/vt-shots/dbg-dl.png' })
  await browser.close()
})().catch((e) => { console.error('FAIL', e.message); process.exit(1) })
