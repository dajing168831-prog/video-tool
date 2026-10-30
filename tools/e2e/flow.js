// H5 全链路：首页输入 → 解析 → 结果页 → 复制文案 → 下载视频/音频 → 历史页
const puppeteer = require('puppeteer-core')
const fs = require('fs')

const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const BASE = process.argv[2] || 'http://127.0.0.1:5180'
const TEXT = process.argv[3] || 'https://www.douyin.com/video/6961737553342991651'
const OUT = 'D:/tmp/vt-shots'
const DL = 'D:/tmp/vt-shots/downloads'

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

/** 真实鼠标点击（UNI-BUTTON 上合成 .click() 不触发 uni 事件） */
async function tap(page, text) {
  const box = await page.evaluate((t) => {
    const els = Array.from(document.querySelectorAll('uni-button, button'))
    const hit = els.find((el) => (el.textContent || '').trim().includes(t))
    if (!hit) return null
    const r = hit.getBoundingClientRect()
    return { x: r.x + r.width / 2, y: r.y + r.height / 2 }
  }, text)
  if (!box) throw new Error(`找不到按钮：${text}`)
  await page.mouse.click(box.x, box.y)
}

;(async () => {
  fs.mkdirSync(DL, { recursive: true })
  for (const f of fs.readdirSync(DL)) fs.unlinkSync(`${DL}/${f}`)

  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-gpu'],
  })
  await browser.defaultBrowserContext().overridePermissions(BASE, ['clipboard-read', 'clipboard-write'])
  const page = await browser.newPage()
  await page.setViewport({ width: 430, height: 932, deviceScaleFactor: 2, isMobile: true, hasTouch: true })
  page.on('pageerror', (e) => console.log('[pageerror]', e.message))
  await page.goto(BASE + '/', { waitUntil: 'networkidle2', timeout: 40000 })
  await sleep(1200)

  // 1. 输入链接：逐字 type 在 uni textarea 上会丢字符，直接原生赋值 + 触发 input
  await page.$eval('textarea', (el, v) => {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set
    setter.call(el, v)
    el.dispatchEvent(new Event('input', { bubbles: true }))
  }, TEXT)
  await sleep(400)
  const got = await page.$eval('textarea', (el) => el.value)
  console.log('STEP1 输入:', JSON.stringify(got), got === TEXT ? '✔' : '✘ 不一致')

  // 2. 点解析
  const t0 = Date.now()
  await tap(page, '开始解析')
  try {
    await page.waitForFunction(() => location.href.includes('pages/result'), { timeout: 180000, polling: 500 })
    console.log(`STEP2 到达结果页 ${((Date.now() - t0) / 1000).toFixed(1)}s`)
  } catch (e) {
    await page.screenshot({ path: `${OUT}/f-fail.png` })
    console.log('STEP2 失败 URL:', page.url())
    console.log('STEP2 失败页面:', (await page.evaluate(() => document.body.innerText.replace(/\n+/g, ' | '))).slice(0, 300))
    throw e
  }

  await sleep(3000)
  await page.screenshot({ path: `${OUT}/f2-result.png`, fullPage: true })
  const bodyText = await page.evaluate(() => document.body.innerText.replace(/\n+/g, ' | '))
  console.log('STEP3 结果页文本:', bodyText.slice(0, 300))

  // 3. video 元素
  const v = await page.evaluate(() => {
    const el = document.querySelector('video')
    if (!el) return null
    return { src: (el.currentSrc || el.src).slice(-60), readyState: el.readyState, w: el.videoWidth, h: el.videoHeight }
  })
  console.log('STEP4 video:', JSON.stringify(v))

  // 4. 复制文案
  await tap(page, '复制文案')
  await sleep(600)
  const clip = await page.evaluate(() => navigator.clipboard.readText().catch((e) => 'ERR ' + e.message))
  console.log('STEP5 剪贴板:', JSON.stringify(String(clip).slice(0, 120)))
  await page.screenshot({ path: `${OUT}/f3-copied.png` })

  // 5. 下载视频
  const client = await page.target().createCDPSession()
  await client.send('Page.setDownloadBehavior', { behavior: 'allow', downloadPath: DL })
  await tap(page, '保存视频')
  let files = []
  for (let i = 0; i < 60; i++) {
    await sleep(1000)
    files = fs.readdirSync(DL).filter((f) => !f.endsWith('.crdownload'))
    if (files.length) break
  }
  console.log('STEP6 视频下载:', files.map((f) => `${f} ${fs.statSync(`${DL}/${f}`).size}B`))

  // 6. 下载音频
  await tap(page, '保存音频')
  let files2 = files
  for (let i = 0; i < 90; i++) {
    await sleep(1000)
    files2 = fs.readdirSync(DL).filter((f) => !f.endsWith('.crdownload'))
    if (files2.length >= 2) break
  }
  console.log('STEP7 音频下载:', files2.map((f) => `${f} ${fs.statSync(`${DL}/${f}`).size}B`))

  // 7. 历史页（tabBar 真实点击）
  const tabBox = await page.evaluate(() => {
    const bar = document.querySelector('uni-tabbar')
    if (!bar) return null
    const items = Array.from(bar.querySelectorAll('*')).filter((e) => (e.textContent || '').trim() === '历史')
    const hit = items[items.length - 1]
    if (!hit) return null
    const r = hit.getBoundingClientRect()
    return { x: r.x + r.width / 2, y: r.y + r.height / 2 }
  })
  if (tabBox) await page.mouse.click(tabBox.x, tabBox.y)
  await sleep(1800)
  await page.screenshot({ path: `${OUT}/f4-history.png` })
  console.log('STEP8 历史页 URL:', page.url())
  console.log('STEP8 历史页文本:', (await page.evaluate(() => document.body.innerText.replace(/\n+/g, ' | '))).slice(0, 300))

  await browser.close()
  console.log('DONE')
})().catch((e) => {
  console.error('FAIL', e.message)
  process.exit(1)
})
