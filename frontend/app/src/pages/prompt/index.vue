<template>
  <view class="chat">
    <view class="topbar">
      <view class="brand">
        <view class="brand-dot"></view>
        <text class="brand-name">提示词优化</text>
      </view>
      <text v-if="msgs.length" class="topbar-act" @click="reset">新对话</text>
    </view>

    <scroll-view
      class="stream"
      scroll-y
      :scroll-into-view="endId"
      :scroll-with-animation="true"
    >
      <view class="stream-inner">
        <view v-if="!msgs.length" class="welcome">
          <view class="welcome-title">说说要做什么片子</view>
          <view class="welcome-sub">写想法 · 粘别家提示词 · 出了片传截图说哪不对</view>
        </view>

        <view v-for="m in msgs" :key="m.id" :id="'m' + m.id" :class="['msg', m.role]">
          <block v-if="m.role === 'user'">
            <view v-if="m.images && m.images.length" class="msg-shots">
              <image
                v-for="(s, i) in m.images"
                :key="i"
                :src="s"
                class="msg-shot"
                mode="aspectFill"
                @click="preview(m.images, i)"
              />
            </view>
            <view v-if="m.text" class="bubble-user">{{ m.text }}</view>
          </block>

          <view v-else class="ai">
            <view v-if="m.loading" class="typing">
              <view class="dot"></view>
              <view class="dot"></view>
              <view class="dot"></view>
              <text class="typing-text">{{ loadingText }}</text>
            </view>
            <view v-else-if="m.error" class="ai-error">{{ m.error }}</view>
            <!-- 提问：只回话，不出稿。一个问题配它自己的选项，点一下发出去 -->
            <block v-else-if="m.data.action === 'ask'">
              <view v-for="(b, bi) in m.data.blocks" :key="'b' + bi" class="ask-block">
                <text v-if="b.text" class="ask-text" user-select selectable>{{ b.text }}</text>
                <view v-if="b.options.length" class="ask-opts">
                  <view
                    v-for="(o, i) in b.options"
                    :key="'o' + i"
                    class="ask-opt"
                    @click="pickOption(o)"
                  >{{ o }}</view>
                </view>
              </view>
            </block>
            <block v-else>
              <view class="ai-meta">
                <text :class="['pill', m.data.red.length ? 'pill-red' : 'pill-ok']">
                  {{ m.data.red.length ? m.data.red.length + ' 条没过' : '通过官方判据 ' + m.data.rules + ' 条' }}
                </text>
                <text class="meta-sub">{{ m.data.format }} · {{ m.data.chars }} 字</text>
              </view>

              <view v-if="m.data.warnings && m.data.warnings.length" class="ai-note">
                <text v-for="(w, i) in m.data.warnings" :key="i" class="ai-note-line">{{ w }}</text>
              </view>
              <view v-if="m.data.red.length" class="ai-red">
                <text v-for="(r, i) in m.data.red" :key="i" class="ai-red-line">✗ {{ r }}</text>
              </view>

              <text class="prompt-out" user-select selectable>{{ m.data.prompt }}</text>

              <view class="ai-acts">
                <text class="act" @click="copy(m.data.prompt)">复制</text>
                <text class="act act-soft" @click="fixThis(m)">哪不对？传图改</text>
              </view>

              <!-- 官方要求的「优化问题」：我们替你定了什么、改了什么。
                   灰字、可折叠，**不进提示词**，复制也带不走。 -->
              <view v-if="m.data.note" class="prompt-note" @click="m.data.noteOpen = !m.data.noteOpen">
                <text class="note-head">
                  {{ m.data.noteOpen ? '收起说明 ▲' : '我替你定了什么 ▾' }}
                </text>
                <text v-if="m.data.noteOpen" class="note-body" user-select selectable>{{ m.data.note }}</text>
              </view>
            </block>
          </view>
        </view>

        <view id="stream-end" class="stream-pad"></view>
      </view>
    </scroll-view>

    <view class="composer">
      <view v-if="shots.length" class="attach">
        <view v-for="(s, i) in shots" :key="i" class="attach-item">
          <image :src="s" class="attach-img" mode="aspectFill" @click="preview(shots, i)" />
          <!-- 编号 = 上传顺序。顾客要在 2.0 那边按同样顺序传，提示词里的 @图片N 才对得上 -->
          <text class="attach-no">@图片{{ i + 1 }}</text>
          <view class="attach-del" @click="delShot(i)">×</view>
        </view>
      </view>

      <view class="box">
        <textarea
          v-model="draft"
          class="ta"
          :placeholder="placeholder"
          :maxlength="20000"
          :focus="taFocus"
          :disabled="loading"
          auto-height
          :show-confirm-bar="false"
          :adjust-position="true"
        />
        <view class="bar">
          <view class="bar-left">
            <view class="tool-pill" @click="chooseShots">
              <text class="tool-plus">＋</text>
              <text class="tool-word">图片</text>
            </view>
            <view class="tool-pill" @click="paste">
              <text class="tool-word">粘贴</text>
            </view>
          </view>
          <view :class="['send', canSend ? 'on' : '']" @click="send">
            <text class="send-arrow">↑</text>
          </view>
        </view>
      </view>

      <view class="opts">
        <view class="opt-chip" @click="showAssets = true">
          <text class="opt-k">素材</text>
          <text class="opt-v">{{ assets.length ? assets.length + ' 样' : '没有' }}</text>
        </view>
        <view :class="['opt-chip', target ? '' : 'opt-need']" @click="pickTarget">
          <text class="opt-k">写给</text>
          <text class="opt-v">{{ targetName }}</text>
        </view>
        <view class="opt-chip" @click="pickModel">
          <text class="opt-k">模型</text>
          <text class="opt-v">{{ modelName }}</text>
        </view>
        <!-- #ifdef H5 -->
        <text class="opt-tip">截图可直接 Ctrl+V</text>
        <!-- #endif -->
      </view>
    </view>

    <!-- 参考素材：只声明「有几样、各是什么」，不用传文件 —— 这里只写提示词 -->
    <view v-if="showAssets" class="mask" @click="showAssets = false"></view>
    <view v-if="showAssets" class="sheet">
      <view class="sheet-head">
        <text class="sheet-title">参考素材</text>
        <text class="sheet-note">说出有几样、各是干什么用的就行，不用传文件</text>
        <text class="sheet-note">编号按上传顺序排：你传的图是 @图片1、@图片2…，这里声明的接着往后排</text>
      </view>

      <view v-for="(a, i) in assets" :key="'a' + i" class="as-row">
        <view class="as-tags">
          <text class="as-tag" @click="pickAssetKind(i)">{{ kindName(a.kind) }}</text>
          <text class="as-tag" @click="pickAssetRole(i)">{{ roleName(a) }}</text>
          <text class="as-del" @click="delAsset(i)">删除</text>
        </view>
        <input
          v-model="a.note"
          class="as-input"
          placeholder="这张里是什么？（人物 / 风格 / 场景）"
        />
      </view>

      <view class="sheet-acts">
        <text class="sheet-add" @click="addAsset">+ 添加一样</text>
        <text class="sheet-ok" @click="showAssets = false">完成</text>
      </view>
    </view>
  </view>
