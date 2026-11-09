<template>
  <DramaAppShell>
    <view class="ds">
      <view class="page-wrap">
        <view class="cl-head">
          <view class="cl-title">照着参考片开新剧</view>
          <view class="cl-sub">先解构一条跑得动的片子，把它的节奏拿来套新商品 —— 文案重写，结构照走。</view>
        </view>

        <!-- 1 参考片 -->
        <view class="card">
          <view class="card-head">
            <view class="card-title"><text class="card-no">片</text>参考片</view>
            <view class="btn-mini" @click="pickRef">{{ refPath ? '重选' : '选视频' }}</view>
          </view>
          <view v-if="!refPath" class="empty">选一条 3 分钟以内的视频（自己拍过的、跑得动的都行）</view>
          <block v-else>
            <view class="cl-file">{{ refLabel }}</view>
            <view class="cl-ops">
              <view class="btn-mini" @click="analyzeRef">
                {{ analyzing ? '解构中…' : (hasBone ? '重新解构' : '解构这条') }}
              </view>
            </view>
            <view class="cl-tip">解构会调用一次视觉模型（花钱）；同一条片解一次就够，结果不会自动重跑。</view>
          </block>
          <view v-if="analyzeErr" class="cl-err">{{ analyzeErr }}</view>
        </view>

        <!-- 2 节奏骨架 -->
        <view class="card">
          <view class="card-head">
            <view class="card-title"><text class="card-no">骨</text>节奏骨架</view>
          </view>
          <view v-if="!hasBone" class="empty">解构完这里会显示：时长 / 镜头数 / 切换点 / 节奏 / 画面风格</view>
          <block v-else>
            <view v-for="b in boneRows" :key="b.key" class="cl-row">
              <text class="cl-k">{{ b.k }}</text>
              <text class="cl-v">{{ b.v }}</text>
            </view>
            <view v-if="summaryText" class="cl-quote">{{ summaryText }}</view>
            <view v-if="rhythmText" class="cl-line">节奏：{{ rhythmText }}</view>
            <view v-if="moveText" class="cl-line">运镜：{{ moveText }}</view>
            <view v-if="styleRows.length" class="cl-block">
              <view class="cl-sub2">画面风格</view>
              <view v-for="s in styleRows" :key="s.key" class="cl-row">
                <text class="cl-k">{{ s.k }}</text>
                <text class="cl-v">{{ s.v }}</text>
              </view>
            </view>
            <view v-if="promptText" class="cl-block">
              <view class="cl-sub2">可复用画面描述</view>
              <view class="cl-quote">{{ promptText }}</view>
              <view class="cl-ops"><view class="btn-mini" @click="copyPrompt">复制</view></view>
            </view>
          </block>
        </view>

        <!-- 3 用这个结构开新片 -->
        <view class="card">
          <view class="card-head">
            <view class="card-title"><text class="card-no">开</text>用这个结构开新片</view>
          </view>
          <view class="field">
            <view class="label">商品名称<text class="label-tip">必填</text></view>
            <input v-model="name" class="input line" placeholder="例：云柔加厚抽纸" />
          </view>
          <view class="field">
            <view class="label">卖点<text class="label-tip">每行一条，只写真有的</text></view>
            <textarea v-model="points" class="input area" placeholder="三层加厚，湿水不破" auto-height />
          </view>
          <view v-if="categories.length" class="field">
            <view class="label">品类</view>
            <view class="opts">
              <view
                v-for="x in categories"
                :key="x"
                :class="['opt', cat === x ? 'on' : '']"
                @click="cat = cat === x ? '' : x"
              >{{ x }}</view>
            </view>
          </view>
          <view class="field">
            <view class="label">片长</view>
            <view class="opts">
              <view
                v-for="d in durations"
                :key="d"
                :class="['opt', duration === d ? 'on' : '']"
                @click="duration = d"
              >{{ d }} 秒</view>
            </view>
          </view>
          <view class="field">
            <view class="label">视频模式<text class="label-tip">决定怎么拍，不是怎么发</text></view>
            <view class="opts">
              <view
                v-for="x in modes"
                :key="x"
                :class="['opt', mode === x ? 'on' : '']"
                @click="mode = mode === x ? '' : x"
              >{{ x }}</view>
            </view>
          </view>
          <view class="field">
            <view class="label">商品在剧情里扮演什么<text class="label-tip">决定戏怎么成立</text></view>
            <view class="opts">
              <view
                v-for="r in roles"
                :key="r"
                :class="['opt', role === r ? 'on' : '']"
                @click="role = r"
              >{{ r }}</view>
            </view>
          </view>
          <view v-if="tplList.length" class="field">
            <view class="label">参考剧本结构<text class="label-tip">可选；照它的节奏重写，不照搬文案</text></view>
            <view class="opts">
              <view class="opt" :class="{ on: !tplId }" @click="tplId = ''">不用</view>
              <view
                v-for="t in tplList"
                :key="t.id"
                :class="['opt', tplId === t.id ? 'on' : '']"
                @click="tplId = tplId === t.id ? '' : t.id"
              >{{ t.name }}<text class="opt-sub">{{ t.sub }}</text></view>
            </view>
          </view>
          <view class="btn-main" :class="{ dim: creating }" @click="startNew">
            {{ creating ? '创建中…' : '创建项目 ›' }}
          </view>
          <view class="cl-tip">创建不花钱；生成剧本要花钱，回脚本页由你点。</view>
        </view>
      </view>
    </view>
  </DramaAppShell>
