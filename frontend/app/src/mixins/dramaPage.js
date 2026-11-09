/**
 * 商品短剧 · 页面共用逻辑（从旧单页 drama/index.vue 原样搬出，方法体一个字没改）。
 *
 * 为什么要混入而不是拆成 composable：
 *   旧页是 options API + 6000 行方法，逐段改写成 composition 等于重写一遍，
 *   风险远大于收益。这里先「整块搬进来」，四步页面各自只取需要的模板块；
 *   等四页稳定后再按业务域收窄（见 docs/DRAMA-UI-RESTRUCTURE.md 第五节）。
 *
 * 🩸 页面生命周期（onLoad/onShow/onUnload）不放这里：uni-app 的页面钩子必须写在页面里，
 *    混入里写了不保证被调用。每页自己声明，再调这里的方法。
 */
import {
  dramaList, dramaGet, dramaCreate, dramaGenerate, dramaConfirm, dramaReset,
  dramaJudge, dramaJudgeApply,
  dramaGridPlan, dramaGridRender, dramaGridCellUrl,
  dramaFilmPlan, dramaFilmRender, dramaFilmUrl, dramaFilmConcat, dramaFilmQuality,
  dramaFilmQc, dramaSubtitleUrl, dramaCoverRun, dramaCoverUrl,
  dramaComposeOptions, dramaComposePlan, dramaComposeRun, dramaComposeUrl,
  dramaBgmUpload, dramaBgmDelete, dramaBgmUrl,
  dramaContactSheet, dramaContactSheetUrl, dramaPreviewGif, dramaPreviewGifUrl,
  dramaPlatforms, dramaExportPlatform, dramaExportPlatformUrl,
  dramaShopQr, dramaShopQrUrl, dramaCarousel, dramaCarouselUrl,
  dramaNativeFeel, dramaNativeFeelUrl, dramaMastering, dramaMasteringUrl,
  dramaPublishPack, dramaPublishLlm,
  dramaHealth, dramaTasks, dramaReadiness, dramaGate,
  dramaRepairPlan, dramaRepairRender, dramaRepairRevert,
  dramaOptions, dramaStageUpload, dramaUploadImage, dramaDeleteImage, dramaImageUrl,
  dramaPatchProduct, dramaImportUrl, dramaStagedUrl,
  dramaExportUrl, dramaDeleteProject, dramaSaveBible,
  dramaUploadCast, dramaDeleteCast, dramaCastSheet,
  dramaTemplates, dramaTemplatesRecommend, dramaTemplatesMine, dramaTemplatesMineSave,
  dramaTemplatesMineDelete, dramaTemplatesCustom, dramaApplyTemplate, dramaClearTemplate,
  dramaScriptTemplates, dramaScriptTemplateSave, dramaRefTemplate,
  dramaTopicOptions, dramaTopicCreate,
  dramaScripts, dramaSelectScript, dramaDeleteScript, dramaImportScript,
  dramaPreflight, dramaVariantsPlan, dramaVariantsRender, dramaVariantUrl,
  dramaMaterials, dramaMaterialUpload, dramaMaterialPatch, dramaMaterialDelete,
  dramaMaterialUrl, dramaCredits, dramaBgmCredit,
  dramaShotMaterials, dramaShotMaterialsSave, dramaShotMaterialsAuto,
  dramaShotClips, dramaShotClipsSave,
  dramaStockSources, dramaStockSearch, dramaStockImport, dramaStockAutoFill,
  dramaMediaImport, dramaMediaImportUni, dramaMediaList, dramaMediaDelete, dramaMediaUrl,
  dramaMediaTranscript, dramaMediaTranscriptStart, dramaMediaTranscriptCancel,
  dramaMediaClips, dramaMediaClipCut, dramaMediaClipUrl, dramaMediaTimeline,
  dramaTtsFreeVoices, dramaTtsFreePreview,
  dramaVoiceGet, dramaVoiceBuild, dramaVoiceDelete,
  dramaDubLangs, dramaDubStart, dramaDubs, dramaDubApply, dramaDubRestore,
  dramaProducts, dramaProductSave, dramaProductApply, dramaProductDelete,
  dramaStylePacks, dramaStylePackExport, dramaStylePackImport, dramaHomogeneity,
  dramaSettings, dramaSettingsSave, dramaSettingsReset, dramaSettingsImport, dramaTrends,
  dramaWorks, dramaMetrics, dramaMetricSave, dramaStyleInsights,
  dramaProbeProviders, dramaProbeRun, dramaTaskResume,
  dramaBatchGet, dramaBatchCreate, dramaBatchPatch, dramaBatchPlan,
  dramaMediaAnalyze, dramaProductionSave,
} from '@/api/request'
import { API_BASE } from '@/config'
import { guessFileKind } from '@/utils/file-kind'

// 视觉记忆六锚（顺序 = 界面展示顺序；只有前 3 项参与「必须出现」判定）
const BIBLE_FIELDS = [
  { key: 'character_anchors', label: '人物', hint: '发型 / 服装色 / 年龄 / 随身细节，逗号分隔' },
  { key: 'product_anchors', label: '商品', hint: '商品名或包装特征' },
  { key: 'wardrobe_anchors', label: '服装', hint: '留空 = 不检查' },
  { key: 'environment_anchors', label: '环境', hint: '地点' },
  { key: 'lighting_anchors', label: '光线', hint: '光线方向' },
  { key: 'forbidden_changes', label: '禁改', hint: '出现就拦，如：换发型、改包装颜色' },
]
/** G1：批量执行器的并发条数（竞品 `batch/page.tsx:419` 的 CONCURRENCY） */
const BATCH_CONCURRENCY = 3
const BATCH_STATUS_TEXT = {
  pending: '排队中', generating: '生成中', composing: '合成中',
  done: '分镜就绪', failed: '失败',
}

const EMPTY_BIBLE_DRAFT = {
  character_anchors: '', product_anchors: '', wardrobe_anchors: '',
  environment_anchors: '', lighting_anchors: '', forbidden_changes: '',
}

const COLORS = ['#12b886', '#4f7cff', '#f59e0b', '#8b5cf6']
/** 列表筛选：新建 = 还没开始跑；进行中 = 跑到一半；已完成 = 至少出过一段成片 */
const FILTERS = [
  { key: 'all', label: '全部' },
  { key: 'new', label: '新建' },
  { key: 'doing', label: '进行中' },
  { key: 'done', label: '已完成' },
]

// G4/G5 效果回流：平台 / 钩子 / 五个数字字段（竞品 `performance-feedback.tsx:31-52`）
const FB_PLATFORMS = [
  { id: 'douyin', label: '抖音' },
  { id: 'tiktok', label: 'TikTok' },
  { id: 'kuaishou', label: '快手' },
  { id: 'xiaohongshu', label: '小红书' },
]
// 我们的结构卡只有 H1–H5 五个编号（`references/output_card.md`），没有竞品那套机制名
const FB_HOOKS = ['H1', 'H2', 'H3', 'H4', 'H5']
const FB_NUMS = [
  { key: 'views', label: '播放' },
  { key: 'likes', label: '点赞' },
  { key: 'comments', label: '评论' },
  { key: 'shares', label: '转发' },
  { key: 'orders', label: '成交' },
]
const EMPTY_METRIC = {
  platform: 'douyin', hookId: '',
  views: '', likes: '', comments: '', shares: '', orders: '', note: '',
}

// D1 试听用的 <audio>（不进响应式 data，避免 Vue 代理媒体元素）
let ttsAudioEl = null
// 小程序端用 InnerAudioContext 播 mp3 字节（没有 Audio / Blob）
let ttsAudioMp = null

