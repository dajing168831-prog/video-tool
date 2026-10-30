<template>
  <view class="page">
    <view class="tabs">
      <view class="tab" :class="{ on: tab === 'parse' }" @click="tab = 'parse'">
        解析记录<text class="n" v-if="list.length">{{ list.length }}</text>
      </view>
      <view class="tab" :class="{ on: tab === 'clone' }" @click="tab = 'clone'">
        复刻作品<text class="n" v-if="clones.length">{{ clones.length }}</text>
      </view>
    </view>

    <!-- ---------------- 解析记录 ---------------- -->
    <block v-if="tab === 'parse'">
      <view v-if="!list.length" class="empty">
        <view class="empty-icon">🕘</view>
        <view class="empty-text">还没有解析记录</view>
      </view>

      <block v-else>
        <view class="toolbar">
          <text class="count">共 {{ list.length }} 条</text>
          <text class="clear" @click="clearAll">清空</text>
        </view>

        <view v-for="item in list" :key="item.token" class="item" @click="open(item)">
          <image
            v-if="item.cover"
            class="cover"
            :src="coverSrc(item)"
            mode="aspectFill"
          />
          <view v-else class="cover cover-ph">
            <text>{{ item.is_video === false ? '图集' : '视频' }}</text>
          </view>

          <view class="info">
            <view class="title">{{ item.title || '（无标题）' }}</view>
            <view class="meta">
              <text class="badge">{{ label(item.platform) }}</text>
              <text class="time">{{ fmtTime(item.time) }}</text>
            </view>
          </view>

          <view class="del" @click.stop="remove(item.token)">×</view>
        </view>
      </block>
    </block>

    <!-- ---------------- 复刻作品 ---------------- -->
    <block v-else>
      <view v-if="!clones.length" class="empty">
        <view class="empty-icon">🎬</view>
        <view class="empty-text">{{ cloneLoading ? '读取中…' : '还没有复刻作品' }}</view>
        <view class="empty-sub" v-if="!cloneLoading">在首页「复刻爆款」里粘一条链接，出的每一版都会留在这里</view>
      </view>

      <block v-else>
        <view class="toolbar">
          <text class="count">共 {{ clones.length }} 个作品 · {{ totalVersions }} 版</text>
          <text class="clear" @click="loadClones">刷新</text>
        </view>

        <view v-for="c in clones" :key="c.id" class="ccard">
          <view class="chead" @click="toggle(c)">
            <image
              v-if="coverOf(c) && !c._coverErr"
              class="ccover"
              :src="coverOf(c)"
              mode="aspectFill"
              @error="c._coverErr = true"
            />
            <view v-else class="ccover ccover-ph">复刻</view>

            <view class="cinfo">
              <view class="ctitle">{{ titleOf(c) }}</view>
              <view class="cmeta">
                <text class="badge" :class="{ off: !versionCount(c) }">{{ versionCount(c) || 0 }} 版</text>
                <text class="time">{{ fmtTime(c.created_at) }}</text>
              </view>
              <view class="cline">{{ statusOf(c) }}</view>
            </view>

            <text class="arrow">{{ c._open ? '▾' : '›' }}</text>
          </view>

          <view class="cbody" v-if="c._open">
            <view v-if="!versionCount(c)" class="cnote">这个作品还没出过片。</view>
            <view
              v-for="(r, i) in (c.renders || [])"
              :key="r.id"
              class="ver"
              @click="openVersion(c, r, i)"
            >
              <text class="vtag">v{{ i + 1 }}</text>
              <text class="vinfo">{{ verInfo(r) }}</text>
              <text class="vgo" :class="r.state">{{ verAction(r) }}</text>
            </view>

            <view class="cbtns">
              <button class="cbtn" size="mini" @click.stop="openDiagnose(c)">继续改这个作品</button>
              <button class="cbtn ghost" size="mini" @click.stop="openLatest(c)">看最新一版</button>
              <button class="cbtn ghost" size="mini" @click.stop="toggleSource(c)">
                {{ c._srcOpen ? '收起原片' : '看解析的原片' }}
              </button>
            </view>

            <!-- 换脸/换画面出问题时，要回头看这次到底解析的是哪条片子 -->
            <video
              v-if="c._srcOpen"
              class="srcvid"
              :src="sourceOf(c)"
              controls
              object-fit="contain"
              :show-fullscreen-btn="true"
            />
          </view>
        </view>
      </block>
    </block>
  </view>
