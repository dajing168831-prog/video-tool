// 验「理解模型没有默认，顾客选什么就是什么」。
// 🩸 2026-10-30 主人：「我们不是说好顾客前端选什么就选什么吗？怎么后端要默认呢？」
//   原来前端预选 lite，顾客一次都没选过，跑的就是 lite。
//
// 判据：① 新浏览器打开，模型那格显示「选一下」② 不选直接发 → 会弹出选择框、不发请求
//      ③ 选了 Pro → 请求体里的 model 必须是 pro ④ 刷新页面后还记得（记在本机）
const puppeteer = require('puppeteer-core')
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const PAGE = 'http://127.0.0.1:8920/#/pages/prompt/index'

const sent = []
let fails = 0
const check = (n, ok, d = '') => {
  console.log(`${ok ? '  ✅' : '  ❌'} ${n}${!ok && d ? '  ' + d : ''}`)
  if (!ok) fails++
}

;(async () => {
  const b = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] })
  const p = await b.newPage()
  await p.setViewport({ width: 430, height: 932, deviceScaleFactor: 2, isMobile: true, hasTouch: true })
  p.on('pageerror', (e) => console.log('[pageerror]', e.message))
  await p.setRequestInterception(true)
  p.on('request', (req) => {
    const u = req.url()
    if (!u.includes(':8911/api/prompt/')) return req.continue()
    const cors = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS', 'Content-Type': 'application/json' }
    if (req.method() === 'OPTIONS') return req.respond({ status: 204, headers: cors, body: '' })
    const path = u.split('/api/prompt/')[1].split('?')[0]
    if (path === 'chat') {
      const body = JSON.parse(req.postData() || '{}')
      sent.push(body)
      return req.respond({ status: 200, headers: cors, body: JSON.stringify({ code: 200, biz_code: 0, msg: '', data: { action: 'ask', question: '选哪个？\n- 甲\n- 乙' } }) }).catch(() => {})
    }
    if (path === 'sessions') return req.respond({ status: 200, headers: cors, body: JSON.stringify({ code: 200, biz_code: 0, msg: '', data: [] }) }).catch(() => {})
    return req.respond({ status: 200, headers: cors, body: JSON.stringify({ code: 200, biz_code: 0, msg: '', data: null }) }).catch(() => {})
  })

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

  await p.goto(PAGE, { waitUntil: 'networkidle2' })
  await sleep(700)
  const chip = await p.evaluate(() => {
    const el = Array.from(document.querySelectorAll('.opt-chip')).find((e) => (e.textContent || '').includes('模型'))
    return el ? el.textContent.trim() : ''
  })
  check('① 新浏览器打开：模型那格是「选一下」（没有预选）',
        chip.includes('选一下'), chip)

  await tap('写给'); await sleep(400); await tap('H3'); await sleep(300)
  await p.click('textarea'); await p.type('textarea', '做个四镜的3D动画短片'); await sleep(150)
  await tap('↑'); await sleep(700)
  check('② 没选模型 → 先弹选择框，请求没发出去',
        sent.length === 0, `已发 ${sent.length} 次`)

  const sheet = await p.evaluate(() => document.body.innerText.includes('豆包 Pro'))
  check('③ 选择框里有 Pro 可选', sheet, '')

  await tap('豆包 Pro'); await sleep(1500)
  check('④ 发出去的请求 model = pro（顾客选的什么就是什么）',
        sent.length === 1 && sent[0].model === 'pro', JSON.stringify(sent.map((s) => s.model)))

  // 刷新：顾客选过的要记住（不预选 ≠ 每次都问）
  await p.goto(PAGE, { waitUntil: 'networkidle2' })
  await sleep(700)
  const chip2 = await p.evaluate(() => {
    const el = Array.from(document.querySelectorAll('.opt-chip')).find((e) => (e.textContent || '').includes('模型'))
    return el ? el.textContent.trim() : ''
  })
  check('⑤ 刷新后还记得选的是 Pro', chip2.includes('Pro'), chip2)

  await p.screenshot({ path: 'D:/tmp/vt-shots/prompt-model.png' })
  await b.close()
  console.log(fails ? `\n模型选择验收：红 ${fails}` : '\n模型选择验收：全绿')
  process.exit(fails ? 1 : 0)
})().catch((e) => { console.error('FAIL', e.message); process.exit(1) })
