<template>
  <DramaAppShell>
    <view class="ds">
      <view class="page-wrap">
        <view class="sc-head">
          <view class="sc-title">示例展示</view>
          <view class="sc-sub">挑一条已经跑完的片子当范例：看成片、看逐镜脚本、看它用的结构。全部是你自己的真实项目，不是内置假数据。</view>
        </view>

        <!-- 1 选一条项目 -->
        <view class="card">
          <view class="card-head">
            <view class="card-title"><text class="card-no">片</text>选一条项目</view>
          </view>
          <view v-if="!projRows.length" class="empty">还没有项目 —— 先去建一条，跑完再回来看</view>
          <view class="sc-chips">
            <view
              v-for="p in projRows"
              :key="p.id"
              :class="['sc-chip', pid === p.id ? 'on' : '']"
              @click="pick(p)"
            >{{ p.name }}</view>
          </view>
        </view>

        <!-- 2 成片 -->
        <view v-if="pid" class="card">
          <view class="card-head">
            <view class="card-title"><text class="card-no">看</text>成片</view>
            <view class="btn-mini" @click="goExport">去导出 ›</view>
          </view>
          <view v-if="!filmUrl" class="empty">这条还没有合成成片（在「视频」页合成后这里才有）</view>
          <block v-else>
            <video class="sc-video" :src="filmUrl" controls object-fit="contain" />
            <view class="sc-meta">{{ metaText }}</view>
          </block>
        </view>

        <!-- 3 逐镜脚本 -->
        <view v-if="pid" class="card">
          <view class="card-head">
            <view class="card-title"><text class="card-no">镜</text>逐镜脚本</view>
            <view class="btn-mini" @click="goScript">打开这条项目 ›</view>
          </view>
          <view v-if="!shotRows.length" class="empty">这条还没有分镜</view>
          <view v-for="s in shotRows" :key="s.key" class="sc-shot">
            <view class="sc-shot-head">
              <text class="sc-no">{{ s.no }}</text>
              <text class="sc-time">{{ s.time }}</text>
              <text class="sc-cam">{{ s.camera }}</text>
            </view>
            <view class="sc-desc">{{ s.desc }}</view>
            <view v-if="s.line" class="sc-line">🎙 {{ s.line }}</view>
          </view>
        </view>

        <!-- 4 参考结构 -->
        <view class="card">
          <view class="card-head">
            <view class="card-title"><text class="card-no">结</text>参考结构</view>
          </view>
          <view v-if="!tplRows.length" class="empty">还没有存过结构模板（分镜页「存成结构模板」跑过的片子可以复用）</view>
          <view v-for="t in tplRows" :key="t.key" class="sc-tpl">
            <view class="sc-tpl-name">{{ t.name }}</view>
            <view class="sc-tpl-meta">{{ t.meta }}</view>
          </view>
        </view>

        <view class="sc-cta" @click="goNew">＋ 照着这些结构开新片</view>
      </view>
    </view>
  </DramaAppShell>
</template>

<script>
/**
 * 示例展示（照竞品 examples/showcase 的定位）
 *
 * 竞品那页放的是**内置示例数据**（`lib/examples` 里写死的一整条示例片 + 三张结构卡）。
 * 我们没有内置示例，也不许现编剧本/台词（硬规矩），所以这页改成
 * **从用户自己的项目里挑一条当范例**：成片用 `compose.outputs.mp4`、逐镜读
 * `storyboard_json.shots`、结构卡读用户自己存的 `/script-templates`。
 * 能力对位（看一整条成片的成片/脚本/结构），内容全部真实，零编造。
 *
 * 🩸 mp-weixin 规矩（docs/DRAMA-UI-RESTRUCTURE.md 第十节）：
 * 所有 v-for 数组（projRows / shotRows / tplRows）都是 data 顶层，值在 pick() 里算好。
 */
import { onLoad } from '@dcloudio/uni-app'
import DramaAppShell from '@/components/drama/AppShell.vue'
import { dramaList, dramaGet, dramaComposeUrl, dramaScriptTemplates } from '@/api/request'