</template>

<script>
import { getHistory, removeHistory, clearHistory, store } from '@/store'
import { PLATFORM_LABEL } from '@/config'
import { fileUrl, cloneFileUrl, cloneHistory } from '@/api/request'

export default {
  data() {
    return {
      tab: 'parse',
      list: [],
      clones: [],
      cloneLoading: false,
    }
  },
  computed: {
    totalVersions() {
      return this.clones.reduce((n, c) => n + (c.renders || []).length, 0)
    },
  },
  onShow() {
    this.list = getHistory()
    // 离开结果页后再进来，模块级缓存可能已过期，这里不清，交给结果页按 token 重新拉
    this.loadClones()
  },
  methods: {
    label(p) {
      return PLATFORM_LABEL[p] || p || ''
    },
    /** 封面外链有防盗链，小程序还过不了白名单 → 统一走服务器代理 */
    coverSrc(item) {
      return fileUrl(item.token, 'cover')
    },
    fmtTime(ts) {
      if (!ts) return ''
      const d = new Date(Number(ts) * (Number(ts) < 1e12 ? 1000 : 1))
      const pad = (n) => String(n).padStart(2, '0')
      return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
    },
    open(item) {
      // 缓存里若正好是这条则复用，否则结果页会按 token 重新拉
      if (store.current && store.current.token !== item.token) store.current = null
      uni.navigateTo({ url: `/pages/result/result?token=${item.token}` })
    },
    remove(token) {
      uni.showModal({
        title: '删除这条记录？',
        success: (r) => {
          if (!r.confirm) return
          removeHistory(token)
          this.list = getHistory()
        },
      })
    },
    clearAll() {
      if (!this.list.length) return
      uni.showModal({
        title: '清空全部记录？',
        content: '仅清除本机列表，不影响已下载的文件',
        success: (r) => {
          if (!r.confirm) return
          clearHistory()
          this.list = []
        },
      })
    },

    // ---------------- 复刻作品 ----------------

    /**
     * 作品库 = 服务器上的复刻任务。之前只有接口没有人调，
     * 结果就是：出了片离开页面就再也找不回来，多版本也挑不了。
     */
    async loadClones() {
      if (this.cloneLoading) return
      this.cloneLoading = true
      try {
        const data = await cloneHistory(50)
        this.clones = (data || [])
          // 只留有形的：能点进去看原片的才值得列
          .filter((c) => c && c.id)
          .map((c) => ({ ...c, _open: false, _coverErr: false }))
        // 有作品就把标签停在作品上（解析记录为空时更是如此）
        if (this.clones.length && !this.list.length) this.tab = 'clone'
      } catch (e) {
        this.clones = []
      } finally {
        this.cloneLoading = false
      }
    },
    toggle(c) {
      c._open = !c._open
    },
    /** 这条作品当初解析用的原片（/clone/{cid}/file/source，支持拖动进度条） */
    sourceOf(c) {
      return cloneFileUrl(c.id, 'source')
    },
    toggleSource(c) {
      c._srcOpen = !c._srcOpen
    },
    versionCount(c) {
      return (c.renders || []).length
    },
    /** 最新一版能播的成片；没有就退回原片封面 */
    latestDone(c) {
      const rs = (c.renders || []).filter((r) => r.state === 'done')
      return rs.length ? rs[rs.length - 1] : null
    },
    coverOf(c) {
      const r = this.latestDone(c)
      if (r) return cloneFileUrl(c.id, 'cover', r.id)
      return cloneFileUrl(c.id, 'srccover')
    },
    titleOf(c) {
      const last = (c.renders || [])[((c.renders || []).length || 0) - 1]
      const first = ((last && last.script) || c.speech_text || '').replace(/\s+/g, ' ').trim()
      if (first) return first.length > 42 ? first.slice(0, 42) + '…' : first
      return (c.meta && c.meta.title) || '未命名复刻'
    },
    statusOf(c) {
      const rs = c.renders || []
      if (!rs.length) return '还没出片'
      const running = rs.filter((r) => r.state === 'queued' || r.state === 'rendering')
      if (running.length) return `${running.length} 版正在出片`
      const last = this.latestDone(c)
      if (!last) {
        const f = rs[rs.length - 1]
        return f && f.error ? `出片失败：${f.error}` : '出片失败'
      }
      const d = last.duration ? `${Number(last.duration).toFixed(1)} 秒` : '—'
      return `最新一版 ${d}${last.qc_ok === false ? ' · 需复核' : ''}`
    },
    verInfo(r) {
      const d = r.state === 'done' && r.duration ? `${Number(r.duration).toFixed(1)}s` : ''
      const t = this.fmtTime(r.created_at)
      const bits = [d, t].filter(Boolean)
      if (r.state === 'failed') bits.push((r.error || '出片失败').slice(0, 24))
      if (r.state === 'done' && r.qc_ok === false) bits.push('需复核')
      return bits.join(' · ')
    },
    verAction(r) {
      if (r.state === 'done') return '看片'
      if (r.state === 'failed') return '重出'
      return '出片中'
    },
    openVersion(c, r, i) {
      if (r.state === 'done') {
        uni.navigateTo({ url: `/pages/clone/result?cid=${c.id}&rid=${r.id}` })
        return
      }
      if (r.state === 'failed') {
        this.openDiagnose(c)
        return
      }
      uni.navigateTo({ url: `/pages/clone/progress?cid=${c.id}&rid=${r.id}` })
    },
    openLatest(c) {
      const r = this.latestDone(c)
      if (!r) {
        uni.showToast({ title: '这个作品还没有成片', icon: 'none' })
        return
      }
      uni.navigateTo({ url: `/pages/clone/result?cid=${c.id}&rid=${r.id}` })
    },
    openDiagnose(c) {
      uni.navigateTo({ url: `/pages/clone/diagnose?cid=${c.id}` })
    },
  },
}
</script>

