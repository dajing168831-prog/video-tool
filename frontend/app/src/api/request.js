import { API_BASE } from '@/config'

/**
 * 统一请求封装：后端信封 {code, biz_code, msg, data}
 * 业务错误抛 Error(msg)，调用方 catch 后 toast。
 */
export function request(path, { method = 'GET', data, timeout = 120000 } = {}) {
  return new Promise((resolve, reject) => {
    uni.request({
      url: API_BASE + path,
      method,
      data,
      timeout,
      header: { 'Content-Type': 'application/json' },
      success(res) {
        if (res.statusCode !== 200) {
          return reject(new Error(`服务异常（HTTP ${res.statusCode}）`))
        }
        const body = res.data || {}
        if (body.code === 200 && body.biz_code === 0) {
          return resolve(body.data)
        }
        reject(new Error(body.msg || '请求失败'))
      },
      fail(e) {
        const msg = e && e.errMsg ? e.errMsg : ''
        if (msg.includes('timeout')) return reject(new Error('请求超时，文件较大时请稍候重试'))
        reject(new Error('网络异常，请检查网络后重试'))
      },
    })
  })
}

/** 解析分享文案 */
export function parseText(text) {
  return request('/api/parse', { method: 'POST', data: { text } })
}

/**
 * 别家稿 → H3 提示词（转换）。
 * 🩸 要单独收 `biz_code=2`：产出仍有一条判据没过时，那份提示词是能用的。
 * 🩸 超时给到 10 分钟：这条路是**模型带思考直出整篇**，实测 9000 字原稿单次要 3–5 分钟。
 */
export function promptConvert(payload) {
  return new Promise((resolve, reject) => {
    uni.request({
      url: API_BASE + '/api/prompt/convert',
      method: 'POST',
      data: payload,
      timeout: 600000,
      header: { 'Content-Type': 'application/json' },
      success(res) {
        if (res.statusCode !== 200) {
          return reject(new Error(`服务异常（HTTP ${res.statusCode}）`))
        }
        const body = res.data || {}
        if (body.code === 200 && (body.biz_code === 0 || body.biz_code === 2)) {
          return resolve(body)
        }
        reject(new Error(body.msg || '转换失败'))
      },
      fail(e) {
        const msg = e && e.errMsg ? e.errMsg : ''
        if (msg.includes('timeout')) return reject(new Error('转换超时，请稍候重试'))
        reject(new Error('网络异常，请检查网络后重试'))
      },
    })
  })
}

/**
 * 对话：有时问一句，有时直接出稿。
 * 🩸 2026-10-30 主人：「不可能一上来就说提示词，需要短暂交流然后才开始调 skill」。
 * 返回的 data.action 是 'ask'（只回话）或 'write'（出成品），前端按它渲染。
 * 超时给 10 分钟：带思考写整篇要 3–5 分钟。
 */
export function promptChat(payload) {
  return new Promise((resolve, reject) => {
    uni.request({
      url: API_BASE + '/api/prompt/chat',
      method: 'POST',
      data: payload,
      timeout: 600000,
      header: { 'Content-Type': 'application/json' },
      success(res) {
        if (res.statusCode !== 200) {
          return reject(new Error(`服务异常（HTTP ${res.statusCode}）`))
        }
        const body = res.data || {}
        if (body.code === 200 && (body.biz_code === 0 || body.biz_code === 2)) {
          return resolve(body)
        }
        reject(new Error(body.msg || '对话失败'))
      },
      fail(e) {
        const msg = e && e.errMsg ? e.errMsg : ''
        if (msg.includes('timeout')) return reject(new Error('等待超时，请重试'))
        reject(new Error('网络异常，请检查网络后重试'))
      },
    })
  })
}

/**
 * 修订：现有提示词 + 截图 + 一句话反馈 → 只改那几处。
 * 🩸 截图走 data URI 直传，后端不落盘 —— 顾客的片子画面不在我们这多存一份。
 * 超时同样给 10 分钟（带思考读图 + 改稿）。
 */
