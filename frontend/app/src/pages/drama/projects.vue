<template>
  <DramaAppShell>
    <view class="ds">
      <view class="page-wrap">
        <view class="head">
          <text class="title">我的项目</text>
          <view class="filters">
            <view
              v-for="f in FILTERS"
              :key="f.key"
              :class="['filter', filter === f.key ? 'on' : '']"
              @click="filter = f.key"
            >{{ f.label }}<text class="n">{{ countOf(f.key) }}</text></view>
          </view>
          <view class="new" @click="goNew">＋ 新建</view>
        </view>

        <view v-if="loading" class="state">正在加载…</view>
        <view v-else-if="!shown.length" class="state">这一类暂时没有项目</view>

        <view v-for="p in shown" :key="p.id" class="row" @click="open(p.id)">
          <view class="row-main">
            <text class="row-name">{{ p.name || '未命名' }}</text>
            <text class="row-stage">{{ p.done ? '已完成' : p.stage }}</text>
          </view>
          <view class="row-side">
            <text class="row-time">{{ p.updated || '' }}</text>
            <text class="row-del" @click.stop="delOne(p)">删</text>
            <text class="row-go">进入 ›</text>
          </view>
        </view>

    <view class="card">
      <view class="card-head">
        <view class="card-title"><text class="card-no">片</text>作品流</view>
        <button class="btn-mini" :disabled="wkBusy" @click="toggleWorks">
          {{ wkOpen ? '收起' : '展开' }}
        </button>
      </view>
      <view v-if="wkOpen" class="sp-box">
        <view class="tts-actions">
          <button class="btn-mini" :disabled="wkBusy" @click="loadWorks">
            {{ wkBusy ? '读取中…' : '刷新' }}
          </button>
          <text v-if="wkNote" class="tts-hint">{{ wkNote }}</text>
        </view>
        <view v-for="w in wkItems" :key="w.id" class="pl-row">
          <image v-if="w.thumbnailUrl" class="wk-thumb" :src="apiBase + w.thumbnailUrl"
                 mode="aspectFill" />
          <view class="pl-info">
            <text class="pl-name">{{ w.projectName || '未命名' }}</text>
            <text class="pl-meta">{{ w.label }} · {{ w.duration }}s · {{ w.createdAt }}</text>
          </view>
          <text class="media-more" @click.stop="playWork(w)">看片</text>
        </view>
        <video v-if="wkPlay" class="wk-player" :src="wkPlay" controls autoplay />
        <view v-if="!wkItems.length && !wkBusy" class="merge-tip">还没有出成功的片子。</view>
        <view class="merge-tip">
          只列盘上真有视频的：合成片 &gt; 拼接整片 &gt; 最后一段；封面缺的每次最多回填 6 张首帧。
        </view>
      </view>
    </view>
      </view>
    </view>
  </DramaAppShell>
</template>

<script>
import DramaAppShell from '@/components/drama/AppShell.vue'
import dramaPageBoot from '@/mixins/dramaPageBoot'
import { dramaList, dramaDeleteProject } from '@/api/request'

/** 我的项目（照竞品 /projects）：项目列表 + 成片墙（作品流） */
const FILTERS = [
  { key: 'all', label: '全部' },
  { key: 'new', label: '新建' },
  { key: 'doing', label: '进行中' },
  { key: 'done', label: '已完成' },
]

export default {
  components: { DramaAppShell },
  mixins: [dramaPageBoot],
  data() {
    return { FILTERS, list: [], loading: false, filter: 'all' }
  },
  computed: {
    shown() {
      return this.list.filter((p) => {
        if (this.filter === 'all') return true
        if (this.filter === 'done') return !!p.done
        if (this.filter === 'new') return !p.done && (!p.stage || p.stage === '新建')
        return !p.done && p.stage && p.stage !== '新建'
      })
    },
  },
  onLoad() {
    this.boot('')
  },
  onShow() {
    this.load()
  },
  methods: {
    async load() {
      this.loading = true
      try {
        this.list = (await dramaList()) || []
      } catch (e) {
        this.list = []
      } finally {
        this.loading = false
      }
    },
    countOf(key) {
      if (key === 'all') return this.list.length
      if (key === 'done') return this.list.filter((p) => p.done).length
      if (key === 'new') return this.list.filter((p) => !p.done && (!p.stage || p.stage === '新建')).length
      return this.list.filter((p) => !p.done && p.stage && p.stage !== '新建').length
    },
    open(id) {
      uni.navigateTo({ url: `/pages/drama/script?id=${id}` })
    },
    /** 删项目（照竞品 projects 页的 deleteProject）；二次确认，删完重拉列表 */
    delOne(p) {
      const name = p.name || '这条'
      uni.showModal({
        title: '删掉这个项目？',
        content: '「' + name + '」的脚本、素材与成片记录会一并删除，无法恢复。',
        success: async (r) => {
          if (!r.confirm) return
          try {
            await dramaDeleteProject(p.id)
            uni.showToast({ title: '已删除', icon: 'none' })
            await this.load()
          } catch (e) {
            uni.showModal({ title: '删除失败', content: e.message || '', showCancel: false })
          }
        },
      })
    },
    goNew() {
      uni.navigateTo({ url: '/pages/drama/new' })
    },
  },
}
</script>

<style scoped>
.head { display: flex; align-items: center; gap: 20rpx; margin-bottom: 20rpx; }
.title { font-size: 32rpx; font-weight: 700; }
.filters { display: flex; gap: 8rpx; }
.filter { padding: 8rpx 18rpx; border-radius: 999rpx; background: #fff; font-size: 22rpx; color: #6b7280; }
.filter.on { background: #e8f8f2; color: #0b8f6b; font-weight: 600; }
.n { margin-left: 6rpx; font-size: 19rpx; color: #b0b6bd; }
.new { margin-left: auto; padding: 10rpx 24rpx; border-radius: 999rpx; background: #12b886; color: #fff; font-size: 23rpx; }
.state { padding: 60rpx; text-align: center; color: #9aa0a6; font-size: 24rpx; }
.row { display: flex; align-items: center; justify-content: space-between; padding: 22rpx 24rpx; background: #fff; border-radius: 14rpx; margin-bottom: 12rpx; }
.row-name { font-size: 26rpx; color: #1f2329; font-weight: 600; }
.row-stage { margin-left: 14rpx; font-size: 20rpx; color: #0b8f6b; }
.row-side { display: flex; align-items: center; gap: 16rpx; }
.row-time { font-size: 20rpx; color: #b0b6bd; }
.row-go { font-size: 22rpx; color: #0b8f6b; }
.row-del { font-size: 21rpx; color: #c62828; padding: 6rpx 12rpx; }
</style>
