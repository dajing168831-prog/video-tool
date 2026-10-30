// 验「历史里到底有没有 AI 那一条」。
// 🩸 2026-10-30 主人：「回看历史又没有了吗？」—— 本地 stash 的过滤条件只看 `text`，
// 而 AI 的消息 `text` 是空的（内容在 `data` 里），于是**每一轮的答案都被扔了**。
//
// 这里刻意让后端**不帮忙记账**（桩只存前端 PUT 上来的那份，模拟没重启的旧后端），
// 这样能过的唯一可能就是前端自己把 AI 那条留下了 —— 比带后端的版本更严。
const puppeteer = require('puppeteer-core')
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const PAGE = 'http://127.0.0.1:8920/#/pages/prompt/index'
const MARK = 'ZZANSWER'
const LONG = `integrated_multimodal_description: 【Shot 1】${MARK} a slow push-in ... `.repeat(6)
const NOTE = 'ZZNOTE 这是第 1 个分镜（15 秒）'

const store = {}
let fails = 0
const check = (n, ok, d = '') => {
  console.log(`${ok ? '  ✅' : '  ❌'} ${n}${!ok && d ? '  ' + d : ''}`)
  if (!ok) fails++
}

;(async () => {
  const b = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] })
  const p = await b.newPage()
  await p.setViewport({ width: 1280, height: 900, deviceScaleFactor: 1 })
  p.on('pageerror', (e) => console.log('[pageerror]', e.message))
  await p.setRequestInterception(true)
  p.on('request', (req) => {
    const u = req.url()
    if (!u.includes(':8911/api/prompt/')) return req.continue()
    const cors = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS', 'Content-Type': 'application/json' }
    if (req.method() === 'OPTIONS') return req.respond({ status: 204, headers: cors, body: '' })
    const path = u.split('/api/prompt/')[1].split('?')[0]
    const send = (data) => req.respond({ status: 200, headers: cors, body: JSON.stringify({ code: 200, biz_code: 0, msg: '', data }) }).catch(() => {})
    if (path === 'chat') {
      return send({ action: 'write', prompt: LONG, red: [], yellow: [], warnings: [], tries: 1, chars: LONG.length, rules: 23, format: '官方 skill 直出', note: NOTE })
    }
    if (path === 'sessions' && req.method() === 'GET') return send(Object.values(store))
    const m = path.match(/^sessions\/([^/]+)$/)
    if (m && req.method() === 'GET') return send(store[m[1]] || null)
    if (m && req.method() === 'PUT') {
      const body = JSON.parse(req.postData() || '{}')
      // ⛔ 只老实存前端推上来的那份：**不**替前端补 AI 消息
      store[m[1]] = Object.assign({ id: m[1], updated_ts: Date.now() }, body)
      const ai = (body.msgs || []).filter((x) => x.role === 'ai')
      console.log(`[PUT] ${m[1]} msgs=${(body.msgs || []).length} 其中 ai=${ai.length}`)
      return send({ id: m[1] })
    }
    if (m && req.method() === 'DELETE') { delete store[m[1]]; return send({ deleted: true }) }
    return send(null)
  })

  await p.goto(PAGE, { waitUntil: 'networkidle2' })
  await sleep(600)
  const tap = async (t) => {
    const box = await p.evaluate((x) => {
      const h = Array.from(document.querySelectorAll('*'))
        .filter((e) => (e.textContent || '').trim() === x && e.getBoundingClientRect().width > 0).pop()
      if (!h) return null
      const r = h.getBoundingClientRect()
      return { x: r.x + r.width / 2, y: r.y + r.height / 2 }
    }, t)
    if (!box) throw new Error('找不到：' + t)
    await p.mouse.click(box.x, box.y)
  }
  await tap('写给'); await sleep(400); await tap('H3'); await sleep(400)
  // 模型也没有默认：先点那格弹出选择框，再选（留空的话发送时会被拦下来问）
  await tap('模型'); await sleep(400); await tap('豆包 Lite'); await sleep(300)
  await p.click('textarea'); await p.type('textarea', '做个四镜的3D动画短片'); await sleep(150)
  await tap('↑'); await sleep(2000)

  const live = await p.evaluate(() => document.body.innerText)
  check('① 页面上有答案（基线，后面的红才有意义）',
        live.includes(MARK), live.slice(0, 120))

  await tap('新对话'); await sleep(500)
  await tap('历史'); await sleep(1000)
  await tap('做个四镜的3D动画短片'); await sleep(1200)
  const got = await p.evaluate(() => document.body.innerText)
  check('② 历史里 AI 那一条还在（正文完整）', got.includes(MARK), got.slice(0, 300))
  check('③ 说明也在（默认展开）', got.includes(NOTE), got.slice(0, 300))

  // 成对：历史里不该冒出「空壳 AI 气泡」
  const shells = await p.evaluate(() => Array.from(document.querySelectorAll('.ai'))
    .filter((e) => e.innerText.trim() === '').length)
  check('④ 没有空白 AI 气泡', shells === 0, `空壳 ${shells} 个`)

  await p.screenshot({ path: 'D:/tmp/vt-shots/prompt-history.png', fullPage: true })
  await b.close()
  console.log(fails ? `\n历史验收：红 ${fails}` : '\n历史验收：全绿')
  process.exit(fails ? 1 : 0)
})().catch((e) => { console.error('FAIL', e.message); process.exit(1) })