export function promptRevise(payload) {
  return new Promise((resolve, reject) => {
    uni.request({
      url: API_BASE + '/api/prompt/revise',
      method: 'POST',
      data: payload,
      timeout: 600000,
      header: { 'Content-Type': 'application/json' },
      success(res) {
        if (res.statusCode !== 200) {
          return reject(new Error(`服务异常（HTTP ${res.statusCode}）`))
        }
        const body = res.data || {}
        if (body.code === 200 && (body.biz_code === 0 || body.biz_code === 2)) {
          return resolve(body)
        }
        reject(new Error(body.msg || '修订失败'))
      },
      fail(e) {
        const msg = e && e.errMsg ? e.errMsg : ''
        if (msg.includes('timeout')) return reject(new Error('修订超时，请稍候重试'))
        reject(new Error('网络异常，请检查网络后重试'))
      },
    })
  })
}

/** 取任务详情 */
export function getTask(token) {
  return request(`/api/task/${token}`)
}

/** 视频 / 音频 / 图片的直链（给 <video> 用） */
export function fileUrl(token, kind) {
  return `${API_BASE}/api/file/${token}/${kind}`
}

/**
 * 口播文案（语音转写）—— **两步，别混用**：
 *   peek = 只读缓存，不花钱；页面打开时调它，转过就直接显示
 *   make = 真去识别（按音频时长计费），只在用户点按钮时调
 */
export function peekTranscript(token) {
  return request(`/api/task/${token}/transcript`)
}

export function makeTranscript(token, refresh = false) {
  const q = refresh ? '?refresh=1' : ''
  // 长视频识别要几十秒到几分钟，按默认 120s 会被前端先掐断
  return request(`/api/task/${token}/transcript${q}`, { method: 'POST', timeout: 600000 })
}

// ---------------------------------------------------------------------------
// 复刻爆款

/** 贴链接开始分析（只读原片，不生成任何东西） */
export function cloneAnalyze(text) {
  return request('/api/clone/analyze', { method: 'POST', data: { text } })
}

/** 直接拿已解析的 token 分析，省一次下载 */
export function cloneAnalyzeToken(token) {
  return request('/api/clone/analyze', { method: 'POST', data: { token } })
}

/** 任务详情（分析进度 + 结构摘要） */
export function cloneDetail(id) {
  return request(`/api/clone/${id}`)
}

/** 视觉盘点：原片里有几个人、各在第几秒（结果缓存，重复调用不花钱） */
export function cloneInventory(id, refresh = false) {
  const q = refresh ? '?refresh=1' : ''
  return request(`/api/clone/${id}/inventory${q}`)
}

/** 可选型号（含每个型号各自收的清晰度档位） */
export function cloneModels(channel = '') {
  const q = channel ? `?channel=${channel}` : ''
  return request(`/api/clone/models${q}`)
}

/** 出片/预览共用的请求体（两边必须完全一致，预览才可信） */
function cloneRenderBody(script, opts = {}) {
  const {
    maskBottom = true,
    regenPrompt = '',
    regenRatio = 0,
    regenShots = null,
    regenMode = 'shots',
    regenChannel = 'auto',
    regenModel = '',
    subjectAsset = '',
    // 结构化规格：换什么 / 保什么 / 声音 / 成片规格
    edit = null,
    // 读音校正：显示词 → 念法（识别原文不动）
    pronounce = null,
    ttsVoice = '',
    // 配音语言：zh / en。留空 = 用分析阶段判定的那个
    lang = '',
    // 逐行文案（翻译结果）。给了就**不再按标点重新切句** —— 外语按 14 字硬切
    // 会把句子切成碎片，每片都带 TTS 头尾静音，总时长能翻到 1.7 倍
    scriptLines = null,
    // 只重配这几行（`scriptLines` 的下标）。null = 整片重配（老行为）
    dubLines = null,
    // 每行用哪个音色（{行号: 音色 ID}）。空 = 全部用 ttsVoice
    dubVoices = null,
    // 方言代码（火山 explicit_dialect）。空 = 标准普通话
    ttsDialect = '',
    // 配音和画面差太多时，是否允许强行对齐（会冻帧/截断）
    allowStretch = false,
    // 语速 -30~30（正数=更快）。null/不传 = 按估算自动定
    speechRate = null,
  } = opts
  return {
    script,
    mask_bottom: maskBottom,
    regen_prompt: regenPrompt,
    regen_ratio: regenRatio,
    // shots = 混剪（挑镜头重画）；whole = 整片重制（1:1，动作跟原片走）
    regen_mode: regenMode,
    regen_channel: regenChannel,
    // 空 = 用该通道的默认型号（老用户不动这一项就不传）
    ...(regenModel ? { regen_model: regenModel } : {}),
    ...(subjectAsset ? { subject_asset: subjectAsset } : {}),
    ...(regenShots ? { regen_shots: regenShots } : {}),
    ...(edit ? { edit } : {}),
    ...(pronounce && Object.keys(pronounce).length ? { pronounce } : {}),
    ...(ttsVoice ? { tts_voice: ttsVoice } : {}),
    ...(lang ? { lang } : {}),
    ...(Array.isArray(scriptLines) && scriptLines.length
      ? { script_lines: scriptLines } : {}),
    // 部分重配：只有明确"不是全部"时才传，全选走老路径
    ...(Array.isArray(dubLines) && dubLines.length
      ? { dub_lines: dubLines } : {}),
    // 每人一个音色：没设置任何一个人时不传，走整片音色
    ...(dubVoices && Object.keys(dubVoices).length
      ? { dub_voices: dubVoices } : {}),
    // 方言：不选就不传，走标准普通话
    ...(ttsDialect ? { tts_dialect: ttsDialect } : {}),
    ...(allowStretch ? { allow_stretch: true } : {}),
    ...(speechRate === null || speechRate === undefined
      ? {} : { speech_rate: speechRate }),
  }
}

