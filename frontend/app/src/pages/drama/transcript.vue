<template>
  <DramaAppShell>
    <view class="ds">
      <DramaProjectHeader :id="pid" current="assets" :name="headerName" :chips="chips" />

      <view v-if="!cur" class="pgstate">正在加载项目…</view>

      <block v-if="cur">
        <!-- ① 原片：导入 + 转写状态（照竞品 transcript 头顶的「导入原片 / 本地转写」两段） -->
        <view class="card">
          <view class="card-head">
            <view class="card-title"><text class="card-no">片</text>原片</view>
            <view class="btn-mini" :disabled="mediaBusy" @click="pickMedia">
              {{ mediaBusy ? ('导入中 ' + mediaPct + '%') : '导入原片' }}
            </view>
          </view>
          <view class="tx-tip">
            MP4 / MOV / WebM / MKV / M4V，最大 1GB。音频在服务端转写，原片不会发给内容平台；
            转写按 5 分钟一块存检查点，断了从断点接着来。
          </view>

          <view v-if="!mediaRows.length" class="empty">还没有导入视频 —— 点右上「导入原片」</view>
          <view v-for="m in mediaRows" :key="m.id" class="tx-row">
            <view class="tx-main" @click="pick(m)">
              <view class="tx-name">
                {{ m.original_name }}
                <text class="tx-tag">{{ m.has_audio ? '有声' : '无声' }}</text>
                <text v-if="m.status === 'ready'" class="tx-tag ok">已转写</text>
                <text v-if="m.status === 'transcribing'" class="tx-tag warn">转写中</text>
                <text v-if="m.status === 'failed'" class="tx-tag bad">失败</text>
              </view>
              <view class="tx-meta">{{ mediaMeta(m) }}</view>
              <view v-if="m.status === 'transcribing'" class="tx-bar">
                <view class="tx-bar-in" :style="{ width: (m.progress || 0) + '%' }"></view>
              </view>
              <view v-if="m.status === 'failed'" class="tx-err">{{ m.error }}</view>
              <view v-if="m.status === 'ready' && m.transcript_summary" class="tx-meta">
                {{ m.transcript_summary.chars }} 字 · {{ m.transcript_summary.segments }} 句
                <text class="tx-link">{{ m.id === pickedId ? '正在看这段' : '看分段 ›' }}</text>
              </view>
            </view>
            <view class="tx-ops">
              <view class="btn-mini" @click.stop="openMedia(m)">播放</view>
              <view v-if="m.has_audio && m.status !== 'transcribing'" class="btn-mini"
                    @click.stop="startTranscribe(m)">
                {{ m.status === 'ready' ? '重转' : '转写' }}
              </view>
              <view v-if="m.status === 'transcribing'" class="btn-mini"
                    @click.stop="cancelTranscribe(m)">停</view>
            </view>
          </view>
        </view>

        <!-- ② 转写正文：搜索 + 分段翻页（竞品 wordSearch / wordPage） -->
        <view class="card">
          <view class="card-head">
            <view class="card-title"><text class="card-no">文</text>转写正文</view>
            <view v-if="pickedId" class="btn-mini" @click="copyAll">复制全文</view>
          </view>

          <view v-if="!pickedId" class="empty">上面点一条已转写的视频，这里按时码列全文</view>
          <view v-else-if="segsLoading" class="empty">正在取转写…</view>
          <view v-else-if="!segAll.length" class="empty">这条还没有转写结果</view>
          <block v-else>
            <view class="tx-cur">{{ pickedName }}</view>

            <input v-model="q" class="input line" placeholder="搜索完整转写稿" @input="applySearch" />
            <view class="tx-search">
              <text class="tx-tip">{{ q ? ('匹配 ' + matchCount + ' 句') : ('共 ' + segAll.length + ' 句') }}</text>
              <text v-if="q" class="tx-link" @click="clearSearch">清空</text>
            </view>

            <view v-for="s in segs" :key="s.key" class="tx-seg">
              <text class="tx-time" @click="copyText(s.time + ' ' + s.text)">{{ s.time }}</text>
              <text class="tx-text">{{ s.text }}</text>
            </view>
            <view v-if="!segs.length" class="empty">没有包含「{{ q }}」的句子</view>

            <view v-if="pageCount > 1" class="tx-pager">
              <view class="btn-mini" :class="{ off: page <= 0 }" @click="goPage(-1)">上一段</view>
              <text class="tx-pageno">第 {{ page + 1 }} / {{ pageCount }} 段</text>
              <view class="btn-mini" :class="{ off: page >= pageCount - 1 }" @click="goPage(1)">下一段</view>
            </view>
          </block>
        </view>

        <!-- ③ 片段工作台：按原话找片段 → 只保留这段（竞品 clips 区） -->
        <view class="card">
          <view class="card-head">
            <view class="card-title"><text class="card-no">段</text>片段工作台</view>
            <view class="btn-mini" :disabled="!pickedId || clipBusy" @click="findClips">
              {{ clipBusy ? '查找中…' : '找片段' }}
            </view>
          </view>
          <view class="tx-tip">按原话、句子和停顿整理片段建议；时长尽量贴完整句子。本地算，不花生成费。</view>

          <input v-model="clipQ" class="input line" placeholder="输入商品、卖点或一句话，留空看建议" />
          <view class="tx-chips">
            <view v-for="n in clipTargets" :key="'ct' + n"
                  :class="['tx-chip', clipTarget === n ? 'on' : '']"
                  @click="clipTarget = n">{{ n }} 秒</view>
          </view>

          <view v-if="!pickedId" class="empty">先在上面选一条已转写的原片</view>
          <view v-else-if="!clipRows.length && !clipBusy" class="empty">点「找片段」整理候选</view>
          <view v-for="c in clipRows" :key="c.id" class="clip-card">
            <view class="clip-text">{{ c.text }}</view>
            <view class="clip-meta">
              {{ c.duration }}s · 说话占比 {{ c.speechPct }}% · {{ c.reason }}
            </view>
            <view class="clip-ops">
              <view class="btn-mini" @click="playSource">预览原片</view>
              <view v-if="!c.out" class="btn-mini" @click="cutOne(c)">只保留这段</view>
              <view v-else class="btn-mini" @click="openCut(c)">
                已剪好 {{ c.out.duration }}s · 打开
              </view>
            </view>
          </view>
        </view>

        <!-- ④ 出口 -->
        <view class="card">
          <view class="card-head">
            <view class="card-title"><text class="card-no">用</text>拿这段文字做什么</view>
          </view>
          <view class="tx-actions">
            <view class="btn-mini" @click="goAssets">按文字剪（选关键词找片段）</view>
            <view class="btn-mini" @click="goScript">回脚本 ›</view>
          </view>
          <view class="tx-tip">按文字剪在素材页：挑一段话、剪成片段当分镜画面，本地算不花生成费。</view>
        </view>
      </block>
    </view>
  </DramaAppShell>