</template>

<script>
import { promptChat, promptConvert, promptRevise } from '@/api/request'

// 可选的理解模型。🩸 只放后端白名单里的 key，别传任意模型名过去。
const MODELS = [
  { key: 'lite', name: '豆包 Lite' },
  { key: 'pro', name: '豆包 Pro' },
  { key: 'deepseek', name: 'DeepSeek' },
]

// 写给哪家视频模型。🩸 **两家平级，没有默认、不排强弱**（2026-10-30 主人）：
// 初始不预选，顾客点一下才走；后端也不给默认值。
const TARGETS = [
  { key: 'sd20', name: 'Seedance 2.0' },
  { key: 'h3', name: 'H3' },
]

// 一眼能看出「这是一份现成稿」的记号：参考标签 / 镜头编号 / 时间码。
// 命中就走转换（保真搬运）；命中不了才当"一句话想法"。
const SCRIPT_HINT = /<\s*(picture|video|audio|subject)\b|第\s*\d+\s*[镜幕]|shot\s*\d+|00:\d{2}|\b\d{1,2}\s*[-–~]\s*\d{1,2}\s*s/i

// 参考素材的类型与用途。🩸 用途只放后端 `h3_convert_route.ROLES` 里的值。
// 图可以当"参考图"也可以当"第一帧/最后一帧"（官方说这是两种完全不同的模式，
// 猜错不是效果差一点，是整个模式跑错 —— 所以让顾客自己选，不替他猜）。
const ASSET_KINDS = [
  { key: 'image', name: '参考图', tag: 'Picture' },
  { key: 'video', name: '参考视频', tag: 'Video' },
  { key: 'audio', name: '参考音频', tag: 'Audio' },
]
const ROLES_BY_KIND = {
  image: [
    { key: 'reference_image', name: '当参考图' },
    { key: 'first_frame', name: '当第一帧' },
    { key: 'last_frame', name: '当最后一帧' },
  ],
  video: [{ key: 'reference_video', name: '当参考视频' }],
  audio: [{ key: 'reference_audio', name: '当参考音频' }],
}

