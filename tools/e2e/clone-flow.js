// 复刻功能 H5 前端验收：结构页 → 填文案 → 出片进度 → 成片页
// 用法: node clone-flow.js <cid> [baseUrl]
const puppeteer = require('puppeteer-core')
const fs = require('fs')
const path = require('path')

const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const CID = process.argv[2]
const BASE = process.argv[3] || 'http://127.0.0.1:8920'
const SHOTS = 'C:/tmp/video-tool/logs/shots'

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function shot(page, name) {
  fs.mkdirSync(SHOTS, { recursive: true })
  const p = path.join(SHOTS, `${name}.png`)
  await page.screenshot({ path: p, fullPage: false })
  console.log(`  📸 ${p}`)
}

async function tap(page, text) {
  // 先把按钮滚进视口：页面长了以后按钮在折叠线以下，坐标点击会打在空白处
  const box = await page.evaluate((t) => {
    const els = Array.from(document.querySelectorAll('uni-button, button'))
    const hit = els.find((el) => (el.textContent || '').trim().includes(t))
    if (!hit) return null
    hit.scrollIntoView({ block: 'center' })
    const r = hit.getBoundingClientRect()
    return { x: r.x + r.width / 2, y: r.y + r.height / 2, visible: r.top >= 0 && r.bottom <= innerHeight }
  }, text)
  if (!box) throw new Error(`找不到按钮：${text}（当前页 ${page.url()}）`)
  if (!box.visible) throw new Error(`按钮不在视口内：${text}`)
  await page.mouse.click(box.x, box.y)
}

;(async () => {
  if (!CID) throw new Error('缺少 cid 参数')
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--window-size=430,932'],
    defaultViewport: { width: 430, height: 932 },
  })
  const page = await browser.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text())
  })

  try {
    console.log('[1] 打开结构页')
    await page.goto(`${BASE}/#/pages/clone/diagnose?cid=${CID}`, { waitUntil: 'networkidle2' })
    await page.waitForSelector('.grid', { timeout: 30000 })
    const stats = await page.evaluate(() =>
      Array.from(document.querySelectorAll('.cell')).map((c) => c.innerText.replace(/\n/g, ' '))
    )
    console.log('    结构卡:', stats.join(' | '))
    const kf = await page.$$eval('.kf', (els) => els.length)
    console.log('    关键帧:', kf, '张')
    await shot(page, 'clone-1-diagnose')

    console.log('[2] 填写新文案')
    const ta = await page.$('uni-textarea textarea')
    if (!ta) throw new Error('找不到文案输入框')
    await ta.click()
    await page.keyboard.down('Control')
    await page.keyboard.press('KeyA')
    await page.keyboard.up('Control')
    await page.keyboard.press('Backspace')
    const left = await page.$eval('uni-textarea textarea', (el) => el.value.length)
    console.log('    清空后剩余字符:', left)
    await page.type('uni-textarea textarea',
      '这条是前端验收写的文案。第一句用来证明输入能用。第二句用来证明分段能用。到这里就结束了。',
      { delay: 8 })
    await sleep(300)
    await shot(page, 'clone-2-script')

    console.log('[3] 开始出片')
    await tap(page, '开始出片')
    await page.waitForFunction(
      () => location.hash.includes('/pages/clone/progress'),
      { timeout: 20000 }
    )
    await shot(page, 'clone-3-progress')
    console.log('    当前:', page.url())

    console.log('[4] 等成片页')
    await page.waitForFunction(
      () => location.hash.includes('/pages/clone/result'),
      { timeout: 180000, polling: 500 }
    )
    await sleep(1500)
    const info = await page.evaluate(() => ({
      title: (document.querySelector('.meta-title') || {}).innerText || '',
      sub: (document.querySelector('.meta-sub') || {}).innerText || '',
      segs: document.querySelectorAll('.seg').length,
      video: document.querySelectorAll('uni-video, video').length,
      src: (document.querySelector('video') || {}).src || '',
    }))
    console.log('    成片页:', JSON.stringify(info))
    await shot(page, 'clone-4-result')

    // 视频真的能播：等 readyState
    const playable = await page.evaluate(async () => {
      const v = document.querySelector('video')
      if (!v) return 'no-video'
      if (v.readyState >= 1) return `readyState=${v.readyState} duration=${v.duration}`
      return await new Promise((res) => {
        v.addEventListener('loadedmetadata', () => res(`readyState=${v.readyState} duration=${v.duration}`), { once: true })
        setTimeout(() => res(`timeout readyState=${v.readyState}`), 15000)
      })
    })
    console.log('    播放器:', playable)

    console.log('[5] 首页入口')
    await page.goto(`${BASE}/#/pages/index/index`, { waitUntil: 'networkidle2' })
    await page.waitForSelector('.clone-entry', { timeout: 15000 })
    await page.click('.clone-entry')  // 入口是 view 不是 button，不能用 tap()
    await sleep(1200)
    await page.waitForFunction(() => location.hash.includes('/pages/clone/index'), { timeout: 10000 })
    console.log('    跳转到:', page.url())
    await shot(page, 'clone-5-entry')

    console.log('\n控制台错误:', errors.length ? errors.slice(0, 6) : '无')
    console.log('验收完成')
  } catch (e) {
    await shot(page, 'clone-FAIL')
    console.error('失败:', e.message)
    console.error('控制台错误:', errors.slice(0, 8))
    process.exitCode = 1
  } finally {
    await browser.close()
  }
})()