<style lang="scss" scoped>
.page {
  min-height: 100vh;
  padding: 24rpx 28rpx 60rpx;
}
.tabs {
  display: flex;
  padding: 0 8rpx 20rpx;
}
.tab {
  position: relative;
  margin-right: 40rpx;
  padding: 10rpx 0 14rpx;
  font-size: 28rpx;
  color: #8b90a0;
}
.tab.on {
  color: #1b1f27;
  font-weight: 600;
}
.tab.on::after {
  content: '';
  position: absolute;
  left: 50%;
  bottom: 0;
  width: 40rpx;
  height: 6rpx;
  margin-left: -20rpx;
  border-radius: 999rpx;
  background: #4f7cff;
}
.tab .n {
  margin-left: 8rpx;
  font-size: 22rpx;
  color: #b6bac2;
}
.empty {
  padding: 200rpx 0;
  text-align: center;
}
.empty-icon {
  font-size: 72rpx;
  opacity: 0.35;
}
.empty-text {
  margin-top: 16rpx;
  font-size: 26rpx;
  color: #9aa0a6;
}
.empty-sub {
  margin: 14rpx 60rpx 0;
  font-size: 23rpx;
  line-height: 1.7;
  color: #b6bac2;
}
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8rpx 8rpx 20rpx;
}
.count {
  font-size: 24rpx;
  color: #9aa0a6;
}
.clear {
  font-size: 24rpx;
  color: #4f7cff;
  padding: 8rpx 16rpx;
}
.item {
  display: flex;
  align-items: center;
  padding: 20rpx;
  margin-bottom: 20rpx;
  background: #fff;
  border-radius: 20rpx;
}
.cover {
  width: 132rpx;
  height: 176rpx;
  border-radius: 14rpx;
  background: #f0f1f5;
  flex-shrink: 0;
}
.cover-ph {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22rpx;
  color: #9aa0a6;
}
.info {
  flex: 1;
  margin-left: 22rpx;
  min-width: 0;
}
.title {
  font-size: 28rpx;
  line-height: 1.5;
  color: #1b1f27;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
}
.meta {
  margin-top: 16rpx;
  display: flex;
  align-items: center;
}
.badge {
  font-size: 20rpx;
  color: #4f7cff;
  background: #eef1fb;
  padding: 4rpx 14rpx;
  border-radius: 999rpx;
}
.badge.off {
  color: #9aa0a6;
  background: #f0f1f5;
}
.time {
  margin-left: 16rpx;
  font-size: 20rpx;
  color: #9aa0a6;
}
.del {
  width: 60rpx;
  height: 60rpx;
  line-height: 54rpx;
  text-align: center;
  font-size: 40rpx;
  color: #c7cbd4;
  flex-shrink: 0;
}