export default {
  components: { DramaAppShell },
  data() {
    return {
      projRows: [],
      pid: '',
      projName: '',
      filmUrl: '',
      metaText: '',
      shotRows: [],
      tplRows: [],
      loading: false,
    }
  },
  onLoad() {
    this.loadProjects()
    this.loadTpls()
  },
  methods: {
    async loadProjects() {
      try {
        const rows = (await dramaList()) || []
        const out = []
        // 列表按更新时间倒序，取前 12 条够挑了；多的去「我的项目」翻
        for (let i = 0; i < rows.length && i < 12; i++) {
          out.push({ id: rows[i].id, name: rows[i].name || '未命名' })
        }
        this.projRows = out
      } catch (e) { this.projRows = [] }
      if (this.projRows.length) this.pick(this.projRows[0])
    },
    async loadTpls() {
      try {
        const r = await dramaScriptTemplates()
        const list = Array.isArray(r) ? r : ((r && r.templates) || [])
        this.tplRows = list.map((t, i) => ({
          key: 't' + i,
          name: t.name || '未命名结构',
          meta: (t.shots_count || 0) + ' 镜 · 共 ' + (t.total_duration || 0) + ' 秒'
            + (t.use_count ? ' · 用过 ' + t.use_count + ' 次' : ''),
        }))
      } catch (e) { this.tplRows = [] }
    },
    async pick(p) {
      if (this.loading) return
      this.loading = true
      this.pid = p.id
      this.projName = p.name
      this.filmUrl = ''
      this.metaText = ''
      this.shotRows = []
      let doc = null
      try { doc = await dramaGet(p.id) } catch (e) {
        uni.showToast({ title: '打开失败', icon: 'none' })
      }
      if (doc) this.buildShow(doc)
      this.loading = false
    },
    /** 把项目文档算成这页要显示的值（mp 端只认 data 顶层数组） */
    buildShow(doc) {
      const out = (doc.compose && doc.compose.outputs) || {}
      if (out.mp4) this.filmUrl = dramaComposeUrl(doc.id)

      const sj = doc.storyboard_json || {}
      const shots = sj.shots || []
      const rows = []
      let acc = 0
      for (let i = 0; i < shots.length; i++) {
        const s = shots[i]
        const dur = Number(s.duration) || 0
        const start = Math.round(acc)
        acc += dur
        const end = Math.round(acc)
        rows.push({
          key: 's' + i,
          no: String(i + 1).padStart(2, '0'),
          time: start + '-' + end + 's',
          camera: s.camera || s.framing || '',
          desc: s.description || '',
          line: s.dialogue || '',
        })
      }
      this.shotRows = rows

      const total = Math.round(acc)
      const res = (doc.film && doc.film.resolution) || '默认'
      this.metaText = shots.length + ' 镜 · 共 ' + total + ' 秒 · ' + res
    },
    goScript() {
      uni.redirectTo({ url: '/pages/drama/script?id=' + this.pid })
    },
    goExport() {
      uni.redirectTo({ url: '/pages/drama/export?id=' + this.pid })
    },
    goNew() {
      uni.reLaunch({ url: '/pages/drama/new' })
    },
  },
}
</script>

<style scoped>
.sc-head { padding: 4rpx 0 18rpx; }
.sc-title { font-size: 34rpx; font-weight: 700; color: #1b1f27; }
.sc-sub { margin-top: 8rpx; font-size: 21rpx; color: #9aa0a6; line-height: 1.6; }
.sc-chips { display: flex; flex-wrap: wrap; gap: 12rpx; padding: 6rpx 0; }
.sc-chip {
  font-size: 22rpx;
  padding: 8rpx 18rpx;
  border-radius: 999rpx;
  background: #f0f2f5;
  color: #4b5563;
}
.sc-chip.on { background: #e8f8f2; color: #0b8f6b; font-weight: 600; }
.sc-video { width: 100%; height: 720rpx; background: #000; border-radius: 12rpx; }
.sc-meta { margin-top: 10rpx; font-size: 21rpx; color: #9aa0a6; }
.sc-shot { padding: 16rpx 0; border-bottom: 1rpx solid #f2f4f7; }
.sc-shot-head { display: flex; align-items: center; gap: 14rpx; }
.sc-no { font-size: 21rpx; color: #9aa0a6; font-family: monospace; }
.sc-time { font-size: 19rpx; padding: 2rpx 10rpx; border-radius: 6rpx; background: #f0f2f5; color: #6b7280; }
.sc-cam { margin-left: auto; font-size: 20rpx; color: #9aa0a6; }
.sc-desc { margin-top: 6rpx; font-size: 24rpx; color: #1b1f27; line-height: 1.6; }
.sc-line { margin-top: 4rpx; font-size: 21rpx; color: #6b7280; }
.sc-tpl { padding: 14rpx 0; border-bottom: 1rpx solid #f2f4f7; }
.sc-tpl-name { font-size: 25rpx; color: #1b1f27; font-weight: 600; }
.sc-tpl-meta { margin-top: 4rpx; font-size: 21rpx; color: #9aa0a6; }
.sc-cta {
  margin: 20rpx 0 40rpx;
  padding: 26rpx;
  text-align: center;
  border-radius: 16rpx;
  background: linear-gradient(150deg, #12b886 0%, #0b8f6b 100%);
  color: #fff;
  font-size: 27rpx;
  font-weight: 600;
}
</style>
