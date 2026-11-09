<template>
  <DramaAppShell>
    <view class="ds">
      <DramaProjectHeader :id="pid" current="production" :name="headerName" :chips="chips" />

      <view v-if="!cur" class="pgstate">正在加载项目…</view>

      <block v-if="cur">
        <!-- 1 工序：这条片子走到哪一步了 -->
        <view class="card">
          <view class="card-head">
            <view class="card-title"><text class="card-no">序</text>工序</view>
            <view class="btn-mini" @click="go('script')">去脚本 ›</view>
          </view>
          <view class="pd-steps">
            <view class="pd-step" :class="cur.view.stepScript.state">
              <text class="pd-step-mark">{{ cur.view.stepScript.icon }}</text>
              <text class="pd-step-name">脚本</text>
              <text class="pd-step-note">{{ cur.view.stepScript.note }}</text>
            </view>
            <view class="pd-step" :class="cur.view.stepAssets.state">
              <text class="pd-step-mark">{{ cur.view.stepAssets.icon }}</text>
              <text class="pd-step-name">素材</text>
              <text class="pd-step-note">{{ cur.view.stepAssets.note }}</text>
            </view>
            <view class="pd-step" :class="cur.view.stepVideo.state">
              <text class="pd-step-mark">{{ cur.view.stepVideo.icon }}</text>
              <text class="pd-step-name">视频</text>
              <text class="pd-step-note">{{ cur.view.stepVideo.note }}</text>
            </view>
            <view class="pd-step" :class="cur.view.stepExport.state">
              <text class="pd-step-mark">{{ cur.view.stepExport.icon }}</text>
              <text class="pd-step-name">导出</text>
              <text class="pd-step-note">{{ cur.view.stepExport.note }}</text>
            </view>
          </view>
        </view>

        <!-- 2 视觉记忆：这一片子的"世界设定" -->
        <view class="card">
          <view class="card-head">
            <view class="card-title"><text class="card-no">忆</text>视觉记忆</view>
            <view class="btn-mini" @click="go('assets')">人物与场景 ›</view>
          </view>
          <view class="pd-grid">
            <view class="pd-kv">
              <text class="pd-k">{{ cur.view.bible1k }}</text>
              <text class="pd-v">{{ cur.view.bible1v }}</text>
            </view>
            <view class="pd-kv">
              <text class="pd-k">{{ cur.view.bible2k }}</text>
              <text class="pd-v">{{ cur.view.bible2v }}</text>
            </view>
            <view class="pd-kv">
              <text class="pd-k">{{ cur.view.bible3k }}</text>
              <text class="pd-v">{{ cur.view.bible3v }}</text>
            </view>
          </view>
          <view class="merge-tip">人物 {{ cur.view.castCount }} 个｜关键帧 {{ cur.view.gridText }}</view>
        </view>

        <!-- 3 质量门 -->
        <view class="card">
          <view class="card-head">
            <view class="card-title"><text class="card-no">门</text>质量门</view>
            <view class="btn-mini" @click="go('export')">发布门禁 ›</view>
          </view>
          <view class="pd-row">
            <text class="pd-k">结构自检</text>
            <text class="pd-tag" :class="cur.view.checkTone">{{ cur.view.checkLabel }}</text>
          </view>
          <view class="pd-row">
            <text class="pd-k">发布门禁</text>
            <text class="pd-tag" :class="cur.view.readinessTone">{{ cur.view.readinessLabel }}</text>
          </view>
          <view class="pd-row">
            <text class="pd-k">出片质检</text>
            <text class="pd-tag" :class="cur.view.qcTone">{{ cur.view.qcLabel }}</text>
          </view>
          <view v-if="cur.view.blockerText" class="film-warn">{{ cur.view.blockerText }}</view>
        </view>

        <!-- 4 版本 -->
        <view class="card">
          <view class="card-head">
            <view class="card-title"><text class="card-no">版</text>版本</view>
            <view class="btn-mini" @click="go('script')">切版本 ›</view>
          </view>
          <view v-if="!vsRows.length" class="empty">还没有存稿版本</view>
          <view v-for="s in vsRows" :key="s.key" class="pd-row">
            <text class="pd-k">{{ s.label }}</text>
            <text class="pd-v">{{ s.title }}</text>
            <text v-if="s.picked" class="pd-tag ok">分镜按这版</text>
          </view>
          <view class="pd-row">
            <text class="pd-k">已出片</text>
            <text class="pd-v">{{ cur.view.doneText }}</text>
          </view>
        </view>

        <!-- 5 模型路由 -->
        <view class="card">
          <view class="card-head">
            <view class="card-title"><text class="card-no">路</text>模型与档位</view>
            <!-- 🩸 型号/清晰度/画面比例都在素材页的「出片设置」卡；原来跳 video 页（那里没有这些控件） -->
            <view class="btn-mini" @click="go('assets')">去出片设置 ›</view>
          </view>
          <view class="pd-row"><text class="pd-k">视频模型</text><text class="pd-v">{{ cur.view.filmModelText }}</text></view>
          <view class="pd-row"><text class="pd-k">接缝链</text><text class="pd-v">{{ cur.view.chainText }}</text></view>
          <view class="pd-row"><text class="pd-k">分辨率</text><text class="pd-v">{{ cur.view.resolutionText }}</text></view>
          <view class="pd-row"><text class="pd-k">画面比例</text><text class="pd-v">{{ cur.view.ratioText }}</text></view>
          <view class="pd-row"><text class="pd-k">真实感</text><text class="pd-v">{{ cur.view.realismName }}</text></view>
          <view class="pd-row"><text class="pd-k">渲染质量</text><text class="pd-v">{{ cur.view.qualityName }}</text></view>
        </view>

        <!-- 6 语义资产 -->
        <view class="card">
          <view class="card-head">
            <view class="card-title"><text class="card-no">资</text>素材资产</view>
            <view class="btn-mini" @click="go('assets')">去素材 ›</view>
          </view>
          <view class="pd-row"><text class="pd-k">素材库</text><text class="pd-v">{{ cur.view.materialCountText }}</text></view>
          <view class="pd-row"><text class="pd-k">长视频原料</text><text class="pd-v">{{ cur.view.mediaCountText }}</text></view>
          <view class="pd-row"><text class="pd-k">关键帧</text><text class="pd-v">{{ cur.view.gridText }}</text></view>
          <view class="pd-row"><text class="pd-k">成片片段</text><text class="pd-v">{{ cur.view.doneText }}</text></view>
        </view>

        <!-- 7 诊断 -->
        <view class="card">
          <view class="card-head">
            <view class="card-title"><text class="card-no">诊</text>诊断</view>
          </view>
          <view v-if="!dgRows.length" class="empty">没有发现异常</view>
          <view v-for="d in dgRows" :key="d.key" class="film-warn">{{ d.text }}</view>
        </view>

        <!-- 8 预览与出口 -->
        <view class="card">
          <view class="card-head">
            <view class="card-title"><text class="card-no">看</text>预览与出口</view>
          </view>
          <view class="pd-actions">
            <view class="btn-mini" @click="go('assets')">看出片</view>
            <view class="btn-mini" @click="go('video')">去合成</view>
            <view class="btn-mini" @click="go('export')">去导出</view>
          </view>
          <view class="merge-tip">这个页面只读：看清整条生产线状态，操作在各步页面做。</view>
        </view>
      </block>
    </view>
  </DramaAppShell>