</template>

<script>
/**
 * 转写工作台（照竞品 app/project/[id]/transcript/page.tsx 的定位）
 *
 * 竞品那页是「浏览器本地 ASR + 时间轴编辑」；我们走**服务端转写**（火山）。
 * 结构上对齐它真正在用的四段：导入原片 → 转写正文（可搜索、分段翻页）→
 * 片段工作台（按原话找片段 / 只保留这段）→ 出口。
 * 🩸 竞品有、我们**没有对应后端**的三块不假装：本地模型选择、词级删口癖编辑、
 * 批量输出队列（最多 12 条）。要做得先补后端，不在页面上放假开关。
 */
import { onUnload } from '@dcloudio/uni-app'
import DramaAppShell from '@/components/drama/AppShell.vue'
import DramaProjectHeader from '@/components/drama/ProjectHeader.vue'
import dramaPageBoot from '@/mixins/dramaPageBoot'
import {
  dramaMediaTranscript, dramaMediaClips, dramaMediaClipCut, dramaMediaClipUrl,
} from '@/api/request'

function mmss(sec) {
  const s = Math.max(0, Math.round(Number(sec) || 0))
  const m = Math.floor(s / 60)
  const r = s % 60
  return m + ':' + (r < 10 ? '0' + r : r)
}