</template>

<script>
/**
 * 照着参考片开新剧（照竞品 app/project/clone/page.tsx 的定位）
 *
 * 竞品那页是「拖参考视频 → /api/replicate/analyze → 建项目 → 直接出片」，
 * 它把复刻和出片一步做完；我们的生产线是「建项目 → 脚本 → 分镜 → 素材 → 出片」，
 * 所以这页只做前半段：**解构参考片拿骨架 → 带上商品信息建项目 → 回脚本页**。
 * 出片仍按我们自己的工序走，不在这一页越级调生成（也避免一进来就花钱）。
 *
 * 解构用的是既有能力 `POST /api/drama/media/analyze`（drama_media_lab）：
 * 抽 8 帧 + 检测切点 → 返回 duration / shot_count / frame_times / scene_rhythm / visual_style。
 *
 * 🩸 小程序端规矩（docs/DRAMA-UI-RESTRUCTURE.md 第十节）：
 * 所有 v-for 数组（boneRows / styleRows / categories / durations / modes / roles / tplList）
 * 都是 data 顶层字段，不绑 computed、不走对象属性路径；值在 onLoad / analyze 里预先算好。
 * 本页不引 dramaPage mixin —— 它面向「已打开的项目」，这页是建项目之前。
 */
import { onLoad } from '@dcloudio/uni-app'
import DramaAppShell from '@/components/drama/AppShell.vue'
import {
  dramaOptions,
  dramaScriptTemplates,
  dramaCreate,
  dramaRefTemplate,
  dramaMediaAnalyze,
} from '@/api/request'

function mmss(sec) {
  const s = Math.max(0, Math.round(Number(sec) || 0))
  const m = Math.floor(s / 60)
  const r = s % 60
  return m + ':' + (r < 10 ? '0' + r : r)
}