export default {
  data() {
    return {
      msgs: [],
      draft: '',
      shots: [],          // data URI，最多 4 张
      loading: false,
      loadingText: '正在写…',
      // 🩸 H3 走 agent 后一轮是 5–12 次模型调用（实测 25～102 秒），请求是**一次性**
      // 返回的、中途没有流。不给秒数的话，60 秒不动 = 顾客以为卡死直接关页。
      waitSec: 0,
      timer: null,
      // 🩸 时长不再在上方选：等聊到该定的时候由模型问（2026-10-30 主人）。
      // 这个值只给「转换 / 修订」两条老路当兜底，对话路线传 0 = 还没定。
      duration: 5,
      model: 'lite',
      models: MODELS,
      target: '',        // 写给哪家：''（还没选）/ sd20 / h3 —— 平级，不预选
      targets: TARGETS,
      assets: [],
      showAssets: false,
      seq: 0,
      endId: '',
      taFocus: false,
      // 本轮会话最近一次产出的提示词 —— 顾客后面说"这不对"时，改的就是它
      lastPrompt: '',
    }
  },
  // #ifdef H5
  // 🩸 截图工具截完直接 Ctrl+V 是最顺的路，比"点＋→翻相册找文件"快得多。
  // 挂在 document 上而不是 textarea：uni 的 textarea 是组件，原生 paste 不透传。
  mounted() {
    document.addEventListener('paste', this.onPaste)
  },
  beforeUnmount() {
    document.removeEventListener('paste', this.onPaste)
    clearInterval(this.timer)
  },
  // #endif

  computed: {
    canSend() {
      return !this.loading && (!!this.draft.trim() || this.shots.length > 0)
    },
    modelName() {
      const m = MODELS.find((x) => x.key === this.model)
      return m ? m.name : MODELS[0].name
    },
    targetName() {
      const t = TARGETS.find((x) => x.key === this.target)
      return t ? t.name : '选一下'
    },
    placeholder() {
      if (this.shots.length) return '哪儿不对？第几镜、什么现象（例：第 3 镜她笑了，不该笑）'
      if (this.lastPrompt) return '还想改哪里？或者开始一份新的'
      return '发消息，说说你想拍什么…'
    },
  },
  methods: {
    // ---------------------------------------------------------------- 消息
    push(role, text, images = [], loading = false) {
      const id = ++this.seq
      this.msgs.push({ id, role, text, images, loading })
      this.toEnd('m' + id)
      return this.msgs[this.msgs.length - 1]
    },
    toEnd(id) {
      this.endId = ''
      this.$nextTick(() => { this.endId = id || 'stream-end' })
    },

    async send() {
      if (!this.canSend) return
      // 🩸 两家平级、没有默认 —— 头一句必须先让顾客选写给谁，
      // 选完就记住，之后不再打断（换家要开新对话，两家格式不通用）。
      if (!this.target) {
        const picked = await this.pickTarget()
        if (!picked) return
      }
      const text = this.draft.trim()
      const imgs = this.shots.slice()

      this.push('user', text, imgs)
      this.draft = ''
      this.shots = []
      const ai = this.push('ai', '', [], true)
      // 历史要在 push 之后取：最后一条是本轮的顾客话，loading 那条没有 data 会被滤掉
      const history = this.buildHistory()
      this.loading = true
      this.waitSec = 0
      // 秒数一直在跳 = 页面活着。前 25 秒不用解释，之后补一句为什么慢，
      // 否则「已 40 秒」本身也像个坏掉的计数器。
      const base = imgs.length ? '正在看图改稿' : '正在写'
      const why = this.target === 'h3' ? '，模型在读官方 skill 包，这是正常的' : ''
      this.loadingText = base + '…'
      clearInterval(this.timer)
      this.timer = setInterval(() => {
        this.waitSec += 1
        this.loadingText = `${base} · 已 ${this.waitSec} 秒`
          + (this.waitSec >= 25 ? why : '')
      }, 1000)

      try {
        const body = await this.route(text, imgs, history)
        const d = body.data || {}
        ai.loading = false
        if (d.action === 'ask') {
          // 🩸 原文 `question` 必须留着：`blocks` 只给渲染用，
          // 进对话历史时要的是模型自己说过的那段字（浏览器实点抓到过丢失）
          ai.data = {
            action: 'ask',
            question: d.question || '',
            blocks: this.parseAsk(d.question),
          }
        } else {
          ai.data = {
            action: 'write',
            prompt: d.prompt || '',
            red: d.red || [],
            yellow: d.yellow || [],
            warnings: d.warnings || [],
            tries: d.tries || 1,
            chars: (d.prompt || '').length,
            rules: d.rules || 0,
            format: d.format || '',
            note: d.note || '',        // 官方 Step 4「优化问题」：说明 + 改了什么
            noteOpen: false,           // 默认收起，不抢提示词的位置
          }
          if (ai.data.prompt) this.lastPrompt = ai.data.prompt
        }
        this.toEnd('m' + ai.id)
      } catch (e) {
        ai.loading = false
        ai.error = (e && e.message) || '请稍后重试'
        this.toEnd('m' + ai.id)
      } finally {
        clearInterval(this.timer)
        this.timer = null
        this.loading = false
      }
    },

    /**
     * 三条路自动分流，**不让人做选择题**：
     *   已经出过稿 / 带截图 → 修订（只改那几处，不重写）
     *   像一份现成稿        → 转换（保真搬运，不问）
     *   其余                → 对话（缺信息先问，够了直接写）
     */
    route(text, imgs, history) {
      // Seedance 2.0 一支：**全部走对话**。2.0 官方 skill 自带「已有提示词就重写」
      // 和「按复杂度分路径 A/B」的判断，不需要我们再分转换/修订两条老路。
      // 截图直接挂在对话里给模型看（H3 那条路才用 /prompt/revise）。
      if (this.target === 'sd20') {
        return promptChat({
          messages: history,
          duration: 0,
          model: this.model,
          target: 'sd20',
          images: imgs,
          assets: this.buildAssets(),
        })
      }
      if (imgs.length || this.lastPrompt) {
        // 本轮刚出过提示词 → 正文是「哪不对」，提示词用上一份；
        // 否则顾客是连提示词带截图一起粘进来的，正文就是那份提示词。
        const has = !!this.lastPrompt
        return promptRevise({
          prompt: has ? this.lastPrompt : text,
          feedback: has ? text : '',
          images: imgs,
          duration: this.duration,
          model: this.model,
          target: 'h3',
        })
      }
      const isScript = text.length >= 200 || SCRIPT_HINT.test(text)
      if (isScript) {
        return promptConvert({
          text,
          duration: this.duration,
          model: this.model,
          target: 'h3',
          assets: this.buildAssets(),
        })
      }
      // duration 传 0 = 还没定，让模型在对话里问（官方单段 4–15 秒它自己会说）
      return promptChat({
        messages: history,
        duration: 0,
        model: this.model,
        target: 'h3',
        images: imgs,
        assets: this.buildAssets(),
      })
    },

    // ---------------------------------------------------------------- 参考素材
    kindName(k) {
      return (ASSET_KINDS.find((x) => x.key === k) || {}).name || k
    },
    roleName(a) {
      const o = (ROLES_BY_KIND[a.kind] || []).find((x) => x.key === a.role)
      return o ? o.name : a.role
    },
    addAsset() {
      if (this.assets.length >= 12) {
        // 官方混用总文件上限 12（h3-readme:85），前端先拦一道
        uni.showToast({ title: '素材最多 12 样', icon: 'none' })
        return
      }
      this.assets.push({ kind: 'image', role: 'reference_image', note: '' })
    },
    delAsset(i) {
      this.assets.splice(i, 1)
    },
    pickAssetKind(i) {
      const list = ASSET_KINDS.map((x) => x.name)
      uni.showActionSheet({
        itemList: list,
        success: (r) => {
          const a = this.assets[i]
          a.kind = ASSET_KINDS[r.tapIndex].key
          // 换了类型，用途跟着换成该类别的第一个（不保留跨类别的非法组合）
          a.role = ROLES_BY_KIND[a.kind][0].key
        },
      })
    },
    pickAssetRole(i) {
      const a = this.assets[i]
      const opts = ROLES_BY_KIND[a.kind] || []
      uni.showActionSheet({
        itemList: opts.map((x) => x.name),
        success: (r) => { a.role = opts[r.tapIndex].key },
      })
    },
    /** 转成后端的 assets 格式：标签按类型分别编号（<Picture 1> / <Video 1> …） */
    buildAssets() {
      const n = { image: 0, video: 0, audio: 0 }
      return this.assets.map((a) => {
        n[a.kind] += 1
        const tag = (ASSET_KINDS.find((k) => k.key === a.kind) || {}).tag || 'Picture'
        return {
          kind: a.kind,
          role: a.role,
          label: `<${tag} ${n[a.kind]}>`,
          note: (a.note || '').trim(),
        }
      })
    },

    /** 把消息流压成模型能读的对话历史。没有 data 的（正在转圈那条）跳过。 */
    buildHistory() {
      const out = []
      for (const m of this.msgs) {
        if (m.role === 'user' && m.text) {
          out.push({ role: 'user', content: m.text })
        } else if (m.role === 'ai' && m.data && !m.loading) {
          const c = m.data.action === 'ask' ? m.data.question : m.data.prompt
          if (c) out.push({ role: 'assistant', content: c })
        }
      }
      return out
    },

    /**
     * 把提问切成「一个问题 + 它自己的选项」若干块。
     * 🩸 不能把所有 `- ` 行堆成同一排：模型一轮会问两个问题（风格 + 时长），
     * 堆一起的话顾客分不清「2D 动画」和「4 秒」哪个属于哪问。
     */
    parseAsk(text) {
      const blocks = []
      let cur = { text: [], options: [] }
      for (const ln of String(text || '').split('\n')) {
        const m = ln.match(/^\s*[-•·*]\s+(.+)$/)
        if (m) {
          cur.options.push(m[1].trim())
          continue
        }
        if (!ln.trim()) continue
        // 已经有选项了又来一行正经话 → 上一问到此为止
        if (cur.options.length) {
          blocks.push(cur)
          cur = { text: [], options: [] }
        }
        cur.text.push(ln.trim())
      }
      if (cur.text.length || cur.options.length) blocks.push(cur)
      return blocks
        .map((b) => ({ text: b.text.join('\n').trim(), options: b.options }))
        .filter((b) => b.text || b.options.length)
    },

    /** 点选项 = 直接把它发出去，不用顾客再按发送 */
    pickOption(o) {
      if (this.loading) return
      this.draft = o
      this.send()
    },

    /** 点「哪不对？传图改」：把上一条产出记下来，等顾客传图说 */
    fixThis(m) {
      this.lastPrompt = m.data.prompt || ''
      this.chooseShots()
    },

    // ---------------------------------------------------------------- 截图
    chooseShots() {
      if (this.loading) return
      const left = 4 - this.shots.length
      if (left <= 0) {
        uni.showToast({ title: '最多 4 张', icon: 'none' })
        return
      }
      // #ifdef H5
      // 🩸 H5 不用 `uni.chooseImage`：它在浏览器里要造 <input file> 并程序化 click，
      // 实测点不动（第一次就是这么废掉的）。直接自己造 input，且在同一个用户手势里 click。
      this.pickH5(left)
      return
      // #endif
      // #ifndef H5
      uni.chooseImage({
        count: left,
        sizeType: ['compressed'],
        sourceType: ['album', 'camera'],
        success: async (res) => {
          const files = (res && res.tempFiles) || []
          const paths = (res && res.tempFilePaths) || []
          for (let i = 0; i < paths.length && i < left; i += 1) {
            // eslint-disable-next-line no-await-in-loop
            const uri = await this.readMini(files[i], paths[i])
            if (uri) this.shots.push(uri)
          }
        },
        fail: (e) => {
          // 🩸 别再静默：上一次就是 fail 被吞掉，看着像"按钮坏了"
          const m = (e && e.errMsg) || ''
          if (!m.includes('cancel')) uni.showToast({ title: '选图失败：' + m, icon: 'none' })
        },
      })
      // #endif
    },

    // #ifdef H5
    /**
     * 粘贴：剪贴板里有图就收。
     * 🩸 剪贴板里**有文字**时不动它 —— 那是顾客在粘提示词，抢过来会把文字弄丢。
     * 微信/QQ/系统截图复制出来只有图没有文字，正好落在这里。
     */
    onPaste(e) {
      const cd = e && e.clipboardData
      if (!cd) return
      const text = cd.getData('text/plain')
      if (text && text.trim()) return

      const files = []
      const items = cd.items || []
      for (let i = 0; i < items.length; i += 1) {
        if (items[i].kind === 'file' && /^image\//.test(items[i].type)) {
          const f = items[i].getAsFile()
          if (f) files.push(f)
        }
      }
      if (!files.length) return

      e.preventDefault()
      const left = 4 - this.shots.length
      if (left <= 0) {
        uni.showToast({ title: '最多 4 张', icon: 'none' })
        return
      }
      files.slice(0, left).forEach(async (f) => {
        const uri = await this.compress(f)
        if (uri) this.shots.push(uri)
      })
      uni.showToast({ title: `收到 ${Math.min(files.length, left)} 张图`, icon: 'none' })
    },

    pickH5(left) {
      const el = document.createElement('input')
      el.type = 'file'
      el.accept = 'image/*'
      el.multiple = left > 1
      el.style.display = 'none'
      el.onchange = async () => {
        const files = Array.prototype.slice.call(el.files || [], 0, left)
        for (let i = 0; i < files.length; i += 1) {
          // eslint-disable-next-line no-await-in-loop
          const uri = await this.compress(files[i])
          if (uri) this.shots.push(uri)
        }
        if (el.parentNode) el.parentNode.removeChild(el)
      }
      document.body.appendChild(el)
      el.click()
    },
    /**
     * 手机截图动辄 3–5MB，base64 之后会撞后端 300 万字符的上限。
     * 这里压到长边 1280 / JPEG 0.82 —— 模型看镜头内容够用了。
     */
    compress(file) {
      return new Promise((resolve) => {
        const fr = new FileReader()
        fr.onerror = () => resolve('')
        fr.onload = () => {
          const img = new Image()
          img.onerror = () => resolve('')
          img.onload = () => {
            const MAX = 1280
            let w = img.width
            let h = img.height
            if (w > MAX || h > MAX) {
              const r = Math.min(MAX / w, MAX / h)
              w = Math.round(w * r)
              h = Math.round(h * r)
            }
            const cv = document.createElement('canvas')
            cv.width = w
            cv.height = h
            cv.getContext('2d').drawImage(img, 0, 0, w, h)
            resolve(cv.toDataURL('image/jpeg', 0.82))
          }
          img.src = String(fr.result || '')
        }
        fr.readAsDataURL(file)
      })
    },
    // #endif

    // #ifndef H5
    /** 小程序：临时路径 → base64 data URI */
    readMini(file, path) {
      return new Promise((resolve) => {
        const fs = uni.getFileSystemManager && uni.getFileSystemManager()
        const p = (file && file.path) || path
        if (!fs || !p) return resolve('')
        fs.readFile({
          filePath: p,
          encoding: 'base64',
          success: (r) => resolve(`data:image/jpeg;base64,${r.data}`),
          fail: () => resolve(''),
        })
      })
    },
    // #endif
    delShot(i) {
      this.shots.splice(i, 1)
    },
    preview(list, i) {
      uni.previewImage({ urls: list, current: list[i] })
    },

    // ---------------------------------------------------------------- 其它
    paste() {
      uni.getClipboardData({
        success: (res) => {
          if (res.data) this.draft = res.data
        },
        fail: () => uni.showToast({ title: '读取剪贴板失败', icon: 'none' }),
      })
    },
    pickModel() {
      const list = MODELS.map((m) => m.name)
      uni.showActionSheet({
        itemList: list,
        success: (r) => { this.model = MODELS[r.tapIndex].key },
      })
    },
    /** 选写给哪家。返回 Promise<boolean>：顾客取消了就是 false，调用方别硬发。 */
    pickTarget() {
      return new Promise((resolve) => {
        uni.showActionSheet({
          itemList: TARGETS.map((t) => t.name),
          success: (r) => {
            const k = TARGETS[r.tapIndex].key
            // 🩸 两家语法完全不同（英文/三字段 vs 中文/镜头编号），
            // 同一个对话里换家 = 历史对不上，只能开新对话。
            if (this.target && this.target !== k && this.msgs.length) this.reset()
            this.target = k
            resolve(true)
          },
          fail: () => resolve(false),
        })
      })
    },
    copy(text) {
      if (!text) return
      uni.setClipboardData({
        data: text,
        success: () => uni.showToast({ title: '已复制', icon: 'none' }),
      })
    },
    reset() {
      this.msgs = []
      this.lastPrompt = ''
      this.draft = ''
      this.shots = []
      this.toEnd('stream-end')
    },
  },
}
</script>