</template>

<script>
/**
 * 导演台 · 生产控制台（照竞品 app/project/[id]/production/page.tsx）
 *
 * 竞品 9 个 Section 都是**只读聚合**：工序 / 视觉记忆 / 质量门 / 版本 /
 * 模型路由 / 语义资产 / 诊断 / 预览。数据全在 `GET /projects/{pid}` 一个文档里，
 * 不需要新接口 —— 所以这页只读、只做聚合与跳转，不改任何状态。
 *
 * 🩸 小程序端（mp-weixin）2026-11-07 真机排查出来的三条硬规矩：
 * 1. 页面模板里**不绑 computed**。uni 的 mp 渲染只在首次渲染（cur 还是 null）时取一次，
 *    之后 cur 有值了也不跟进，整页会停在「正在加载项目…」。
 *    → 所有要显示的值在 onLoad 里算好落进 data（`fillView`），模板只读 data。
 * 2. 这页**不用 v-for**（列表按固定几行展开 + v-if）。mp 端只要模板里出现 v-for，
 *    整页 setData 就会停更，页面永远停在首屏状态。
 * 3. 不用原生 `<button>`，用 `<view class="btn-mini">`。
 */
import DramaAppShell from '@/components/drama/AppShell.vue'
import DramaProjectHeader from '@/components/drama/ProjectHeader.vue'
import dramaPageBoot from '@/mixins/dramaPageBoot'
import { dramaGet, dramaMediaList, dramaMaterials } from '@/api/request'

