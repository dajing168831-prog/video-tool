// 判断 headless Chrome 里 blob 下载到底能不能落盘（小文件 vs 大文件）
const puppeteer = require('puppeteer-core')
const fs = require('fs')
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const DL = 'D:/tmp/vt-shots/downloads'

;(async () => {
  fs.mkdirSync(DL, { recursive: true })
  for (const f of fs.readdirSync(DL)) fs.unlinkSync(`${DL}/${f}`)
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] })
  const page = await browser.newPage()
  const client = await page.createCDPSession()
  await client.send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: DL, eventsEnabled: true })
  client.on('Browser.downloadWillBegin', (e) => console.log('[begin]', e.suggestedFilename))
  client.on('Browser.downloadProgress', (e) => console.log('[progress]', e.state, e.receivedBytes))
  await page.goto('data:text/html,<h1>t</h1>')

  // 1KB blob
  await page.evaluate(() => {
    const blob = new Blob(['x'.repeat(1024)], { type: 'text/plain' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = 'small.txt'
    document.body.appendChild(a)
    a.click()
  })
  await sleep(3000)
  console.log('after small:', fs.readdirSync(DL))

  // 41MB blob
  await page.evaluate(() => {
    const blob = new Blob([new Uint8Array(41 * 1024 * 1024)], { type: 'video/mp4' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = 'big.mp4'
    document.body.appendChild(a)
    a.click()
  })
  for (let i = 0; i < 10; i++) {
    await sleep(2000)
    if (fs.readdirSync(DL).includes('big.mp4')) break
  }
  console.log('after big:', fs.readdirSync(DL).map((f) => `${f}:${fs.statSync(`${DL}/${f}`).size}`))
  await browser.close()
})().catch((e) => { console.error('FAIL', e.message); process.exit(1) })