/** 音色试听：固定演示句，全站按音色缓存（点过一次之后所有人都免费） */
export function cloneVoiceDemo(id, voice) {
  return request(`/api/clone/${id}/voice-demo`, {
    method: 'POST',
    data: { voice },
  })
}

/** 文案试听：按 文案+音色+语速 缓存；返回的 seconds 是**实测**时长 */
export function cloneVoicePreview(id, text, opts = {}) {
  const { voice = '', rate = 0, lang = '' } = opts
  return request(`/api/clone/${id}/voice-preview`, {
    method: 'POST',
    data: { text, voice, rate, lang },
  })
}

/** 试听接口返回的是站内相对路径，播放前补上 API 前缀 */
export function cloneAudioUrl(path) {
  return path ? `${API_BASE}${path}` : ''
}

/** 把中文文案逐句翻成目标语种（C6）。返回 {lines, lang, ratio, passes} */
export function cloneTranslate(id, text, lang) {
  return request(`/api/clone/${id}/translate`, {
    method: 'POST',
    data: { text, lang },
  })
}

/** 出片前预览：本地算的，不花钱。返回会动几段 / 调几次模型 / 成片帧数合同 */
export function clonePlan(id, script, opts = {}) {
  return request(`/api/clone/${id}/plan`, {
    method: 'POST',
    data: cloneRenderBody(script, opts),
  })
}

/**
 * 用官方 skill 现写这一单的逐段编辑指令（**会调用一次对话模型，花钱**）。
 * 写好后落盘，出片直接用它；参数（勾选/参考图/文案/型号）改了签名就变，
 * 出片会回落代码编译版 —— 所以改完参数再点一次。
 */
export function clonePrompts(id, script, opts = {}, force = false) {
  return request(`/api/clone/${id}/prompts${force ? '?force=true' : ''}`, {
    method: 'POST',
    data: cloneRenderBody(script, opts),
    // 要读官方 skill 再逐段写，默认 120s 不够（实测 2 段 40–90s，段多更久）
    timeout: 600000,
  })
}

/** 看这一单当前落盘的逐段指令（零费用，不调模型） */
export function clonePromptsView(id) {
  return request(`/api/clone/${id}/prompts`, { method: 'GET' })
}

/** 这次能复用几段、要重画几段、为什么 —— 全本地算，不花钱 */
export function cloneReusePlan(id, script, opts = {}) {
  return request(`/api/clone/${id}/reuse-plan`, {
    method: 'POST',
    data: cloneRenderBody(script, opts),
  })
}

/** 提交出片 */
export function cloneRender(id, script, opts = {}) {
  return request(`/api/clone/${id}/render`, {
    method: 'POST',
    data: cloneRenderBody(script, opts),
  })
}

