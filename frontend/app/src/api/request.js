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
    regenShots = null,
    regenMode = 'auto',
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
    // 口音还原（火山 tone_fidelity）。只对复刻音色生效；默认关=老请求体不变
    ttsFidelity = false,
    // 配音和画面差太多时，是否允许强行对齐（会冻帧/截断）
    allowStretch = false,
    // 语速 -30~30（正数=更快）。null/不传 = 按估算自动定
    speechRate = null,
    // 🩸 只出前 N 段（预览）：0/不传 = 全部。>0 只跑前 N 段、不拼接成片，
    //   先看效果；继续出全部时同样的参数再调一次，前 N 段命中缓存不重复扣费。
    maxSegments = 0,
    // 🩸 强制重跑：跳过逐段产物缓存，重新调模型（会再扣一次费）。
    //   默认 False —— 同样输入永远命中缓存；失败想再抽一次必须显式打开。
    force = false,
  } = opts
  return {
    script,
    mask_bottom: maskBottom,
    regen_prompt: regenPrompt,
    // auto = 勾了哪几镜就重制哪几镜（其余保原片）；whole = 整片重制
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
    // 口音还原：只在显式打开时传
    ...(ttsFidelity ? { tts_fidelity: true } : {}),
    ...(allowStretch ? { allow_stretch: true } : {}),
    ...(speechRate === null || speechRate === undefined
      ? {} : { speech_rate: speechRate }),
    // 预览（只出前 N 段）：不传 = 全部，保持老请求体形状不变
    ...(maxSegments > 0 ? { max_segments: maxSegments } : {}),
    // 强制重跑：只在显式打开时传，保持老请求体形状不变
    ...(force ? { force: true } : {}),
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
  const { voice = '', rate = 0, lang = '', fidelity = false } = opts
  return request(`/api/clone/${id}/voice-preview`, {
    method: 'POST',
    data: { text, voice, rate, lang, fidelity },
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

/** 把「只出前 N 段」的预览继续出完：同参数重跑全片，已出的段命中缓存不重复扣费 */
export function cloneRenderContinue(id, rid) {
  return request(`/api/clone/${id}/render/${rid}/continue`, { method: 'POST' })
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

// ===== 商品短剧（独立子项目，规则来自 D:/skills/product-drama） =====

export function dramaHealth() {
  return request('/api/drama/health')
}

export function dramaList() {
  return request('/api/drama/projects')
}

export function dramaGet(id) {
  return request(`/api/drama/projects/${id}`)
}

/** 新建表单的全部选项（品类/价格带/人群/平台/模式/片长/上限） */
export function dramaOptions() {
  return request('/api/drama/options')
}

function _upload(path, filePath) {
  return new Promise((resolve, reject) => {
    uni.uploadFile({
      url: `${API_BASE}${path}`,
      filePath,
      name: 'file',
      timeout: 300000,
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

/** 新建表单专用：项目还没建，图先落暂存区，返回 {name} */
export function dramaStageUpload(filePath) {
  return _upload('/api/drama/uploads', filePath)
}

/** 暂存图的预览地址（项目还没建时用） */
export function dramaStagedUrl(name) {
  return `${API_BASE}/api/drama/uploads/${encodeURIComponent(name)}`
}

/** 粘商品链接一键导入：返回 {title, description, images[]} */
export function dramaImportUrl(url) {
  return request('/api/drama/import-url', {
    method: 'POST',
    data: { url },
    timeout: 60000,
  })
}

/** 给已建好的项目补商品图，返回整个 doc */
export function dramaUploadImage(id, filePath) {
  return _upload(`/api/drama/projects/${id}/images`, filePath)
}

/** 传/换某个角色的人物参考图（脸、发型、服装的锚） */
export function dramaUploadCast(id, name, filePath) {
  return _upload(`/api/drama/projects/${id}/cast?name=${encodeURIComponent(name)}`, filePath)
}

/** 生成 2×2 四视图定妆照（花钱）：照剧本里的外观画四个机位 */
export function dramaCastSheet(id, name) {
  return request(`/api/drama/projects/${id}/cast/sheet?name=${encodeURIComponent(name)}`, {
    method: 'POST',
    timeout: 600000,
  })
}

// ── 出镜人物库（跨项目复用；有图传图，没图在这里生成定妆照）──

/** 全部人物，返回 {presenters:[{id,name,appearance,note,image,source,created}]} */
export function dramaPresenters() {
  return request('/api/drama/presenters')
}

/** 建一个人物（同名直接返回已有的那个） */
export function dramaPresenterCreate(name, appearance = '', note = '') {
  return request('/api/drama/presenters', {
    method: 'POST',
    data: { name, appearance, note },
  })
}

export function dramaPresenterPatch(id, patch) {
  return request(`/api/drama/presenters/${id}`, { method: 'PATCH', data: patch })
}

export function dramaPresenterDelete(id) {
  return request(`/api/drama/presenters/${id}`, { method: 'DELETE' })
}

/** 库里的定妆图（image 为空表示还没图，直接绑会失败） */
export function dramaPresenterUrl(id) {
  return `${API_BASE}/api/drama/presenters/${encodeURIComponent(id)}/file`
}

/** 有图就传图 */
export function dramaPresenterPhoto(id, filePath) {
  return _upload(`/api/drama/presenters/${id}/photo`, filePath)
}

/** 没图就在这里生成 2×2 四视图定妆照（花钱，只在用户点的时候调） */
export function dramaPresenterSheet(id) {
  return request(`/api/drama/presenters/${id}/sheet`, {
    method: 'POST',
    timeout: 600000,
  })
}

/** 把库里的人绑进这个项目的 cast（复制图进项目目录） */
export function dramaCastFromLibrary(id, presenterId, name = '') {
  return request(`/api/drama/projects/${id}/cast/from-library`, {
    method: 'POST',
    data: { presenter_id: presenterId, name },
  })
}

export function dramaDeleteCast(id, name) {
  return request(`/api/drama/projects/${id}/cast/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  })
}

export function dramaDeleteImage(id, name) {
  return request(`/api/drama/projects/${id}/images/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  })
}

export function dramaImageUrl(id, name) {
  return `${API_BASE}/api/drama/projects/${id}/images/${encodeURIComponent(name)}`
}

/** 事后改商品信息（只改传了的字段） */
export function dramaPatchProduct(id, patch) {
  return request(`/api/drama/projects/${id}/product`, {
    method: 'PATCH',
    data: patch,
  })
}

/** 保存视觉记忆六锚（人物/商品/服装/环境/光线/禁改） */
export function dramaSaveBible(id, bible) {
  return request(`/api/drama/projects/${id}/bible`, {
    method: 'PATCH',
    data: bible,
  })
}

export function dramaCreate(product, answers) {
  return request('/api/drama/projects', {
    method: 'POST',
    data: { product, answers },
  })
}

/**
 * 故事世界候选（2026-11-07）：建项目和出结构卡之间的一步。
 * `route` 空 = 两条路线各出 3 个；填「荒诞」/「煽情」= 只出那一条。
 * 煽情那条内部会让模型先做一轮用户调研，但产出只是假设，不对外声称是真实评论。
 */
/** 可选的短剧类型（顾客挑「拍成什么片」用） */
export function dramaWorldGenres() {
  return request('/api/drama/world-genres')
}

/** genre 非空 = 只在顾客挑的这一个类型里出候选 */
export function dramaWorlds(id, route = '', genre = '') {
  return request(`/api/drama/projects/${id}/worlds`, {
    method: 'POST',
    data: { route, genre },
    timeout: 300000,
  })
}

/** 选中一个世界（写进项目，之后结构卡和剧本都按它来） */
export function dramaPickWorld(id, body) {
  return request(`/api/drama/projects/${id}/world`, {
    method: 'POST',
    data: body,
  })
}

/** 生成一个阶段：card / script / storyboard / check（模型写整篇，给足 5 分钟） */
export function dramaGenerate(id, stage) {
  return request(`/api/drama/projects/${id}/generate?stage=${stage}`, {
    method: 'POST',
    timeout: 300000,
  })
}

export function dramaConfirm(id) {
  return request(`/api/drama/projects/${id}/confirm`, { method: 'POST' })
}

export function dramaReset(id, stage) {
  return request(`/api/drama/projects/${id}/reset?stage=${stage}`, { method: 'POST' })
}

export function dramaJudge(id) {
  return request(`/api/drama/projects/${id}/judge`, {
    method: 'POST',
    timeout: 300000,
  })
}

export function dramaJudgeApply(id, keys) {
  return request(`/api/drama/projects/${id}/judge/apply`, {
    method: 'POST',
    data: { keys },
  })
}

export function dramaGridPlan(id) {
  return request(`/api/drama/projects/${id}/grid/plan`, {
    method: 'POST',
    timeout: 300000,
  })
}

/** 出九宫格整图 —— 会花钱，只在用户明确点了之后调用 */
export function dramaGridRender(id, board = 1) {
  return request(`/api/drama/projects/${id}/grid/render?board=${board}`, {
    method: 'POST',
    timeout: 600000,
  })
}

/** board：第几块分镜板（1 起）。60 秒的片子按出片段各出一块板。 */
export function dramaGridImageUrl(id, board = 1) {
  return `${API_BASE}/api/drama/projects/${id}/grid/file?board=${board}`
}

export function dramaGridCellUrl(id, idx, board = 1) {
  return `${API_BASE}/api/drama/projects/${id}/grid/file/${idx}?board=${board}`
}

/** 规划出片 —— 纯计算，不花钱。model 决定单次时长 / 参考图张数 / 提示词口径；
 *  resolution / ratio 决定出片清晰度与画面比例（两者都进 plan_hash，改了必须重规划） */
export function dramaFilmPlan(id, model = '', chain = 'off', realism = 'auto',
                             resolution = '', ratio = '') {
  const q = [
    model ? `model=${encodeURIComponent(model)}` : '',
    resolution ? `resolution=${encodeURIComponent(resolution)}` : '',
    ratio ? `ratio=${encodeURIComponent(ratio)}` : '',
    `chain=${encodeURIComponent(chain || 'off')}`,
    `realism=${encodeURIComponent(realism || 'auto')}`,
  ].filter(Boolean).join('&')
  return request(`/api/drama/projects/${id}/film/plan?${q}`, {
    method: 'POST',
    timeout: 120000,
  })
}

/** 出片 —— 会花钱，只在用户明确点了之后调用。no=0 出全部段。
 *  `planHash` = 确认卡上那一版计划的指纹：后端会拿现在的文档重算，
 *  对不上就中止、不提交不扣费。 */
export function dramaFilmRender(id, no = 0, resolution = '720p', planHash = '') {
  const q = `no=${no}&resolution=${resolution}` +
            (planHash ? `&plan_hash=${encodeURIComponent(planHash)}` : '')
  return request(`/api/drama/projects/${id}/film/render?${q}`, {
    method: 'POST',
    timeout: 1800000,
  })
}

/** 7 维质量评分：调一次视觉模型（小钱），只在主人点「评这段」时走 */
export function dramaFilmQuality(id, no) {
  return request(`/api/drama/projects/${id}/film/${no}/quality`, {
    method: 'POST',
    timeout: 300000,
  })
}

/** 成片技术质检（本地 ffmpeg，零费用）：黑屏/长静音/响度/削波/定格/流完整性 */
export function dramaFilmQc(id, target = 'all', expectSeconds = 0) {
  const q = `target=${encodeURIComponent(target)}` +
            (expectSeconds ? `&expect_seconds=${expectSeconds}` : '')
  return request(`/api/drama/projects/${id}/qc?${q}`, {
    method: 'POST',
    timeout: 600000,
  })
}

/** 窗口精准修复 · 预演（不花钱）：只算区间/生成时长/花费/指纹 */
export function dramaRepairPlan(id, no, start = 0, end = 0, note = '') {
  const q = `no=${no}&start=${start || 0}&end=${end || 0}` +
            (note ? `&note=${encodeURIComponent(note)}` : '')
  return request(`/api/drama/projects/${id}/film/repair/plan?${q}`, {
    method: 'POST',
    timeout: 120000,
  })
}

/** 窗口精准修复 · 执行（会花钱）：带确认卡指纹，后端重算对不上就中止 */
export function dramaRepairRender(id, no, planHash, start = 0, end = 0, note = '') {
  const q = `no=${no}&plan_hash=${encodeURIComponent(planHash)}` +
            `&start=${start || 0}&end=${end || 0}` +
            (note ? `&note=${encodeURIComponent(note)}` : '')
  return request(`/api/drama/projects/${id}/film/repair/render?${q}`, {
    method: 'POST',
    timeout: 1800000,
  })
}

/** 切回修复前的原段（纯本地，不花钱） */
export function dramaRepairRevert(id, no) {
  return request(`/api/drama/projects/${id}/film/repair/revert?no=${no}`, {
    method: 'POST',
    timeout: 60000,
  })
}

/** 把已出的各段按顺序拼成整片（本地 ffmpeg，不花钱） */
export function dramaFilmConcat(id) {
  return request(`/api/drama/projects/${id}/film/concat`, {
    method: 'POST',
    timeout: 600000,
  })
}

/** no = 段号 或 'all'（拼好的整片） */
export function dramaFilmUrl(id, no) {
  return `${API_BASE}/api/drama/projects/${id}/film/file/${no}`
}

/** 删项目（连同商品图/关键帧/成片）—— 界面必须二次确认 */
export function dramaDeleteProject(id) {
  return request(`/api/drama/projects/${id}`, { method: 'DELETE' })
}

// ===== 预设库 + 成片模板（竞品 look / camera / caption presets + 391 条模板） =====

/** 三张预设表一次拿全（Look 14 / 运镜 22 / 字幕 4 + 运镜词表块） */
export function dramaPresets() {
  return request('/api/drama/presets', { timeout: 30000 })
}

/** 模板库：group=分组 / category=中文类目 / q=关键词 */
export function dramaTemplates({ group = 'all', category = '', q = '' } = {}) {
  const qs = `group=${encodeURIComponent(group)}&category=${encodeURIComponent(category)}&q=${encodeURIComponent(q)}`
  return request(`/api/drama/templates?${qs}`, { timeout: 60000 })
}

/** 按商品推荐（空输入返回空列表，界面别显示假推荐） */
export function dramaTemplatesRecommend({ category = '', name = '', points = '', limit = 4 } = {}) {
  const qs = `category=${encodeURIComponent(category)}&name=${encodeURIComponent(name)}`
    + `&points=${encodeURIComponent(points)}&limit=${limit}`
  return request(`/api/drama/templates/recommend?${qs}`, { timeout: 30000 })
}

export function dramaTemplateOne(id) {
  return request(`/api/drama/templates/${encodeURIComponent(id)}`, { timeout: 30000 })
}

/** 我的模板（自建 / 导入 / 编辑） */
export function dramaTemplatesMine() {
  return request('/api/drama/templates/mine', { timeout: 30000 })
}

/** 存：给了 share 就是导入分享文件，给了 template 就是存配方 */
export function dramaTemplatesMineSave(payload) {
  return request('/api/drama/templates/mine', { method: 'POST', data: payload, timeout: 60000 })
}

export function dramaTemplatesMineUpdate(payload) {
  return request('/api/drama/templates/mine', { method: 'PUT', data: payload, timeout: 60000 })
}

export function dramaTemplatesMineDelete(id) {
  return request(`/api/drama/templates/mine?id=${encodeURIComponent(id)}`, { method: 'DELETE' })
}

/** AI 按商品定制一款配方（要花钱：一次模型调用） */
export function dramaTemplatesCustom({ name = '', category = '', points = '' } = {}) {
  return request('/api/drama/templates/custom', {
    method: 'POST',
    data: { name, category, points },
    timeout: 180000,
  })
}

/** 项目选中哪个模板（存项目文档里，不是浏览器本地） */
export function dramaApplyTemplate(id, payload) {
  return request(`/api/drama/projects/${id}/template`, {
    method: 'POST', data: payload, timeout: 30000,
  })
}

export function dramaClearTemplate(id) {
  return request(`/api/drama/projects/${id}/template`, { method: 'DELETE', timeout: 30000 })
}

// ===== 剧本结构模板（把自己跑通的分镜节奏存下来，换商品复用） =====

export function dramaScriptTemplates() {
  return request('/api/drama/script-templates', { timeout: 30000 })
}

/** 把项目当前已定的分镜存成结构模板（零费用，纯落盘） */
export function dramaScriptTemplateSave(id, name) {
  return request(`/api/drama/projects/${id}/script-template`, {
    method: 'POST', data: { name }, timeout: 30000,
  })
}

export function dramaScriptTemplateDelete(tid) {
  return request(`/api/drama/script-templates/${encodeURIComponent(tid)}`, { method: 'DELETE' })
}

/** 给项目设/清参考结构（id 传空 = 取消）；会记一次使用次数 */
export function dramaRefTemplate(id, tid) {
  return request(`/api/drama/projects/${id}/ref-template`, {
    method: 'POST', data: { id: tid || '' }, timeout: 30000,
  })
}

export function dramaExportUrl(id) {
  return `${API_BASE}/api/drama/projects/${id}/export`
}

/** 发布前自检（纯计算，零费用） */
export function dramaReadiness(id) {
  return request(`/api/drama/projects/${id}/readiness`, {
    method: 'POST',
    timeout: 120000,
  })
}

/** 发布门禁（脚本自检 + 成片质检 + 7 维验收 + AI 带货规则，最差状态胜出） */
export function dramaGate(id) {
  return request(`/api/drama/projects/${id}/gate`, {
    method: 'POST',
    timeout: 600000,
  })
}

/** 在飞任务视图：`active=1` 只回还没收尾的（这些是已付钱的钱） */
export function dramaTasks(active = 1) {
  return request(`/api/drama/tasks?active=${active}`, { method: 'GET', timeout: 60000 })
}

/** 一键流水线：从 from_stage 起跑（judge / stock_fill / compose），后台跑、进度落盘。
 *  🩸 这三段都不出片（判官=文本费 / 配画面=免费源 / 合成=本地 ffmpeg） */
export function dramaPipelineStart(id, fromStage = 'judge', opts = {}) {
  return request(`/api/drama/projects/${id}/pipeline`, {
    method: 'POST',
    data: { from_stage: fromStage, ...opts },
    timeout: 60000,
  })
}

/** 流水线状态（前端轮询）：status = idle/running/done/failed/interrupted */
export function dramaPipelineState(id) {
  return request(`/api/drama/projects/${id}/pipeline`, { method: 'GET', timeout: 30000 })
}

/** 任务中心三档：paid（已发出去的钱）/ running / attention / recent / batch */
export function dramaTaskCenter() {
  return request('/api/drama/task-center', { method: 'GET', timeout: 60000 })
}

/** 字幕导出地址（浏览器直接开就是下载）：format 只认 srt / vtt */
export function dramaSubtitleUrl(id, format = 'srt') {
  return `${API_BASE}/api/drama/projects/${id}/subtitle?format=${format}`
}

/** 生成封面（本地 ffmpeg 抽帧 + 压标题，零费用） */
export function dramaCoverRun(id, title = '', at = 1, position = 'center') {
  const q = `title=${encodeURIComponent(title)}&at=${at || 1}&position=${position}`
  return request(`/api/drama/projects/${id}/cover?${q}`, {
    method: 'POST',
    timeout: 180000,
  })
}

/** 封面图地址 */
export function dramaCoverUrl(id) {
  return `${API_BASE}/api/drama/projects/${id}/cover/file`
}

// ===== D 组合成与音频（BGM / 字幕烧录 / 转场 / 渲染三档 / 尾卡 / 速览 / GIF） =====
// 全部本地 ffmpeg，零生成费；出片（花钱）仍然只走 dramaFilmRender。

/** 合成可选项：转场四档 / 渲染三档 / 字幕四档 + 默认值 */
export function dramaComposeOptions() {
  return request('/api/drama/compose/options')
}

/** 合成规划（零费用、不编码）：时间轴 / 字幕条 / 切点 / 警告 */
export function dramaComposePlan(id, payload = {}) {
  return request(`/api/drama/projects/${id}/compose/plan`, {
    method: 'POST',
    data: payload,
    timeout: 120000,
  })
}

/** 执行合成（本地 ffmpeg，零生成费）。plan_hash 对不上后端会中止、不产出。 */
export function dramaComposeRun(id, payload = {}) {
  return request(`/api/drama/projects/${id}/compose`, {
    method: 'POST',
    data: payload,
    timeout: 1800000,
  })
}

/** 合成片地址 */
export function dramaComposeUrl(id, name) {
  // 不带 name = 最新一版；带 name = 历史里的某一版（后端只认 compose-日期-时间.mp4）
  const q = name ? `?name=${encodeURIComponent(name)}` : ''
  return `${API_BASE}/api/drama/projects/${id}/compose/file${q}`
}

/** 上传 BGM：mp3 / wav / aac / m4a，≤20MB */
export function dramaBgmUpload(id, filePath) {
  return _upload(`/api/drama/projects/${id}/bgm`, filePath)
}

export function dramaBgmDelete(id) {
  return request(`/api/drama/projects/${id}/bgm`, { method: 'DELETE' })
}

export function dramaBgmUrl(id) {
  return `${API_BASE}/api/drama/projects/${id}/bgm/file`
}

/** 成片速览（本地 ffmpeg）：smart=按真实切点取样，even=均匀取样 */
export function dramaContactSheet(id, params = {}) {
  const q = Object.keys(params)
    .map((k) => `${encodeURIComponent(k)}=${encodeURIComponent(params[k])}`)
    .join('&')
  return request(`/api/drama/projects/${id}/contact-sheet${q ? '?' + q : ''}`, {
    method: 'POST',
    timeout: 600000,
  })
}

export function dramaContactSheetUrl(id) {
  return `${API_BASE}/api/drama/projects/${id}/contact-sheet/file`
}

/** 预览 GIF（本地 ffmpeg）：成片的一小段 → 128 色循环 GIF */
export function dramaPreviewGif(id, params = {}) {
  const q = Object.keys(params)
    .map((k) => `${encodeURIComponent(k)}=${encodeURIComponent(params[k])}`)
    .join('&')
  return request(`/api/drama/projects/${id}/preview-gif${q ? '?' + q : ''}`, {
    method: 'POST',
    timeout: 600000,
  })
}

export function dramaPreviewGifUrl(id) {
  return `${API_BASE}/api/drama/projects/${id}/preview-gif/file`
}

// ===== E 组 · 发行物料（多平台导出 / 二维码 / 图文卡 / 原生感 / 母版 / 发布文案） =====
// 除 `dramaPublishLlm` 外全部本地 ffmpeg，零生成费。

/** 平台规格 + 构图三档 + 原生感三档 + 卡片主题 */
export function dramaPlatforms() {
  return request('/api/drama/platforms')
}

/** 按平台重构图导出。preview=true 只回单帧 data URL，不产片 */
export function dramaExportPlatform(id, payload = {}) {
  return request(`/api/drama/projects/${id}/export-platform`, {
    method: 'POST',
    data: payload,
    timeout: 1800000,
  })
}

export function dramaExportPlatformUrl(id) {
  return `${API_BASE}/api/drama/projects/${id}/export-platform/file`
}

/** 店铺二维码（UTM）。burn=true 表示打算烧进成片 → 抖音会被拒（除非 force） */
export function dramaShopQr(id, payload = {}) {
  return request(`/api/drama/projects/${id}/shop-qr`, { method: 'POST', data: payload })
}

export function dramaShopQrUrl(id) {
  return `${API_BASE}/api/drama/projects/${id}/shop-qr/file`
}

/** 小红书图文卡：标题卡 + 每镜台词一卡 */
export function dramaCarousel(id, payload = {}) {
  return request(`/api/drama/projects/${id}/carousel`, {
    method: 'POST',
    data: payload,
    timeout: 600000,
  })
}

export function dramaCarouselUrl(id, idx) {
  return `${API_BASE}/api/drama/projects/${id}/carousel/file/${idx}`
}

/** 原生感后期：手持漂移 + 颗粒 + 去精致调色 */
export function dramaNativeFeel(id, payload = {}) {
  return request(`/api/drama/projects/${id}/native-feel`, {
    method: 'POST',
    data: payload,
    timeout: 1800000,
  })
}

export function dramaNativeFeelUrl(id) {
  return `${API_BASE}/api/drama/projects/${id}/native-feel/file`
}

/** 母版：action=analyze 只体检，action=render 才产新片 */
export function dramaMastering(id, payload = {}) {
  return request(`/api/drama/projects/${id}/mastering`, {
    method: 'POST',
    data: payload,
    timeout: 1800000,
  })
}

export function dramaMasteringUrl(id) {
  return `${API_BASE}/api/drama/projects/${id}/mastering/file`
}

/** 发布文案 · 模板版（零费用、确定性） */
export function dramaPublishPack(id, payload = {}) {
  return request(`/api/drama/projects/${id}/publish-pack`, { method: 'POST', data: payload })
}

/** 发布文案 · 模型版（花一次调用） */
export function dramaPublishLlm(id, payload = {}) {
  return request(`/api/drama/projects/${id}/publish`, {
    method: 'POST',
    data: payload,
    timeout: 180000,
  })
}

// ---------- 第六批：生成链增强 ----------

/** 话题起片：选项（五种旁白风格 / 片长档 / 版本数上限） */
export function dramaTopicOptions() {
  return request('/api/drama/topic/options')
}

/** 话题起片：一句话主题 → 建项目 + 写 N 版内容向脚本（一次模型调用） */
export function dramaTopicCreate(payload = {}) {
  return request('/api/drama/topic', { method: 'POST', data: payload, timeout: 300000 })
}

/** 多版脚本：列出全部版本 */
export function dramaScripts(id) {
  return request(`/api/drama/projects/${id}/scripts`)
}

/** 多版脚本：切版本 */
export function dramaSelectScript(id, sid) {
  return request(`/api/drama/projects/${id}/scripts/${sid}/select`, { method: 'POST' })
}

/** 多版脚本：删版本 */
export function dramaDeleteScript(id, sid) {
  return request(`/api/drama/projects/${id}/scripts/${sid}`, { method: 'DELETE' })
}

/** 手写脚本导入：一句一镜切开，直接有分镜（不调模型） */
export function dramaImportScript(id, payload = {}) {
  return request(`/api/drama/projects/${id}/import-script`, { method: 'POST', data: payload })
}

/** 能力预检：可选型号能力摘要（不调模型） */
export function dramaModelCapabilities() {
  return request('/api/drama/model-capabilities')
}

/** 能力预检：会怎么改参数 + 会踩什么坑 */
export function dramaPreflight(payload = {}) {
  return request('/api/drama/preflight', { method: 'POST', data: payload })
}

/** 变体矩阵：只出计划（不合成） */
export function dramaVariantsPlan(id, payload = {}) {
  return request(`/api/drama/projects/${id}/variants/plan`, { method: 'POST', data: payload })
}

/** 变体矩阵：按计划逐条合成（本地 ffmpeg，零生成费） */
export function dramaVariantsRender(id, payload = {}) {
  return request(`/api/drama/projects/${id}/variants/render`, {
    method: 'POST',
    data: payload,
    timeout: 3600000,
  })
}

export function dramaVariantUrl(id, idx) {
  return `${API_BASE}/api/drama/projects/${id}/variants/${idx}/file`
}

/** B2 素材库：项目自己的素材池（图 / 视频），带标签与出处 */
export function dramaMaterials(id) {
  return request(`/api/drama/projects/${id}/materials`)
}

export function dramaMaterialUpload(id, filePath) {
  return _upload(`/api/drama/projects/${id}/materials`, filePath)
}

/** 改原名 / 标签 / 出处（author·license·source_url 是授权清单的依据） */
export function dramaMaterialPatch(id, name, body) {
  return request(`/api/drama/projects/${id}/materials/${encodeURIComponent(name)}`, {
    method: 'PATCH', data: body,
  })
}

export function dramaMaterialDelete(id, name) {
  return request(`/api/drama/projects/${id}/materials/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  })
}

export function dramaMaterialUrl(id, name) {
  return `${API_BASE}/api/drama/projects/${id}/materials/${encodeURIComponent(name)}/file`
}

/** B5 授权清单：素材库 + BGM + AI 出片段 */
export function dramaCredits(id, format = 'json') {
  if (format === 'md') {
    return fetch(`${API_BASE}/api/drama/projects/${id}/credits?format=md`)
      .then((r) => r.text())
  }
  return request(`/api/drama/projects/${id}/credits`, { data: { format } })
}

/** 登记 BGM 出处（author / license / source_url） */
export function dramaBgmCredit(id, body) {
  return request(`/api/drama/projects/${id}/bgm/credit`, { method: 'POST', data: body })
}

/** B4 每镜参考画面：已绑的 + 可选图片 */
export function dramaShotMaterials(id) {
  return request(`/api/drama/projects/${id}/shot-materials`)
}

/** 整表保存（items: [{shot_id, material}]）—— 删一条 = 提交时不含它 */
export function dramaShotMaterialsSave(id, items) {
  return request(`/api/drama/projects/${id}/shot-materials`, { method: 'PUT', data: { items } })
}

/** 逐镜自动配一张（只补没配的，命中 0 词不配） */
export function dramaShotMaterialsAuto(id) {
  return request(`/api/drama/projects/${id}/shot-materials/auto`, { method: 'POST' })
}

/** 素材当画面（视频）：已绑的 + 可选视频 */
export function dramaShotClips(id) {
  return request(`/api/drama/projects/${id}/shot-clips`)
}

/** 整表保存（items: [{shot_id, material}]）—— 一镜一段 */
export function dramaShotClipsSave(id, items) {
  return request(`/api/drama/projects/${id}/shot-clips`, { method: 'PUT', data: { items } })
}

/** 免版权素材源（B3）：哪些免 Key、支持什么媒体类型 */
export function dramaStockSources() {
  return request('/api/drama/stock/sources')
}

/** 多源检索（只预览，不下载）：{ query, source, media_type, orientation, per_page } */
export function dramaStockSearch(id, data) {
  return request(`/api/drama/projects/${id}/stock/search`, { method: 'POST', data })
}

/** 把选中的候选下载进来：图/视频进素材库，音频进 BGM 位（只传 source + media_type + id） */
export function dramaStockImport(id, data) {
  return request(`/api/drama/projects/${id}/stock/import`, { method: 'POST', data })
}

/** 逐镜自动配画面（联网搜库 → 降级阶梯 → 下载入库 → 绑定） */
export function dramaStockAutoFill(id, data) {
  return request(`/api/drama/projects/${id}/stock/auto-fill`, { method: 'POST', data })
}

/** B6 长视频导入：原始 body 流式上传（不穿 multipart）—— 1GB 才不会先在服务端落一份临时盘。
 *  `filePath` = H5 下 chooseFile 给的 blob URL；`name` = 原名（决定扩展名白名单）。
 *  返回 { source }；onProgress(pct) 给进度条用。 */
export function dramaMediaImport(id, filePath, name, onProgress) {
  return new Promise((resolve, reject) => {
    const send = (blob) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', `${API_BASE}/api/drama/projects/${id}/media/import`)
      xhr.setRequestHeader('X-File-Name', encodeURIComponent(name || 'video.mp4'))
      xhr.setRequestHeader('Content-Type', 'application/octet-stream')
      xhr.timeout = 0 // 1GB 传得可能很久，不设超时
      if (xhr.upload && onProgress) {
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) onProgress(Math.min(100, Math.round((e.loaded / e.total) * 100)))
        }
      }
      xhr.onload = () => {
        let body = {}
        try {
          body = JSON.parse(xhr.responseText || '{}')
        } catch (e) {
          return reject(new Error(`服务返回异常（HTTP ${xhr.status}）`))
        }
        if (body.code === 200 && body.biz_code === 0) return resolve(body.data)
        reject(new Error(body.msg || '上传失败'))
      }
      xhr.onerror = () => reject(new Error('上传失败，请检查网络'))
      xhr.onabort = () => reject(new Error('上传已取消'))
      xhr.send(blob)
    }
    // blob: URL 是 H5 才有的；其它端没有 Blob 全局时直接报人话
    if (typeof Blob !== 'undefined' && filePath && typeof filePath !== 'string') return send(filePath)
    if (typeof fetch !== 'function') return reject(new Error('请在网页版导入长视频'))
    fetch(filePath)
      .then((r) => r.blob())
      .then(send)
      .catch(() => reject(new Error('读取文件失败，请重选一次')))
  })
}

/**
 * 长视频导入（小程序端）：小程序没有 XHR 原始 body，只能走 uni.uploadFile 的 multipart。
 * 后端同一个端点 `/media/import` 认两种 content-type，落盘后走同一套校验。
 */
export function dramaMediaImportUni(id, filePath, name, onProgress) {
  return new Promise((resolve, reject) => {
    const task = uni.uploadFile({
      url: `${API_BASE}/api/drama/projects/${id}/media/import`,
      filePath,
      name: 'file',
      header: { 'X-File-Name': encodeURIComponent(name || 'video.mp4') },
      timeout: 0,
      success(res) {
        let body = {}
        try {
          body = JSON.parse(res.data)
        } catch (e) {
          return reject(new Error(`服务返回异常（HTTP ${res.status}）`))
        }
        if (body.code === 200 && body.biz_code === 0) return resolve(body.data)
        reject(new Error(body.msg || '导入失败'))
      },
      fail() {
        reject(new Error('上传失败，请检查网络'))
      },
    })
    if (task && task.onProgressUpdate && onProgress) {
      task.onProgressUpdate((e) => onProgress(e.progress || 0))
    }
  })
}

/** 已导入的长视频原料列表（和素材库分开） */
export function dramaMediaList(id) {
  return request(`/api/drama/projects/${id}/media`)
}

/** 删掉一条导入的长视频（文件 + 索引） */
export function dramaMediaDelete(id, mid) {
  return request(`/api/drama/projects/${id}/media/${mid}`, { method: 'DELETE' })
}

/** 原视频播放地址（支持 Range，可以直接拖动进度条） */
export function dramaMediaUrl(id, mid) {
  return `${API_BASE}/api/drama/projects/${id}/media/${mid}/file`
}

/** B7 转写状态 / 进度 / 全文（前端轮询这个） */
export function dramaMediaTranscript(id, mid) {
  return request(`/api/drama/projects/${id}/media/${mid}/transcript`)
}

/** 开始 / 取消转写：action = 'start' | 'cancel'；resume=false 丢掉旧检查点从头来 */
export function dramaMediaTranscriptStart(id, mid, opts = {}) {
  return request(`/api/drama/projects/${id}/media/${mid}/transcript`, {
    method: 'POST',
    data: { action: 'start', language: 'zh', ...opts },
    timeout: 60000,
  })
}

export function dramaMediaTranscriptCancel(id, mid) {
  return request(`/api/drama/projects/${id}/media/${mid}/transcript`, {
    method: 'POST',
    data: { action: 'cancel' },
    timeout: 60000,
  })
}

/** B8 按文字剪：按关键词找候选片段（本地算，不花钱）。params = {query, target_seconds, limit} */
export function dramaMediaClips(id, mid, params = {}) {
  const q = Object.keys(params)
    .filter((k) => params[k] !== '' && params[k] !== undefined && params[k] !== null)
    .map((k) => `${encodeURIComponent(k)}=${encodeURIComponent(params[k])}`)
    .join('&')
  return request(`/api/drama/projects/${id}/media/${mid}/clips${q ? '?' + q : ''}`)
}

/** 把选中的片段真剪出来（本地 ffmpeg 重编码，零生成费） */
export function dramaMediaClipCut(id, mid, body) {
  return request(`/api/drama/projects/${id}/media/${mid}/clips/cut`, {
    method: 'POST',
    data: body,
    timeout: 600000,
  })
}

/** 剪好的片段地址 */
export function dramaMediaClipUrl(id, mid, name) {
  return `${API_BASE}/api/drama/projects/${id}/media/${mid}/clips/${name}/file`
}

/** B9 时间线导出：拿文本内容（inline），前端自己落文件。body = {format, ranges?, revision?} */
export function dramaMediaTimeline(id, mid, body = {}) {
  return request(`/api/drama/projects/${id}/media/${mid}/timeline`, {
    method: 'POST',
    data: { ...body, inline: true },
    timeout: 60000,
  })
}

/** D1 配音：免费音色表（微软 Edge 朗读，不用 Key） */
export function dramaTtsFreeVoices() {
  return request('/api/drama/tts/free')
}

/** D3 配音轨：现状（几句、文件还在不在） */
export function dramaVoiceGet(id) {
  return request(`/api/drama/projects/${id}/voice`)
}

/** D3 配音轨：给整片配音（逐句合成，免费音色；句子多要等，给足超时） */
export function dramaVoiceBuild(id, body = {}) {
  return request(`/api/drama/projects/${id}/voice/build`, {
    method: 'POST',
    data: body,
    timeout: 600000,
  })
}

/** D3 配音轨：删掉登记（合成退回模型原生出声） */
export function dramaVoiceDelete(id) {
  return request(`/api/drama/projects/${id}/voice`, { method: 'DELETE' })
}

/** ArrayBuffer → 文本（只用来读后端的错误 JSON，内容很短）—— 仅小程序用 */
function _mpBufToText(buf) {
  try {
    const bytes = new Uint8Array(buf)
    let s = ''
    for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i])
    return decodeURIComponent(escape(s))
  } catch (e) {
    return ''
  }
}

/**
 * D1 配音试听：后端失败时回 JSON，这里转成人话 reject。
 * H5 拿 mp3 Blob；小程序拿 mp3 ArrayBuffer（小程序没有 XMLHttpRequest / Blob）。
 */
export function dramaTtsFreePreview(body) {
  // #ifdef H5
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_BASE}/api/drama/tts/free`)
    xhr.responseType = 'blob'
    xhr.setRequestHeader('Content-Type', 'application/json')
    xhr.onload = () => {
      const blob = xhr.response
      if (xhr.status !== 200) {
        reject(new Error('试听失败'))
        return
      }
      if (blob && (blob.type || '').indexOf('json') >= 0) {
        const reader = new FileReader()
        reader.onload = () => {
          let msg = '试听失败'
          try { msg = JSON.parse(reader.result).msg || msg } catch (e) { /* 保持默认 */ }
          reject(new Error(msg))
        }
        reader.readAsText(blob)
        return
      }
      resolve(blob)
    }
    xhr.onerror = () => reject(new Error('网络错误，试听失败'))
    xhr.ontimeout = () => reject(new Error('试听超时'))
    xhr.timeout = 60000
    xhr.send(JSON.stringify(body || {}))
  })
  // #endif

  // #ifndef H5
  return new Promise((resolve, reject) => {
    uni.request({
      url: `${API_BASE}/api/drama/tts/free`,
      method: 'POST',
      data: body || {},
      timeout: 60000,
      responseType: 'arraybuffer',
      header: { 'Content-Type': 'application/json' },
      success(res) {
        if (res.statusCode !== 200) {
          reject(new Error('试听失败'))
          return
        }
        const h = res.header || {}
        const ct = String(h['content-type'] || h['Content-Type'] || '')
        if (ct.indexOf('json') >= 0) {
          let msg = '试听失败'
          try { msg = JSON.parse(_mpBufToText(res.data)).msg || msg } catch (e) { /* 保持默认 */ }
          reject(new Error(msg))
          return
        }
        resolve(res.data)
      },
      fail(e) {
        const m = (e && e.errMsg) || ''
        reject(new Error(m.indexOf('timeout') >= 0 ? '试听超时' : '网络错误，试听失败'))
      },
    })
  })
  // #endif
}

/** D8 译制：支持的语言 + 每种语言推荐的免费配音音色 */
export function dramaDubLangs() {
  return request('/api/drama/dub/langs')
}

/** 把当前分镜译成目标语言（apply=true 直接写回分镜，写回前自动备份） */
export function dramaDubStart(id, body) {
  return request(`/api/drama/projects/${id}/dub`, {
    method: 'POST',
    data: body,
    timeout: 300000,
  })
}

/** 已译版本列表 */
export function dramaDubs(id) {
  return request(`/api/drama/projects/${id}/dubs`)
}

/** 应用某个译制版本 */
export function dramaDubApply(id, lang) {
  return request(`/api/drama/projects/${id}/dubs/${lang}/apply`, { method: 'POST' })
}

/** 还原应用译制版之前的原分镜 */
export function dramaDubRestore(id) {
  return request(`/api/drama/projects/${id}/dubs/restore`, { method: 'POST' })
}

/** A3 商品库：列表（跨项目复用商品卡） */
export function dramaProducts() {
  return request('/api/drama/products')
}

/** 把当前项目的商品信息存进商品库 */
export function dramaProductSave(projectId, name) {
  return request('/api/drama/products', {
    method: 'POST',
    data: { project_id: projectId, name: name || '' },
  })
}

/** 把商品卡应用到某个项目（字段照抄 + 图片复制进项目） */
export function dramaProductApply(prid, projectId) {
  return request(`/api/drama/products/${prid}/apply`, {
    method: 'POST',
    data: { project_id: projectId },
  })
}

/** 删商品卡 */
export function dramaProductDelete(prid) {
  return request(`/api/drama/products/${prid}`, { method: 'DELETE' })
}

/** 直接建一张商品卡（不经过项目） */
export function dramaProductCreate(body) {
  return request('/api/drama/products/create', {
    method: 'POST',
    data: body,
  })
}

/** 给商品卡传一张图（最多 5 张） */
export function dramaProductImageUpload(prid, filePath) {
  return _upload(`/api/drama/products/${prid}/images`, filePath)
}

/** 删商品卡上的一张图 */
export function dramaProductImageDelete(prid, name) {
  return request(`/api/drama/products/${prid}/images/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  })
}

/** 改商品卡字段（name/category/price/platform/audience/facts/points，只传要改的） */
export function dramaProductPatch(prid, patch) {
  return request(`/api/drama/products/${prid}`, {
    method: 'PATCH',
    data: patch,
  })
}

/** 商品卡里的图片（预览用） */
export function dramaProductImageUrl(prid, name) {
  return `${API_BASE}/api/drama/products/${prid}/images/${encodeURIComponent(name)}`
}

/** D7 风格配方：内置配方 + 格式标记 */
export function dramaStylePacks() {
  return request('/api/drama/style-packs')
}

/** 项目当前设置导出成配方文本 */
export function dramaStylePackExport(projectId) {
  return request(`/api/drama/projects/${projectId}/style-pack`)
}

/** 导入配方（只覆盖配方里带的那几项合成设置） */
export function dramaStylePackImport(projectId, text) {
  return request(`/api/drama/projects/${projectId}/style-pack`, {
    method: 'POST',
    data: { text },
  })
}

/** F8 跨项目结构自检 */
export function dramaHomogeneity(limit = 8) {
  return request(`/api/drama/insights/homogeneity?limit=${limit}`)
}

/** H4 设置中心：全局默认值 + 密钥状态（只回掩码） */
export function dramaSettings() {
  return request('/api/drama/settings')
}

/** 改全局默认值（只传要改的项） */
export function dramaSettingsSave(patch) {
  return request('/api/drama/settings', { method: 'PATCH', data: { settings: patch } })
}

/** 恢复默认 */
export function dramaSettingsReset() {
  return request('/api/drama/settings/reset', { method: 'POST' })
}

/** H4 旧版设置导入：跑五版修复，只搬语义对得上的项 */
export function dramaSettingsImport(body) {
  return request('/api/drama/settings/import', { method: 'POST', data: body, timeout: 60000 })
}

/** G3 趋势话题：source=cn 国内（抖音→头条）｜给 geo 走 Google Trends */
export function dramaTrends(params = {}) {
  const q = []
  if (params.source) q.push(`source=${encodeURIComponent(params.source)}`)
  if (params.geo) q.push(`geo=${encodeURIComponent(params.geo)}`)
  if (params.limit) q.push(`limit=${encodeURIComponent(params.limit)}`)
  if (params.persona) q.push(`persona=${encodeURIComponent(params.persona)}`)
  return request(`/api/drama/trends${q.length ? '?' + q.join('&') : ''}`)
}

/** G2 作品流：跨项目成片墙（缺封面的按预算回填首帧） */
export function dramaWorks() {
  return request('/api/drama/works')
}

/** G4 这个项目录过的发布数据（新的在前） */
export function dramaMetrics(pid) {
  return request(`/api/drama/projects/${pid}/metrics`)
}

/** G4 录入一条发布数据（风格/品类由后端定格） */
export function dramaMetricSave(pid, data) {
  return request(`/api/drama/projects/${pid}/metrics`, { method: 'POST', data })
}

/** G5 全站风格/钩子成效（按转化率降序） */
export function dramaStyleInsights() {
  return request('/api/drama/insights/styles')
}

/** C4 可探测通道登记（只回是否配置，不回 Key） */
export function dramaProbeProviders() {
  return request('/api/drama/probe')
}

/** C4 跑连通性探针：传空数组 = 测全部登记的通道 */
export function dramaProbeRun(names = []) {
  return request('/api/drama/probe', { method: 'POST', data: { names } })
}

/** C17 领回**已提交**的云端任务（只查+下载，不会重新提交） */
export function dramaTaskResume(pid, no) {
  return request(`/api/drama/projects/${pid}/tasks/${no}/resume`, { method: 'POST' })
}

/** G1 批量作业：查作业（active=1 找在飞的；job_id 查指定；都不传 = 最新一个） */
export function dramaBatchGet(params = {}) {
  const q = []
  if (params.job_id) q.push(`job_id=${encodeURIComponent(params.job_id)}`)
  if (params.active) q.push('active=1')
  return request(`/api/drama/batch${q.length ? '?' + q.join('&') : ''}`)
}

/** G1 建批量作业（同一时间只留一个在飞，旧的 running 会被结算成 cancelled） */
export function dramaBatchCreate(config, items) {
  return request('/api/drama/batch', { method: 'POST', data: { config, items } })
}

/** G1 写回：条目（状态/项目/合成/错误）或作业结算（running/done/cancelled） */
export function dramaBatchPatch(payload) {
  return request('/api/drama/batch', { method: 'PATCH', data: payload })
}

/** G1 反同质化轮换计划（钩子/音色/字幕；同 seed 可复现） */
export function dramaBatchPlan(body) {
  return request('/api/drama/batch/plan', { method: 'POST', data: body })
}

/** B11 媒体解构：传文件路径，服务端读 Key（Key 不上前端） */
export function dramaMediaAnalyze(filePath) {
  return new Promise((resolve, reject) => {
    uni.uploadFile({
      url: `${API_BASE}/api/drama/media/analyze`,
      filePath,
      name: 'file',
      timeout: 300000,
      success(res) {
        let body = {}
        try {
          body = JSON.parse(res.data)
        } catch (e) {
          return reject(new Error(`服务返回异常（HTTP ${res.status}）`))
        }
        if (body.code === 200 && body.biz_code === 0) return resolve(body.data)
        reject(new Error(body.msg || '媒体解构失败'))
      },
      fail() {
        reject(new Error('上传失败，请检查网络'))
      },
    })
  })
}

/** B11 把解构结论存进项目（mediaType/summary/tags/reusablePrompt） */
export function dramaProductionSave(pid, mediaInsight) {
  return request(`/api/drama/projects/${pid}/production`, {
    method: 'PATCH',
    data: { mediaInsight },
  })
}
