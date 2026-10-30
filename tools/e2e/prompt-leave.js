// 真机式验收：**发出去就点「新对话」**，回头在「历史」里要能看到完整输出。
// 🩸 2026-10-30 主人：「我不在那个页面也会把之前的提问输出完整」。
//
// 后端那一半由 p18 S6 证明（请求取消、活照跑、落盘）。这里验前端那一半：
//   ① 请求里带 sid（不带的话后端不知道该写进哪份）
//   ② 中途点「新对话」不会把结果塞进新对话，也不会拿半截去覆盖历史
//   ③ 「历史」按钮在空对话里也在，点开能拉到后端写的那一轮
// 后端用桩：把 8911 的 /api/prompt/* 全拦下来，按新后端的语义自己记账，
// 不发一次真请求、不花一分钱。
const puppeteer = require('puppeteer-core')
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const PAGE = 'http://127.0.0.1:8920/#/pages/prompt/index'

// 成品要够长、够有辨识度：恢复出来的卡里必须**整段**都在
const MARK = 'ZZPROMPT'
const LONG = `【Shot 1】${MARK} a slow push-in across a rain-soaked alley... `.repeat(12)

const store = {}          // sid -> 会话行（跟 backend/app/services/prompt_sessions.py 同构）
const seen = { sid: '' }  // 抓前端到底有没有把 sid 发上来

let fails = 0
function check(name, ok, detail = '') {
  console.log(`${ok ? '  ✅' : '  ❌'} ${name}${!ok && detail ? '  ' + detail : ''}`)
  if (!ok) fails++
}

function row(sid) {
  return store[sid] || (store[sid] = {
    id: sid, title: '', target: '', turns: 0, last_prompt: '',
    msgs: [], updated: '', updated_ts: 0,
  })
}

// 后端那一半的语义：不管前端还在不在，跑完就把这一轮写进文件
function append(sid, user, ai) {
  const r = row(sid)
  if (user) {
    r.msgs.push({ role: 'user', text: user, shots: 0, data: null, error: '' })
    r.turns += 1
    if (!r.title) r.title = user.slice(0, 60)
  }
  if (ai) {
    r.msgs.push({ role: 'ai', text: '', shots: 0, data: ai, error: '' })
    if (ai.prompt) r.last_prompt = ai.prompt
  }
  r.updated = '2026-10-30 15:00:00'
  r.updated_ts = Date.now()
}

const ENV = JSON.stringify({ code: 200, biz_code: 0, msg: '', data: null })

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

    const send = (data, biz = 0, msg = '') => req.respond({
      status: 200, headers: cors,
      body: JSON.stringify({ code: 200, biz_code: biz, msg, data }),
    }).catch(() => {})

    const path = url.split('/api/prompt/')[1].split('?')[0]

    if (path === 'chat' && req.method() === 'POST') {
      const b = JSON.parse(req.postData() || '{}')
      seen.sid = b.sid || ''
      const text = (b.messages || []).filter((m) => m.role === 'user').pop()
      const user = (text && text.content) || ''
      const card = {
        action: 'write', prompt: LONG, red: [], yellow: [], warnings: [],
        tries: 1, chars: LONG.length, rules: 20, format: '官方 skill 直出', note: '',
      }
      await sleep(2500)                      // 模型慢：给顾客足够时间点「新对话」
      append(seen.sid, user, card)           // ← 前端早走了，这里照样记账
      return send(card)
    }
    if (path === 'sessions' && req.method() === 'GET') return send(Object.values(store))
    const m = path.match(/^sessions\/([^/]+)$/)
    if (m && req.method() === 'GET') return send(store[m[1]] || null)
    if (m && req.method() === 'PUT') {
      const b = JSON.parse(req.postData() || '{}')
      store[m[1]] = Object.assign(row(m[1]), b, { updated_ts: Date.now() })
      return send({ id: m[1] })
    }
    if (m && req.method() === 'DELETE') { delete store[m[1]]; return send({ deleted: true }) }
    return send(null)
  })

  await page.goto(PAGE, { waitUntil: 'networkidle2' })
  await sleep(800)

  // 选「写给」= H3（两家没有默认，头一句必问）
  const tap = async (txt, sel = '*') => {
    // 🩸 只认**看得见**的：底部 tabbar 里也有一条文字是「历史」，尺寸 0，
    // 点它等于点在 (0,0)，页面毫无反应（第一次跑就栽在这）。
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
  await tap('写给')
  await sleep(500)
  await tap('H3')
  await sleep(400)

  await page.click('textarea')
  await page.type('textarea', '做个四镜的3D动画短片', { delay: 20 })
  await sleep(200)
  await tap('↑')                              // 发送
  await sleep(600)

  // 关键动作：模型还在跑，顾客点「新对话」
  await tap('新对话')
  await sleep(300)
  const afterReset = await page.evaluate(() => document.body.innerText.replace(/\n+/g, ' | '))
  check('① 点「新对话」后是干净的新对话（没把上一轮塞进来）',
        !afterReset.includes(MARK), afterReset.slice(0, 160))

  await sleep(3500)                           // 等桩把那一轮跑完（此时前端已经离开了）
  check('② 请求里带上了 sid', !!seen.sid, JSON.stringify(seen))

  // 历史按钮必须还在（空对话里也要有 —— 不然最需要它的时候消失）
  await tap('历史')
  await sleep(1200)
  const panel = await page.evaluate(() => document.body.innerText.replace(/\n+/g, ' | '))
  check('③ 空对话里「历史」按钮仍在，点开能看到那一份',
        panel.includes('做成') || panel.includes('四镜'), panel.slice(0, 200))

  await tap('做个四镜的3D动画短片')
  await sleep(1500)
  const got = await page.evaluate(() => document.body.innerText)
  check('④ 切回去看到的是**完整成品**（不是半截、不是空白卡）',
        got.includes(MARK) && got.includes('Shot 1'), got.slice(0, 200))

  await page.screenshot({ path: 'D:/tmp/vt-shots/prompt-leave.png' })
  await browser.close()
  console.log(fails ? `\n离开页面验收：红 ${fails}` : '\n离开页面验收：全绿')
  process.exit(fails ? 1 : 0)
})().catch((e) => { console.error('FAIL', e.message); process.exit(1) })