/* ---------------- 复刻作品卡 ---------------- */
.ccard {
  margin-bottom: 20rpx;
  background: #fff;
  border-radius: 20rpx;
  overflow: hidden;
}
.chead {
  display: flex;
  align-items: center;
  padding: 20rpx;
}
.ccover {
  width: 132rpx;
  height: 176rpx;
  border-radius: 14rpx;
  background: #f0f1f5;
  flex-shrink: 0;
}
.ccover-ph {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22rpx;
  color: #9aa0a6;
}
.cinfo {
  flex: 1;
  margin-left: 22rpx;
  min-width: 0;
}
.ctitle {
  font-size: 28rpx;
  line-height: 1.5;
  color: #1b1f27;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
}
.cmeta {
  margin-top: 14rpx;
  display: flex;
  align-items: center;
}
.cline {
  margin-top: 10rpx;
  font-size: 22rpx;
  color: #9aa0a6;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 1;
  overflow: hidden;
}
.arrow {
  width: 40rpx;
  text-align: right;
  font-size: 30rpx;
  color: #c7cbd4;
}
.cbody {
  padding: 0 20rpx 20rpx;
  border-top: 1rpx solid #f0f1f5;
}
.cnote {
  padding: 20rpx 0;
  font-size: 23rpx;
  color: #9aa0a6;
}
.ver {
  display: flex;
  align-items: center;
  padding: 22rpx 0;
  border-bottom: 1rpx solid #f4f5f8;
}
.vtag {
  width: 56rpx;
  font-size: 24rpx;
  color: #4f7cff;
  font-weight: 600;
}
.vinfo {
  flex: 1;
  font-size: 23rpx;
  color: #6b7280;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.vgo {
  flex-shrink: 0;
  margin-left: 16rpx;
  padding: 6rpx 18rpx;
  font-size: 22rpx;
  color: #4f7cff;
  border: 1rpx solid #cfd9ff;
  border-radius: 999rpx;
}
.vgo.failed {
  color: #e5484d;
  border-color: #f7c5c6;
}
.vgo.rendering,
.vgo.queued {
  color: #b6bac2;
  border-color: #eceef3;
}
.cbtns {
  display: flex;
  flex-wrap: wrap;
  padding-top: 20rpx;
}
.cbtn {
  margin-right: 16rpx;
  margin-bottom: 12rpx;
  border-radius: 999rpx;
  background: #eef1fb;
  color: #4f7cff;
  font-size: 24rpx;
}
.cbtn.ghost {
  background: #fff5f2;
  color: #ff5a3c;
}
.srcvid {
  width: 100%;
  height: 420rpx;
  margin-top: 20rpx;
  border-radius: 16rpx;
  background: #000;
}
</style>