<style scoped>
.chat {
  display: flex;
  flex-direction: column;
  background: #fff;
  overflow: hidden;
}
/* #ifdef H5 */
/* 🩸 不能用 `height: 100vh`：H5 顶部还有一条 44px 的固定导航栏 + 44px 占位块，
   100vh 会多出一截，整页变成可滚动 —— 底部的时长/模型就被推到视口外（2026-10-30 实测）。
   直接把对话区钉在导航栏下方到视口底，页面永不需要滚动。 */
.chat {
  position: fixed;
  top: calc(44px + env(safe-area-inset-top, 0px));
  left: 0;
  right: 0;
  bottom: 0;
}
/* #endif */
/* #ifndef H5 */
.chat {
  height: 100vh;
}
/* #endif */

/* ---------- 顶栏 ---------- */
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 92rpx;
  padding: 0 32rpx;
  border-bottom: 1rpx solid #f0f1f4;
  background: #fff;
}
.brand {
  display: flex;
  align-items: center;
}
.brand-dot {
  width: 16rpx;
  height: 16rpx;
  margin-right: 14rpx;
  border-radius: 50%;
  background: linear-gradient(135deg, #5b6cff 0%, #7a4dff 100%);
}
.brand-name {
  font-size: 30rpx;
  font-weight: 600;
  color: #1a1d29;
}
.topbar-act {
  font-size: 25rpx;
  color: #8a8f9c;
}

/* ---------- 消息流 ---------- */
.stream {
  flex: 1;
  min-height: 0;
  height: 0;
}
.stream-inner {
  padding: 24rpx 32rpx 0;
}
.stream-pad {
  height: 32rpx;
}

.welcome {
  padding: 120rpx 0 40rpx;
  text-align: center;
}
.welcome-title {
  font-size: 46rpx;
  font-weight: 700;
  color: #1a1d29;
  letter-spacing: 1rpx;
}
.welcome-sub {
  margin-top: 18rpx;
  font-size: 25rpx;
  color: #9aa0ae;
}
.msg {
  margin-bottom: 40rpx;
}
.msg.user {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}
.msg-shots {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 12rpx;
  margin-bottom: 12rpx;
}
.msg-shot {
  width: 180rpx;
  height: 180rpx;
  border-radius: 16rpx;
  background: #f2f3f5;
}
.bubble-user {
  max-width: 78%;
  padding: 22rpx 26rpx;
  border-radius: 24rpx 24rpx 6rpx 24rpx;
  background: #f2f3f5;
  font-size: 28rpx;
  line-height: 1.65;
  color: #1a1d29;
  word-break: break-word;
  white-space: pre-wrap;
}

/* ---------- AI 回复 ---------- */
.ai-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 18rpx;
}
.pill {
  padding: 8rpx 18rpx;
  border-radius: 999rpx;
  font-size: 22rpx;
}
.pill-ok {
  background: #eef7f1;
  color: #1f9254;
}
.pill-red {
  background: #fdecec;
  color: #d9363e;
}
.meta-sub {
  margin-left: 16rpx;
  font-size: 22rpx;
  color: #b0b5c0;
}
.ai-note {
  margin-bottom: 14rpx;
}
.ai-note-line {
  display: block;
  padding: 12rpx 18rpx;
  margin-bottom: 8rpx;
  border-radius: 12rpx;
  background: #f2f4f8;
  font-size: 22rpx;
  line-height: 1.6;
  color: #5a6072;
}
.ai-red {
  margin-bottom: 14rpx;
}
.ai-red-line {
  display: block;
  padding: 12rpx 18rpx;
  margin-bottom: 8rpx;
  border-radius: 12rpx;
  background: #fdecec;
  font-size: 22rpx;
  line-height: 1.6;
  color: #c0392b;
}
/* 提问：一句人话 + 底下可点的选项 */
.ask-block + .ask-block {
  margin-top: 28rpx;
}
.ask-text {
  display: block;
  font-size: 28rpx;
  line-height: 1.7;
  color: #1a1d29;
  white-space: pre-wrap;
  word-break: break-word;
}
.ask-opts {
  display: flex;
  flex-wrap: wrap;
  margin-top: 20rpx;
}
.ask-opt {
  margin: 0 14rpx 14rpx 0;
  padding: 14rpx 26rpx;
  border-radius: 999rpx;
  border: 2rpx solid #d9deff;
  background: #f5f7ff;
  font-size: 25rpx;
  color: #4350d6;
}
.ask-opt:active {
  background: #e6eaff;
}
.ai-error {
  padding: 22rpx 24rpx;
  border-radius: 16rpx;
  background: #fdecec;
  font-size: 25rpx;
  line-height: 1.7;
  color: #c0392b;
  word-break: break-word;
}
.prompt-out {
  display: block;
  padding: 24rpx;
  border-radius: 16rpx;
  background: #f7f8fa;
  font-size: 24rpx;
  line-height: 1.8;
  color: #2a2e3a;
  white-space: pre-wrap;
  word-break: break-word;
}
.ai-acts {
  display: flex;
  margin-top: 16rpx;
}
.act {
  margin-right: 28rpx;
  font-size: 24rpx;
  color: #5b6cff;
}
.act-soft {
  color: #8a8f9c;
}
/* 「优化问题」：给顾客看的说明，不进提示词、复制带不走 */
.prompt-note {
  margin-top: 20rpx;
  padding: 20rpx 24rpx;
  border-radius: 16rpx;
  border: 1rpx dashed #dfe2ea;
  background: #fbfbfc;
}
.note-head {
  display: block;
  font-size: 24rpx;
  color: #7b8194;
}
.note-body {
  display: block;
  margin-top: 12rpx;
  font-size: 24rpx;
  line-height: 1.8;
  color: #6b7280;
  white-space: pre-wrap;
  word-break: break-word;
}