/** 视频延长：在这一版的前面或后面再接一段（模型只出新增段，拼接在后端做） */
export function cloneExtend(id, data) {
  return request(`/api/clone/${id}/extend`, { method: 'POST', data })
}

/** 导出配方：镜头表 / 逐句文案与时间 / 参数 / 每次出片的设置（不含原片视频） */
export function cloneRecipe(id) {
  return request(`/api/clone/${id}/recipe`)
}

/** 可选配音音色（火山官方 2.0 列表）。lang 留空 = 按这个任务分析出的语言给 */
/** 声音复刻：上传一段人声训练自己的音色（speaker_id = 控制台音色槽位，S_ 开头） */
export function cloneTrainVoice(speakerId, filePath, lang = 'zh') {
  return new Promise((resolve, reject) => {
    uni.uploadFile({
      url: `${API_BASE}/api/clone/voices/train`,
      filePath,
      name: 'file',
      formData: { speaker_id: speakerId, lang },
      timeout: 300000,
      success(res) {
        let body = {}
        try {
          body = JSON.parse(res.data)
        } catch (e) {
          return reject(new Error(`服务返回异常（HTTP ${res.status}）`))
        }
        if (body.code === 200 && body.biz_code === 0) return resolve(body.data)
        reject(new Error(body.msg || '训练提交失败'))
      },
      fail() {
        reject(new Error('上传失败，请检查网络'))
      },
    })
  })
}

/** 查复刻训练状态；status=2/4 时可以直接配音 */
export function cloneVoiceStatus(speakerId) {
  return request(`/api/clone/voices/train/${encodeURIComponent(speakerId)}`)
}

export function cloneVoices(id, lang) {
  const q = []
  if (id) q.push('cid=' + encodeURIComponent(id))
  if (lang) q.push('lang=' + encodeURIComponent(lang))
  return request('/api/clone/voices' + (q.length ? '?' + q.join('&') : ''))
}

/** 时长估算 + 读音候选（本地计算，不花钱） */
export function cloneEstimate(id, text) {
  return request('/api/clone/estimate', {
    method: 'POST',
    data: { cid: id || '', text: text || '' },
  })
}

/** 上传某个槽位的参考图（person / product / scene） */
export function cloneUploadRef(id, slot, filePath) {
  return new Promise((resolve, reject) => {
    uni.uploadFile({
      url: `${API_BASE}/api/clone/${id}/ref/${slot}`,
      filePath,
      name: 'file',
      timeout: 600000,
      success(res) {
        let body = {}
        try {
          body = JSON.parse(res.data)
        } catch (e) {
          return reject(new Error(`服务返回异常（HTTP ${res.status}）`))
        }
        if (body.code === 200 && body.biz_code === 0) return resolve(body.data)
        reject(new Error(body.msg || '上传失败'))
      },
      fail() {
        reject(new Error('上传失败，请检查网络'))
      },
    })
  })
}

/** 删掉某个槽位的参考图：换装/道具删掉一行时，后面的图必须跟着走，
    不然「第 3 件的包」会跑去除掉那行空出来的第 2 格，静默换错东西。 */
export function cloneDeleteRef(id, slot) {
  return request(`/api/clone/${id}/ref/${slot}`, { method: 'DELETE' })
}

/** 上传风格参考**视频**（A9）：和风格参考图互斥，后端收到就删掉那张图。
    单段 2–15 秒、≤50MB；能不能再塞下母版由后端按型号算 */
export function cloneUploadStyleVideo(id, filePath) {
  return new Promise((resolve, reject) => {
    uni.uploadFile({
      url: `${API_BASE}/api/clone/${id}/style-video`,
      filePath,
      name: 'file',
      timeout: 600000,
      success(res) {
        let body = {}
        try {
          body = JSON.parse(res.data)
        } catch (e) {
          return reject(new Error(`服务返回异常（HTTP ${res.status}）`))
        }
        if (body.code === 200 && body.biz_code === 0) return resolve(body.data)
        reject(new Error(body.msg || '上传失败'))
      },
      fail() {
        reject(new Error('上传失败，请检查网络'))
      },
    })
  })
}