export default {
  components: { DramaAppShell, DramaProjectHeader },
  mixins: [dramaPageBoot],
  data() {
    return {
      pickedId: '',
      pickedName: '',
      segAll: [],
      segs: [],
      segsLoading: false,
      fullText: '',
      q: '',
      matchCount: 0,
      page: 0,
      pageSize: 50,
      // 片段工作台（本页自己的候选列表，不碰 mixin 里按 m.id 存的那套）
      clipQ: '',
      clipTarget: 30,
      clipTargets: [15, 30, 60],
      clipRows: [],
      clipBusy: false,
      pickedMedia: null,
    }
  },
  computed: {
    headerName() {
      return (this.cur && this.cur.product && this.cur.product.name) || '商品短剧'
    },
    chips() {
      if (!this.cur) return []
      const a = this.cur.answers || {}
      return [a.duration ? a.duration + '秒' : '', a.form, a.role].filter(Boolean)
    },
    pageCount() {
      // 以「搜索命中的句数」分页，不是全文句数（搜完仍按 50 句一页）
      return Math.max(1, Math.ceil(this.matchCount / this.pageSize))
    },
  },
  async onLoad(q) {
    const pid = (q && q.id) || ''
    this.pid = pid
    if (!pid) {
      uni.showToast({ title: '缺少项目号', icon: 'none' })
      return
    }
    await this.boot(pid)
    await this.safe(this.loadMedia)
    // 进来就挑第一条已转写的，省一次点击
    for (let i = 0; i < this.mediaRows.length; i++) {
      if (this.mediaRows[i].status === 'ready') { this.pick(this.mediaRows[i]); break }
    }
    if (this.mediaRows.some((m) => m.status === 'transcribing')) this.scheduleTrPoll()
  },
  onUnload() {
    if (this.trPoll) clearTimeout(this.trPoll)
    this.trPoll = null
  },
  methods: {
    async pick(m) {
      if (!m || m.status !== 'ready') {
        uni.showToast({ title: '这条还没转写', icon: 'none' })
        return
      }
      this.pickedId = m.id
      this.pickedName = m.original_name || ''
      this.pickedMedia = m
      this.segAll = []
      this.segs = []
      this.fullText = ''
      this.clipRows = []
      this.q = ''
      this.matchCount = 0
      this.page = 0
      this.segsLoading = true
      try {
        const r = await dramaMediaTranscript(this.cur.id, m.id)
        const t = (r && r.transcript && r.transcript.transcript) || {}
        const list = t.segments || []
        const out = []
        for (let i = 0; i < list.length; i++) {
          const s = list[i]
          out.push({
            key: 's' + i,
            time: mmss(s.start) + ' - ' + mmss(s.end),
            text: String(s.text || '').trim(),
            low: String(s.text || '').toLowerCase(),
          })
        }
        this.segAll = out
        this.fullText = t.text || ''
        this.renderPage()
      } catch (e) {
        uni.showToast({ title: '取转写失败', icon: 'none' })
      }
      this.segsLoading = false
    },
    /** 搜索只在本地过滤（竞品也是先把全文拿到浏览器再搜）；分页 50 句一段 */
    renderPage() {
      const kw = (this.q || '').trim().toLowerCase()
      const hit = kw ? this.segAll.filter((s) => s.low.indexOf(kw) >= 0) : this.segAll.slice()
      this.matchCount = hit.length
      const max = Math.max(1, Math.ceil(hit.length / this.pageSize))
      if (this.page > max - 1) this.page = max - 1
      if (this.page < 0) this.page = 0
      const from = this.page * this.pageSize
      this.segs = hit.slice(from, from + this.pageSize)
    },
    applySearch() {
      this.page = 0
      this.renderPage()
    },
    clearSearch() {
      this.q = ''
      this.page = 0
      this.renderPage()
    },
    goPage(d) {
      const next = this.page + d
      if (next < 0 || next > this.pageCount - 1) return
      this.page = next
      this.renderPage()
    },
    async findClips() {
      if (!this.cur || !this.pickedId || this.clipBusy) return
      this.clipBusy = true
      try {
        const r = await dramaMediaClips(this.cur.id, this.pickedId, {
          query: (this.clipQ || '').trim(),
          target_seconds: Number(this.clipTarget) || 30,
          limit: 6,
        })
        const rows = []
        const list = r.candidates || []
        for (let i = 0; i < list.length; i++) {
          const c = list[i]
          rows.push({
            id: c.id,
            text: String(c.text || '').trim(),
            duration: Number(c.duration).toFixed(1),
            speechPct: Math.round(Number(c.speech_ratio || 0) * 100),
            reason: this.clipReason(c.reasons),
            start: c.start,
            end: c.end,
            out: null,
          })
        }
        this.clipRows = rows
        if (!rows.length) uni.showToast({ title: '没找到合适的片段', icon: 'none' })
      } catch (e) {
        uni.showModal({ title: '找片段失败', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.clipBusy = false
      }
    },
    async cutOne(c) {
      if (!this.cur || this.clipBusy) return
      this.clipBusy = true
      try {
        const r = await dramaMediaClipCut(this.cur.id, this.pickedId, { start: c.start, end: c.end })
        const rows = this.clipRows.slice()
        for (let i = 0; i < rows.length; i++) {
          if (rows[i].id === c.id) rows[i] = { ...rows[i], out: r }
        }
        this.clipRows = rows
        uni.showToast({ title: '剪好了', icon: 'success' })
      } catch (e) {
        uni.showModal({ title: '剪不出来', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.clipBusy = false
      }
    },
    openCut(c) {
      if (!c.out) return
      this.previewFile(dramaMediaClipUrl(this.cur.id, this.pickedId, c.out.name), c.out.name, 'video')
    },
    playSource() {
      if (this.pickedMedia) this.openMedia(this.pickedMedia)
    },
    copyAll() {
      if (!this.fullText) {
        uni.showToast({ title: '还没有全文', icon: 'none' })
        return
      }
      uni.setClipboardData({ data: this.fullText })
    },
    copyText(t) {
      uni.setClipboardData({ data: String(t || '') })
    },
    goAssets() {
      uni.redirectTo({ url: '/pages/drama/assets?id=' + this.pid })
    },
    goScript() {
      uni.redirectTo({ url: '/pages/drama/script?id=' + this.pid })
    },
  },
}
</script>

<style scoped>
.pgstate { padding: 60rpx; text-align: center; color: #9aa0a6; font-size: 24rpx; }
.tx-tip { font-size: 20rpx; color: #9aa0a6; line-height: 1.6; padding: 6rpx 0 12rpx; }
.tx-row {
  display: flex;
  align-items: flex-start;
  gap: 14rpx;
  padding: 18rpx 0;
  border-bottom: 1rpx solid #f2f4f7;
}
.tx-main { flex: 1; min-width: 0; }
.tx-name { font-size: 26rpx; color: #1b1f27; font-weight: 600; }
.tx-tag {
  margin-left: 10rpx;
  font-size: 18rpx;
  padding: 2rpx 10rpx;
  border-radius: 999rpx;
  background: #f0f2f5;
  color: #6b7280;
}
.tx-tag.ok { background: #e8f8f2; color: #0b8f6b; }
.tx-tag.warn { background: #fff6e5; color: #a06400; }
.tx-tag.bad { background: #fdecec; color: #c62828; }
.tx-meta { margin-top: 6rpx; font-size: 21rpx; color: #9aa0a6; }
.tx-link { margin-left: 12rpx; color: #0b8f6b; }
.tx-err { margin-top: 6rpx; font-size: 21rpx; color: #c62828; }
.tx-bar { margin-top: 8rpx; height: 8rpx; border-radius: 4rpx; background: #eef0f4; overflow: hidden; }
.tx-bar-in { height: 8rpx; background: #0b8f6b; }
.tx-ops { flex: none; display: flex; flex-direction: column; gap: 8rpx; }
.tx-cur { font-size: 22rpx; color: #6b7280; padding: 8rpx 0; }
.tx-search {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4rpx 0 10rpx;
}
.tx-seg { display: flex; gap: 14rpx; padding: 10rpx 0; border-bottom: 1rpx dashed #f2f4f7; }
.tx-time { flex: none; width: 150rpx; font-size: 20rpx; color: #9aa0a6; }
.tx-text { flex: 1; font-size: 24rpx; color: #1b1f27; line-height: 1.6; }
.tx-pager {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16rpx 0 4rpx;
}
.tx-pageno { font-size: 21rpx; color: #9aa0a6; }
.tx-actions { display: flex; flex-wrap: wrap; gap: 12rpx; padding: 8rpx 0; }

/* 片段工作台 */
.tx-chips { display: flex; flex-wrap: wrap; padding: 10rpx 0 14rpx; }
.tx-chip {
  padding: 8rpx 20rpx;
  margin: 0 12rpx 10rpx 0;
  border-radius: 999rpx;
  background: #f2f4f8;
  border: 1rpx solid #e9ecf2;
  font-size: 22rpx;
  color: #6b7280;
}
.tx-chip.on { background: #e7f8f2; border-color: #12b886; color: #0b8f6b; font-weight: 600; }
.clip-card {
  border: 1rpx solid #eef0f4;
  border-radius: 14rpx;
  padding: 16rpx 18rpx;
  margin-top: 14rpx;
}
.clip-text { font-size: 24rpx; color: #1b1f27; line-height: 1.6; }
.clip-meta { margin-top: 6rpx; font-size: 20rpx; color: #9aa0a6; }
.clip-ops { display: flex; flex-wrap: wrap; gap: 10rpx; margin-top: 12rpx; }
.btn-mini.off { opacity: 0.4; }
</style>