/* 打字机 */
.typing {
  display: flex;
  align-items: center;
}
.dot {
  width: 12rpx;
  height: 12rpx;
  margin-right: 8rpx;
  border-radius: 50%;
  background: #c8ccd6;
  animation: blink 1.2s infinite;
}
.dot:nth-child(2) {
  animation-delay: 0.2s;
}
.dot:nth-child(3) {
  animation-delay: 0.4s;
}
@keyframes blink {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 1; }
}
.typing-text {
  margin-left: 10rpx;
  font-size: 23rpx;
  color: #9aa0ae;
}

/* ---------- 底部输入 ---------- */
.composer {
  padding: 12rpx 24rpx calc(24rpx + env(safe-area-inset-bottom, 0px));
  background: #fff;
}
.attach {
  display: flex;
  flex-wrap: wrap;
  gap: 12rpx;
  margin-bottom: 12rpx;
  padding-left: 4rpx;
}
.attach-item {
  position: relative;
}
.attach-img {
  width: 110rpx;
  height: 110rpx;
  border-radius: 14rpx;
  background: #f2f3f5;
}
.attach-no {
  position: absolute;
  left: 6rpx;
  bottom: 6rpx;
  padding: 0 8rpx;
  border-radius: 8rpx;
  background: rgba(26, 29, 41, 0.62);
  color: #fff;
  font-size: 20rpx;
  line-height: 30rpx;
}
.attach-del {
  position: absolute;
  top: -10rpx;
  right: -10rpx;
  width: 34rpx;
  height: 34rpx;
  line-height: 32rpx;
  text-align: center;
  border-radius: 50%;
  background: rgba(26, 29, 41, 0.72);
  color: #fff;
  font-size: 24rpx;
}