const EMPTY_STEP = { icon: '·', state: '', note: '' }

export default {
  components: { DramaAppShell, DramaProjectHeader },
  mixins: [dramaPageBoot],
  data() {
    // pid / cur 由 mixin 提供，这里不要重复声明（重复声明会盖掉 mixin 的响应式）
    return {
      materials: [],
      media: [],
      vsRows: [],
      dgRows: [],
    }
  },
  computed: {
    // 只给子组件 props 用（props 走 `u-p` 通道，不受上面第 1 条影响）
    headerName() {
      return (this.cur && this.cur.product && this.cur.product.name) || '商品短剧'
    },
    chips() {
      if (!this.cur) return []
      const a = this.cur.answers || {}
      return [a.duration ? a.duration + '秒' : '', a.form, a.role].filter(Boolean)
    },
  },
  async onLoad(q) {
    const pid = (q && q.id) || ''
    this.pid = pid
    if (!pid) {
      uni.showToast({ title: '缺少项目号', icon: 'none' })
      return
    }

    let doc = null
    let mats = []
    let media = []
    try { doc = await dramaGet(pid) } catch (e) { uni.showToast({ title: '打开失败', icon: 'none' }) }
    try { mats = (await dramaMaterials(pid)).materials || [] } catch (e) { /* 素材拉不到不影响主体 */ }
    try { media = (await dramaMediaList(pid)).sources || [] } catch (e) { /* 长视频拉不到不影响主体 */ }
    let vv = null
    try { vv = this.buildView(doc, mats, media) } catch (e) { /* 视图值算不出来就保持空态，不影响打开 */ }

    // 🩸 视图值挂在 cur.view 上一次性交出去 —— 小程序端只认 mixin 的 cur 这一条响应式链路
    if (doc && vv) doc.view = vv
    this.cur = doc
  },
  methods: {
    /** 把项目文档算成这页要显示的一整套值（全部落 data，模板不碰 computed） */
    buildView(doc, mats, media) {
      const view = {}
      const c = doc || {}
      const film = c.film || {}
      const plan = film.plan || null
      const segs = (plan && plan.segments) || []
      const files = film.files || {}
      const grid = c.grid || {}
      const cells = grid.cells || []
      const readiness = c.readiness || {}
      const answers = c.answers || {}

      let doneN = 0
      for (let i = 0; i < segs.length; i++) {
        const s = segs[i]
        if (files[s.no || s.index]) doneN++
      }
      const gridDone = cells.filter((x) => x && x.file).length
      const gridTotal = cells.length
      view.gridText = gridDone + '/' + gridTotal
      view.doneText = doneN + '/' + segs.length + ' 段'
      view.materialCountText = mats.length + ' 条'
      view.mediaCountText = media.length + ' 条'

      const ready = readiness.overall === 'ready'
      const readyLabel = { ready: '可发布', risky: '有风险', needsWork: '建议先改' }[readiness.overall] || '未检查'
      view.stepScript = {
        icon: c.card_confirmed ? '✓' : '·',
        state: c.card_confirmed ? 'done' : '',
        note: c.script ? '有剧本' : '待写',
      }
      view.stepAssets = {
        icon: (gridDone >= gridTotal && gridTotal) ? '✓' : '·',
        state: (gridDone >= gridTotal && gridTotal) ? 'done' : '',
        note: '关键帧 ' + gridDone + '/' + gridTotal,
      }
      view.stepVideo = {
        icon: (doneN >= segs.length && segs.length) ? '✓' : '·',
        state: (doneN >= segs.length && segs.length) ? 'done' : '',
        note: '出片 ' + doneN + '/' + segs.length,
      }
      view.stepExport = { icon: ready ? '✓' : '·', state: ready ? 'done' : '', note: readyLabel }

      const bible = c.visual_bible || {}
      const slots = [
        ['look', '画面基调'], ['palette', '色彩'], ['lighting', '光线'],
        ['camera', '镜头'], ['texture', '质感'], ['world', '世界观'],
      ]
      const filled = slots.filter((s) => bible[s[0]])
      if (filled.length) {
        view.bible1k = filled[0][1]; view.bible1v = String(bible[filled[0][0]])
        view.bible2k = filled[1] ? filled[1][1] : ''; view.bible2v = filled[1] ? String(bible[filled[1][0]]) : ''
        view.bible3k = filled[2] ? filled[2][1] : ''; view.bible3v = filled[2] ? String(bible[filled[2][0]]) : ''
      } else {
        view.bible1k = '视觉圣经'; view.bible1v = '还没定（在素材页定完关键帧会有）'
        view.bible2k = ''; view.bible2v = ''
        view.bible3k = ''; view.bible3v = ''
      }
      view.castCount = (c.cast || []).length

      view.checkLabel = c.check ? '已自检' : '未自检'
      view.checkTone = c.check ? 'ok' : 'dim'
      view.readinessLabel = readyLabel
      view.readinessTone = { ready: 'ok', risky: 'warn', needsWork: 'bad' }[readiness.overall] || 'dim'
      const blockers = readiness.blockers || []
      view.blockerText = blockers.length
        ? '⚠ 还差 ' + blockers.length + ' 条：' + blockers.slice(0, 3).join('；')
        : ''
      const qc = film.qc || film.quality
      if (!qc) { view.qcLabel = '未跑'; view.qcTone = 'dim' }
      else if (qc.passed === false || qc.ok === false) { view.qcLabel = '有问题'; view.qcTone = 'bad' }
      else { view.qcLabel = '通过'; view.qcTone = 'ok' }

      const realismMap = { auto: '自动（按品类）', constraints: '强约束', off: '关闭' }
      const qualityMap = { fast: '快速 720p', standard: '标准 1080p', high: '高码率' }
      view.filmModelText = film.model || '未选（用全局默认）'
      view.chainText = film.chain || '未选'
      view.resolutionText = film.resolution || '默认'
      view.ratioText = film.ratio || '9:16'
      view.realismName = realismMap[film.realism] || film.realism || '默认'
      view.qualityName = qualityMap[answers.quality] || answers.quality || '标准'

      const picked = c.storyboard_script_id || ''
      const vs = c.scripts || []
      this.vsRows = vs.slice(0, 3).map((s, i) => ({
        key: 'v' + i,
        label: '脚本 v' + s.version,
        title: s.title || '未命名',
        picked: s.id === picked,
      }))

      const rows = []
      const rej = film.rejects || []
      for (let i = 0; i < rej.length && i < 2; i++) {
        const r = rej[i]
        rows.push('⚠ 第 ' + r.no + ' 镜被拒' + (r.reason ? '：' + r.reason : ''))
      }
      const lints = c.storyboard_lints || []
      for (let i = 0; i < lints.length && rows.length < 4; i++) {
        rows.push('⚠ 分镜提示：' + lints[i])
      }
      this.dgRows = rows.map((text, i) => ({ key: 'd' + i, text }))
      return view
    },
    go(step) {
      const route = { script: 'script', assets: 'assets', video: 'video', export: 'export' }[step]
      if (!route) return
      uni.redirectTo({ url: `/pages/drama/${route}?id=${this.pid}` })
    },
  },
}
</script>

