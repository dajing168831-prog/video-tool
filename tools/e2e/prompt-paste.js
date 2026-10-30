// 真机式验收：**粘一份现成稿**发出去，走的必须是对话路，而且带着「只换格式别改内容」的意图。
// 🩸 2026-10-30 转换那条路下线（它拿到 8 镜稿会自己补运镜、自己加内容）。
// 后端用桩：不打真模型、不花钱。
const puppeteer = require('puppeteer-core')
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const PAGE = 'http://127.0.0.1:8920/#/pages/prompt/index'

// 一份"看起来就是现成稿"的字：够长 + 有 SHOT 记号 + 有时间码
const SCRIPT = 'Multi-shot sequence with hard cuts between shots.\n'
  + Array.from({ length: 8 }, (_, i) =>
    `SHOT ${i + 1}\nWide shot at 00:0${i}.000 of the same woman in an olive-green jacket, `
    + 'dust floating in strong sunlight beams inside an abandoned ornate mansion.').join('\n\n')
const MARK = 'MTEST'

const got = { path: '', body: null, visible: '' }

let fails = 0
function check(name, ok, detail = '') {
  console.log(`${ok ? '  ✅' : '  ❌'} ${name}${!ok && detail ? '  ' + detail : ''}`)
  if (!ok) fails++
}

;(async () => {
  const browser = await puppeteer.launch({
    executablePath: CHROME, headless: 'new', args: ['--no-sandbox'],
  })
  const page = await browser.newPage()
  await page.setViewport({ width: 430, height: 932, deviceScaleFactor: 2, isMobile: true, hasTouch: true })
  page.on('pageerror', (e) => console.log('[pageerror]', e.message))

  await page.setRequestInterception(true)
  page.on('request', async (req) => {
    const url = req.url()
    if (!url.includes(':8911/api/prompt/')) return req.continue()
    const cors = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Headers': '*',
      'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
      'Content-Type': 'application/json',
    }
    if (req.method() === 'OPTIONS') return req.respond({ status: 204, headers: cors, body: '' })
    const send = (data) => req.respond({
      status: 200, headers: cors,
      body: JSON.stringify({ code: 200, biz_code: 0, msg: '', data }),
    }).catch(() => {})

    const path = url.split('/api/prompt/')[1].split('?')[0]
    if (req.method() === 'POST' && (path === 'chat' || path === 'convert' || path === 'revise')) {
      got.path = path
      got.body = JSON.parse(req.postData() || '{}')
      return send({ action: 'ask', question: '多少秒？', blocks: [] })
    }
    if (path === 'sessions' && req.method() === 'GET') return send([])
    return send(null)
  })

  await page.goto(PAGE, { waitUntil: 'networkidle2' })
  await sleep(800)

  const tap = async (txt, sel = '*') => {
    const box = await page.evaluate((t, s) => {
      const hit = Array.from(document.querySelectorAll(s))
        .filter((el) => {
          if ((el.textContent || '').trim() !== t) return false
          const r = el.getBoundingClientRect()
          return r.width > 0 && r.height > 0
        })
        .pop()
      if (!hit) return null
      const r = hit.getBoundingClientRect()
      return { x: r.x + r.width / 2, y: r.y + r.height / 2 }
    }, txt, sel)
    if (!box) throw new Error('找不到可点的：' + txt)
    await page.mouse.click(box.x, box.y)
  }

  await tap('写给'); await sleep(500)
  await tap('H3'); await sleep(400)
  await tap('模型'); await sleep(400); await tap('豆包 Lite'); await sleep(300)

  // 直接塞进输入框（uni-app 的 textarea 用 type 太慢，paste 也不一定生效）
  await page.click('textarea')
  // 直接改 value / 派发 input 都不进框架的双向绑定，得**真敲**（真敲才走 uni 的 input 事件）
  await page.type('textarea', SCRIPT, { delay: 0 })
  await sleep(300)
  // 🩸 发送按钮用坐标点不到（算出来的中心点落在了别的层上，点了没反应），
  // 直接派发 click —— 这一步验的是"发了什么"，不是"点得准不准"。
  await page.evaluate(() => document.querySelector('.send').click())
  await sleep(1500)

  check('① 走的是对话路（不是 /convert）', got.path === 'chat', got.path)
  const last = ((got.body || {}).messages || []).filter((m) => m.role === 'user').pop()
  const sent = (last && last.content) || ''
  check('② 发出去的话里带着「内容一个字都别改」', sent.includes('内容一个字都别改'), sent.slice(0, 80))
  check('③ 原稿正文一字不少地一起发了', sent.includes('SHOT 8') && sent.includes('00:07.000'), sent.slice(-80))
  check('④ duration 传 0（让模型问，不是写死 5）', got.body && got.body.duration === 0, String(got.body && got.body.duration))

  // 顾客自己那条气泡里要看得见这句（不藏）
  const visible = await page.evaluate(() => document.body.innerText)
  check('⑤ 顾客那条消息里看得到这句话（不是偷偷加的）',
    visible.includes('内容一个字都别改'), visible.slice(0, 160))

  await page.screenshot({ path: 'D:/tmp/vt-shots/prompt-paste.png' })
  await browser.close()
  console.log(fails ? `\n粘稿走对话路验收：红 ${fails}` : '\n粘稿走对话路验收：全绿')
  process.exit(fails ? 1 : 0)
})().catch((e) => { console.error('FAIL', e.message); process.exit(1) })