.box {
  padding: 20rpx 20rpx 14rpx;
  border-radius: 26rpx;
  border: 2rpx solid #e5e6eb;
  background: #fff;
}
.box:focus-within {
  border-color: #c3caff;
}
.ta {
  width: 100%;
  min-height: 72rpx;
  max-height: 320rpx;
  font-size: 28rpx;
  line-height: 1.6;
  color: #1a1d29;
}
.bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10rpx;
}
.bar-left {
  display: flex;
  align-items: center;
}
.tool-pill {
  display: flex;
  align-items: center;
  height: 56rpx;
  margin-right: 16rpx;
  padding: 0 22rpx;
  border-radius: 999rpx;
  border: 2rpx solid #e5e6eb;
  background: #fff;
}
.tool-pill:active {
  background: #f3f5ff;
  border-color: #d9deff;
}
.tool-plus {
  margin-right: 4rpx;
  font-size: 28rpx;
  line-height: 1;
  color: #5b6cff;
}
.tool-word {
  font-size: 25rpx;
  color: #5a6072;
}
.send {
  width: 60rpx;
  height: 60rpx;
  line-height: 58rpx;
  text-align: center;
  border-radius: 50%;
  background: #eaebf0;
  transition: background 0.15s;
}
.send.on {
  background: linear-gradient(135deg, #5b6cff 0%, #7a4dff 100%);
}
.send-arrow {
  font-size: 30rpx;
  color: #fff;
  font-weight: 700;
}

.opts {
  display: flex;
  margin-top: 14rpx;
  padding-left: 6rpx;
}
.opt-chip {
  display: flex;
  align-items: center;
  margin-right: 14rpx;
  padding: 10rpx 22rpx;
  border-radius: 999rpx;
  background: #f5f6f8;
}
.opt-chip:active {
  background: #eceffd;
}
/* 还没选写给谁时，这个胶囊要显眼一点 —— 它卡着不能发 */
.opt-need {
  background: #fff3e8;
}
.opt-need .opt-k,
.opt-need .opt-v {
  color: #d97516;
}
.opt-k {
  font-size: 22rpx;
  color: #9aa0ae;
}
.opt-v {
  margin-left: 10rpx;
  font-size: 24rpx;
  font-weight: 600;
  color: #3a3f4d;
}
.opt-tip {
  margin-left: auto;
  margin-right: 6rpx;
  font-size: 21rpx;
  color: #c2c7d2;
}

/* ---------- 参考素材面板 ---------- */
.mask {
  position: fixed;
  left: 0;
  right: 0;
  top: 0;
  bottom: 0;
  z-index: 90;
  background: rgba(16, 18, 27, 0.32);
}
.sheet {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 91;
  max-height: 72vh;
  overflow-y: auto;
  padding: 32rpx 28rpx calc(28rpx + env(safe-area-inset-bottom, 0px));
  border-radius: 28rpx 28rpx 0 0;
  background: #fff;
  box-shadow: 0 -8rpx 40rpx rgba(20, 24, 60, 0.12);
}
.sheet-head {
  margin-bottom: 20rpx;
}
.sheet-title {
  display: block;
  font-size: 30rpx;
  font-weight: 700;
  color: #1a1d29;
}
.sheet-note {
  display: block;
  margin-top: 8rpx;
  font-size: 22rpx;
  color: #9aa0ae;
}
.as-row {
  margin-bottom: 16rpx;
  padding: 18rpx;
  border-radius: 16rpx;
  background: #f7f8fa;
}
.as-tags {
  display: flex;
  align-items: center;
}
.as-tag {
  margin-right: 14rpx;
  padding: 10rpx 22rpx;
  border-radius: 999rpx;
  border: 2rpx solid #d9deff;
  background: #f5f7ff;
  font-size: 24rpx;
  color: #4350d6;
}
.as-del {
  margin-left: auto;
  font-size: 23rpx;
  color: #d9363e;
}
.as-input {
  margin-top: 14rpx;
  padding: 16rpx 18rpx;
  border-radius: 12rpx;
  background: #fff;
  font-size: 25rpx;
  color: #2a2e3a;
}
.sheet-acts {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 12rpx;
}
.sheet-add {
  font-size: 26rpx;
  color: #5b6cff;
}
.sheet-ok {
  padding: 16rpx 48rpx;
  border-radius: 999rpx;
  background: linear-gradient(135deg, #5b6cff 0%, #7a4dff 100%);
  font-size: 27rpx;
  font-weight: 600;
  color: #fff;
}
</style>