/** 上传原片声音处理用的音频（C4）：kind = bgm 换曲 / sfx 加音效。
    只收纯音频（≤20MB），不进提示词、不占参考素材编号 */
export function cloneUploadAudio(id, kind, filePath) {
  return new Promise((resolve, reject) => {
    uni.uploadFile({
      url: `${API_BASE}/api/clone/${id}/audio/${kind}`,
      filePath,
      name: 'file',
      timeout: 600000,
      success(res) {
        let body = {}
        try {
          body = JSON.parse(res.data)
        } catch (e) {
          return reject(new Error(`服务返回异常（HTTP ${res.status}）`))
        }
        if (body.code === 200 && body.biz_code === 0) return resolve(body.data)
        reject(new Error(body.msg || '上传失败'))
      },
      fail() {
        reject(new Error('上传失败，请检查网络'))
      },
    })
  })
}

/** 删掉上传的 BGM / 音效 */
export function cloneDeleteAudio(id, kind) {
  return request(`/api/clone/${id}/audio/${kind}`, { method: 'DELETE' })
}

/** 删掉风格参考视频 */
export function cloneDeleteStyleVideo(id) {
  return request(`/api/clone/${id}/style-video`, { method: 'DELETE' })
}

/** 上传换人参考图（一张人物照片，用来锁长相） */
export function cloneUploadSubject(id, filePath) {
  return new Promise((resolve, reject) => {
    uni.uploadFile({
      url: `${API_BASE}/api/clone/${id}/subject`,
      filePath,
      name: 'file',
      timeout: 600000,
      success(res) {
        let body = {}
        try {
          body = JSON.parse(res.data)
        } catch (e) {
          return reject(new Error(`服务返回异常（HTTP ${res.status}）`))
        }
        if (body.code === 200 && body.biz_code === 0) return resolve(body.data)
        reject(new Error(body.msg || '上传失败'))
      },
      fail() {
        reject(new Error('上传失败，请检查网络'))
      },
    })
  })
}

/** 出片进度 */
export function cloneRenderDetail(id, rid) {
  return request(`/api/clone/${id}/render/${rid}`)
}

/** 复刻历史 */
export function cloneHistory(limit = 50) {
  return request(`/api/clone/history?limit=${limit}`)
}


/** 复刻相关文件直链 */
export function cloneFileUrl(id, kind, rid) {
  if (kind === 'out' || kind === 'cover' || kind === 'ass') {
    return `${API_BASE}/api/clone/${id}/render/${rid}/file/${kind}`
  }
  if (kind === 'source') return `${API_BASE}/api/clone/${id}/file/source`
  if (kind === 'srccover') return `${API_BASE}/api/clone/${id}/cover`
  if (kind === 'kf') return `${API_BASE}/api/clone/${id}/kf/${rid}`
  if (kind === 'sheet') return `${API_BASE}/api/clone/${id}/sheet`
  if (kind === 'subject') return `${API_BASE}/api/clone/${id}/file/subject`
  // 风格参考视频（A9）：它不是图片槽，单独一条路由
  if (kind === 'refvideo') return `${API_BASE}/api/clone/${id}/file/ref-video`
  // kind = 'slot:person' / 'slot:product' / 'slot:scene'
  if (kind.startsWith('slot:')) return `${API_BASE}/api/clone/${id}/file/slot/${kind.slice(5)}`
  return ''
}


// ---------------------------------------------------------------- 提示词对话历史（存后端）
//
// 🩸 2026-10-30：历史原来只存浏览器本地，换台机器就没了；「新对话」一按旧对话也回不去。
// 现在存在后端 `data/prompt_sessions/<编号>.json`（只存文字，截图只记张数）。

/** 历史对话列表（摘要：标题/时间/几轮，不含正文） */
export function promptSessions() {
  return request('/api/prompt/sessions')
}

/** 打开一份对话（含全部消息） */
export function promptSession(id) {
  return request(`/api/prompt/sessions/${id}`)
}

/** 整份保存（前端每次有新内容就整份推上来） */
export function promptSessionSave(id, payload) {
  return request(`/api/prompt/sessions/${id}`, { method: 'PUT', data: payload })
}

/** 删掉一份 */
export function promptSessionDel(id) {
  return request(`/api/prompt/sessions/${id}`, { method: 'DELETE' })
}