<style scoped>
.pd-steps { display: flex; flex-wrap: wrap; gap: 12rpx; }
.pd-step {
  flex: 1 1 150rpx;
  padding: 16rpx;
  border-radius: 12rpx;
  background: #f7f8fa;
  display: flex;
  flex-direction: column;
  gap: 4rpx;
}
.pd-step.done { background: #e8f8f2; }
.pd-step-mark { font-size: 24rpx; color: #0b8f6b; }
.pd-step-name { font-size: 26rpx; font-weight: 600; color: #1b1f27; }
.pd-step-note { font-size: 20rpx; color: #9aa0a6; }
.pd-grid { display: flex; flex-wrap: wrap; }
.pd-kv { width: 50%; padding: 8rpx 0; }
.pd-k { display: block; font-size: 20rpx; color: #9aa0a6; }
.pd-v { display: block; font-size: 24rpx; color: #1b1f27; margin-top: 2rpx; }
.pd-row {
  display: flex;
  align-items: center;
  gap: 12rpx;
  padding: 12rpx 0;
  border-bottom: 1rpx solid #f2f4f7;
}
.pd-tag {
  margin-left: auto;
  font-size: 20rpx;
  padding: 4rpx 12rpx;
  border-radius: 999rpx;
  background: #f0f2f5;
  color: #6b7280;
}
.pd-tag.ok { background: #e8f8f2; color: #0b8f6b; }
.pd-tag.warn { background: #fff6e5; color: #a06400; }
.pd-tag.bad { background: #fdecec; color: #c62828; }
.pd-tag.dim { background: #f0f2f5; color: #9aa0a6; }
.pd-actions { display: flex; flex-wrap: wrap; gap: 12rpx; padding: 8rpx 0; }
</style>