export default {
  components: { DramaAppShell },
  data() {
    return {
      // 参考片
      refPath: '',
      refLabel: '',
      analyzing: false,
      analyzeErr: '',
      // 骨架
      hasBone: false,
      boneRows: [],
      styleRows: [],
      summaryText: '',
      rhythmText: '',
      moveText: '',
      promptText: '',
      // 新建
      name: '',
      points: '',
      cat: '',
      duration: 30,
      mode: '',
      role: '转折道具',
      categories: [],
      durations: [],
      modes: [],
      roles: [],
      tplList: [],
      tplId: '',
      creating: false,
    }
  },
  onLoad() {
    this.loadOpts()
  },
  methods: {
    async loadOpts() {
      try {
        const o = (await dramaOptions()) || {}
        this.categories = (o.categories || []).slice()
        this.durations = (o.durations || []).slice()
        this.modes = (o.modes || []).slice()
        this.roles = (o.roles || []).slice()
        if (this.durations.length) this.duration = this.durations[0]
        if (this.roles.length) this.role = this.roles[0]
      } catch (e) { /* 选项拉不到就用手上的默认，不拦建项目 */ }
      try {
        const r = await dramaScriptTemplates()
        const list = Array.isArray(r) ? r : ((r && r.templates) || [])
        this.tplList = list.map((t) => ({
          id: t.id,
          name: t.name,
          sub: t.shots_count || t.total_duration
            ? ' ' + (t.shots_count || 0) + '镜/' + (t.total_duration || 0) + 's'
            : '',
        }))
      } catch (e) { this.tplList = [] }
    },

    /** 选参考片：小程序从聊天记录/相册取，H5 用文件框；两边都限 80MB / 3 分钟 */
    pickRef() {
      if (this.analyzing) return
      const take = (path, size) => {
        if (!path) return
        if (size && size > 80 * 1024 * 1024) {
          uni.showToast({ title: '视频不能超过 80MB', icon: 'none' })
          return
        }
        this.refPath = path
        this.refLabel = '已选视频 ' + ((Number(size || 0) / 1024 / 1024).toFixed(1)) + 'MB'
        this.analyzeErr = ''
        // 换片就把旧骨架清掉 —— 避免拿上一条片的节奏去开新片
        this.hasBone = false
        this.boneRows = []
        this.styleRows = []
        this.summaryText = ''
        this.rhythmText = ''
        this.moveText = ''
        this.promptText = ''
      }
      // #ifdef H5
      uni.chooseFile({
        count: 1,
        extension: ['.mp4', '.mov', '.webm', '.mkv', '.m4v'],
        success: (r) => {
          const f = ((r && r.tempFiles) || [])[0] || {}
          take(((r && r.tempFilePaths) || [])[0], f.size)
        },
      })
      // #endif
      // #ifndef H5
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
      // #endif
    },

    /** 解构：一次视觉模型调用（付费），只由用户点 */
    async analyzeRef() {
      if (!this.refPath || this.analyzing) return
      this.analyzing = true
      this.analyzeErr = ''
      try {
        const r = (await dramaMediaAnalyze(this.refPath)) || {}
        this.fillBone(r)
        this.hasBone = true
      } catch (e) {
        this.analyzeErr = e.message || '解构失败'
      }
      this.analyzing = false
    },

    /** 把解构结果算成几组行（mp 端只认 data 顶层数组，不绑对象属性路径） */
    fillBone(r) {
      const meta = r.metadata || {}
      const rows = []
      if (meta.duration) rows.push({ key: 'k0', k: '时长', v: Number(meta.duration).toFixed(1) + ' 秒' })
      if (meta.shot_count) rows.push({ key: 'k1', k: '镜头数', v: meta.shot_count + ' 个' })
      const ft = meta.frame_times || []
      if (ft.length) {
        const list = []
        for (let i = 0; i < ft.length; i++) list.push(mmss(ft[i]))
        rows.push({ key: 'k2', k: '抽帧点', v: list.join(' / ') })
      }
      rows.push({ key: 'k3', k: '音轨', v: meta.has_audio ? '有声' : '无声' })
      this.boneRows = rows

      this.summaryText = r.summary || ''
      const m = r.motion || {}
      this.rhythmText = m.scene_rhythm || ''
      this.moveText = (m.camera_moves || []).join(' / ') + (m.pacing ? (m.camera_moves && m.camera_moves.length ? ' · ' : '') + m.pacing : '')
      this.promptText = r.reusable_prompt || ''

      const vs = r.visual_style || {}
      const srows = []
      const slots = [['lighting', '光线'], ['palette', '色彩'], ['composition', '构图'], ['camera', '镜头']]
      for (let i = 0; i < slots.length; i++) {
        if (vs[slots[i][0]]) srows.push({ key: 's' + i, k: slots[i][1], v: String(vs[slots[i][0]]) })
      }
      this.styleRows = srows
    },

    copyPrompt() {
      if (!this.promptText) return
      uni.setClipboardData({ data: this.promptText })
    },

    async startNew() {
      if (this.creating) return
      if (!this.name.trim()) {
        uni.showToast({ title: '先填商品名称', icon: 'none' })
        return
      }
      this.creating = true
      try {
        const product = {
          name: this.name.trim(),
          points: this.points.split('\n').map((s) => s.trim()).filter(Boolean),
          facts: '',
          audience: '',
          category: this.cat,
          price: '',
          platform: '',
          images: [],
        }
        const answers = { form: '情景短剧', duration: this.duration, role: this.role, mode: this.mode }
        const doc = await dramaCreate(product, answers)
        if (this.tplId) {
          try { await dramaRefTemplate(doc.id, this.tplId) } catch (e) {
            uni.showToast({ title: '结构模板没挂上', icon: 'none' })
          }
        }
        uni.redirectTo({ url: '/pages/drama/script?id=' + doc.id })
      } catch (e) {
        uni.showToast({ title: e.message || '创建失败', icon: 'none' })
      }
      this.creating = false
    },
  },
}
</script>

<style scoped>
.cl-head { padding: 4rpx 0 18rpx; }
.cl-title { font-size: 34rpx; font-weight: 700; color: #1b1f27; }
.cl-sub { margin-top: 8rpx; font-size: 21rpx; color: #9aa0a6; line-height: 1.6; }
.cl-file { font-size: 24rpx; color: #1b1f27; padding: 10rpx 0; }
.cl-ops { display: flex; flex-wrap: wrap; gap: 12rpx; padding: 8rpx 0; }
.cl-tip { font-size: 20rpx; color: #9aa0a6; line-height: 1.6; padding: 8rpx 0; }
.cl-err { font-size: 21rpx; color: #c62828; padding: 8rpx 0; }
.cl-row {
  display: flex;
  align-items: flex-start;
  gap: 12rpx;
  padding: 10rpx 0;
  border-bottom: 1rpx solid #f2f4f7;
}
.cl-k { flex: none; width: 120rpx; font-size: 21rpx; color: #9aa0a6; }
.cl-v { flex: 1; font-size: 23rpx; color: #1b1f27; line-height: 1.6; }
.cl-quote {
  margin-top: 10rpx;
  padding: 14rpx 16rpx;
  border-radius: 10rpx;
  background: #f7f8fa;
  font-size: 22rpx;
  color: #4b5563;
  line-height: 1.7;
}
.cl-line { margin-top: 10rpx; font-size: 22rpx; color: #4b5563; line-height: 1.7; }
.cl-block { margin-top: 18rpx; }
.cl-sub2 { font-size: 21rpx; color: #9aa0a6; padding-bottom: 4rpx; }
.btn-main.dim { opacity: 0.6; }
.opt-sub { margin-left: 8rpx; font-size: 18rpx; color: #9aa0a6; }
</style>