export default {
  data() {
    return {
      list: [],
      cur: null,
      creating: false,
      busy: '',
      // 建完自动写稿时当前走到哪一步（结构卡 / 写剧本 / 出分镜），空 = 没在写
      bootStep: '',
      // 合成（D 批）：本地 ffmpeg，零生成费。这些值只是**界面草稿**；
      // 规划后以后端 `plan.config` 为准（plan_hash 锁的就是那一版）。
      comp: {
        transition: 'direct_concat', render_preset: 'standard',
        captions: true, caption_preset: 'standard',
        bgm_volume: 0.18, bgm_duck: true, bgm_fade_out: 3, bgm_intro_skip: 0,
        end_card: false, end_card_text: '', end_card_seconds: 3,
        end_card_image: '', end_card_qr_ratio: 0.34,
        // D3 人声落地：默认开（有配音轨时走过去播音腔链 + 房间底噪）
        voice_ground: true,
      },
      compOpt: { transitions: [], renders: [], captions: [], defaults: {} },
      compProxy: false, // 速览时是否同时出审片小样（短边 720 + 时间码）
      // 发行物料（E 批）：全部本地 ffmpeg，零生成费；发布文案模板版也零费用
      mat: {
        platform: 'douyin', framing: 'blur', preview: '',
        qrUrl: '', qrBurn: false,
        theme: 'night',
        strength: 'subtle', grain: true, vignette: false, halation: false, phoneCompress: false,
        normalize: true, deflicker: false,
      },
      matOpt: { platforms: [], framing_modes: [], native_strengths: [], card_themes: [] },
      form: {
        url: '', name: '', points: '', facts: '', audience: '',
        category: '', price: '', platform: '',
        images: [], // [{ name, url }] —— name 是服务端文件名，url 用来预览
      },
      //: 🩸 2026-11-09：上一次成功「点解析」的链接。用来判断顾客是换了链接（还是同一条重试）——
      //: 换了链接却什么都没抓到，就必须把上一个商品的资料清掉，否则会照着旧商品写稿。
      lastImportUrl: '',
      // form 留空 = 让模型自己挑形态（不再默认情景短剧，否则每条片一个骨架）
      // line = 做片路线：'A' 竞品线（照商品直接写稿，不经过故事世界）/ 'B' 创意故事线（先挑世界）。
      // 2026-11-08 主人定：两条线分开，A 线一个字不动；老项目没有这个键 = A 线。
      answers: { line: 'A', form: '', form_note: '', duration: 30, role: '转折道具', mode: '' },
      castSkip: false,   // 这一页里已经确认「没定妆也要出板」，不再重复拦
      // 选项由后端 `/api/drama/options` 给，前端不写死；没拿到前给个空壳防报错
      opt: {
        categories: [], prices: [], audiences: [], platforms: [], modes: [],
        forms: ['情景短剧'], durations: [15, 30, 60],
        roles: ['转折道具', '欲望对象', '身份符号'], max_pics: 5,
      },
      editing: false, // 老项目改商品资料
      filter: 'all',
      // 出片型号：2.5 和 2.0 的单次时长 / 参考图上限 / 提示词口径都不是一套
      filmModel: '',
      // 清晰度 / 画面比例（1:1 竞品 video 页两个选择器）
      // 🩸 resRows 是**当前型号**吃得下的档，切型号要重算；必须是 data 顶层数组，
      //    模板绑 `opt.film_models[i].resolutions` 这种对象路径在 mp 端会整页停更。
      filmResolution: '720p',
      filmRatio: '9:16',
      resRows: [],
      ratioRows: [
        { id: '9:16', label: '竖屏 9:16' },
        { id: '16:9', label: '横屏 16:9' },
        { id: '1:1', label: '方形 1:1' },
      ],
      // 窗口精准修复：一次只开一段（no=0 表示没在修）
      repair: { no: 0, start: '', end: '', note: '', plan: null },
      // 视觉记忆六锚：输入框里是逗号分隔文本，保存时拆成数组
      bibleOpen: false,
      bibleFields: BIBLE_FIELDS,
      bibleDraft: { ...EMPTY_BIBLE_DRAFT },
      // 在飞任务：已付钱、还没收尾的出片登记
      activeTasks: [],
      // 成片模板（配方库）。draft = 新建时选中但还没落盘的；curTpl = 项目上已落盘的
      tpl: {
        open: false, tab: 'lib',
        groups: [], list: [], mine: [],
        group: 'all', q: '', show: 60,
        total: 0, busy: false,
        rec: [], draft: null, draftMineId: '',
        custom: null, customBusy: false,
        importText: '', importBusy: false, warnings: [],
      },
      // 剧本结构模板（自己跑通的分镜节奏）；draftId = 新建时选中的那条
      scriptTpl: { list: [], draftId: '' },
      // ---- 第六批：生成链增强 ----
      catTpl: '',                 // A5 品类脚本模板（新建时选，跟着品类过滤）
      scripts: [],                // A7 多版脚本（后端给的版本列表）
      scriptStale: false,         // 切了版本、但分镜还是按上一版写的
      // D1（2026-11-08）：重出结构卡后，剧本/分镜还是旧卡写的 → 必须让顾客看见
      scriptCardStale: false,
      storyboardCardStale: false,
      // D2：定妆图对应的剧本版本已变，或角色已不在剧本里
      castStale: [],
      applyLog: [],                // 本次「应用判官意见」改了哪几处（镜/格/前→后）
      castStaleText: '',          // 上面那堆的名字，模板里不能用箭头函数，先拼好
      importOpen: false,          // A8 手写稿输入区
      importText: '', importTitle: '',
      preflight: null,            // C16 能力预检结果
      chain: 'off',               // C9 接缝档：off / tail
      realism: 'auto',            // C12 真实感档：auto / constraints / off
      variant: { open: false, count: 3, seed: 1, plan: null, rows: [], busy: '' },
      topic: {
        open: false, topic: '', style: 'knowledge', duration: 30, count: 3,
        opt: { styles: [], durations: [], min_count: 1, max_count: 5 },
        busy: false,
      },
      // ---- 第七批：素材库 / 授权清单 ----
      pool: [],                    // 项目素材池
      poolBusy: '',                // 'upload' / 'save' / 'del'
      poolEdit: { open: false, row: null, name: '', tags: '', author: '', license: '', sourceUrl: '' },
      credits: null,               // 授权清单（json）
      // ---------- B4 每镜参考画面 ----------
      shotMats: [],                // [{shot_id, material, original_name}]
      shotImages: [],              // 素材库里可当参考画面的图片
      matPick: { open: false, seg: 0, shotId: 0, material: '', shots: [] },
      // ---------- B6/B8 素材当画面（视频）----------
      clipItems: [],               // [{shot_id, material, original_name, seconds, dialogue}]
      clipVideos: [],              // 素材库里可当画面的视频
      clipPick: { open: false, shotId: 0, material: '' },
      // ---------- B3 免版权素材搜索 ----------
      stockQ: '',                  // 检索词
      stockType: 'video',          // video / image / audio
      stockSource: 'all',          // all / 具体源 id
      stockSources: [],            // 源清单（含 keyless / available）
      stockResults: [],            // 候选
      stockBusy: '',               // 'search' / 'import'
      stockMsg: '',                // 跳过/出错的源提示
      stockImported: '',           // 刚导进来的那条 id（按钮回显）
      mediaRows: [],               // B6 长视频原料（和素材库分开）
      mediaBusy: false,            // 长视频上传中
      mediaPct: 0,                 // 上传进度 0-100
      trOpen: {},                  // 哪条长视频展开了转写文字
      trText: {},                  // 已拿到的转写全文（按素材 id）
      trPoll: null,                // 转写轮询定时器
      clipOpen: {},                // 哪条长视频展开了「按文字剪」
      clipQ: {},                   // 每行的关键词
      clipTarget: {},              // 每行的目标时长（秒）
      clipBusy: {},                // 每行正在算/正在剪
      clipRes: {},                 // 每行的候选片段
      clipOut: {},                 // 已剪出来的片段：{ [mid]: { [clipId]: {...} } }
      tlBusy: {},                  // 哪条视频正在导出时间线
      ttsOpen: false,              // 「配音试听」卡是否展开
      ttsVoices: [],               // 免费音色表
      ttsVoiceIndex: 0,            // 当前选中音色
      ttsText: '',                 // 试听台词
      ttsBusy: false,              // 正在合成
      ttsHint: '',                 // 试听状态提示
      voiceLines: 0,               // 分镜里有台词的镜头数（整片配音要配几句）
      voiceNote: '',               // 整片配音轨状态
      voiceBuilding: false,        // 正在整片配音
      dubOpen: false,              // 「多语言译制」卡是否展开
      dubLangs: [],                // 支持的语言表
      dubLangIndex: 0,             // 当前选中语言
      dubBusy: false,              // 正在译制
      dubNote: '',                 // 译制状态提示
      dubs: [],                    // 已译版本
      dubCanRestore: false,        // 有没有可还原的原分镜
      plOpen: false,               // 「商品库」卡是否展开
      plBusy: false,               // 正在存/应用商品卡
      plItems: [],                 // 商品库列表
      plNote: '',                  // 商品库状态提示
      spOpen: false,               // 「风格配方」卡是否展开
      spBusy: false,               // 正在导入/导出配方
      spBuiltin: [],               // 内置配方
      spText: '',                  // 待导入的配方文本
      spNote: '',                  // 配方状态提示
      spDropped: [],               // 这份配方里这边用不了的字段
      hgOpen: false,               // 「结构自检」卡是否展开
      hgBusy: false,               // 正在比对
      hg: null,                    // 自检结果
      stOpen: false,               // 「设置中心」卡是否展开
      stBusy: false,               // 正在存设置
      stNote: '',                  // 设置状态提示
      st: {},                      // 全局默认值
      stKeys: [],                  // 密钥状态（只有掩码）
      stOpts: { caption_preset: [], render_preset: [], transition: [], tts_voice: [],
                film_resolution: [], film_ratio: [], film_chain: [], film_realism: [] },
      stImportOpen: false,         // H4 旧版导入是否展开
      stImportText: '',            // 贴进来的旧设置 JSON
      stImportBusy: false,
      stImportNote: '',
      stImportFixed: [],           // 本次跑过的修复
      stImportDropped: [],         // 没搬的项（逐条说明）
      trOpen: false,               // 「趋势话题」卡是否展开
      trBusy: false,               // 正在拉榜单
      trTopics: [],                // 话题列表
      trCats: [],                  // 类目表
      trPick: null,                // 今日一条
      trCat: 'all',                // 当前类目筛选
      trNote: '',                  // 状态提示
      wkOpen: false,               // 「作品流」卡是否展开
      wkBusy: false,               // 正在读成片墙
      wkItems: [],                 // 跨项目成片
      wkNote: '',                  // 成片墙状态提示
      wkPlay: '',                  // 正在内联播放的片子（绝对地址）
      fbOpen: false,               // 「效果回流」卡是否展开
      fbBusy: false,               // 正在保存
      fbNote: '',                  // 回流状态提示
      fbRows: [],                  // 这个项目录过的发布数据（新的在前）
      fbStyles: [],                // 全站风格成效
      fbHooks: [],                 // 全站钩子成效
      fbForm: { ...EMPTY_METRIC },
      FB_PLATFORMS,
      FB_HOOKS,
      FB_NUMS,
      tkHint: '',                  // 在飞任务固定提示（别重复提交）
      tkBusy: false,               // 正在刷新任务列表
      tkBusyNo: '',                // 正在领回哪一条（pid:no）
      tkMsg: {},                   // 每条领回的结果（pid:no → 人话）
      prRows: [],                  // C4 可探测通道登记
      prBusy: '',                  // 正在测哪个通道（'all' = 全部）
      prResults: {},               // 每个通道最近一次探测结果
      mlOpen: false,               // 「媒体解构」卡是否展开
      mlBusy: false,               // 正在解构
      mlFile: null,                // {path,size,kind}
      mlNote: '',                  // 解构状态提示
      mlResult: null,              // 解构结果
      mlProjectId: '',             // 要存进哪个项目
      mlSaving: false,             // 正在存
      btOpen: false,               // 「批量作业」卡是否展开
      btBusy: false,               // 正在建作业
      btRunning: false,            // 执行器正在跑
      btAbort: false,              // 停止标记
      btProducts: [],              // 商品库
      btPicked: [],                // 勾选的商品 id
      btDuration: 30,              // 片长（15/30/60）
      btAnti: true,                // 反同质化轮换
      btJob: null,                 // 当前/最近一次作业
      btItems: [],                 // 作业条目
      btPlan: [],                  // 轮换计划
      btResumable: false,          // 有没跑完的作业
      btNote: '',                  // 状态提示
      stockFillBusy: false,        // 自动配画面进行中
      stockFillMsg: '',            // 自动配画面结果（配了几镜 / 哪几镜没配上）
      FILTERS,
    }
  },
  computed: {
    ttsVoiceLabels() {
      return this.ttsVoices.map((v) => v.label)
    },
    /** D3：项目里已经生成几句配音（以轨道文件条目为准，不靠界面状态猜） */
    voiceTrackCount() {
      return (((this.cur || {}).voice_track || {}).items || []).length
    },
    dubLabels() {
      return this.dubLangs.map((v) => v.name)
    },
    // 作品流里的缩略图/视频是后端相对路径，播放要拼上 API 主机
    apiBase() {
      return API_BASE
    },
    mlProjectNames() {
      return (this.list || []).map((p) => p.name || p.id)
    },
    btDoneCount() {
      return (this.btItems || []).filter((i) => i.status === 'done').length
    },
    // 趋势话题：按类目筛（未分类的只在「全部」里出现）
    trShown() {
      const list = this.trTopics || []
      return this.trCat === 'all' ? list : list.filter((t) => t.category === this.trCat)
    },
    // 结构自检：配对按分数倒序，界面只列最像的 5 对
    hgPairs() {
      const list = (this.hg && this.hg.similar_pairs) || []
      return list.slice(0, 5)
    },
    // 分镜里所有镜头（「素材当画面」按镜绑定，素材镜不进 AI 组）
    storyShots() {
      const shots = ((this.cur && this.cur.storyboard_json) || {}).shots || []
      return shots.map((s, i) => ({
        id: Number(s.id || i + 1),
        desc: String(s.description || '').slice(0, 16),
        dialogue: String(s.dialogue || '').trim(),
        duration: Number(s.duration || 0),
      }))
    },
    // 当前媒体类型下能选的源（Openverse 没有视频，选视频时不列）
    stockSrcs() {
      const t = this.stockType
      return (this.stockSources || []).filter((s) => {
        if (t === 'audio') return (s.media_types || []).includes('audio')
        return (s.media_types || []).includes(t)
      })
    },
    stockTypeLabel() {
      return { video: '视频', image: '图片', audio: '音乐' }[this.stockType] || '素材'
    },
    shown() {
      const l = this.list || []
      if (this.filter === 'done') return l.filter((p) => p.done)
      if (this.filter === 'new') return l.filter((p) => !p.done && p.stage === '新建')
      if (this.filter === 'doing') return l.filter((p) => !p.done && p.stage !== '新建')
      return l
    },
    steps() {
      const c = this.cur || {}
      if (c.content_type === 'topic') {
        // 话题片只有三步：脚本 → 分镜 → 出片（结构卡/判官/九宫格都是带货的环节）
        const t = [
          { key: 'script', label: '脚本', done: !!c.script },
          { key: 'storyboard', label: '分镜', done: !!c.storyboard_json },
          { key: 'film', label: '出片', done: !!(c.film && c.film.files && Object.keys(c.film.files).length) },
        ]
        const i = t.findIndex((s) => !s.done)
        return t.map((s, k) => ({ ...s, state: s.done ? 'done' : k === i ? 'cur' : 'todo' }))
      }
      const raw = [
        { key: 'card', label: '结构卡', done: !!c.card && !!c.card_confirmed },
        { key: 'script', label: '剧本', done: !!c.script_json },
        { key: 'storyboard', label: '分镜', done: !!c.storyboard_json },
        { key: 'judge', label: '判官', done: !!c.judge },
        { key: 'grid', label: '关键帧', done: !!c.grid },
        { key: 'check', label: '自检', done: !!c.check },
        { key: 'film', label: '出片', done: !!(c.film && c.film.files && Object.keys(c.film.files).length) },
      ]
      const i = raw.findIndex((s) => !s.done)
      return raw.map((s, k) => ({ ...s, state: s.done ? 'done' : k === i ? 'cur' : 'todo' }))
    },
    totalSeconds() {
      const shots = (this.cur && this.cur.storyboard_json && this.cur.storyboard_json.shots) || []
      const t = shots.reduce((n, s) => n + (Number(s.duration) || 0), 0)
      return Math.round(t * 10) / 10
    },
    /** 有没有任何一段出好了 —— 有才谈得上出封面/导出 */
    anyFilm() {
      const f = (this.cur && this.cur.film && this.cur.film.files) || {}
      return Object.keys(f).length > 0
    },
    coverUrl() {
      return this.cur ? dramaCoverUrl(this.cur.id) : ''
    },
    taskNames() {
      const names = (this.activeTasks || []).map((t) => t.product || t.pid)
      return names.slice(0, 3).join('、') + (names.length > 3 ? ' 等' : '')
    },
    /** 有没有台词 —— 一个字都没有就没有字幕可导，别摆个点了没反应的按钮 */
    hasDialogue() {
      const shots = (this.cur && this.cur.storyboard_json && this.cur.storyboard_json.shots) || []
      return shots.some((s) => String(s.dialogue || '').trim())
    },
    productShots() {
      const shots = (this.cur && this.cur.storyboard_json && this.cur.storyboard_json.shots) || []
      return shots.filter((s) => s.product).length
    },
    hasCells() {
      const g = (this.cur && this.cur.grid) || {}
      return (g.cell_files || []).length === 9
    },
    /** 已经定妆的角色数（有参考图 = 定了，上传/生成都算） */
    castDone() {
      return (this.castList || []).filter((c) => !!c.image).length
    },
    /** 分镜板：≤30 秒一块；60 秒按出片段每段一块（后端 `grid.boards`）。
     *  老项目只有顶层那一块 → 当成单板，行为和以前一样。 */
    gridBoards() {
      const g = (this.cur && this.cur.grid) || {}
      const bs = g.boards
      if (Array.isArray(bs) && bs.length) return bs
      return g && g.cells ? [g] : []
    },
    plan() {
      return (this.cur && this.cur.film && this.cur.film.plan) || null
    },
    /** 合成规划（后端算的：时间轴 / 字幕条 / 切点 / 警告） */
    compPlan() {
      return (this.cur && this.cur.compose && this.cur.compose.plan) || null
    },
    compOut() {
      return (this.cur && this.cur.compose && this.cur.compose.outputs) || {}
    },
    compBgm() {
      return (this.cur && this.cur.compose && this.cur.compose.bgm) || null
    },
    compReady() {
      return !!(this.plan && (this.plan.segments || []).length && this.allRendered)
    },
    compUrl() {
      return this.cur && this.compOut.mp4 ? dramaComposeUrl(this.cur.id) : ''
    },
    compSheetUrl() {
      return this.cur && this.compOut.sheet ? dramaContactSheetUrl(this.cur.id) : ''
    },
    compGifUrl() {
      return this.cur && this.compOut.gif ? dramaPreviewGifUrl(this.cur.id) : ''
    },
    /** ---- 发行物料（E 批）---- */
    matMats() {
      return (this.cur && this.cur.materials) || {}
    },
    matExportRec() {
      return this.matMats.export || null
    },
    matQrRec() {
      return this.matMats.qr || null
    },
    matCardsRec() {
      return this.matMats.cards || null
    },
    matNativeRec() {
      return this.matMats.native || null
    },
    matMasterRec() {
      return this.matMats.master || null
    },
    matPack() {
      return (this.cur && this.cur.publish && this.cur.publish.pack) || null
    },
    matExportUrl() {
      return this.matExportRec && this.cur ? dramaExportPlatformUrl(this.cur.id) : ''
    },
    matQrUrl() {
      return this.matQrRec && this.cur ? dramaShopQrUrl(this.cur.id) : ''
    },
    matNativeUrl() {
      return this.matNativeRec && this.cur ? dramaNativeFeelUrl(this.cur.id) : ''
    },
    matMasterUrl() {
      return this.matMasterRec && this.cur ? dramaMasteringUrl(this.cur.id) : ''
    },
    matCardUrls() {
      if (!this.cur || !this.matCardsRec) return []
      return (this.matCardsRec.files || []).map((_, i) => dramaCarouselUrl(this.cur.id, i))
    },
    /** 确认卡上的花费。没配单价就直说未知 —— 绝不把「不知道」显示成「免费」 */
    priceText() {
      const p = (this.plan && this.plan.price) || {}
      if (!p.known || p.amount === null || p.amount === undefined) {
        return p.note || '单价未配置，花费未知'
      }
      return `约 ¥${p.amount}（${p.rate}/秒 × ${p.seconds} 秒）`
    },
    /** 修复预演的花费（按模型实际生成时长算，不是按替换区间） */
    repairPriceText() {
      const p = (this.repair.plan && this.repair.plan.price) || {}
      if (!p.known || p.amount === null || p.amount === undefined) {
        return p.note || '单价未配置，花费未知'
      }
      return `约 ¥${p.amount}（${p.rate}/秒 × ${p.seconds} 秒）`
    },
    /** 九宫格自己那份检查结果（出图前显示；后端出图时还会再拦一次） */
    gridBibleIssues() {
      // 多块板时逐块汇总（bible_issues 是后端按板各算一份）
      const out = []
      for (const b of (this.gridBoards || [])) {
        for (const i of (b.bible_issues || [])) out.push(i)
      }
      return out
    },
    gridBibleFails() {
      return this.gridBibleIssues.filter((i) => i.severity === 'fail')
    },
    /** F7 逐格提示：描述里写了先后顺序，静帧画不出来（只提示，不拦出图） */
    gridCellLints() {
      const out = []
      for (const b of (this.gridBoards || [])) {
        for (const w of (b.cell_lints || [])) out.push(w)
      }
      return out
    },
    /** 一致性检查结果：缺锚 warn、禁改 fail（后端出片时会再查一遍，这里是提前显示） */
    bibleIssues() {
      return (this.plan && this.plan.bible_issues) || []
    },
    bibleFails() {
      return this.bibleIssues.filter((i) => i.severity === 'fail')
    },
    repairBibleFails() {
      return ((this.repair.plan && this.repair.plan.bible_issues) || [])
        .filter((i) => i.severity === 'fail')
    },
    /** 视频模式一句话解释 —— 它现在**真的会改分镜写法**，不只是标签 */
    modeHint() {
      const m = {
        产品特写: '全程不出现人物，只拍商品本身：材质、细节、效果。商品出镜 100%。',
        图文混剪: '商品为主、节奏最紧、不出真人。⚠️ 文字卡片不在本管线生成，要后期自己叠。',
        场景演示: '在真实生活场景里演示：只出手部、背影、侧影，不露可辨认的正脸。',
        真人出镜: '真人出镜、允许正脸，靠表情和语气演戏，外观锚要写全。',
      }
      return m[this.answers.mode] || '不选也行：分镜按剧本自然写，不做额外限制。'
    },
    /** 人物参考图：剧本里有几个人就列几行，谁传了图谁就有图 */
    castList() {
      const c = this.cur || {}
      const chars = (c.script_json && c.script_json.characters) || []
      const have = {}
      ;(c.cast || []).forEach((x) => {
        const n = String((x && x.name) || '').trim()
        if (n && x.image) have[n] = { image: String(x.image), source: x.source || 'upload' }
      })
      const names = chars.map((x) => String((x && x.name) || '').trim()).filter(Boolean)
      const out = names.map((n) => ({
        name: n,
        image: (have[n] && have[n].image) || '',
        source: (have[n] && have[n].source) || '',
      }))
      // 剧本文档后来改过名字、但图还在的，也列出来（不然传了图却看不见）
      Object.keys(have).forEach((n) => {
        if (names.indexOf(n) < 0) out.push({ name: n, image: have[n].image, source: have[n].source })
      })
      return out
    },
    /** 这一种模式里会不会出现人（不出人就不给主播库，免得模型硬塞一个） */
    peopleMode() {
      return this.answers.mode !== '产品特写' && this.answers.mode !== '图文混剪'
    },
    presenterHint() {
      const p = (this.opt.presenters || []).find((x) => x.name === this.answers.presenter)
      if (!p) return '模型会从素人原型里挑一个，或照同样的「普通素人」标准自己写'
      return `${p.persona}｜适合${p.good_for}｜重新生成剧本才生效`
    },
    /** 商品角色一句话解释 */
    roleHint() {
      const r = {
        转折道具: '商品是翻盘的那一下——前面输得越惨，它登场时越有戏。推荐默认。',
        欲望对象: '别人想要它、抢它、羡慕它——冲突围绕"谁配得上"展开。',
        身份符号: '用它说明"我是什么样的人"——适合有面子属性、能被看见的东西。',
      }
      return r[this.answers.role] || ''
    },
    merged() {
      return (this.cur && this.cur.film && this.cur.film.merged) || ''
    },
    /** 每段都出完了才能拼 */
    allRendered() {
      const segs = (this.plan && this.plan.segments) || []
      const files = (this.cur && this.cur.film && this.cur.film.files) || {}
      return segs.length > 0 && segs.every((s) => files[s.no] && files[s.no].name)
    },
    applicableCount() {
      const vs = (this.cur && this.cur.judge && this.cur.judge.verdicts) || []
      return vs.reduce((n, v) => n + (v.issues || []).filter((i) => i.new_text).length, 0)
    },
    /** 判官一共给了几条意见 —— 一条都不能应用时，用来解释「为什么没有按钮」 */
    judgeIssueCount() {
      const vs = (this.cur && this.cur.judge && this.cur.judge.verdicts) || []
      return vs.reduce((n, v) => n + (v.issues || []).length, 0)
    },
    /** 列表一次给全 391 款，界面分批画 —— 全渲染会卡 */
    tplShown() {
      return (this.tpl.list || []).slice(0, this.tpl.show)
    },
    tplTotal() {
      return this.tpl.total || 391
    },
    /** 项目现在的模板（选了才显示换/清） */
    curTpl() {
      return ((this.cur && this.cur.template) || {}).template || null
    },
    // ---- 第六批 ----
    isTopic() {
      return !!(this.cur && this.cur.content_type === 'topic')
    },
    /** A5：当前品类下可挑的脚本模板名（后端 options 给的是「类目 → 模板名」表） */
    catTplOptions() {
      const cat = this.form.category
      const row = (this.opt.script_templates || []).find((x) => x.name === cat)
      return row ? row.templates || [] : []
    },
    /** C15：上次合成出来的变体（每条带文件与摘要） */
    variantRows() {
      const v = (this.cur && this.cur.variants) || {}
      return v.slots || []
    },
    /** B5：清单里要附的署名行（可直接粘进发布文案） */
    creditAttributions() {
      const m = this.credits || {}
      return [...(m.items || []), ...(m.bgm ? [m.bgm] : [])].filter((x) => x.attributionLine)
    },
    /** C9：接缝档（后端规划时读它；改了就得重新规划，指纹会变） */
    chainLabel() {
      return this.chain === 'tail' ? '续拍' : '关'
    },
    topicStyleHint() {
      const s = (this.topic.opt.styles || []).find((x) => x.id === this.topic.style)
      return s ? s.directive : ''
    },
    topicShots() {
      return ((this.cur && this.cur.storyboard_json) || {}).shots || []
    },
    topicStyleName() {
      const id = (this.cur && this.cur.narration_style) || ''
      const s = (this.topic.opt.styles || []).find((x) => x.id === id)
      return s ? s.name : (id || '—')
    },
    confidenceName() {
      const c = ((this.preflight || {}).capabilities || {}).confidence
      return c === 'known' ? '规格已确认' : c === 'inferred' ? '按型号族推定' : '未知型号'
    },
  },
  methods: {
    /**
     * 建完项目后要不要先去挑「故事世界」（2026-11-08 A/B 两条线分开）。
     * A 线（快速出片）= false，直接写稿；B 线（创意故事）= true；已经挑过世界的也不再问。
     * 🩸 抽成方法而不是各页内联判断 —— 探针能直接调它验分支，不用真建项目/真调模型。
     */
    needWorld() {
      return this.answers.line === 'B' && !this.answers.world
    },
    /** 拉「还有钱卡着吗」—— 读数失败不挡主流程 */
    async loadTasks() {
      this.tkBusy = true
      try {
        const r = await dramaTasks(1)
        this.activeTasks = (r && r.tasks) || []
        this.tkHint = (r && r.hint) || ''
      } catch (e) {
        this.activeTasks = []
      } finally {
        this.tkBusy = false
      }
    },
    /** C17：领回已提交的任务（只查+下载，不重新提交） */
    async resumeTask(t) {
      const key = `${t.pid}:${t.no}`
      if (this.tkBusyNo) return
      this.tkBusyNo = key
      try {
        const r = await dramaTaskResume(t.pid, t.no)
        this.tkMsg = { ...this.tkMsg, [key]: r.message || r.status || '已处理' }
        if (r.status === 'succeeded') {
          if (this.cur && this.cur.id === t.pid && r.doc) this.cur = r.doc
          await this.loadTasks()
        }
      } catch (e) {
        this.tkMsg = { ...this.tkMsg, [key]: e.message || '领取失败' }
      } finally {
        this.tkBusyNo = ''
      }
    },
    // ---------- 成片模板（竞品 391 条配方） ----------
    /** 启动时只拉一次库元信息（分组 + 总数 + 全量列表），以后按条件重拉 */
    async loadTemplatesMeta() {
      if (this.tpl.groups.length && this.tpl.list.length) return
      try {
        const r = await dramaTemplates({ group: 'all', q: '' })
        this.tpl.groups = r.groups || []
        this.tpl.list = r.templates || []
        this.tpl.total = r.total || 0
      } catch (e) {
        // 库拿不到不挡主流程：模板是可选增强，不是必填项
        console.warn('[drama] 读取模板库失败', e.message)
      }
    },
    async loadMine() {
      try {
        this.tpl.mine = (await dramaTemplatesMine()) || []
      } catch (e) {
        this.tpl.mine = []
      }
    },
    /** 按商品给推荐（空输入后端返回空数组，界面就不显示这一行） */
    async refreshRec() {
      try {
        this.tpl.rec = (await dramaTemplatesRecommend({
          category: (this.creating ? this.form.category : (this.cur && this.cur.product && this.cur.product.category)) || '',
          name: (this.creating ? this.form.name : ((this.cur && this.cur.product && this.cur.product.name) || '')).trim(),
          points: this.creating
            ? this.form.points.split('\n').map((s) => s.trim()).filter(Boolean).join(' ')
            : (((this.cur || {}).product || {}).points || []).join(' '),
          limit: 4,
        })) || []
      } catch (e) {
        this.tpl.rec = []
      }
    },
    async loadTemplateList() {
      try {
        this.tpl.busy = true
        const r = await dramaTemplates({
          group: this.tpl.group,
          category: (this.creating ? this.form.category : ((this.cur || {}).product || {}).category) || '',
          q: this.tpl.q,
        })
        this.tpl.list = r.templates || []
        this.tpl.groups = r.groups || this.tpl.groups
        this.tpl.total = r.total || this.tpl.total
        this.tpl.show = 60
      } catch (e) {
        uni.showToast({ title: e.message || '读取模板失败', icon: 'none' })
      } finally {
        this.tpl.busy = false
      }
    },
    openTpl(tab) {
      this.tpl.open = true
      this.tpl.tab = tab || 'lib'
      this.tpl.warnings = []
      this.loadMine()
      if (!this.tpl.list.length) this.loadTemplateList()
      this.refreshRec()
    },
    switchTab(t) {
      this.tpl.tab = t
      if (t === 'mine') this.loadMine()
    },
    pickGroup(g) {
      this.tpl.group = g
      this.loadTemplateList()
    },
    /** 两个模板是不是同一个（内置比 id，自建比库里 id） */
    isSameTpl(a, b) {
      return !!(a && b && (a.id === b.id) && (a.name || {}).zh === (b.name || {}).zh)
    },
    groupName(gid) {
      const g = (this.tpl.groups || []).find((x) => x.id === gid)
      return g ? g.name : ''
    },
    srcName(s) {
      return { ai: 'AI 定制', import: '导入', edit: '改过' }[s] || ''
    },
    /** 选中一款：新建中的项目先拿在手里，等创建成功再落盘 */
    async pickTpl(t, mineId) {
      if (this.creating || !this.cur) {
        this.tpl.draft = t
        this.tpl.draftMineId = mineId || ''
        this.tpl.open = false
        return
      }
      await this.applyTplToCur(t, mineId)
    },
    async applyTplToCur(t, mineId) {
      if (!this.cur || this.busy) return
      this.busy = 'tpl'
      try {
        const r = await dramaApplyTemplate(this.cur.id,
          mineId ? { mine_id: mineId } : { template: t })
        this.cur.template = { template: (r && r.template) || t }
        this.tpl.open = false
        uni.showToast({ title: '已套用模板', icon: 'none' })
      } catch (e) {
        uni.showModal({ title: '套用失败', content: e.message, showCancel: false })
      } finally {
        this.busy = ''
      }
    },
    async clearCurTpl() {
      if (!this.cur || this.busy) return
      this.busy = 'tpl'
      try {
        await dramaClearTemplate(this.cur.id)
        this.cur.template = null
      } catch (e) {
        uni.showToast({ title: e.message || '取消失败', icon: 'none' })
      } finally {
        this.busy = ''
      }
    },
    /** AI 定制：花一次模型调用，先把话说清楚 */
    async customTpl() {
      const name = this.form.name.trim()
      if (!name) {
        uni.showToast({ title: '先回表单填商品名称', icon: 'none' })
        return
      }
      if (this.tpl.customBusy) return
      this.tpl.customBusy = true
      try {
        const r = await dramaTemplatesCustom({
          name,
          category: this.form.category || '',
          points: this.form.points.split('\n').map((s) => s.trim()).filter(Boolean).join('；'),
        })
        this.tpl.custom = r.template
      } catch (e) {
        uni.showModal({ title: '定制失败', content: e.message, showCancel: false })
      } finally {
        this.tpl.customBusy = false
      }
    },
    async saveCustom() {
      if (!this.tpl.custom) return
      try {
        const r = await dramaTemplatesMineSave({ template: this.tpl.custom })
        await this.loadMine()
        this.tpl.warnings = (r && r.warnings) || []
        uni.showToast({ title: '已存进我的模板', icon: 'none' })
      } catch (e) {
        uni.showToast({ title: e.message || '保存失败', icon: 'none' })
      }
    },
    async importTpl() {
      const txt = (this.tpl.importText || '').trim()
      if (!txt) {
        uni.showToast({ title: '先把分享内容粘进来', icon: 'none' })
        return
      }
      if (this.tpl.importBusy) return
      this.tpl.importBusy = true
      this.tpl.warnings = []
      try {
        const r = await dramaTemplatesMineSave({ share: txt })
        this.tpl.warnings = (r && r.warnings) || []
        this.tpl.importText = ''
        await this.loadMine()
        this.tpl.tab = 'mine'
        uni.showToast({ title: `导入 ${((r && r.templates) || []).length} 款`, icon: 'none' })
      } catch (e) {
        uni.showModal({ title: '导入失败', content: e.message, showCancel: false })
      } finally {
        this.tpl.importBusy = false
      }
    },
    /** 分享 = 把剥掉 id 的配方复制进剪贴板（配方就该能传来传去） */
    async exportTpl(t) {
      try {
        const r = await dramaTemplatesMine()
        const row = (r || []).find((x) => x.id === t.id) || t
        const body = {
          kind: 'clipforge-ad-template',
          version: 1,
          template: Object.fromEntries(Object.entries(row).filter(([k]) => k !== 'id')),
        }
        uni.setClipboardData({
          data: JSON.stringify(body, null, 2),
          success: () => uni.showToast({ title: '配方已复制', icon: 'none' }),
        })
      } catch (e) {
        uni.showToast({ title: e.message || '分享失败', icon: 'none' })
      }
    },
    // ---------- 剧本结构模板（跑通的分镜节奏，换商品复用） ----------
    async loadScriptTpls() {
      try {
        this.scriptTpl.list = (await dramaScriptTemplates()) || []
      } catch (e) {
        this.scriptTpl.list = []
      }
    },
    async saveAsScriptTpl() {
      const c = this.cur || {}
      const shots = (c.storyboard_json && c.storyboard_json.shots) || []
      if (!shots.length) {
        uni.showToast({ title: '还没分镜', icon: 'none' })
        return
      }
      const name = ((c.product && c.product.name) || '未命名') + ' 结构'
      const yes = await new Promise((res) => {
        uni.showModal({
          title: '存为结构模板？',
          content: `把这 ${shots.length} 镜的节奏存成「${name}」，下次换商品可照这套节奏重写（存的是结构，不是文案）`,
          success: (m) => res(!!m.confirm),
        })
      })
      if (!yes) return
      try {
        const row = await dramaScriptTemplateSave(c.id, name)
        await this.loadScriptTpls()
        uni.showToast({ title: `已存：${row.shots_count} 镜`, icon: 'none' })
      } catch (e) {
        uni.showModal({ title: '没存上', content: e.message, showCancel: false })
      }
    },
    async setRefTemplate(id) {
      if (!this.cur || this.busy) return
      this.busy = 'ref'
      try {
        await dramaRefTemplate(this.cur.id, id)
        if (!id) this.cur.ref_template = null
        else {
          const t = this.scriptTpl.list.find((x) => x.id === id)
          this.cur.ref_template = { id, name: t ? t.name : '参考结构' }
        }
        uni.showToast({ title: id ? '已设参考结构' : '已取消', icon: 'none' })
      } catch (e) {
        uni.showModal({ title: '设置失败', content: e.message, showCancel: false })
      } finally {
        this.busy = ''
      }
    },
    async pickRefTemplate() {
      if (!this.scriptTpl.list.length) {
        uni.showToast({ title: '还没有结构模板', icon: 'none' })
        return
      }
      const names = this.scriptTpl.list.map((t) => `${t.name}（${t.shots_count}镜/${t.total_duration}s）`)
      uni.showActionSheet({
        itemList: names,
        success: (r) => this.setRefTemplate(this.scriptTpl.list[r.tapIndex].id),
      })
    },
    async delMine(t) {
      const r = await new Promise((res) => {
        uni.showModal({
          title: '删掉这个模板？',
          content: `「${(t.name || {}).zh}」删了就找不回来`,
          success: (m) => res(!!m.confirm),
        })
      })
      if (!r) return
      try {
        await dramaTemplatesMineDelete(t.id)
        await this.loadMine()
      } catch (e) {
        uni.showToast({ title: e.message || '删除失败', icon: 'none' })
      }
    },
    color(i) {
      return COLORS[i % COLORS.length]
    },
    countOf(key) {
      const l = this.list || []
      if (key === 'done') return l.filter((p) => p.done).length
      if (key === 'new') return l.filter((p) => !p.done && p.stage === '新建').length
      if (key === 'doing') return l.filter((p) => !p.done && p.stage !== '新建').length
      return l.length
    },
    async loadOptions() {
      try {
        const o = await dramaOptions()
        this.opt = { ...this.opt, ...o }
      } catch (e) {
        // 选项拿不到不挡主流程：表单会退化成只有必填项
        console.warn('[drama] 读取选项失败', e.message)
      }
    },
    /** 一站式自检：报障时先点这个，一次把环境问题全摊开 */
    async healthRun() {
      this.busy = 'health'
      try {
        const h = await dramaHealth()
        const lines = []
        if (h.problems && h.problems.length) {
          lines.push('发现 ' + h.problems.length + ' 个问题：')
          h.problems.forEach((p) => lines.push('· ' + p))
        } else {
          lines.push('环境正常。')
        }
        lines.push(`ffmpeg：${h.ffmpeg && h.ffmpeg.exists ? '有' : '没有'}`
          + `｜磁盘剩 ${h.disk_free_gb == null ? '未知' : h.disk_free_gb + ' GB'}`
          + `｜项目 ${h.paths ? h.paths.projects : 0} 个`)
        if ((this.activeTasks || []).length) {
          lines.push('')
          lines.push(`在飞出片 ${this.activeTasks.length} 笔（已付钱）：`)
          this.activeTasks.forEach((t) => {
            lines.push(`· ${t.product || t.pid} 第 ${t.no} 段，${t.at} 发出`)
          })
          lines.push('先去平台查，别重复提交 —— 重复提交就是再付一次。')
        }
        uni.showModal({
          title: h.ok ? '自检：正常' : '自检：有问题',
          content: lines.join('\n'),
          showCancel: false,
        })
      } catch (e) {
        uni.showModal({
          title: '自检没跑成',
          content: e.message || '后端连不上，先看后端是否在跑',
          showCancel: false,
        })
      } finally {
        this.busy = ''
      }
    },
    async loadList() {
      try {
        this.list = await dramaList()
      } catch (e) {
        uni.showToast({ title: e.message || '读取项目失败', icon: 'none' })
      }
    },
    startNew() {
      this.creating = true
      this.cur = null
      this.editing = false
      this.form = {
        url: '', name: '', points: '', facts: '', audience: '',
        category: '', price: '', platform: '', images: [],
      }
      this.lastImportUrl = ''
      this.answers = { line: 'A', form: '', form_note: '', duration: 30, role: '转折道具', mode: '', presenter: '' }
      this.tpl.draft = null
      this.tpl.draftMineId = ''
      this.catTpl = ''
      if (!this.opt.categories.length) this.loadOptions()
      this.loadTemplatesMeta()
    },
    /** 粘链接一键导入：只填**抓到的**，抓不到就提醒，绝不补编 */
    /**
     * 抓到了页面、但页里没有商品信息时，说清楚是哪种情况（2026-11-08）。
     * 实测（真接口）：淘宝/天猫返回空壳页，拼多多只回站名，抖音只回「商品详情」，
     * 京东首页能抓到 —— 这类站的商品页程序读不到，只能靠截图。
     */
    linkNoInfoHint(u) {
      const s = String(u || '')
      const blocked = ['taobao.com', 'tmall.com', 'yangkeduo.com', 'jinritemai.com', 'douyin.com']
        .find((h) => s.indexOf(h) >= 0)
      return blocked
        ? '淘宝/天猫/抖音/拼多多这类商品页不给程序读，改用「上传商品图」截图最快'
        : '这个页面里没有商品信息，确认是不是商品详情页；或改用「上传商品图」'
    },
    async importUrl() {
      const u = (this.form.url || '').trim()
      if (!u) {
        uni.showToast({ title: '先粘一个链接', icon: 'none' })
        return
      }
      if (this.busy) return
      this.busy = 'import'
      try {
        const r = await dramaImportUrl(u)
        //: 🩸 2026-11-09 主人实测：换了链接但淘宝/京东抓不到（title 为空），
        //: 商品名还留着上一个商品的「女儿红」，建出来的项目拿旧资料写稿 —— 张冠李戴。
        //: 所以：换了链接（和上次解析的不是同一条）就允许覆盖；且一条都没抓到时把旧资料清掉。
        const prev = this.lastImportUrl || ''
        const changed = !!prev && prev !== u
        this.lastImportUrl = u
        const nothing = !r.title && !r.description && !r.price_text && !(r.images || []).length
        if (changed && nothing) {
          this.form.name = ''
          this.form.facts = ''
          this.form.price = ''
          this.form.images = []
        }
        if (r.title && (changed || !this.form.name.trim())) this.form.name = r.title
        if (r.description && (changed || !this.form.facts.trim())) this.form.facts = r.description
        //: 🩸 2026-11-08：后端 `/import-url` 解析出的 `price_text` 以前只用来弹提示，
        //: 从没写进 `form.price` —— 结果商品资料卡「价格」永远显示「—」，
        //: 顾客还得手填一次。抓不到就留空，不编（C10）。
        if (r.price_text && (changed || !this.form.price)) this.form.price = String(r.price_text).trim()
        if (!(changed && nothing)) {
          const left = this.opt.max_pics - this.form.images.length
          for (const n of (r.images || []).slice(0, Math.max(0, left))) {
            this.form.images.push({ name: n, url: dramaStagedUrl(n) })
          }
        }
        const got = [
          r.title ? '标题' : '', r.description ? '描述' : '',
          r.price_text ? `价格 ${r.price_text}` : '',
          (r.images || []).length ? `${r.images.length} 张图` : '',
        ].filter(Boolean)
        if (got.length) {
          uni.showToast({ title: '已导入：' + got.join(' / '), icon: 'none' })
        } else if (changed && nothing) {
          uni.showModal({
            title: '这条链接抓不到商品信息',
            content: '淘宝/京东/抖音这类商品页不给程序读。上一个商品的资料已清空，'
              + '请手动填商品名称和卖点，或改用「上传商品图」。',
            showCancel: false,
          })
        } else {
          uni.showToast({ title: this.linkNoInfoHint(u), icon: 'none' })
        }
      } catch (e) {
        uni.showModal({ title: '导入失败', content: e.message, showCancel: false })
      } finally {
        this.busy = ''
      }
    },
    cancelNew() {
      this.creating = false
      this.form.images = []
      // 回到上一个项目的视图，不把用户丢在空页面上
      if (this.list.length && !this.cur) this.open(this.list[0].id)
    },
    /** 选商品图 —— 先落暂存区拿到文件名，创建时后端搬进项目目录 */
    pickPics() {
      if (this.busy) return
      const left = this.opt.max_pics - this.form.images.length
      if (left <= 0) return
      uni.chooseImage({
        count: left,
        sizeType: ['compressed'],
        sourceType: ['album', 'camera'],
        success: async (res) => {
          const paths = (res && res.tempFilePaths) || []
          if (!paths.length) return
          this.busy = 'pic'
          try {
            for (const p of paths) {
              if (this.form.images.length >= this.opt.max_pics) break
              // eslint-disable-next-line no-await-in-loop
              const r = await dramaStageUpload(p)
              this.form.images.push({ name: r.name, url: p })
            }
          } catch (e) {
            uni.showModal({ title: '上传失败', content: e.message, showCancel: false })
          } finally {
            this.busy = ''
          }
        },
        fail: (e) => {
          const m = (e && e.errMsg) || ''
          if (!m.includes('cancel')) uni.showToast({ title: '选图失败：' + m, icon: 'none' })
        },
      })
    },
    dropPic(i) {
      this.form.images.splice(i, 1)
    },
    /** 老项目：给已有项目加图（直接进项目目录） */
    addProjectPics() {
      if (this.busy || !this.cur) return
      const have = ((this.cur.product || {}).images || []).length
      const left = this.opt.max_pics - have
      if (left <= 0) {
        uni.showToast({ title: `最多 ${this.opt.max_pics} 张`, icon: 'none' })
        return
      }
      uni.chooseImage({
        count: left,
        sizeType: ['compressed'],
        sourceType: ['album', 'camera'],
        success: async (res) => {
          const paths = (res && res.tempFilePaths) || []
          if (!paths.length) return
          this.busy = 'pic'
          try {
            for (const p of paths) {
              // eslint-disable-next-line no-await-in-loop
              this.cur = await dramaUploadImage(this.cur.id, p)
            }
          } catch (e) {
            uni.showModal({ title: '上传失败', content: e.message, showCancel: false })
          } finally {
            this.busy = ''
          }
        },
      })
    },
    async dropProjectPic(name) {
      if (this.busy || !this.cur) return
      try {
        this.cur = await dramaDeleteImage(this.cur.id, name)
      } catch (e) {
        uni.showModal({ title: '删除失败', content: e.message, showCancel: false })
      }
    },
    picUrl(name) {
      return this.cur ? dramaImageUrl(this.cur.id, name) : ''
    },
    /** 老项目改商品资料（品类/人群/平台这些事后能补） */
    startEdit() {
      const p = (this.cur && this.cur.product) || {}
      const a = (this.cur && this.cur.answers) || {}
      this.form = {
        name: p.name || '',
        points: (p.points || []).join('\n'),
        facts: p.facts || '',
        audience: p.audience || '',
        category: p.category || '',
        price: p.price || '',
        platform: p.platform || '',
        images: [],
      }
      this.answers = {
        form: a.form || '情景短剧',
        duration: a.duration || 30,
        role: a.role || '转折道具',
        mode: a.mode || '',
        presenter: a.presenter || '',
      }
      this.editing = true
    },
    cancelEdit() {
      this.editing = false
    },
    async saveEdit() {
      if (this.busy || !this.cur) return
      if (!this.form.name.trim()) {
        uni.showToast({ title: '商品名称不能为空', icon: 'none' })
        return
      }
      this.busy = 'save'
      try {
        this.cur = await dramaPatchProduct(this.cur.id, {
          name: this.form.name.trim(),
          points: this.form.points.split('\n').map((s) => s.trim()).filter(Boolean),
          facts: this.form.facts,
          audience: this.form.audience,
          category: this.form.category,
          price: this.form.price,
          platform: this.form.platform,
          mode: this.answers.mode,
          presenter: this.answers.presenter,
        })
        this.editing = false
        await this.loadList()
      } catch (e) {
        uni.showModal({ title: '保存失败', content: e.message, showCancel: false })
      } finally {
        this.busy = ''
      }
    },
    async create() {
      if (!this.form.name.trim()) {
        uni.showToast({ title: '先填商品名称', icon: 'none' })
        return
      }
      if (this.busy) return
      this.busy = 'create'
      try {
        const product = {
          name: this.form.name.trim(),
          points: this.form.points.split('\n').map((s) => s.trim()).filter(Boolean),
          facts: this.form.facts,
          audience: this.form.audience,
          category: this.form.category,
          price: this.form.price,
          platform: this.form.platform,
          // 粘的链接存进项目：抓不到商品信息也能当店铺链接用（发布文案 UTM + 结尾二维码）
          url: (this.form.url || '').trim(),
          images: this.form.images.map((x) => x.name),
        }
        // A5：品类脚本模板跟着项目走（空 = 该类目默认第一条，由后端挑）
        this.cur = await dramaCreate(product, { ...this.answers, script_template: this.catTpl })
        this.creating = false
        this.pool = []
        this.credits = null
        this.shotMats = []
        this.shotImages = []
        this.clipItems = []
        this.clipVideos = []
        this.mediaRows = []
        this.loadMaterials()
        this.loadShotMats()
        this.loadShotClips()
        this.loadMedia()
        // 模板在项目建好后才落盘（配方存项目文档里，不是浏览器本地）
        if (this.tpl.draft) {
          try {
            const r = await dramaApplyTemplate(this.cur.id, this.tpl.draftMineId
              ? { mine_id: this.tpl.draftMineId }
              : { template: this.tpl.draft })
            if (r && r.template) this.cur.template = { template: r.template }
          } catch (e) {
            uni.showToast({ title: '模板没挂上：' + (e.message || ''), icon: 'none' })
          }
        }
        if (this.scriptTpl.draftId) {
          try {
            await dramaRefTemplate(this.cur.id, this.scriptTpl.draftId)
            const t = this.scriptTpl.list.find((x) => x.id === this.scriptTpl.draftId)
            if (t) this.cur.ref_template = { id: t.id, name: t.name }
          } catch (e) {
            uni.showToast({ title: '结构模板没挂上：' + (e.message || ''), icon: 'none' })
          }
        }
        this.scriptTpl.draftId = ''
        this.tpl.draft = null
        this.tpl.draftMineId = ''
        await this.loadList()
      } catch (e) {
        uni.showToast({ title: e.message || '创建失败', icon: 'none' })
      } finally {
        this.busy = ''
      }
    },
    /**
     * 建完立刻把稿子写出来：结构卡 → 确认 → 剧本 → 分镜。
     *
     * 竞品就是这一步（`start/page.tsx:402-424`：创建后调 `/api/llm/script` 直接拿到
     * 带镜头的剧本，再跳 `?auto=1`），所以用户进脚本页时看到的已经是成稿，
     * 而不是四个空步骤挨个点。结构卡不再当人工闸门，写错了照样能重新生成。
     *
     * 失败不拦：项目已经建好，脚本页上每一段都有「重新生成」可重试。
     * 返回 { ok, failedAt, msg }，调用方决定要不要提示。
     */
    async bootDraft(pid) {
      let step = '结构卡'
      this.bootStep = step
      try {
        await dramaGenerate(pid, 'card')
        await dramaConfirm(pid)
        step = '写剧本'
        this.bootStep = step
        await dramaGenerate(pid, 'script')
        step = '出分镜'
        this.bootStep = step
        const doc = await dramaGenerate(pid, 'storyboard')
        this.bootStep = ''
        return { ok: true, doc }
      } catch (e) {
        this.bootStep = ''
        return { ok: false, failedAt: step, msg: (e && e.message) || '生成失败' }
      }
    },
    /** 把项目里现在生效的六锚同步到输入框（没存过的是后端从剧本/商品资料现抽的） */
    syncBible() {
      const b = (this.cur && this.cur.visual_bible) || (this.plan && this.plan.bible) || {}
      const draft = { ...EMPTY_BIBLE_DRAFT }
      Object.keys(draft).forEach((k) => {
        draft[k] = (b[k] || []).join('，')
      })
      this.bibleDraft = draft
    },
    async saveBible() {
      if (!this.cur || this.busy) return
      let replan = false
      this.busy = 'bible-save'
      try {
        const split = (s) => String(s || '')
          .split(/[,，、\n]/).map((x) => x.trim()).filter(Boolean)
        const payload = {}
        Object.keys(this.bibleDraft).forEach((k) => { payload[k] = split(this.bibleDraft[k]) })
        this.cur = await dramaSaveBible(this.cur.id, payload)
        this.syncBible()
        uni.showToast({ title: '视觉锚点已保存', icon: 'none' })
        replan = !!this.plan
      } catch (e) {
        uni.showModal({ title: '保存失败', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.busy = ''
      }
      // 重新规划一次让「缺锚/禁改」列表即时更新（规划不花钱）
      // ⚠️ 必须放在 busy 清空之后：filmPlan 开头就 busy 检查，塞在 try 里等于没调
      if (replan) await this.filmPlan()
    },
    /* ===== 人物参考图：板只管构图，脸/发型/服装以这里的图为准 ===== */
    castUrl(image) {
      return dramaImageUrl(this.cur.id, image)
    },
    /** 两条路都留着：传真人照片（我们）／照外观生成四视图（竞品同款） */
    pickCast(name) {
      if (!this.cur || this.busy) return
      uni.showActionSheet({
        itemList: ['上传一张照片', '生成四视图定妆照（会花钱）'],
        success: (r) => {
          if (r.tapIndex === 0) this.uploadCast(name)
          else if (r.tapIndex === 1) this.castSheet(name)
        },
      })
    },
    /** 上传真人照片锁脸 */
    uploadCast(name) {
      if (!this.cur || this.busy) return
      uni.chooseImage({
        count: 1,
        sizeType: ['compressed'],
        sourceType: ['album', 'camera'],
        success: async (res) => {
          const p = ((res && res.tempFilePaths) || [])[0]
          if (!p) return
          let done = false
          this.busy = 'cast'
          try {
            this.cur = await dramaUploadCast(this.cur.id, name, p)
            done = true
          } catch (e) {
            uni.showModal({
              title: `「${name}」的图没传上`,
              content: e.message || '请稍后重试',
              showCancel: false,
            })
          } finally {
            this.busy = ''
          }
          // 换了脸 = 上一版计划作废：重算一版（规划不花钱），指纹跟着变
          if (done && ((this.cur.storyboard_json || {}).shots || []).length) await this.filmPlan()
        },
      })
    },
    /** 生成 2×2 四视图定妆照：脸/发型/服装四个机位一次画出来，比一张照片锁得更稳 */
    async castSheet(name) {
      if (!this.cur || this.busy) return
      const go = await new Promise((res) =>
        uni.showModal({
          title: `给「${name}」生成定妆照`,
          content: '照剧本里写的外观画一张 2×2 四视图（正面/侧面/背面/特写），'
            + '出图会花钱。生成后会替换这个角色现在用的图。',
          confirmText: '开始生成',
          success: (x) => res(x.confirm),
          fail: () => res(false),
        })
      )
      if (!go) return
      let done = false
      this.busy = 'cast-sheet'
      try {
        this.cur = await dramaCastSheet(this.cur.id, name)
        done = true
      } catch (e) {
        uni.showModal({
          title: `「${name}」的定妆照没出来`,
          content: e.message || '请稍后重试',
          showCancel: false,
        })
      } finally {
        this.busy = ''
      }
      if (done && ((this.cur.storyboard_json || {}).shots || []).length) await this.filmPlan()
    },
    async removeCast(name) {
      if (!this.cur || this.busy) return
      const go = await new Promise((res) =>
        uni.showModal({
          title: `删掉「${name}」的参考图`,
          content: '删掉后这个人不再锁脸，只靠分镜板和文字描述。',
          success: (x) => res(x.confirm),
          fail: () => res(false),
        })
      )
      if (!go) return
      let done = false
      this.busy = 'cast-del'
      try {
        this.cur = await dramaDeleteCast(this.cur.id, name)
        done = true
      } catch (e) {
        uni.showModal({ title: '删除失败', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.busy = ''
      }
      if (done && ((this.cur.storyboard_json || {}).shots || []).length) await this.filmPlan()
    },
    async open(id) {
      if (this.busy) return
      try {
        this.cur = await dramaGet(id)
        // D1/D2：上游改过、下游没重做 —— 后端算好放在 doc 里，这里落到页面状态
        this.scriptCardStale = !!this.cur.script_stale
        this.storyboardCardStale = !!this.cur.storyboard_stale_card
        this.castStale = this.cur.cast_stale || []
        this.castStaleText = this.castStale.map((x) => x.name).join('、')
        // 做片路线跟着项目走（原来只活在内存里，重开就退回 A 线）
        this.answers = { ...this.answers, line: ((this.cur.answers || {}).line === 'B' ? 'B' : 'A') }
        this.applyLog = []          // 换了项目/重开页面，上一次的应用记录就不再对应当前分镜
        this.syncBible()
        this.syncComp()
        this.creating = false
        // 型号跟着项目走：规划过就用它记下的那档，没规划过用默认档
        const f = this.cur.film || {}
        this.filmModel = f.model || this.opt.default_film_model || ''
        // 没存过 → 用设置中心的全局默认（H4 那几个 film_* 默认值）
        this.chain = f.chain || this.st.film_chain || 'off'
        this.realism = f.realism || this.st.film_realism || 'auto'
        this.filmResolution = f.resolution || this.st.film_resolution || '720p'
        this.filmRatio = f.ratio || this.st.film_ratio || '9:16'
        this.syncResRows()
        this.preflight = null
        this.variant = { ...this.variant, plan: null, rows: [] }
        this.credits = null
        this.poolEdit = { ...this.poolEdit, open: false }
        this.matPick = { ...this.matPick, open: false }
        this.clipPick = { ...this.clipPick, open: false }
        this.loadScripts()
        this.loadMaterials()
        this.loadShotMats()
        this.loadShotClips()
        this.loadMedia()
        this.loadVoice()
      } catch (e) {
        uni.showToast({ title: e.message || '打开失败', icon: 'none' })
      }
    },
    // ---------- 第六批：生成链增强 ----------
    /** A7：项目的全部脚本版本（后端按版本倒序给） */
    async loadScripts() {
      if (!this.cur) return
      try {
        const r = await dramaScripts(this.cur.id)
        this.scripts = (r && r.scripts) || []
        this.scriptStale = !!(r && r.storyboard_stale)
      } catch (e) {
        this.scripts = []
        this.scriptStale = false
      }
    },
    async switchScript(sid) {
      if (!this.cur || this.busy) return
      this.busy = 'script-switch'
      try {
        const r = await dramaSelectScript(this.cur.id, sid)
        if (r && r.project) this.cur = r.project
        await this.loadScripts()
      } catch (e) {
        uni.showToast({ title: e.message || '切换失败', icon: 'none' })
      } finally {
        this.busy = ''
      }
    },
    async removeScript(s) {
      if (!this.cur || this.busy) return
      const ok = await new Promise((res) => uni.showModal({
        title: '删掉这一版？',
        content: s.title || ('第 ' + s.version + ' 版'),
        success: (x) => res(x.confirm),
        fail: () => res(false),
      }))
      if (!ok) return
      this.busy = 'script-del'
      try {
        this.cur = await dramaDeleteScript(this.cur.id, s.id)
        await this.loadScripts()
      } catch (e) {
        uni.showToast({ title: e.message || '删除失败', icon: 'none' })
      } finally {
        this.busy = ''
      }
    },
    // ---------- B4 每镜参考画面 ----------
    async loadShotMats() {
      if (!this.cur) return
      try {
        const r = await dramaShotMaterials(this.cur.id)
        this.shotMats = (r && r.items) || []
        this.shotImages = (r && r.images) || []
      } catch (e) {
        this.shotMats = []
        this.shotImages = []
      }
    },
    matName(name) {
      const row = (this.shotMats || []).find((m) => m.material === name)
      return (row && row.original_name) || name
    },
    segShots(seg) {
      // 本段镜头（按分镜顺序）—— 配画面时选「配给哪一镜」
      const shots = ((this.cur && this.cur.storyboard_json) || {}).shots || []
      return ((seg && seg.shot_ids) || []).map((id) => {
        const s = shots.find((x) => Number(x.id) === Number(id))
        return { id: Number(id), text: s ? String(s.description || '').slice(0, 10) : '' }
      })
    },
    matOfShot(shotId) {
      return (this.shotMats || []).find((m) => Number(m.shot_id) === Number(shotId)) || null
    },
    openMatPick(seg) {
      if (!this.cur) return
      const shots = this.segShots(seg)
      const free = shots.find((s) => !this.matOfShot(s.id)) || shots[0]
      const cur = free ? this.matOfShot(free.id) : null
      this.matPick = { open: true, seg: seg ? seg.no : 0, shots,
                       shotId: free ? free.id : 0, material: (cur && cur.material) || '' }
    },
    async saveMatPick() {
      if (!this.cur || !this.matPick.shotId) return
      if (!this.matPick.material) {
        uni.showToast({ title: '先选一张图片', icon: 'none' })
        return
      }
      const items = (this.shotMats || [])
        .filter((m) => Number(m.shot_id) !== Number(this.matPick.shotId))
        .map((m) => ({ shot_id: m.shot_id, material: m.material }))
      items.push({ shot_id: this.matPick.shotId, material: this.matPick.material })
      await this.putShotMats(items)
    },
    async clearShotMat(shotId) {
      const items = (this.shotMats || [])
        .filter((m) => Number(m.shot_id) !== Number(shotId))
        .map((m) => ({ shot_id: m.shot_id, material: m.material }))
      await this.putShotMats(items)
    },
    async putShotMats(items) {
      if (!this.cur || this.busy) return
      this.busy = 'shot-mat'
      let changed = false
      try {
        const r = await dramaShotMaterialsSave(this.cur.id, items)
        this.shotMats = (r && r.items) || []
        this.matPick.open = false
        changed = true
      } catch (e) {
        // request 层已提示
      } finally {
        this.busy = ''
      }
      // ⚠️ 绑定改了 = 提示词和参考图都变了 → 计划必须重算；
      // 但 filmPlan 开头就查 busy，所以只能等 busy 清空之后再调。
      if (changed) await this.filmPlan()
    },
    async autoShotMats() {
      if (!this.cur || this.busy) return
      this.busy = 'shot-mat'
      let changed = false
      try {
        const r = await dramaShotMaterialsAuto(this.cur.id)
        this.shotMats = (r && r.items) || []
        changed = true
        const added = Number((r && r.added) || 0)
        const skipped = Number((r && r.skipped) || 0)
        uni.showToast({
          title: `自动配了 ${added} 镜${skipped ? `，${skipped} 镜没匹配上（不硬塞）` : ''}`,
          icon: 'none',
          duration: 2500,
        })
      } catch (e) {
        // request 层已提示
      } finally {
        this.busy = ''
      }
      if (changed) await this.filmPlan()
    },

    // ---------- B6/B8 素材当画面（视频）：这一镜不再由 AI 生成 ----------
    async loadShotClips() {
      if (!this.cur) return
      try {
        const r = await dramaShotClips(this.cur.id)
        this.clipItems = (r && r.items) || []
        this.clipVideos = (r && r.videos) || []
      } catch (e) {
        this.clipItems = []
        this.clipVideos = []
      }
    },
    clipOf(shotId) {
      return (this.clipItems || []).find((x) => Number(x.shot_id) === Number(shotId)) || null
    },
    openClipPick(shotId) {
      const cur = this.clipOf(shotId)
      this.clipPick = { open: true, shotId, material: (cur && cur.material) || '' }
    },
    async saveClipPick() {
      if (!this.cur || !this.clipPick.shotId) return
      if (!this.clipPick.material) {
        uni.showToast({ title: '先选一段视频', icon: 'none' })
        return
      }
      const sid = Number(this.clipPick.shotId)
      const items = (this.clipItems || [])
        .filter((x) => Number(x.shot_id) !== sid)
        .map((x) => ({ shot_id: x.shot_id, material: x.material }))
      items.push({ shot_id: sid, material: this.clipPick.material })
      const shot = (this.storyShots || []).find((x) => x.id === sid)
      await this.putClips(items, shot)
    },
    async clearClip(shotId) {
      const items = (this.clipItems || [])
        .filter((x) => Number(x.shot_id) !== Number(shotId))
        .map((x) => ({ shot_id: x.shot_id, material: x.material }))
      await this.putClips(items)
    },
    async putClips(items, shot) {
      if (!this.cur || this.busy) return
      this.busy = 'shot-clip'
      let changed = false
      try {
        const r = await dramaShotClipsSave(this.cur.id, items)
        this.clipItems = (r && r.items) || []
        this.clipPick.open = false
        changed = true
      } catch (e) {
        // request 层已提示
      } finally {
        this.busy = ''
      }
      if (shot && shot.dialogue) {
        uni.showModal({
          title: '这一镜有台词',
          content: `镜头 ${shot.id} 的台词「${shot.dialogue}」不会出现在成片里 —— 素材里没有这句话，字幕也不会烧。`,
          showCancel: false,
        })
      }
      // 绑定改了 = 段结构、提示词、时间线全变 → 必须重算（filmPlan 开头查 busy，所以要等清空后调）
      if (changed) await this.filmPlan()
    },

    // ---------- B3 免版权素材搜索 ----------
    async loadStockSources() {
      try {
        const r = await dramaStockSources()
        this.stockSources = (r && r.sources) || []
      } catch (e) {
        this.stockSources = []
      }
    },
    stockSourceLabel(id) {
      if (id === 'all') return '全部'
      const s = (this.stockSources || []).find((x) => x.id === id)
      return s ? s.label : id
    },
    stockSize(c) {
      const bits = []
      if (c.width && c.height) bits.push(`${c.width}×${c.height}`)
      if (c.duration_sec) bits.push(`${Number(c.duration_sec).toFixed(1)}s`)
      return bits.join(' · ')
    },
    async doStockSearch() {
      if (!this.cur || this.stockBusy) return
      const q = String(this.stockQ || '').trim()
      if (!q) {
        uni.showToast({ title: '先填检索词', icon: 'none' })
        return
      }
      this.stockBusy = 'search'
      this.stockMsg = ''
      try {
        const r = await dramaStockSearch(this.cur.id, {
          query: q, source: this.stockSource, media_type: this.stockType, per_page: 10,
        })
        this.stockResults = (r && r.candidates) || []
        if (r && r.sources && r.sources.length && !this.stockSources.length) this.stockSources = r.sources
        const skipped = ((r && r.skipped_sources) || []).map((x) => this.stockSourceLabel(x))
        const errored = ((r && r.errored_sources) || []).map((x) => this.stockSourceLabel(x))
        const bits = []
        if (skipped.length) bits.push(`${skipped.join('、')} 要先配 Key`)
        if (errored.length) bits.push(`${errored.join('、')} 这次没连上`)
        this.stockMsg = bits.join('｜')
        if (!this.stockResults.length && !bits.length) this.stockMsg = '没搜到，换个检索词试试（英文召回更好）'
      } catch (e) {
        uni.showModal({ title: '搜索失败', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.stockBusy = ''
      }
    },
    async importStock(c) {
      if (!this.cur || this.stockBusy) return
      this.stockBusy = 'import'
      try {
        const r = await dramaStockImport(this.cur.id, {
          source: c.source, media_type: c.media_type, id: String(c.id),
        })
        this.stockImported = `${c.source}:${c.id}`
        if (r.kind === 'bgm') {
          this.cur = r.project
          uni.showToast({ title: '已设为 BGM', icon: 'success' })
        } else {
          await this.loadMaterials()
          await this.loadShotMats()
          await this.loadShotClips()
          uni.showToast({
            title: r.duplicate ? '素材库里已有' : '已加进素材库',
            icon: 'success',
          })
        }
      } catch (e) {
        uni.showModal({ title: '导入失败', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.stockBusy = ''
      }
    },

    async autoFillStock() {
      if (!this.cur || this.stockFillBusy) return
      const go = await new Promise((res) =>
        uni.showModal({
          title: '自动配画面',
          content: '按分镜逐镜从免版权库搜图，下载后绑成每一镜的参考画面（不改出片段数、不生成视频）。搜不到贴题的镜头会留空，不硬塞。',
          success: (x) => res(x.confirm),
          fail: () => res(false),
        })
      )
      if (!go) return
      this.stockFillBusy = true
      this.stockFillMsg = ''
      try {
        const r = await dramaStockAutoFill(this.cur.id, { media_type: 'image' })
        const lv = r.levels || {}
        const bits = []
        bits.push(`配了 ${r.filled}/${r.filled + (r.unmatched || []).length} 镜`)
        if (lv.original) bits.push(`原词命中 ${lv.original}`)
        if (lv.narrowed) bits.push(`放宽后命中 ${lv.narrowed}`)
        if (lv.universal) bits.push(`通用词 ${lv.universal}`)
        const miss = (r.unmatched || []).map((u) => u.shot_id)
        if (miss.length) bits.push(`没配上：镜头 ${miss.join('、')}（只搜到通用词或不贴题，没硬塞）`)
        this.stockFillMsg = bits.join('｜')
        if (r.project) this.cur = r.project
        await this.loadMaterials()
        await this.loadShotMats()
        await this.filmPlan()
        uni.showToast({ title: `配了 ${r.filled} 镜`, icon: r.filled ? 'success' : 'none' })
      } catch (e) {
        uni.showModal({ title: '自动配画面失败', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.stockFillBusy = false
      }
    },

    // ---------- B6 长视频导入（自有素材原料区，和素材库分开） ----------
    async loadMedia() {
      if (!this.cur) return
      try {
        const r = await dramaMediaList(this.cur.id)
        this.mediaRows = r.sources || []
      } catch (e) {
        this.mediaRows = []
      }
    },
    mediaMeta(m) {
      const bits = []
      const d = Number(m.duration || 0)
      if (d > 0) {
        const mm = Math.floor(d / 60)
        const ss = Math.round(d % 60)
        bits.push(mm ? `${mm}分${ss}秒` : `${ss}秒`)
      }
      if (m.width && m.height) bits.push(`${m.width}×${m.height}`)
      const kb = Number(m.size_bytes || 0) / 1024
      bits.push(kb >= 1024 * 1024 ? `${(kb / 1024 / 1024).toFixed(2)}GB`
        : kb >= 1024 ? `${(kb / 1024).toFixed(1)}MB` : `${Math.max(1, Math.round(kb))}KB`)
      bits.push(m.has_audio ? '有声' : '无声')
      return bits.join(' · ')
    },
    pickMedia() {
      if (!this.cur || this.mediaBusy) return
      // #ifdef H5
      uni.chooseFile({
        count: 1,
        extension: ['.mp4', '.mov', '.webm', '.mkv', '.m4v'],
        success: async (r) => {
          const f = ((r && r.tempFiles) || [])[0] || {}
          const path = ((r && r.tempFilePaths) || [])[0]
          if (!path) return
          const name = f.name || 'video.mp4'
          const size = Number(f.size || 0)
          if (size > 1024 * 1024 * 1024) {
            uni.showModal({ title: '文件太大', content: '单个视频不能超过 1GB', showCancel: false })
            return
          }
          await this.runMediaImport(path, name, this.mediaUploadH5)
        },
      })
      // #endif
      // #ifndef H5
      // 小程序没有文件选择框：从聊天记录里选视频，走 uni.uploadFile 的 multipart
      uni.chooseMessageFile({
        count: 1,
        type: 'video',
        success: async (r) => {
          const f = ((r && r.tempFiles) || [])[0] || {}
          const path = f.path
          if (!path) return
          const name = f.name || 'video.mp4'
          if (Number(f.size || 0) > 1024 * 1024 * 1024) {
            uni.showModal({ title: '文件太大', content: '单个视频不能超过 1GB', showCancel: false })
            return
          }
          await this.runMediaImport(path, name, this.mediaUploadMp)
        },
      })
      // #endif
    },
    /** H5：原始 body 直传（不带 multipart 包装） */
    mediaUploadH5(path, name, onPct) {
      return dramaMediaImport(this.cur.id, path, name, onPct)
    },
    /** 小程序：uni.uploadFile（multipart），后端同端点兼容 */
    mediaUploadMp(path, name, onPct) {
      return dramaMediaImportUni(this.cur.id, path, name, onPct)
    },
    /** 长视频导入的公共收尾：忙态 / 进度 / 列表更新 / 报错（H5 与小程序共用） */
    async runMediaImport(path, name, upload) {
      this.mediaBusy = true
      this.mediaPct = 0
      try {
        const r2 = await upload(path, name, (pct) => { this.mediaPct = pct })
        const s = r2.source || {}
        this.mediaRows = [s, ...this.mediaRows.filter((x) => x.id !== s.id)]
        uni.showToast({ title: '导入完成', icon: 'success' })
      } catch (e) {
        uni.showModal({ title: '导入失败', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.mediaBusy = false
        this.mediaPct = 0
      }
    },
    async dropMedia(m) {
      if (!this.cur || this.mediaBusy) return
      const go = await new Promise((res) =>
        uni.showModal({
          title: '删掉这条视频',
          content: `「${m.original_name}」会从盘上删掉，删了要重新传。`,
          success: (x) => res(x.confirm),
          fail: () => res(false),
        })
      )
      if (!go) return
      try {
        await dramaMediaDelete(this.cur.id, m.id)
        this.mediaRows = this.mediaRows.filter((x) => x.id !== m.id)
      } catch (e) {
        uni.showModal({ title: '删除失败', content: e.message || '请稍后重试', showCancel: false })
      }
    },
    /**
     * 跨端打开一个文件：H5 新标签页（能下载）；小程序进预览页用原生组件播/看。
     * 🩸 小程序没有「新标签页」，以前这些入口在小程序里点了没反应或只复制一个打不开的链接。
     */
    previewFile(url, name = '', kind = '') {
      if (!url) return
      // #ifdef H5
      window.open(url, '_blank')
      // #endif
      // #ifndef H5
      const k = kind || guessFileKind(name || url)
      uni.navigateTo({
        url: `/pages/drama/preview?kind=${k}`
          + `&name=${encodeURIComponent(name || '')}`
          + `&url=${encodeURIComponent(url)}`,
      })
      // #endif
    },
    openMedia(m) {
      this.previewFile(dramaMediaUrl(this.cur.id, m.id), m.original_name || '', 'video')
    },
    patchMediaRow(src) {
      if (!src || !src.id) return
      this.mediaRows = this.mediaRows.map((x) => (x.id === src.id ? { ...x, ...src } : x))
    },
    async startTranscribe(m) {
      if (!this.cur || this.mediaBusy) return
      try {
        const r = await dramaMediaTranscriptStart(this.cur.id, m.id, { action: 'start' })
        this.patchMediaRow(r.source)
        this.scheduleTrPoll()
      } catch (e) {
        uni.showModal({ title: '没法转写', content: e.message || '请稍后重试', showCancel: false })
      }
    },
    async cancelTranscribe(m) {
      try {
        await dramaMediaTranscriptCancel(this.cur.id, m.id)
        this.mediaRows = this.mediaRows.map((x) =>
          x.id === m.id ? { ...x, status: x.transcript_summary ? 'ready' : 'uploaded', progress: 0 } : x
        )
      } catch (e) {
        uni.showToast({ title: e.message || '取消失败', icon: 'none' })
      }
    },
    scheduleTrPoll() {
      if (this.trPoll) return
      this.trPoll = setTimeout(async () => {
        this.trPoll = null
        await this.refreshTranscribing()
      }, 1800)
    },
    async refreshTranscribing() {
      if (!this.cur) return
      const rows = this.mediaRows.filter((m) => m.status === 'transcribing')
      for (const m of rows) {
        try {
          const r = await dramaMediaTranscript(this.cur.id, m.id)
          this.patchMediaRow(r.source)
          const t = r.transcript || {}
          if (t.status === 'ready' && t.transcript) {
            this.trText = { ...this.trText, [m.id]: t.transcript.text || '' }
            uni.showToast({ title: '转写完成', icon: 'success' })
          }
          if (t.status === 'failed') {
            uni.showToast({ title: t.error || '转写失败', icon: 'none' })
          }
        } catch (e) {
          /* 单条拉取失败不打断轮询 */
        }
      }
      if (this.mediaRows.some((m) => m.status === 'transcribing')) this.scheduleTrPoll()
    },
    clipReason(reasons) {
      const map = { query: '关键词命中', sentence: '句末完整', pause: '停顿时收' }
      return (reasons || []).map((r) => map[r] || r).join(' · ')
    },
    toggleClips(m) {
      this.clipOpen = { ...this.clipOpen, [m.id]: !this.clipOpen[m.id] }
    },
    async findClips(m) {
      if (!this.cur || this.clipBusy[m.id]) return
      this.clipBusy = { ...this.clipBusy, [m.id]: true }
      try {
        const r = await dramaMediaClips(this.cur.id, m.id, {
          query: (this.clipQ[m.id] || '').trim(),
          target_seconds: Number(this.clipTarget[m.id] || 30),
          limit: 6,
        })
        this.clipRes = { ...this.clipRes, [m.id]: r.candidates || [] }
        if (!(r.candidates || []).length) {
          uni.showToast({ title: '没找到合适的片段', icon: 'none' })
        }
      } catch (e) {
        uni.showModal({ title: '找片段失败', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.clipBusy = { ...this.clipBusy, [m.id]: false }
      }
    },
    async cutClip(m, c) {
      if (!this.cur || this.clipBusy[m.id]) return
      this.clipBusy = { ...this.clipBusy, [m.id]: true }
      try {
        const r = await dramaMediaClipCut(this.cur.id, m.id, { start: c.start, end: c.end })
        this.clipOut = {
          ...this.clipOut,
          [m.id]: { ...(this.clipOut[m.id] || {}), [c.id]: r },
        }
        uni.showToast({ title: '剪好了', icon: 'success' })
      } catch (e) {
        uni.showModal({ title: '剪不出来', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.clipBusy = { ...this.clipBusy, [m.id]: false }
      }
    },
    openClipFile(m, c) {
      const out = (this.clipOut[m.id] || {})[c.id]
      if (!out) return
      this.previewFile(dramaMediaClipUrl(this.cur.id, m.id, out.name), out.name, 'video')
    },
    /* ===== G2 作品流：跨项目成片墙 ===== */
    async toggleWorks() {
      this.wkOpen = !this.wkOpen
      if (this.wkOpen && !this.wkItems.length) await this.loadWorks()
    },
    async loadWorks() {
      if (this.wkBusy) return
      this.wkBusy = true
      try {
        const r = await dramaWorks()
        this.wkItems = r.works || []
        this.wkNote = `${r.total || 0} 条成片`
          + (r.backfilled ? ` · 本次补了 ${r.backfilled} 张封面` : '')
        if (!this.wkItems.length) this.wkPlay = ''
      } catch (e) {
        this.wkItems = []
        this.wkNote = e.message || '读取失败'
      } finally {
        this.wkBusy = false
      }
    },
    playWork(w) {
      this.wkPlay = API_BASE + w.url
    },

    /* ===== G4/G5 效果回流：发布后回填 → 学出哪种风格更能卖 ===== */
    async toggleFeedback() {
      this.fbOpen = !this.fbOpen
      if (this.fbOpen) await this.loadFeedback()
    },
    async loadFeedback() {
      if (!this.cur) return
      try {
        const [m, ins] = await Promise.all([
          dramaMetrics(this.cur.id), dramaStyleInsights(),
        ])
        this.fbRows = m.metrics || []
        this.fbStyles = ins.insights || []
        this.fbHooks = ins.hookInsights || []
      } catch (e) {
        this.fbNote = e.message || '读取失败'
      }
    },
    async saveMetric() {
      if (this.fbBusy || !this.cur) return
      if (!(Number(this.fbForm.views) > 0)) {
        this.fbNote = '「播放」必填'
        return
      }
      this.fbBusy = true
      try {
        await dramaMetricSave(this.cur.id, { ...this.fbForm })
        this.fbNote = '已保存'
        // 与竞品一致：保留平台，其余清空（下一条接着录）
        this.fbForm = { ...EMPTY_METRIC, platform: this.fbForm.platform }
        await this.loadFeedback()
      } catch (e) {
        this.fbNote = e.message || '保存失败'
      } finally {
        this.fbBusy = false
      }
    },
    pct(x) {
      return (Number(x || 0) * 100).toFixed(2) + '%'
    },

    /* ===== G3 趋势话题：今天该发什么 ===== */
    trCatLabel(c) {
      return {
        ent: '娱乐', food: '美食', tech: '科技', game: '游戏', sports: '体育',
        fashion: '时尚', car: '汽车', pets: '萌宠', life: '生活', society: '社会',
      }[c] || c
    },
    async toggleTrends() {
      this.trOpen = !this.trOpen
      if (this.trOpen && !this.trTopics.length) await this.loadTrends('cn')
    },
    async loadTrends(src) {
      if (this.trBusy) return
      this.trBusy = true
      try {
        const params = src === 'google' ? { geo: 'US' } : { source: 'cn' }
        // 人设 = 当前项目的受众；没有项目就不传（后端按榜首给「今日一条」）
        const persona = ((this.cur && this.cur.product) || {}).audience || ''
        if (persona) params.persona = persona
        const r = await dramaTrends(params)
        this.trTopics = r.topics || []
        this.trCats = r.categories || []
        this.trPick = r.pick || null
        this.trCat = 'all'
        const name = { douyin: '抖音', toutiao: '头条', google: 'Google' }[r.source] || r.source
        this.trNote = r.error || `${name} · ${r.count} 条`
      } catch (e) {
        this.trTopics = []
        this.trPick = null
        this.trNote = e.message || '拉取失败'
      } finally {
        this.trBusy = false
      }
    },
    useTrend(t) {
      this.topic.topic = t.title
      this.trOpen = false
      this.openTopic()
    },

    /* ===== H4 设置中心：全局默认值（新建项目 / 合成面板从这里取默认） ===== */
    /** 打开页面时先取全局默认，没存过合成设置的项目按它预填 */
    /* ===== B11 媒体解构实验室 ===== */
    toggleMediaLab() {
      this.mlOpen = !this.mlOpen
    },
    /** 媒体解构实验室的选文件（和下面长视频导入的 `pickMedia()` 不是一回事，别同名覆盖） */
    pickLabMedia(kind) {
      if (this.mlBusy) return
      const take = (path, size) => {
        if (!path) return
        const limit = kind === 'image' ? 15 * 1024 * 1024 : 80 * 1024 * 1024
        if (size && size > limit) {
          uni.showToast({ title: kind === 'image' ? '图片不能超过 15MB' : '视频不能超过 80MB', icon: 'none' })
          return
        }
        this.mlFile = { path, size: size || 0, kind }
        this.mlResult = null
        this.mlNote = ''
      }
      if (kind === 'image') {
        uni.chooseImage({
          count: 1,
          success: (res) => {
            const f = (res.tempFiles || [])[0] || {}
            take((res.tempFilePaths || [])[0], f.size)
          },
        })
      } else {
        uni.chooseVideo({
          compressed: false,
          success: (res) => {
            if (res.duration > 180) {
              uni.showToast({ title: '视频最长支持 3 分钟', icon: 'none' })
              return
            }
            take(res.tempFilePath, res.size)
          },
        })
      }
    },
    async analyzeMedia() {
      if (!this.mlFile || this.mlBusy) return
      this.mlBusy = true
      this.mlNote = ''
      try {
        this.mlResult = await dramaMediaAnalyze(this.mlFile.path)
      } catch (e) {
        this.mlNote = e.message || '解构失败'
      } finally {
        this.mlBusy = false
      }
    },
    copyReusablePrompt() {
      if (!this.mlResult || !this.mlResult.reusable_prompt) return
      uni.setClipboardData({ data: this.mlResult.reusable_prompt })
    },
    mlPickProject(e) {
      const row = (this.list || [])[Number(e.detail.value)]
      this.mlProjectId = row ? row.id : ''
    },
    async saveMediaInsight() {
      if (!this.mlResult || !this.mlProjectId || this.mlSaving) return
      this.mlSaving = true
      try {
        await dramaProductionSave(this.mlProjectId, {
          mediaType: this.mlResult.media_type,
          summary: this.mlResult.summary,
          tags: this.mlResult.subjects || [],
          reusablePrompt: this.mlResult.reusable_prompt,
        })
        uni.showToast({ title: '已存进项目' })
      } catch (e) {
        uni.showToast({ title: e.message || '保存失败', icon: 'none' })
      } finally {
        this.mlSaving = false
      }
    },
    mlFileLabel() {
      if (!this.mlFile) return ''
      const mb = this.mlFile.size / 1024 / 1024
      return this.mlFile.kind === 'image' ? `图片 ${mb.toFixed(1)}MB` : `视频 ${mb.toFixed(1)}MB`
    },
    /* ===== G1 批量作业 ===== */
    btStatusText(s) {
      return BATCH_STATUS_TEXT[s] || s
    },
    togglePick(id) {
      if (this.btRunning) return
      this.btPicked = this.btPicked.includes(id)
        ? this.btPicked.filter((x) => x !== id)
        : [...this.btPicked, id]
    },
    async toggleBatch() {
      this.btOpen = !this.btOpen
      if (this.btOpen) await this.loadBatch()
    },
    async loadBatch() {
      if (!this.btProducts.length) {
        try {
          const r = await dramaProducts()
          this.btProducts = (r && r.products) || []
        } catch (e) {
          /* 商品库读不到不拦批量卡 */
        }
      }
      try {
        let r = await dramaBatchGet({ active: 1 })
        if (!r || !r.job) r = await dramaBatchGet({})
        this.btJob = (r && r.job) || null
        this.btItems = (r && r.items) || []
        this.btResumable = !!(this.btJob && this.btJob.status === 'running' && !this.btRunning)
        const cfg = (this.btJob && this.btJob.config) || {}
        this.btPlan = Array.isArray(cfg.plan) ? cfg.plan : []
      } catch (e) {
        this.btNote = e.message || '读取批量作业失败'
      }
    },
    btPatchLocal(id, patch) {
      this.btItems = this.btItems.map((it) => (it.id === id ? { ...it, ...patch } : it))
      if (this.btJob && this.btJob.items) {
        this.btJob.items = this.btJob.items.map((it) => (it.id === id ? { ...it, ...patch } : it))
      }
    },
    /** 写回是 best-effort：失败不许打断整批（竞品 `batch/page.tsx:229-237`） */
    async btReport(id, patch) {
      try {
        await dramaBatchPatch({ item_id: id, patch })
      } catch (e) {
        /* 落盘失败不拦执行 */
      }
    },
    async startBatch() {
      if (this.btRunning || this.btBusy) return
      const picked = this.btProducts.filter((p) => this.btPicked.includes(p.id))
      if (!picked.length) {
        this.btNote = '先选至少一个商品'
        return
      }
      this.btBusy = true
      this.btNote = ''
      try {
        const seed = Date.now() % 100000
        let plan = []
        if (this.btAnti) {
          try {
            const r = await dramaBatchPlan({ count: picked.length, seed })
            plan = (r && r.slots) || []
          } catch (e) {
            plan = []
          }
        }
        const items = picked.map((p, i) => ({
          product_id: p.id,
          product_name: p.name,
          variation: plan[i] ? plan[i].summary : '',
        }))
        const cfg = { duration: this.btDuration, anti_homogeneity: this.btAnti, seed, plan }
        const made = await dramaBatchCreate(cfg, items)
        const got = await dramaBatchGet({ job_id: made.job_id })
        this.btJob = got.job
        this.btItems = got.items || []
        this.btPlan = plan
        await this.executeBatch(this.btJob, plan)
      } catch (e) {
        this.btNote = e.message || '批量作业没建起来'
      } finally {
        this.btBusy = false
      }
    },
    async resumeBatch() {
      if (!this.btJob || this.btRunning) return
      const cfg = this.btJob.config || {}
      this.btPlan = Array.isArray(cfg.plan) ? cfg.plan : []
      if (cfg.duration) this.btDuration = cfg.duration
      await this.executeBatch(this.btJob, this.btPlan)
    },
    async discardBatch() {
      if (!this.btJob || this.btRunning) return
      try {
        await dramaBatchPatch({ job_id: this.btJob.id, status: 'cancelled' })
      } catch (e) {
        /* 无视 */
      }
      this.btResumable = false
      this.btJob = { ...this.btJob, status: 'cancelled' }
    },
    abortBatch() {
      this.btAbort = true
      this.btNote = '停止中：已发出去的请求会写完再停'
    },
    /** 执行器：并发 3，逐条推进（竞品 `batch/page.tsx:413-451`） */
    async executeBatch(job, plan) {
      if (!job) return
      this.btRunning = true
      this.btAbort = false
      this.btResumable = false
      this.btNote = ''
      const work = (job.items || []).map((it, idx) => ({ it, slot: (plan || [])[idx] }))
      let cursor = 0
      const worker = async () => {
        while (!this.btAbort) {
          const idx = cursor++
          if (idx >= work.length) break
          const one = work[idx]
          if (one.it.status === 'done') continue
          await this.runBatchItem(one.it, one.slot)
        }
      }
      try {
        const n = Math.min(BATCH_CONCURRENCY, work.length)
        await Promise.all(Array.from({ length: n }, worker))
      } finally {
        const status = this.btAbort ? 'cancelled' : 'done'
        try {
          await dramaBatchPatch({ job_id: job.id, status })
        } catch (e) {
          /* 结算失败不拦界面 */
        }
        this.btRunning = false
        this.btAbort = false
        await this.loadBatch()
      }
    },
    /** 一条商品：建项目 → 存商品图 → 结构卡 → 确认 → 剧本 → 分镜 */
    async runBatchItem(it, slot) {
      this.btPatchLocal(it.id, { status: 'generating', error: null })
      await this.btReport(it.id, { status: 'generating' })
      const p = this.btProducts.find((x) => x.id === it.product_id) || { name: it.product_name }
      try {
        const doc = await dramaCreate(
          {
            name: p.name || it.product_name,
            points: p.points || [],
            facts: p.facts || '',
            audience: p.audience || '',
            category: p.category || '',
            price: p.price || '',
            platform: p.platform || '',
            images: [],
          },
          {
            form: '情景短剧',
            duration: this.btDuration,
            role: '转折道具',
            mode: '',
            presenter: '',
            preferred_hook: slot ? slot.hook_id : '',
          },
        )
        const pid = doc.id
        this.btPatchLocal(it.id, { project_id: pid })
        await this.btReport(it.id, { project_id: pid })
        // 商品图从商品库复制进项目（失败不拦：剧本/分镜不依赖图）
        try {
          await dramaProductApply(it.product_id, pid)
        } catch (e) {
          /* 图复制失败不拦 */
        }
        if (this.btAbort) return
        await dramaGenerate(pid, 'card')
        if (this.btAbort) return
        await dramaConfirm(pid)
        await dramaGenerate(pid, 'script')
        if (this.btAbort) return
        await dramaGenerate(pid, 'storyboard')
        this.btPatchLocal(it.id, { status: 'done' })
        await this.btReport(it.id, { status: 'done' })
      } catch (e) {
        const msg = (e && e.message) || '生成失败'
        this.btPatchLocal(it.id, { status: 'failed', error: msg })
        await this.btReport(it.id, { status: 'failed', error: msg })
      }
    },
    async initSettingsDefaults() {
      await this.loadSettings()
      this.applySettingsToCompose()
    },
    /* ===== C4 平台 Key 连通性：服务端只读探针 ===== */
    async loadProbeProviders() {
      if (this.prRows.length) return
      try {
        const r = await dramaProbeProviders()
        this.prRows = r.providers || []
      } catch (e) {
        /* 探测登记是锦上添花，加载失败不打断设置卡 */
      }
    },
    prOf(name) {
      return this.prRows.find((x) => x.name === name) || null
    },
    prSupported(name) {
      const p = this.prOf(name)
      return !!(p && p.supported)
    },
    prStatusText(s) {
      return {
        ok: '正常', invalid: 'Key 无效', unknown: '无法判定',
        missing: '未配置', unsupported: '不支持探测',
      }[s] || s
    },
    prNote(name) {
      const r = this.prResults[name]
      if (r) return `${this.prStatusText(r.status)} · ${r.message}`
      const p = this.prOf(name)
      if (p && !p.supported) return p.reason || '不支持只读探测'
      return ''
    },
    async probeOne(name) {
      if (this.prBusy) return
      this.prBusy = name
      try {
        const r = await dramaProbeRun([name])
        const row = (r.results || [])[0]
        if (row) this.prResults = { ...this.prResults, [name]: row }
      } catch (e) {
        this.prResults = { ...this.prResults,
          [name]: { status: 'unknown', message: e.message || '探测失败' } }
      } finally {
        this.prBusy = ''
      }
    },
    async probeAll() {
      if (this.prBusy) return
      this.prBusy = 'all'
      try {
        const r = await dramaProbeRun([])
        const map = { ...this.prResults }
        ;(r.results || []).forEach((x) => { map[x.name] = x })
        this.prResults = map
      } catch (e) {
        this.prResults = { ...this.prResults,
          deepseek: { status: 'unknown', message: e.message || '探测失败' } }
      } finally {
        this.prBusy = ''
      }
    },
    async toggleSettings() {
      this.stOpen = !this.stOpen
      if (this.stOpen && !this.stKeys.length) await this.loadSettings()
    },
    async loadSettings() {
      try {
        const r = await dramaSettings()
        this.st = { ...this.st, ...(r.settings || {}) }
        this.stOpts = r.options || this.stOpts
        this.stKeys = r.keys || []
        this.loadProbeProviders()
      } catch (e) {
        this.stNote = e.message || '设置加载失败'
      }
    },
    /** H4：旧版设置导入（五版修复 + 只搬语义对得上的项） */
    async importLegacySettings() {
      const text = (this.stImportText || '').trim()
      if (!text) {
        uni.showToast({ title: '先把旧设置 JSON 贴进来', icon: 'none' })
        return
      }
      if (this.stImportBusy) return
      this.stImportBusy = true
      this.stImportNote = '迁移中…'
      this.stImportFixed = []
      this.stImportDropped = []
      try {
        const r = await dramaSettingsImport({ legacy: text })
        this.st = { ...this.st, ...(r.settings || {}) }
        this.stImportFixed = r.fixed || []
        this.stImportDropped = r.dropped || []
        const n = Object.keys(r.mapped || {}).length
        this.stImportNote = `搬过来 ${n} 项，修好 ${this.stImportFixed.length} 条`
      } catch (e) {
        this.stImportNote = e.message || '迁移失败，检查 JSON 格式'
      } finally {
        this.stImportBusy = false
      }
    },
    /** 当前项目已经存过合成设置时，全局默认不覆盖它（只影响没存过的项目） */
    applySettingsToCompose() {
      const saved = (this.cur && this.cur.compose && this.cur.compose.options) || null
      if (saved) return false
      if (this.st.caption_preset) this.comp.caption_preset = this.st.caption_preset
      if (this.st.render_preset) this.comp.render_preset = this.st.render_preset
      if (this.st.transition) this.comp.transition = this.st.transition
      if (this.st.bgm_volume != null) this.comp.bgm_volume = this.st.bgm_volume
      if (this.st.bgm_duck != null) this.comp.bgm_duck = this.st.bgm_duck
      return true
    },
    async saveSettings() {
      if (this.stBusy) return
      this.stBusy = true
      try {
        const patch = {
          caption_preset: this.st.caption_preset,
          render_preset: this.st.render_preset,
          transition: this.st.transition,
          bgm_volume: Number(this.st.bgm_volume),
          bgm_duck: !!this.st.bgm_duck,
          tts_voice: this.st.tts_voice,
          film_resolution: this.st.film_resolution,
          film_ratio: this.st.film_ratio,
          film_chain: this.st.film_chain,
          film_realism: this.st.film_realism,
        }
        const r = await dramaSettingsSave(patch)
        this.st = { ...this.st, ...(r.settings || {}) }
        this.stNote = `已保存（${(r.changed || []).length} 项）`
        this.applySettingsToCompose()
      } catch (e) {
        uni.showModal({ title: '保存失败', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.stBusy = false
      }
    },
    resetSettings() {
      if (this.stBusy) return
      uni.showModal({
        title: '恢复默认？',
        content: '只改全局默认值，项目里存过的合成设置不受影响。',
        success: async (res) => {
          if (!res.confirm) return
          this.stBusy = true
          try {
            const r = await dramaSettingsReset()
            this.st = { ...this.st, ...(r.settings || {}) }
            this.stNote = '已恢复默认'
            this.applySettingsToCompose()
          } catch (e) {
            uni.showModal({ title: '恢复失败', content: e.message || '请稍后重试', showCancel: false })
          } finally {
            this.stBusy = false
          }
        },
      })
    },
    onStVolume(e) {
      const raw = Number((e && e.detail && e.detail.value) || 0) / 100
      this.st.bgm_volume = Math.max(0.05, Math.min(0.4, Math.round(raw * 100) / 100))
    },

    /* ===== D7 风格配方：纯 JSON 合成设置，可导出分享、可导入 ===== */
    async toggleStyles() {
      this.spOpen = !this.spOpen
      if (this.spOpen && !this.spBuiltin.length) await this.loadStylePacks()
    },
    async loadStylePacks() {
      try {
        const r = await dramaStylePacks()
        this.spBuiltin = r.builtin || []
      } catch (e) {
        this.spNote = e.message || '配方表加载失败'
      }
    },
    async applyStylePack(pack) {
      if (!this.cur || this.spBusy) return
      this.spBusy = true
      try {
        const r = await dramaStylePackImport(this.cur.id, JSON.stringify(pack))
        this.spDropped = r.dropped || []
        this.spNote = `已套用：${r.pack.name}`
        await this.open(this.cur.id)
      } catch (e) {
        uni.showModal({ title: '套用失败', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.spBusy = false
      }
    },
    async exportStylePack() {
      if (!this.cur || this.spBusy) return
      this.spBusy = true
      try {
        const r = await dramaStylePackExport(this.cur.id)
        // #ifdef H5
        const blob = new Blob([r.text], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = r.file_name || 'style-pack.json'
        a.click()
        URL.revokeObjectURL(url)
        // #endif
        // #ifndef H5
        // 小程序没有浏览器下载：把配方原文塞进输入框（下面就是导入框），再复制一份
        this.spText = r.text
        uni.setClipboardData({ data: r.text })
        // #endif
        this.spNote = `已导出 ${r.file_name || '配方'}`
      } catch (e) {
        uni.showModal({ title: '导出失败', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.spBusy = false
      }
    },
    async importStylePack() {
      if (!this.cur || this.spBusy) return
      const text = (this.spText || '').trim()
      if (!text) {
        this.spNote = '先粘贴一份配方 JSON'
        return
      }
      this.spBusy = true
      try {
        const r = await dramaStylePackImport(this.cur.id, text)
        this.spDropped = r.dropped || []
        this.spNote = `已导入：${r.pack.name}`
        await this.open(this.cur.id)
      } catch (e) {
        this.spDropped = []
        uni.showModal({ title: '导入失败', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.spBusy = false
      }
    },

    /* ===== F8 结构自检：最近几条是不是同一个模板 ===== */
    async toggleHomogeneity() {
      this.hgOpen = !this.hgOpen
      if (this.hgOpen && !this.hg) await this.refreshHomogeneity()
    },
    async refreshHomogeneity() {
      if (this.hgBusy) return
      this.hgBusy = true
      try {
        this.hg = await dramaHomogeneity(8)
      } catch (e) {
        uni.showModal({ title: '自检失败', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.hgBusy = false
      }
    },

    async toggleProductLib() {
      this.plOpen = !this.plOpen
      if (this.plOpen) await this.refreshProducts()
    },
    async refreshProducts() {
      try {
        const r = await dramaProducts()
        this.plItems = r.products || []
      } catch (e) {
        this.plNote = e.message || '商品库加载失败'
      }
    },
    async saveCurrentProduct() {
      if (!this.cur || this.plBusy) return
      this.plBusy = true
      try {
        const r = await dramaProductSave(this.cur.id)
        this.plNote = `已存进商品库：${r.name}`
        await this.refreshProducts()
      } catch (e) {
        uni.showModal({ title: '存不进商品库', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.plBusy = false
      }
    },
    useProduct(item) {
      if (!this.cur || this.plBusy) return
      uni.showModal({
        title: '用这个商品卡？',
        content: `会用「${item.name}」覆盖当前项目的商品信息与商品图。`,
        success: async (res) => {
          if (!res.confirm) return
          this.plBusy = true
          try {
            const r = await dramaProductApply(item.id, this.cur.id)
            this.plNote = `已应用：${r.product.name}（${r.added_images} 张图）`
            await this.open(this.cur.id)
            await this.refreshProducts()
          } catch (e) {
            uni.showModal({ title: '应用失败', content: e.message || '请稍后重试', showCancel: false })
          } finally {
            this.plBusy = false
          }
        },
      })
    },
    removeProduct(item) {
      if (this.plBusy) return
      uni.showModal({
        title: '删掉这张商品卡？',
        content: '只删商品库里的这一份，项目里的商品图不受影响。',
        success: async (res) => {
          if (!res.confirm) return
          this.plBusy = true
          try {
            await dramaProductDelete(item.id)
            await this.refreshProducts()
          } catch (e) {
            uni.showModal({ title: '删除失败', content: e.message || '请稍后重试', showCancel: false })
          } finally {
            this.plBusy = false
          }
        },
      })
    },
    async toggleDub() {
      this.dubOpen = !this.dubOpen
      if (!this.dubOpen || !this.cur) return
      try {
        if (!this.dubLangs.length) {
          const r = await dramaDubLangs()
          this.dubLangs = r.langs || []
        }
        await this.refreshDubs()
      } catch (e) {
        this.dubNote = e.message || '语言表加载失败'
      }
    },
    async refreshDubs() {
      if (!this.cur) return
      const r = await dramaDubs(this.cur.id)
      this.dubs = r.dubs || []
      this.dubCanRestore = !!r.can_restore
    },
    onDubLang(e) {
      this.dubLangIndex = Number(e.detail.value || 0)
    },
    async runDub() {
      if (!this.cur || this.dubBusy) return
      const lang = (this.dubLangs[this.dubLangIndex] || {}).code
      if (!lang) {
        uni.showToast({ title: '先选目标语言', icon: 'none' })
        return
      }
      this.dubBusy = true
      this.dubNote = '译制中…'
      try {
        const r = await dramaDubStart(this.cur.id, { target_lang: lang })
        this.dubNote = `译好 ${r.summary.shots} 段 · 推荐音色 ${r.recommended_voice || '无'}`
        await this.refreshDubs()
      } catch (e) {
        this.dubNote = ''
        uni.showModal({ title: '译制失败', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.dubBusy = false
      }
    },
    async applyDub(d) {
      if (!this.cur || this.dubBusy) return
      this.dubBusy = true
      try {
        await dramaDubApply(this.cur.id, d.lang)
        uni.showToast({ title: `已应用${d.lang_name}`, icon: 'none' })
        await this.open(this.cur.id)
        await this.refreshDubs()
      } catch (e) {
        uni.showModal({ title: '应用失败', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.dubBusy = false
      }
    },
    async restoreDub() {
      if (!this.cur || this.dubBusy) return
      this.dubBusy = true
      try {
        await dramaDubRestore(this.cur.id)
        uni.showToast({ title: '已还原原文分镜', icon: 'none' })
        await this.open(this.cur.id)
        await this.refreshDubs()
      } catch (e) {
        uni.showModal({ title: '还原失败', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.dubBusy = false
      }
    },
    async toggleTts() {
      this.ttsOpen = !this.ttsOpen
      if (this.ttsOpen && !this.ttsVoices.length) {
        try {
          const r = await dramaTtsFreeVoices()
          this.ttsVoices = r.voices || []
          const i = this.ttsVoices.findIndex((v) => v.value === r.default)
          this.ttsVoiceIndex = i >= 0 ? i : 0
        } catch (e) {
          this.ttsHint = e.message || '音色表加载失败'
        }
      }
    },
    onTtsVoice(e) {
      this.ttsVoiceIndex = Number(e.detail.value || 0)
    },
    /** D3：读项目配音轨现状（几句、文件还在不在） */
    async loadVoice() {
      if (!this.cur) return
      try {
        const r = await dramaVoiceGet(this.cur.id)
        this.voiceLines = Number(r.lines || 0)
        const probs = r.problems || []
        this.voiceNote = probs.length ? (probs.length + ' 句配音文件不见了，重新生成一次') : ''
      } catch (e) {
        this.voiceLines = 0
      }
    },
    /** D3：整片配音（免费音色，逐句落盘）—— 由使用者点，不自动跑 */
    async buildVoiceTrack() {
      if (!this.cur || this.voiceBuilding) return
      const voice = (this.ttsVoices[this.ttsVoiceIndex] || {}).value || ''
      this.voiceBuilding = true
      this.voiceNote = '整片配音中…（逐句合成，句子多要等一会）'
      try {
        const doc = await dramaVoiceBuild(this.cur.id, { voice })
        this.cur = doc
        const n = (((doc.voice_track || {}).items) || []).length
        this.voiceLines = Number((doc.voice_track || {}).count || this.voiceLines)
        this.voiceNote = '已生成 ' + n + ' 句 —— 合成时按镜头槽位拼进成片'
      } catch (e) {
        this.voiceNote = e.message || '配音失败，请稍后重试'
      } finally {
        this.voiceBuilding = false
      }
    },
    /** D3：删掉配音轨登记 —— 合成退回模型原生出声（文件留在盘上，重生成会覆盖） */
    async dropVoiceTrack() {
      if (!this.cur || this.voiceBuilding) return
      this.voiceNote = '删除中…'
      try {
        this.cur = await dramaVoiceDelete(this.cur.id)
        this.voiceNote = '已删掉配音轨，合成会用模型原生声'
      } catch (e) {
        this.voiceNote = e.message || '删除失败'
      }
    },
    async ttsPreview() {
      const text = (this.ttsText || '').trim()
      if (!text) {
        uni.showToast({ title: '先输入要试听的台词', icon: 'none' })
        return
      }
      if (this.ttsBusy) return
      const voice = (this.ttsVoices[this.ttsVoiceIndex] || {}).value || ''
      this.ttsBusy = true
      this.ttsHint = '合成中…'
      try {
        const blob = await dramaTtsFreePreview({ text, voice })
        // #ifdef H5
        if (ttsAudioEl) {
          ttsAudioEl.pause()
          URL.revokeObjectURL(ttsAudioEl.src)
        }
        ttsAudioEl = new Audio(URL.createObjectURL(blob))
        ttsAudioEl.play()
        // #endif
        // #ifdef MP-WEIXIN
        // 小程序：ArrayBuffer 先写进缓存目录，InnerAudioContext 只能播文件路径
        const fs = wx.getFileSystemManager()
        const path = `${wx.env.USER_DATA_PATH}/tts-${Date.now()}.mp3`
        fs.writeFileSync(path, blob, 'binary')
        if (ttsAudioMp) ttsAudioMp.destroy()
        ttsAudioMp = wx.createInnerAudioContext()
        ttsAudioMp.src = path
        ttsAudioMp.play()
        // #endif
        this.ttsHint = '已合成，正在播放'
      } catch (e) {
        this.ttsHint = ''
        uni.showModal({ title: '试听失败', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.ttsBusy = false
      }
    },
    hasClipped(m) {
      return Object.keys(this.clipOut[m.id] || {}).length > 0
    },
    async exportTimeline(m, fmt) {
      if (!this.cur || this.tlBusy[m.id]) return
      this.tlBusy = { ...this.tlBusy, [m.id]: true }
      try {
        const r = await dramaMediaTimeline(this.cur.id, m.id, { format: fmt })
        // #ifdef H5
        const blob = new Blob([r.content], { type: r.mime_type || 'text/plain' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = r.file_name || `timeline.${fmt}`
        document.body.appendChild(a)
        a.click()
        a.remove()
        setTimeout(() => URL.revokeObjectURL(url), 1000)
        // #endif
        // #ifndef H5
        uni.setClipboardData({ data: r.content })
        // #endif
        uni.showToast({ title: '导出了 ' + r.clips + ' 段', icon: 'none' })
      } catch (e) {
        uni.showModal({ title: '导出失败', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.tlBusy = { ...this.tlBusy, [m.id]: false }
      }
    },
    async toggleTranscript(m) {
      const open = !this.trOpen[m.id]
      this.trOpen = { ...this.trOpen, [m.id]: open }
      if (open && !this.trText[m.id]) {
        try {
          const r = await dramaMediaTranscript(this.cur.id, m.id)
          const t = (r.transcript || {}).transcript || {}
          this.trText = { ...this.trText, [m.id]: t.text || '' }
        } catch (e) {
          uni.showToast({ title: '取转写失败', icon: 'none' })
        }
      }
    },

    // ---------- 第七批：素材库（B2）/ 授权清单（B5） ----------
    async loadMaterials() {
      if (!this.cur) return
      try {
        const r = await dramaMaterials(this.cur.id)
        this.pool = (r && r.materials) || []
      } catch (e) {
        this.pool = []
      }
    },
    humanSize(n) {
      const b = Number(n || 0)
      if (b >= 1024 * 1024) return `${(b / 1024 / 1024).toFixed(1)}MB`
      if (b >= 1024) return `${Math.round(b / 1024)}KB`
      return `${b}B`
    },
    materialMeta(m) {
      const bits = []
      if (m.width && m.height) bits.push(`${m.width}×${m.height}`)
      if (m.durationSec) bits.push(`${Number(m.durationSec).toFixed(1)}s`)
      bits.push(this.humanSize(m.size_bytes))
      if (m.license) bits.push(m.license)
      return bits.filter(Boolean).join(' · ')
    },
    pickMaterial() {
      if (!this.cur || this.poolBusy) return
      const up = async (filePath) => {
        if (!filePath) return
        this.poolBusy = 'upload'
        try {
          const r = await dramaMaterialUpload(this.cur.id, filePath)
          await this.loadMaterials()
          await this.loadShotMats()
          await this.loadShotClips()
          uni.showToast({
            title: (r && r.duplicate) ? '这份已经在库里了' : '已入库',
            icon: 'none',
          })
        } catch (e) {
          uni.showModal({ title: '上传失败', content: e.message || '请稍后重试', showCancel: false })
        } finally {
          this.poolBusy = ''
        }
      }
      // #ifdef H5
      uni.chooseFile({
        count: 1,
        extension: ['.mp4', '.webm', '.mov', '.m4v', '.jpg', '.jpeg', '.png', '.webp'],
        success: (r) => up(((r && r.tempFilePaths) || [])[0]),
      })
      // #endif
      // #ifndef H5
      // 小程序：从聊天记录选文件（视频/图片都给），上传本身走 uni.uploadFile
      uni.chooseMessageFile({
        count: 1,
        type: 'all',
        success: (r) => up((((r && r.tempFiles) || [])[0] || {}).path),
      })
      // #endif
    },
    openMaterial(m) {
      this.poolEdit = {
        open: true,
        row: m,
        name: m.original_name || '',
        tags: (m.tags || []).join(', '),
        author: m.author || '',
        license: m.license || '',
        sourceUrl: m.source_url || '',
      }
    },
    async saveMaterial() {
      const e = this.poolEdit
      if (!this.cur || !e.row || this.poolBusy) return
      this.poolBusy = 'save'
      try {
        const tags = (e.tags || '').split(',').map((t) => t.trim()).filter(Boolean)
        await dramaMaterialPatch(this.cur.id, e.row.name, {
          original_name: e.name.trim(),
          tags,
          author: e.author.trim(),
          license: e.license.trim(),
          source_url: e.sourceUrl.trim(),
        })
        e.open = false
        await this.loadMaterials()
        await this.loadShotMats()
        await this.loadShotClips()
        this.credits = null
        uni.showToast({ title: '已保存', icon: 'none' })
      } catch (err) {
        uni.showModal({ title: '保存失败', content: err.message || '', showCancel: false })
      } finally {
        this.poolBusy = ''
      }
    },
    async removeMaterial(m) {
      if (!this.cur || this.poolBusy) return
      const go = await new Promise((res) => uni.showModal({
        title: '删掉这份素材？',
        content: m.original_name || m.name,
        success: (x) => res(x.confirm),
        fail: () => res(false),
      }))
      if (!go) return
      this.poolBusy = 'del'
      try {
        await dramaMaterialDelete(this.cur.id, m.name)
        await this.loadMaterials()
        // 删掉的素材若还被某镜当参考画面，绑定必须一起撤（否则出片时会报「画面不在了」）
        if ((this.shotMats || []).some((x) => x.material === m.name)) {
          await this.putShotMats((this.shotMats || [])
            .filter((x) => x.material !== m.name)
            .map((x) => ({ shot_id: x.shot_id, material: x.material })))
        }
        await this.loadShotMats()
        // 画面素材（视频）同理：删了就必须解除绑定，否则合成时会报「素材不在了」
        if ((this.clipItems || []).some((x) => x.material === m.name)) {
          await this.putClips((this.clipItems || [])
            .filter((x) => x.material !== m.name)
            .map((x) => ({ shot_id: x.shot_id, material: x.material })))
        }
        await this.loadShotClips()
        this.credits = null
      } catch (e) {
        uni.showToast({ title: e.message || '删除失败', icon: 'none' })
      } finally {
        this.poolBusy = ''
      }
    },
    async loadCredits() {
      if (!this.cur || this.busy) return
      try {
        const r = await dramaCredits(this.cur.id)
        this.credits = (r && r.manifest) || null
      } catch (e) {
        uni.showModal({ title: '清单没生成', content: e.message || '', showCancel: false })
      }
    },
    async copyCredits() {
      if (!this.cur) return
      try {
        const md = await dramaCredits(this.cur.id, 'md')
        uni.setClipboardData({ data: md, success: () => uni.showToast({ title: '已复制', icon: 'none' }) })
      } catch (e) {
        uni.showToast({ title: '复制失败', icon: 'none' })
      }
    },
    pickCatTpl(name) {
      this.catTpl = this.catTpl === name ? '' : name
    },
    /** A8：手写稿 → 一句一镜，直接出分镜（不调模型、不花钱） */
    async submitImport() {
      if (!this.cur || this.busy) return
      const text = (this.importText || '').trim()
      if (text.length < 2) {
        uni.showToast({ title: '先贴一段口播稿', icon: 'none' })
        return
      }
      this.busy = 'import-script'
      try {
        const r = await dramaImportScript(this.cur.id, {
          script: text, title: (this.importTitle || '').trim(),
        })
        this.cur = r.project
        this.importOpen = false
        this.importText = ''
        this.importTitle = ''
        await this.loadScripts()
        uni.showToast({ title: '已切成 ' + r.count + ' 镜', icon: 'none' })
      } catch (e) {
        uni.showModal({ title: '导入失败', content: e.message || '', showCancel: false })
      } finally {
        this.busy = ''
      }
    },
    /** C16：出片前的能力预检（纯计算，不花钱） */
    async runPreflight() {
      if (!this.cur) return
      const seg = ((this.plan || {}).segments || [])[0] || {}
      const refCount = Number(seg.ref_count || 0)
      try {
        this.preflight = await dramaPreflight({
          model: this.filmModel || this.opt.default_film_model || '',
          duration: Number(seg.seconds || 0) || Number(this.totalSeconds || 0) || null,
          resolution: this.filmResolution || '720p',
          aspect_ratio: this.filmRatio || '9:16',
          chain_mode: this.chain,
          reference_image_count: refCount,
        })
      } catch (e) {
        this.preflight = null
      }
    },
    /** C9：换接缝档 → 预检 + 重新规划（规划不花钱，但指纹会变，必须重看一遍） */
    async pickChain(mode) {
      if (this.busy || this.chain === mode) return
      this.chain = mode
      await this.runPreflight()
      if (this.cur && (this.cur.storyboard_json || {}).shots) await this.filmPlan()
    },
    /** C12：换真实感档 → 重新规划（提示词变了，确认卡必须重看一遍；不花钱） */
    async pickRealism(mode) {
      if (this.busy || this.realism === mode) return
      this.realism = mode
      if (this.cur && (this.cur.storyboard_json || {}).shots) await this.filmPlan()
    },
    /** C15：变体计划（不合成） */
    async variantPlan() {
      if (!this.cur || this.variant.busy) return
      this.variant.busy = 'plan'
      try {
        const p = await dramaVariantsPlan(this.cur.id, {
          count: Number(this.variant.count) || 3,
          seed: Number(this.variant.seed) || 1,
        })
        this.variant = { ...this.variant, plan: p, open: true }
      } catch (e) {
        uni.showModal({ title: '变体计划失败', content: e.message || '', showCancel: false })
      } finally {
        this.variant.busy = ''
      }
    },
    /** C15：按计划逐条合成（本地 ffmpeg，零生成费；每条都要跑一遍渲染） */
    async variantRender() {
      if (!this.cur || this.variant.busy) return
      const n = ((this.variant.plan || {}).slots || []).length
      if (!n) {
        uni.showToast({ title: '先出计划', icon: 'none' })
        return
      }
      const ok = await new Promise((res) => uni.showModal({
        title: '合成 ' + n + ' 条变体？',
        content: '本地 ffmpeg 逐条渲染，不花生成费，但会占一段时间。主合成那一条不会被覆盖。',
        success: (x) => res(x.confirm),
        fail: () => res(false),
      }))
      if (!ok) return
      this.variant.busy = 'render'
      try {
        const goal = this.variant.plan ? this.variant.plan : null
        const d = await dramaVariantsRender(this.cur.id, {
          count: goal ? goal.count : this.variant.count,
          seed: goal ? goal.seed : this.variant.seed,
        })
        this.cur = d.project
        this.variant.rows = d.variants || []
        uni.showToast({ title: '变体已合成', icon: 'none' })
      } catch (e) {
        uni.showModal({ title: '变体合成失败', content: e.message || '', showCancel: false })
      } finally {
        this.variant.busy = ''
      }
    },
    openVariant(idx) {
      if (!this.cur) return
      this.openUrl(dramaVariantUrl(this.cur.id, idx))
    },
    // ---------- A6 话题起片 ----------
    async loadTopicOptions() {
      try {
        this.topic.opt = await dramaTopicOptions()
      } catch (e) {
        console.warn('[drama] 话题选项读取失败', e.message)
      }
    },
    openTopic() {
      this.creating = false
      this.topic.open = true
      if (!(this.topic.opt.styles || []).length) this.loadTopicOptions()
    },
    async createTopic() {
      const topic = (this.topic.topic || '').trim()
      if (topic.length < 2) {
        uni.showToast({ title: '先写一句话主题', icon: 'none' })
        return
      }
      if (this.topic.busy) return
      this.topic.busy = true
      try {
        const r = await dramaTopicCreate({
          topic,
          narration_style: this.topic.style,
          duration: this.topic.duration,
          count: this.topic.count,
        })
        this.topic.open = false
        this.topic.topic = ''
        await this.loadList()
        this.cur = r.project
        this.variant = { ...this.variant, plan: null, rows: [] }
        await this.loadScripts()
      } catch (e) {
        uni.showModal({ title: '起片失败', content: e.message || '', showCancel: false })
      } finally {
        this.topic.busy = false
      }
    },
    async gen(stage) {
      if (!this.cur || this.busy) return
      this.busy = stage
      try {
        this.cur = await dramaGenerate(this.cur.id, stage)
        if (stage === 'script') await this.loadScripts()
        await this.loadList()
      } catch (e) {
        // 🩸 生成失败必须停住给人看完（2026-11-08）：分镜被校验拦下时后端会带
        // 具体原因（「缺哪几句台词」「超了多少秒」），用 toast 一闪就看不见，
        // 人会以为「点了没反应、台词还是老的」。
        uni.showModal({
          title: stage === 'storyboard' ? '分镜没通过校验' : '生成失败',
          content: e.message || '请稍后重试',
          showCancel: false,
        })
      } finally {
        this.busy = ''
      }
    },
    async confirmCard() {
      if (!this.cur || this.busy) return
      this.busy = 'confirm'
      try {
        this.cur = await dramaConfirm(this.cur.id)
        await this.loadList()
      } catch (e) {
        uni.showToast({ title: e.message || '确认失败', icon: 'none' })
      } finally {
        this.busy = ''
      }
    },
    async resetAll() {
      if (!this.cur || this.busy) return
      const r = await new Promise((res) =>
        uni.showModal({
          title: '清空重来',
          content: '结构卡、剧本、分镜、自检都会被清掉，商品信息保留。',
          success: (x) => res(x.confirm),
          fail: () => res(false),
        })
      )
      if (!r) return
      this.busy = 'reset'
      try {
        this.cur = await dramaReset(this.cur.id, 'card')
        await this.loadList()
      } catch (e) {
        uni.showToast({ title: e.message || '重置失败', icon: 'none' })
      } finally {
        this.busy = ''
      }
    },
    judgeName(j) {
      return { pace: '节奏', voice: '口语', idea: '创意', structure: '结构', visual: '画面' }[j] || j
    },
    tierLabel(t) {
      return { invariant: '必须改', default: '建议改', taste: '参考' }[t] || t
    },
    fieldLabel(f) {
      return {
        dialogue: '台词', description: '画面', duration: '时长',
        framing: '景别', product: '商品', structure: '结构',
      }[f] || f
    },
    scoreCls(s) {
      return s >= 4 ? 'good' : s >= 3 ? 'mid' : 'low'
    },
    async runJudge() {
      if (!this.cur || this.busy) return
      this.busy = 'judge'
      this.applyLog = []            // 重新审稿 = 上一轮的应用记录过期了
      try {
        this.cur = await dramaJudge(this.cur.id)
        await this.loadList()
      } catch (e) {
        uni.showToast({ title: e.message || '审稿失败', icon: 'none', duration: 3000 })
      } finally {
        this.busy = ''
      }
    },
    async applyIssue(it) {
      if (!this.cur || this.busy) return
      await this.doApply([`${it.shot_id}:${it.field}`])
    },
    async applyAll() {
      if (!this.cur || this.busy) return
      await this.doApply([])
    },
    async doApply(keys) {
      this.busy = 'apply'
      try {
        // 改之前先留一份分镜，应用完逐格比 —— 不然只弹一句「已应用 N 条」，
        // 人根本看不出改了哪儿（2026-11-08 主人原话：「我不知道到底有没有改变啊」）
        const before = ((this.cur && this.cur.storyboard_json) || {}).shots || []
        const res = await dramaJudgeApply(this.cur.id, keys)
        const after = ((res.doc || {}).storyboard_json || {}).shots || []
        const oldById = {}
        before.forEach((s) => { oldById[String(s.id)] = s })
        const diff = []
        after.forEach((s) => {
          const old = oldById[String(s.id)]
          if (!old) return
          ;['dialogue', 'description', 'framing'].forEach((f) => {
            const a = String(old[f] || '')
            const b = String(s[f] || '')
            if (a !== b) diff.push({ shot: s.id, field: f, from: a, to: b })
          })
        })
        this.applyLog = diff
        this.cur = res.doc
        await this.loadList()
        const n = (res.applied || []).length
        const skip = (res.skipped || []).length
        if (!diff.length) {
          uni.showToast({
            title: n ? `已应用 ${n} 条` : `没有可应用的（跳过 ${skip}）`,
            icon: 'none',
            duration: 3000,
          })
          return
        }
        // 逐条摆出来：镜几、哪一格、从什么变成什么
        const lines = diff.slice(0, 6).map((d) =>
          `镜 ${d.shot} ${this.fieldLabel(d.field)}：${d.from || '（空）'} → ${d.to || '（空）'}`)
        if (diff.length > 6) lines.push(`…还有 ${diff.length - 6} 处，往下滑看分镜`)
        uni.showModal({
          title: `改了 ${diff.length} 处` + (skip ? `（跳过 ${skip}）` : ''),
          content: lines.join('\n'),
          showCancel: false,
        })
      } catch (e) {
        uni.showModal({
          title: '应用失败',
          content: e.message || '改完不合格，已丢弃',
          showCancel: false,
        })
      } finally {
        this.busy = ''
      }
    },
    cellUrl(idx, board = 1) {
      return this.cur ? dramaGridCellUrl(this.cur.id, idx, board) : ''
    },
    async planGrid() {
      if (!this.cur || this.busy) return
      this.busy = 'grid-plan'
      try {
        this.cur = await dramaGridPlan(this.cur.id)
        await this.loadList()
        // 规划 ≠ 出图：这一步免费、也不会有图。不说清楚人会以为点了没反应（2026-11-08）
        const nb = (this.cur.grid && (this.cur.grid.boards || []).length) || 1
        uni.showToast({
          title: this.cur.grid
            ? (nb > 1
              ? `规划好了（没花钱）：这部片子要 ${nb} 块板，每段一块。往下滑一块一块出图，出图才扣费`
              : '规划好了（没花钱）。往下滑看九宫格，点「出九宫格图」才扣费')
            : '规划好了，但没拿到可用结果',
          icon: 'none',
          duration: 4000,
        })
      } catch (e) {
        uni.showModal({
          title: '规划失败',
          content: e.message || '模型没给出可用规划',
          showCancel: false,
        })
      } finally {
        this.busy = ''
      }
    },
    async renderGrid(board = 1) {
      if (!this.cur || this.busy) return
      // 还有角色没定妆 → 先问，不要闷头花钱出一块「一镜一个样」的板（2026-11-08）
      if (!this.castSkip && (this.castMissing || []).length) {
        const miss = this.castMissing
        const goCast = await new Promise((res) =>
          uni.showModal({
            title: `还有 ${miss.length} 个角色没定妆`,
            content: `${miss.join('、')} 还没有参考图。现在出板，这几位的长相只能靠文字，`
              + '九格和整片容易一镜一个样。要先去定妆吗？',
            confirmText: '先去定妆',
            cancelText: '仍要出板',
            success: (x) => res(x.confirm),
            fail: () => res(false),
          })
        )
        if (goCast) {
          this.goPresenters()
          return
        }
        this.castSkip = true   // 本页不再拦；换页/刷新会再问一次
      }
      // 九宫格是付费出图，禁改词还在就别去花钱（后端会再拦一次）
      if (this.gridBibleFails.length) {
        uni.showModal({
          title: '视觉记忆拦住了',
          content: `禁改词「${this.gridBibleFails[0].anchor}」还在这版九宫格提示词里。先改锚点或重新规划。`,
          showCancel: false,
        })
        return
      }
      const go = await new Promise((res) =>
        uni.showModal({
          title: '出九宫格图',
          content: '这一步会消耗额度生成一张图。确定现在出吗？',
          confirmText: '出图',
          success: (x) => res(x.confirm),
          fail: () => res(false),
        })
      )
      if (!go) return
      this.busy = 'grid-render'
      let done = false
      try {
        this.cur = await dramaGridRender(this.cur.id, board)
        done = true
        await this.loadList()
      } catch (e) {
        uni.showModal({
          title: '出图失败',
          content: e.message || '请稍后重试',
          showCancel: false,
        })
      } finally {
        this.busy = ''
      }
      // 新板 = 出片提示词里的板占 @图片1、后面参考图编号全挪一位 → 上一版计划作废，
      // 重算一版（规划不花钱），别让人拿着旧计划去点出片然后被指纹拦下
      if (done && ((this.cur.storyboard_json || {}).shots || []).length) await this.filmPlan()
    },
    modelLabel(id) {
      const m = (this.opt.film_models || []).find((x) => x.id === id)
      return m ? m.label : (id || '')
    },
    preflightWarnName(code) {
      return ({
        'capabilities-unknown': '型号不在目录里，能力按兜底档推定，可能被接口拒',
        'native-audio-unavailable': '这个型号不出原生音轨',
        'reference-images-trimmed': '参考图超过型号上限，多出来的会被截掉',
        'reference-conditioning-unavailable': '这个型号不吃参考图',
        'reference-audio-unavailable': '这个型号不吃参考音频',
      })[code] || code
    },
    /** C16：改写项里的字段名与原因都用中文，别把内部代码甩给用户 */
    preflightFieldName(field) {
      return ({
        duration: '时长', resolution: '分辨率', aspectRatio: '画幅', chainMode: '接缝',
      })[field] || field
    },
    preflightAdjustName(code) {
      return ({
        'clamped-duration': '不在本型号可出时长内，已收到最近的档',
        'mapped-resolution': '本型号没有这一档，已换成最接近的可用档',
        'adaptive-ratio': '已换成最接近的画幅',
        'unsupported-last-frame': '本型号没有尾帧通道，接缝退回关闭',
      })[code] || code
    },
    /** 当前型号吃得下的清晰度档（模型能力表 `/options` 的 `film_models[].resolutions`） */
    syncResRows() {
      const m = (this.opt.film_models || []).find((x) => x.id === this.filmModel) || {}
      const rows = (m.resolutions || []).map((r) => ({ id: r, label: String(r).toUpperCase() }))
      this.resRows = rows
      // 换到低档型号时，原来选的 1080p/4k 它吃不下 → 落到该型号的默认档
      if (rows.length && !rows.some((r) => r.id === this.filmResolution)) {
        this.filmResolution = m.default_resolution || rows[0].id
      }
    },
    /** 换清晰度：规划是纯计算（不花钱），但指纹会变 → 必须重新规划重看一遍 */
    async pickResolution(v) {
      if (!this.cur || this.busy || this.filmResolution === v) return
      this.filmResolution = v
      if ((this.cur.storyboard_json || {}).shots) await this.filmPlan()
    },
    /** 换画面比例：同上，重新规划（提示词里的画幅句也会跟着改） */
    async pickRatio(v) {
      if (!this.cur || this.busy || this.filmRatio === v) return
      this.filmRatio = v
      if ((this.cur.storyboard_json || {}).shots) await this.filmPlan()
    },
    /** 换型号：规划是纯计算（不花钱），换了直接重算一版给人看 */
    async pickModel(m) {
      if (!this.cur || this.busy || this.filmModel === m.id) return
      this.filmModel = m.id
      this.syncResRows()
      if ((this.cur.storyboard_json || {}).shots) await this.filmPlan()
      await this.runPreflight()
    },
    async filmPlan() {
      if (!this.cur || this.busy) return
      this.busy = 'film-plan'
      try {
        this.cur = await dramaFilmPlan(this.cur.id, this.filmModel, this.chain, this.realism,
                                       this.filmResolution, this.filmRatio)
        this.syncBible()
        await this.runPreflight()
        // 规划 ≠ 出片：这一步免费、不出视频。往下滑就是计划卡，点「确认，开始出片」才扣费
        const p = this.plan || {}
        const segs = (p.segments || []).length
        uni.showToast({
          title: segs
            ? `算好了（没花钱）：${segs} 段 / ${p.total_seconds || 0} 秒。往下滑到「出片计划」确认出片`
            : '规划完成，但没有可出的段，往下滑看提示',
          icon: 'none',
          duration: 4500,
        })
      } catch (e) {
        uni.showModal({ title: '规划失败', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.busy = ''
      }
    },
    async filmRender(no) {
      if (!this.cur || this.busy) return
      // 确认卡锁的是**这一版计划的指纹**：后端拿现在的文档重算，对不上就不提交
      if (!this.plan || !this.plan.plan_hash) {
        uni.showToast({ title: '先规划出片，看过提示词再出', icon: 'none' })
        return
      }
      // 一致性硬闸（后端也会再拦一次）：禁改词还在，就别去花钱
      if (this.bibleFails.length) {
        uni.showModal({
          title: '视觉记忆拦住了',
          content: `禁改词「${this.bibleFails[0].anchor}」还在这版提示词里。先改提示词或改锚点，再出片。`,
          showCancel: false,
        })
        return
      }
      const s = ((this.plan && this.plan.segments) || []).find((x) => x.no === no) || {}
      const refs = (s.prod_count || 0) + (s.board ? 1 : 0) + (s.cast_count || 0)
      const dense = (this.plan.dialogue_warnings || []).length
      const content = [
        `${this.modelLabel(this.plan.model)}｜${s.seconds || '?'} 秒｜${refs} 张参考图`,
        `花费：${this.priceText}`,
        dense ? `台词偏挤：${dense} 个镜头念不完（见下方红字）` : '',
        '下面那份提示词就是要发出去的那一版，确认后真扣费。',
      ].filter(Boolean).join('\n')
      const go = await new Promise((res) =>
        uni.showModal({
          title: `确认出第 ${no} 段`,
          content,
          confirmText: '确认出片',
          success: (x) => res(x.confirm),
          fail: () => res(false),
        })
      )
      if (!go) return
      this.busy = 'film-render' + no
      try {
        this.cur = await dramaFilmRender(this.cur.id, no, this.filmResolution, this.plan.plan_hash)
      } catch (e) {
        const msg = e.message || '请稍后重试'
        if (msg.indexOf('计划和你看的那一版不一样了') >= 0) {
          this.busy = ''
          await this.filmStaleReplan()
          return
        }
        uni.showModal({ title: `第 ${no} 段出片失败`, content: msg, showCancel: false })
      } finally {
        this.busy = ''
      }
    },
    /** 出片被指纹拦下 = 计划过期，不是出错：自动重算一版（免费），再让人确认一次。 */
    async filmStaleReplan() {
      await this.filmPlan()
      uni.showModal({
        title: '计划已按现在的分镜重算（没花钱）',
        content: '分镜 / 分镜板 / 参考图改过 —— 出片提示词和参考图编号都变了，'
          + '旧确认不能再付这一版的钱。往下滑看一眼新的出片计划，确认后才会真扣费。',
        showCancel: false,
      })
    },
    filmFile(no) {
      const f = (this.cur && this.cur.film && this.cur.film.files) || {}
      return f[no] && f[no].name ? dramaFilmUrl(this.cur.id, no) : ''
    },
    filmErr(no) {
      const f = (this.cur && this.cur.film && this.cur.film.files) || {}
      return (f[no] && f[no].error) || ''
    },
    filmEntry(no) {
      const f = (this.cur && this.cur.film && this.cur.film.files) || {}
      return f[String(no)] || {}
    },
    /* ===== 7 维质量评分（建议，不是自动处置） ===== */
    verdictLabel(v) {
      return { accept: '可以用', review: '得人看', reject: '不能用' }[v] || ''
    },
    /* ===== 成片体检（本地 ffmpeg，零费用） ===== */
    techEntry(target) {
      const t = (this.cur && this.cur.film && this.cur.film.tech_qc) || {}
      return t[String(target)] || null
    },
    techLabel(level) {
      return { ok: '可以发', warn: '有提醒', fail: '别发' }[level] || ''
    },
    techLevelMark(level) {
      return { ok: '✓', warn: '!', fail: '✗' }[level] || ''
    },
    techCheckName(id) {
      return {
        'video-stream': '视频流',
        'audio-stream': '音频流',
        duration: '时长',
        resolution: '分辨率',
        black: '黑屏',
        silence: '静音',
        loudness: '响度',
        'true-peak': '峰值',
        freeze: '定格',
      }[id] || id
    },
    async techRun(target) {
      if (!this.cur || this.busy) return
      this.busy = 'tech' + target
      try {
        this.cur = await dramaFilmQc(this.cur.id, target)
      } catch (e) {
        uni.showModal({
          title: '体检没跑成',
          content: e.message || '请稍后重试',
          showCancel: false,
        })
      } finally {
        this.busy = ''
      }
    },
    async qualityRun(no) {
      if (!this.cur || this.busy) return
      const go = await new Promise((res) =>
        uni.showModal({
          title: `评第 ${no} 段`,
          content: '会抽 6 帧发给视觉模型打 7 个维度的分，费很小但不是 0。'
            + '\n评分只给建议：换型号、重出都要你再点一次。',
          confirmText: '开始评',
          success: (x) => res(x.confirm),
          fail: () => res(false),
        })
      )
      if (!go) return
      this.busy = 'qc' + no
      try {
        this.cur = await dramaFilmQuality(this.cur.id, no)
      } catch (e) {
        uni.showModal({
          title: `第 ${no} 段评分失败`,
          content: e.message || '请稍后重试',
          showCancel: false,
        })
      } finally {
        this.busy = ''
      }
    },
    qualityAct(no, a) {
      if (this.busy || !a) return
      // 花钱的两条不替他执行：重出走现有的确认卡，换型号让人自己挑
      if (a.key === 'regenerate') {
        this.filmRender(no)
        return
      }
      const text = {
        accept: '这条可以用，不用再花钱。',
        review: '机器判不了：点「看这段」自己看一眼，再决定要不要重出。',
        local_fix: '画面本身可用，只是文字要修：字幕/包装文字在后期单独处理，不用重出。',
        switch_model: '在上面的「出片型号」里挑另一个，点「重新规划」，看过提示词再出片。',
      }[a.key] || a.why
      uni.showModal({ title: a.label, content: text, showCancel: false })
    },
    openRepair(no) {
      if (this.busy) return
      this.repair = { no, start: '', end: '', note: '', plan: null }
    },
    async repairPreview(no) {
      if (!this.cur || this.busy) return
      this.busy = 'repair-plan'
      try {
        this.repair.plan = await dramaRepairPlan(
          this.cur.id, no,
          Number(this.repair.start || 0), Number(this.repair.end || 0),
          (this.repair.note || '').trim())
      } catch (e) {
        uni.showModal({ title: '修复预演失败', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.busy = ''
      }
    },
    async repairRender(no) {
      const p = this.repair.plan
      if (!this.cur || this.busy || !p || !p.plan_hash) return
      const rf = (p.bible_issues || []).filter((i) => i.severity === 'fail')
      if (rf.length) {
        uni.showModal({
          title: '视觉记忆拦住了',
          content: `禁改词「${rf[0].anchor}」还在这版修复提示词里。先改说明或改锚点。`,
          showCancel: false,
        })
        return
      }
      const go = await new Promise((res) =>
        uni.showModal({
          title: `确认修第 ${no} 段`,
          content: `替换 ${p.window.start}–${p.window.end}s，模型生成 ${p.generated_seconds}s\n`
            + `花费：${this.repairPriceText}\n原片保留，修完能切回。`,
          confirmText: '确认修复',
          success: (x) => res(x.confirm),
          fail: () => res(false),
        })
      )
      if (!go) return
      this.busy = 'repair-render' + no
      try {
        this.cur = await dramaRepairRender(
          this.cur.id, no, p.plan_hash,
          Number(this.repair.start || 0), Number(this.repair.end || 0),
          (this.repair.note || '').trim())
        this.repair = { no: 0, start: '', end: '', note: '', plan: null }
      } catch (e) {
        uni.showModal({ title: `第 ${no} 段修复失败`, content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.busy = ''
      }
    },
    async repairRevert(no) {
      if (!this.cur || this.busy) return
      const go = await new Promise((res) =>
        uni.showModal({
          title: `切回第 ${no} 段原版`,
          content: '只把指针换回修复前的文件，不删除、不花钱。',
          confirmText: '切回',
          success: (x) => res(x.confirm),
          fail: () => res(false),
        })
      )
      if (!go) return
      this.busy = 'repair-revert' + no
      try {
        this.cur = await dramaRepairRevert(this.cur.id, no)
      } catch (e) {
        uni.showModal({ title: '切回失败', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.busy = ''
      }
    },
    openFilm(no) {
      if (!this.cur) return
      this.previewFile(dramaFilmUrl(this.cur.id, no), `镜头${no}.mp4`, 'video')
    },
    async filmConcat() {
      if (!this.cur || this.busy) return
      this.busy = 'film-concat'
      try {
        this.cur = await dramaFilmConcat(this.cur.id)
        uni.showToast({ title: '已拼成整片', icon: 'success' })
      } catch (e) {
        uni.showModal({ title: '拼接失败', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.busy = ''
      }
    },

    /* ===== 合成（D 批）：本地 ffmpeg，零生成费 =====
       出片（花钱）仍然只走 filmRender；这里只加工**已经出好的段**。 */
    async loadComposeOptions() {
      try {
        // 🩸 服务端回 data:null 时不能把默认值覆盖成 null，否则合成面板模板直接崩
        const r = await dramaComposeOptions()
        if (!r || typeof r !== 'object') return
        this.compOpt = r
        const d = this.compOpt.defaults || {}
        if (d.transition) this.comp.transition = d.transition
        if (d.render_preset) this.comp.render_preset = d.render_preset
        if (d.caption_preset) this.comp.caption_preset = d.caption_preset
        this.comp.bgm_volume = d.bgm_volume != null ? d.bgm_volume : this.comp.bgm_volume
      } catch (e) {
        // 选项拉不到不挡主流程；后端仍会给默认值
      }
    },
    /** 把项目里存过的合成设置读回表单（没存过就保持默认） */
    syncComp() {
      const saved = (this.cur && this.cur.compose && this.cur.compose.options) || null
      if (saved) {
        const end = saved.end_card || {}
        this.comp = {
          ...this.comp,
          transition: saved.transition || this.comp.transition,
          render_preset: saved.render_preset || this.comp.render_preset,
          captions: saved.captions !== false,
          caption_preset: saved.caption_preset || this.comp.caption_preset,
          bgm_volume: saved.bgm_volume != null ? saved.bgm_volume : this.comp.bgm_volume,
          bgm_duck: saved.bgm_duck !== false,
          bgm_fade_out: saved.bgm_fade_out != null ? saved.bgm_fade_out : this.comp.bgm_fade_out,
          bgm_intro_skip: saved.bgm_intro_skip != null ? saved.bgm_intro_skip : 0,
          end_card: end.enabled === true,
          end_card_text: end.text || '',
          end_card_seconds: end.seconds || 3,
          end_card_image: end.image || '',
          end_card_qr_ratio: end.qr_ratio || 0.34,
          voice_ground: saved.voice_ground !== false,
        }
      }
      const bgm = (this.cur && this.cur.compose && this.cur.compose.bgm) || null
      if (bgm && bgm.volume != null) this.comp.bgm_volume = bgm.volume
    },
    capLabel(id) {
      return { standard: '标准', bold: '重击大字', minimal: '极简', karaoke: '卡拉OK逐字' }[id] || id
    },
    onBgmVolume(e) {
      const v = Number((e && e.detail && e.detail.value) || 0) / 100
      this.comp.bgm_volume = Math.max(0.05, Math.min(0.4, Math.round(v * 100) / 100))
    },
    compPayload() {
      return {
        transition: this.comp.transition,
        render_preset: this.comp.render_preset,
        captions: !!this.comp.captions,
        caption_preset: this.comp.caption_preset,
        bgm_volume: Number(this.comp.bgm_volume),
        bgm_duck: !!this.comp.bgm_duck,
        bgm_fade_out: Number(this.comp.bgm_fade_out),
        bgm_intro_skip: Number(this.comp.bgm_intro_skip),
        end_card: !!this.comp.end_card,
        end_card_text: this.comp.end_card_text || '',
        end_card_seconds: Number(this.comp.end_card_seconds),
        end_card_image: this.comp.end_card_image || '',
        end_card_qr_ratio: Number(this.comp.end_card_qr_ratio),
        // D3：人声落地开关（关掉 = 干声老形状，指纹也跟着变）
        voice_ground: !!this.comp.voice_ground,
        // 有规划过就带上指纹：设置/片段变了后端会拒，不会产出和确认卡不一样的片
        plan_hash: (this.compPlan && this.compPlan.plan_hash) || '',
      }
    },
    async composePlan() {
      if (!this.cur || this.busy) return
      this.busy = 'comp-plan'
      try {
        this.cur = await dramaComposePlan(this.cur.id, { ...this.compPayload(), plan_hash: '' })
      } catch (e) {
        uni.showModal({ title: '合成规划失败', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.busy = ''
      }
    },
    async composeRun() {
      if (!this.cur || this.busy) return
      if (!this.compPlan) {
        uni.showToast({ title: '先规划一次，看清会做成什么样', icon: 'none' })
        return
      }
      const p = this.compPlan
      const go = await new Promise((res) =>
        uni.showModal({
          title: '合成整片',
          content: `本地 ffmpeg，不花生成费。${p.total_seconds} 秒 / ${p.segments.length} 段 / `
            + `转场「${(p.transition || {}).label || ''}」/ ${(p.render || {}).label || ''}档。`
            + '合成会新出一个文件，不覆盖已有的段。',
          confirmText: '开始合成',
          success: (x) => res(x.confirm),
          fail: () => res(false),
        })
      )
      if (!go) return
      this.busy = 'comp-run'
      try {
        this.cur = await dramaComposeRun(this.cur.id, this.compPayload())
        uni.showToast({ title: '已合成', icon: 'success' })
      } catch (e) {
        uni.showModal({ title: '合成失败', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.busy = ''
      }
    },
    pickBgm() {
      if (!this.cur || this.busy) return
      const up = async (filePath) => {
        if (!filePath) return
        this.busy = 'bgm'
        try {
          this.cur = await dramaBgmUpload(this.cur.id, filePath)
          uni.showToast({ title: 'BGM 已上传', icon: 'success' })
        } catch (e) {
          uni.showModal({ title: '上传失败', content: e.message || '请稍后重试', showCancel: false })
        } finally {
          this.busy = ''
        }
      }
      // #ifdef H5
      uni.chooseFile({
        count: 1,
        extension: ['.mp3', '.wav', '.aac', '.m4a'],
        success: (r) => up(((r && r.tempFilePaths) || [])[0]),
      })
      // #endif
      // #ifndef H5
      uni.chooseMessageFile({
        count: 1,
        type: 'file',
        extension: ['mp3', 'wav', 'aac', 'm4a'],
        success: (r) => up((((r && r.tempFiles) || [])[0] || {}).path),
      })
      // #endif
    },
    async dropBgm() {
      if (!this.cur || this.busy) return
      const go = await new Promise((res) =>
        uni.showModal({
          title: '删掉这条 BGM',
          content: '删掉后合成不再混背景乐。',
          success: (x) => res(x.confirm),
          fail: () => res(false),
        })
      )
      if (!go) return
      this.busy = 'bgm-del'
      try {
        this.cur = await dramaBgmDelete(this.cur.id)
      } catch (e) {
        uni.showModal({ title: '删除失败', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.busy = ''
      }
    },
    async compSheet() {
      if (!this.cur || this.busy) return
      this.busy = 'sheet'
      try {
        this.cur = await dramaContactSheet(this.cur.id, {
          mode: 'smart', proxy: this.compProxy ? 1 : 0,
        })
        uni.showToast({ title: '速览已生成', icon: 'success' })
      } catch (e) {
        uni.showModal({ title: '速览生成失败', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.busy = ''
      }
    },
    async compGif() {
      if (!this.cur || this.busy) return
      this.busy = 'gif'
      try {
        this.cur = await dramaPreviewGif(this.cur.id, { duration: 4, width: 360 })
        uni.showToast({ title: 'GIF 已生成', icon: 'success' })
      } catch (e) {
        uni.showModal({ title: 'GIF 生成失败', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.busy = ''
      }
    },
    openCompose() {
      if (!this.compUrl) return
      this.previewFile(this.compUrl, '合成成片.mp4', 'video')
    },
    openSheet() {
      if (!this.compSheetUrl) return
      this.previewFile(this.compSheetUrl, '分镜表.png', 'image')
    },
    openGif() {
      if (!this.compGifUrl) return
      this.previewFile(this.compGifUrl, '速览.gif', 'image')
    },
    // ---------------- 发行物料（E 批 · 本地 ffmpeg，零生成费） ----------------
    /** 平台/构图/强度/主题选项表；拉不到就不显示区块，不挡主流程 */
    async loadMaterialOptions() {
      try {
        // 同上：null 不能顶掉默认的平台表
        const r = await dramaPlatforms()
        if (r && typeof r === 'object') this.matOpt = r
      } catch (e) {
        // 选项拉不到 = 后端没重启；不弹窗打断，按钮点下去会自己报错
      }
    },
    matPlatformName(id) {
      const p = (this.matOpt.platforms || []).find((x) => x.id === id)
      return p ? p.name : id
    },
    matFraming() {
      return { mode: this.mat.framing }
    },
    openUrl(url, name = '') {
      if (!url) return
      this.previewFile(url, name)
    },
    /** 单帧预览：同一套构图滤镜，只出小图，不产片 */
    async matPreview() {
      if (!this.cur || this.busy) return
      this.busy = 'matpreview'
      try {
        const r = await dramaExportPlatform(this.cur.id, {
          platform: this.mat.platform,
          framing: this.matFraming(),
          preview: true,
          preview_time: 1,
        })
        this.mat.preview = r.preview
      } catch (e) {
        uni.showModal({ title: '预览失败', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.busy = ''
      }
    },
    /** 按平台规格重构图 + 重编码（本地，零费用） */
    async matExport() {
      if (!this.cur || this.busy) return
      this.busy = 'matexport'
      try {
        const r = await dramaExportPlatform(this.cur.id, {
          platform: this.mat.platform,
          framing: this.matFraming(),
        })
        this.cur = r.project
        const rep = r.report || {}
        uni.showToast({
          title: rep.within_cap ? '导出完成（在码率线内）' : '导出完成（码率超线）',
          icon: 'none',
        })
      } catch (e) {
        uni.showModal({ title: '导出失败', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.busy = ''
      }
    },
    /** 二维码：勾了「要烧进片」时抖音会被后端拒（站外导流） */
    async matQr() {
      if (!this.cur || this.busy) return
      this.busy = 'matqr'
      try {
        const r = await dramaShopQr(this.cur.id, {
          url: this.mat.qrUrl,
          platform: this.mat.platform,
          burn: this.mat.qrBurn,
        })
        this.cur = r.project
        uni.showToast({ title: '二维码已生成', icon: 'success' })
      } catch (e) {
        uni.showModal({ title: '二维码', content: e.message || '生成失败', showCancel: false })
      } finally {
        this.busy = ''
      }
    },
    async matCards() {
      if (!this.cur || this.busy) return
      this.busy = 'matcards'
      try {
        const r = await dramaCarousel(this.cur.id, { theme: this.mat.theme })
        this.cur = r.project
        uni.showToast({ title: `出了 ${r.count} 张`, icon: 'none' })
      } catch (e) {
        uni.showModal({ title: '图文卡', content: e.message || '生成失败', showCancel: false })
      } finally {
        this.busy = ''
      }
    },
    previewCards() {
      if (!this.matCardUrls.length) return
      uni.previewImage({ urls: this.matCardUrls, current: this.matCardUrls[0] })
    },
    async matNative() {
      if (!this.cur || this.busy) return
      this.busy = 'matnative'
      try {
        this.cur = await dramaNativeFeel(this.cur.id, {
          strength: this.mat.strength,
          grain: this.mat.grain,
          vignette: this.mat.vignette,
          halation: this.mat.halation,
          phone_compress: this.mat.phoneCompress,
        })
        uni.showToast({ title: '原生感已处理', icon: 'success' })
      } catch (e) {
        uni.showModal({ title: '原生感', content: e.message || '处理失败', showCancel: false })
      } finally {
        this.busy = ''
      }
    },
    async matMasterAnalyze() {
      if (!this.cur || this.busy) return
      this.busy = 'matmastera'
      try {
        const r = await dramaMastering(this.cur.id, { action: 'analyze' })
        const a = r.analysis || {}
        this.mat.normalize = !!(r.options && r.options.normalize_audio)
        uni.showModal({
          title: '体检完成',
          content: `接缝 ${a.summary ? a.summary.total : 0} 处：`
            + `${a.summary ? a.summary.strong : 0} 处明显跳、`
            + `${a.summary ? a.summary.review : 0} 处该看一眼`
            + (a.loudness ? `\n响度 ${a.loudness.input_i} LUFS（目标 -14）` : '\n无音轨'),
          showCancel: false,
        })
      } catch (e) {
        uni.showModal({ title: '体检失败', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.busy = ''
      }
    },
    async matMasterRender() {
      if (!this.cur || this.busy) return
      if (!this.mat.normalize && !this.mat.deflicker) {
        uni.showToast({ title: '至少选一项精修', icon: 'none' })
        return
      }
      this.busy = 'matmasterr'
      try {
        const r = await dramaMastering(this.cur.id, {
          action: 'render',
          normalize_audio: this.mat.normalize,
          deflicker: this.mat.deflicker,
        })
        this.cur = r.project
        uni.showToast({ title: '精修完成', icon: 'success' })
      } catch (e) {
        uni.showModal({ title: '精修失败', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.busy = ''
      }
    },
    /** 发布文案：模板版零费用；AI 版先确认（会花一次调用） */
    matPublish(llm) {
      if (!this.cur || this.busy) return
      if (!llm) return this.runPublish(false)
      uni.showModal({
        title: 'AI 版文案',
        content: '会调用一次模型（花钱）。继续吗？',
        success: (res) => { if (res.confirm) this.runPublish(true) },
      })
    },
    async runPublish(llm) {
      this.busy = llm ? 'matllm' : 'matpack'
      try {
        const fn = llm ? dramaPublishLlm : dramaPublishPack
        const r = await fn(this.cur.id, { platform: this.mat.platform })
        this.cur = r.project
        uni.showToast({ title: llm ? 'AI 文案已生成' : '文案已生成', icon: 'success' })
      } catch (e) {
        uni.showModal({ title: '发布文案', content: e.message || '生成失败', showCancel: false })
      } finally {
        this.busy = ''
      }
    },
    copyText(text) {
      if (!text) return
      uni.setClipboardData({ data: String(text) })
      uni.showToast({ title: '已复制', icon: 'none' })
    },
    copyTags() {
      if (!this.matPack) return
      this.copyText((this.matPack.hashtags || []).join(' '))
    },
    copyAll() {
      if (!this.cur) return
      const c = this.cur
      const txt = [
        `# ${c.product.name} · 商品短剧`,
        `形态：${c.answers.form}｜片长：${c.answers.duration}s｜商品角色：${c.answers.role}`,
        '', '## 结构卡', c.card || '',
        '', '## 剧本', c.script || '',
        '', '## 分镜表', c.storyboard || '',
        '', '## 自检', c.check || '',
      ].join('\n')
      uni.setClipboardData({ data: txt })
    },
    /** 导出成 md 文件（浏览器直接开这个地址就是下载） */
    exportMd() {
      if (!this.cur) return
      this.previewFile(dramaExportUrl(this.cur.id), `${(this.cur.product || {}).name || '项目'}.md`, 'text')
    },
    /* ===== 发布自检 / 发布门禁（纯计算，不花钱） ===== */
    readinessLevel(r) {
      if (!r) return ''
      return { ready: 'ok', risky: 'warn', needsWork: 'fail' }[r.overall] || ''
    },
    readinessLabel(r) {
      if (!r) return ''
      return { ready: '可发布', risky: '有风险', needsWork: '建议先改' }[r.overall] || ''
    },
    readinessName(k) {
      return {
        compliance: '广告法',
        hook: '开场钩子',
        duration: '时长',
        caption: '字幕读速',
        cta: '行动号召',
        structure: '带货三段式',
        productEarly: '商品前 3 秒',
        aigc: 'AIGC 角标',
      }[k] || k
    },
    gateName(id) {
      return {
        readiness: '脚本自检',
        qc: '成片质检',
        quality: 'AI 镜头验收',
        credits: '素材授权',
        aiPolicy: 'AI 带货规则',
        realMix: '实拍占比',
      }[id] || id
    },
    async readinessRun() {
      if (!this.cur || this.busy) return
      this.busy = 'readiness'
      try {
        this.cur = await dramaReadiness(this.cur.id)
      } catch (e) {
        uni.showModal({ title: '自检没跑成', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.busy = ''
      }
    },
    async gateRun() {
      if (!this.cur || this.busy) return
      this.busy = 'gate'
      try {
        this.cur = await dramaGate(this.cur.id)
      } catch (e) {
        uni.showModal({ title: '门禁没跑成', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.busy = ''
      }
    },
    /** 出封面：抽帧 + 压商品名标题，本地 ffmpeg，不花钱 */
    async coverRun() {
      if (!this.cur || this.busy) return
      this.busy = 'cover'
      try {
        const title = (this.cur.product && this.cur.product.name) || ''
        this.cur = await dramaCoverRun(this.cur.id, title, 1, 'center')
        uni.showToast({ title: '封面已生成', icon: 'success' })
      } catch (e) {
        uni.showModal({ title: '封面没出成', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.busy = ''
      }
    },
    openCover() {
      if (!this.cur) return
      this.previewFile(dramaCoverUrl(this.cur.id), '封面.png', 'image')
    },
    /** 字幕导出（SRT/VTT）：时轴按分镜计划时长累加，是可编辑草稿 */
    exportSubtitle(fmt) {
      if (!this.cur) return
      this.previewFile(dramaSubtitleUrl(this.cur.id, fmt), `字幕.${fmt}`, 'text')
    },
    delProject() {
      if (!this.cur || this.busy) return
      const name = this.cur.product.name || '这条'
      uni.showModal({
        title: '删掉这个项目？',
        content: `「${name}」的商品图、关键帧、成片会一起删掉，删了恢复不了。`,
        confirmText: '删掉',
        confirmColor: '#e5484d',
        success: async (r) => {
          if (!r.confirm) return
          this.busy = 'del'
          try {
            await dramaDeleteProject(this.cur.id)
            this.cur = null
            await this.loadList()
            if (this.list.length) this.open(this.list[0].id)
          } catch (e) {
            uni.showModal({ title: '删除失败', content: e.message, showCancel: false })
          } finally {
            this.busy = ''
          }
        },
      })
    },
  },
}
