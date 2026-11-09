<template>
  <view class="shell">
    <!-- 移动端顶部条：菜单 + 当前页名 -->
    <view class="topbar">
      <text class="topbar-menu" @click="drawer = !drawer">☰</text>
      <text class="topbar-title">{{ currentLabel }}</text>
      <text class="topbar-bell" @click="taskOpen = true">🔔<text v-if="taskCount" class="bell-dot">{{ taskCount }}</text></text>
    </view>

    <!-- 侧栏（桌面常驻 / 移动抽屉） -->
    <view :class="['sidebar', drawer ? 'open' : '']">
      <view class="brand" @click="go('/pages/drama/start')">
        <text class="brand-name">商品短剧</text>
        <text class="brand-sub">商品不是贴片，是转折点</text>
      </view>

      <view v-for="sec in visibleSections" :key="sec.label" class="sec">
        <text class="sec-label">{{ sec.label }}</text>
        <view
          v-for="item in sec.items"
          :key="item.key"
          :class="['nav', isActive(item) ? 'on' : '']"
          @click="go(item.href)"
        >
          <text class="nav-ico">{{ item.icon }}</text>
          <text class="nav-text">{{ item.label }}</text>
        </view>
      </view>

      <view class="sec sec-bottom">
        <view class="task-entry" @click="taskOpen = true">
          <text class="nav-ico">🔔</text>
          <text class="nav-text">任务中心</text>
          <text v-if="taskCount" class="task-entry-dot">{{ taskCount }}</text>
        </view>
        <view :class="['nav', isActive(SETTINGS) ? 'on' : '']" @click="go(SETTINGS.href)">
          <text class="nav-ico">{{ SETTINGS.icon }}</text>
          <text class="nav-text">{{ SETTINGS.label }}</text>
        </view>
        <view class="nav nav-mode" @click="toggleMode">
          <text class="nav-ico">◐</text>
          <text class="nav-text">{{ mode === 'pro' ? '导演模式' : '小白模式' }}</text>
        </view>
        <text class="mode-tip">{{ mode === 'pro' ? '全部专业工具已解锁' : '只留一键出片主路径' }}</text>
      </view>
    </view>

    <view v-if="drawer" class="mask" @click="drawer = false" />

    <!-- 内容区 -->
    <view class="content">
      <slot />
    </view>

    <!-- 任务中心（铃铛弹层）：进行中的钱都在这 -->
    <view v-if="taskOpen" class="mask" @click="taskOpen = false" />
    <view v-if="taskOpen" class="task-panel">
      <view class="task-head">
        <text class="task-title">任务中心</text>
        <text class="task-close" @click="taskOpen = false">关闭</text>
      </view>
      <text class="task-sub">{{ taskHint || '付费出片在飞、流水线跑到哪一步，都在这' }}</text>
      <view v-if="!taskCount" class="task-empty">暂无进行中的任务</view>
      <view v-for="g in groups" :key="g.key" class="task-group">
        <text v-if="g.rows.length" class="task-group-label">{{ g.label }}</text>
        <view v-for="(t, i) in g.rows" :key="g.key + i" class="task-row" @click="openTask(t)">
          <text class="task-name">{{ t.project || t.project_id || t.name || '任务' }}</text>
          <text :class="['task-state', g.tone]">{{ g.tone === 'bad' ? '需处理' : t.stage_label || t.kind || t.status || '' }}</text>
        </view>
      </view>
      <view class="task-foot" @click="go('/pages/drama/projects')">
        <text>去「我的项目」看全部</text>
      </view>
    </view>
  </view>
</template>

<script>
import { dramaTaskCenter } from '@/api/request'

/**
 * 商品短剧全局外壳 —— 照竞品 app-shell.tsx:24-45 的两组导航 + 底部设置 + 任务中心。
 * 竞品用 next/link 切路由；uni-app 用 uni.navigateTo / reLaunch（顶部页用 reLaunch 避免栈堆积）。
 *
 * 与竞品刻意一致的两点：
 *  · 小白模式下「新建项目 / 批量出片 / 媒体解构」从侧栏隐藏（竞品 proOnly）
 *  · 任务中心独立入口，不让「进行中的任务」混在业务页里
 * 与竞品不同的一点：不挂「爆款复刻」—— 那是我们另一条产品线，不串。
 */
const SECTIONS = [
  {
    label: '创作',
    items: [
      { key: 'home', label: '工作台', icon: '⌂', href: '/pages/drama/start' },
      { key: 'new', label: '新建项目', icon: '＋', href: '/pages/drama/new', proOnly: true },
      { key: 'topic', label: '说一个话题', icon: '〝', href: '/pages/drama/topic', proOnly: true },
      { key: 'clone', label: '照着参考片开新剧', icon: '⧉', href: '/pages/drama/clone', proOnly: true },
      { key: 'batch', label: '批量出片', icon: '▤', href: '/pages/drama/batch', proOnly: true },
      { key: 'lab', label: '媒体解构', icon: '⌕', href: '/pages/drama/media-lab', proOnly: true },
    ],
  },
  {
    label: '资产',
    items: [
      { key: 'projects', label: '我的项目', icon: '▢', href: '/pages/drama/projects' },
      { key: 'products', label: '商品库', icon: '▦', href: '/pages/drama/products' },
      { key: 'presenters', label: '出镜人物', icon: '☺', href: '/pages/drama/presenters' },
      { key: 'showcase', label: '示例展示', icon: '◎', href: '/pages/drama/showcase' },
    ],
  },
]
const SETTINGS = { key: 'settings', label: '设置', icon: '⚙', href: '/pages/drama/settings' }
const MODE_KEY = 'drama_ui_mode'

export default {
  name: 'DramaAppShell',
  data() {
    return {
      drawer: false,
      taskOpen: false,
      mode: 'simple',
      center: { paid: [], running: [], attention: [], recent: [] },
      taskHint: '',
      SETTINGS,
      route: '',
    }
  },
  computed: {
    visibleSections() {
      return SECTIONS.map((s) => ({
        label: s.label,
        items: s.items.filter((i) => this.mode === 'pro' || !i.proOnly),
      }))
    },
    currentLabel() {
      const all = [].concat(...SECTIONS.map((s) => s.items), [SETTINGS])
      const hit = all.find((i) => this.route.indexOf(i.href) === 0)
      return hit ? hit.label : '商品短剧'
    },
    groups() {
      return [
        { key: 'running', label: '进行中（流水线）', tone: 'ok', rows: this.center.running || [] },
        { key: 'attention', label: '需要处理', tone: 'bad', rows: this.center.attention || [] },
        { key: 'paid', label: '付费出片在飞', tone: 'ok', rows: this.center.paid || [] },
        { key: 'recent', label: '最近跑完', tone: 'dim', rows: this.center.recent || [] },
      ]
    },
    taskCount() {
      return this.groups.reduce((n, g) => n + g.rows.length, 0)
    },
  },
  created() {
    try {
      const m = uni.getStorageSync(MODE_KEY)
      if (m === 'pro' || m === 'simple') this.mode = m
    } catch (e) { /* 读不到就用默认 */ }
    this.route = '/' + (getCurrentPages().slice(-1)[0] || {}).route
    this.loadTasks()
  },
  methods: {
    isActive(item) {
      return this.route === item.href
    },
    go(href) {
      this.drawer = false
      if (this.route === href) return
      // 🩸 侧栏 = 一级导航，一律 reLaunch 清栈：小程序页面栈上限 10 层，
      // 原来除工作台外都 navigateTo，来回切几下就「页面栈已满」报错。
      // 项目内切步仍走 Stepper 的 redirectTo（replace，不堆栈）。
      uni.reLaunch({ url: href })
    },
    toggleMode() {
      this.mode = this.mode === 'pro' ? 'simple' : 'pro'
      try { uni.setStorageSync(MODE_KEY, this.mode) } catch (e) { /* 存不了不影响当次 */ }
    },
    async loadTasks() {
      try {
        const r = await dramaTaskCenter()
        this.center = {
          paid: (r && r.paid) || [],
          running: (r && r.running) || [],
          attention: (r && r.attention) || [],
          recent: (r && r.recent) || [],
        }
        const bad = this.center.attention.length
        this.taskHint = bad ? `有 ${bad} 条任务失败，点进去看是哪一段` : ''
      } catch (e) {
        this.center = { paid: [], running: [], attention: [], recent: [] }
      }
    },
    openTask(t) {
      const pid = t && (t.project_id || t.id)
      this.taskOpen = false
      if (!pid) return
      uni.navigateTo({ url: `/pages/drama/script?id=${pid}` })
    },
  },
}
</script>

<style scoped>
.shell {
  min-height: 100vh;
  background: #f6f7fb;
  display: flex;
}

/* ===== 侧栏 ===== */
.sidebar {
  width: 420rpx;
  flex: none;
  background: #ffffff;
  border-right: 1rpx solid #eef0f4;
  padding: 32rpx 20rpx 24rpx;
  display: flex;
  flex-direction: column;
}
.brand { padding: 0 12rpx 26rpx; }
.brand-name {
  display: block;
  font-size: 34rpx;
  font-weight: 700;
  color: #0b8f6b;
}
.brand-sub {
  display: block;
  margin-top: 6rpx;
  font-size: 20rpx;
  color: #9aa0a6;
}
.sec { margin-bottom: 26rpx; }
.sec-label {
  display: block;
  padding: 0 12rpx 8rpx;
  font-size: 20rpx;
  color: #b0b6bd;
  letter-spacing: 2rpx;
}
.nav {
  display: flex;
  align-items: center;
  gap: 14rpx;
  padding: 16rpx 12rpx;
  border-radius: 12rpx;
  margin-bottom: 4rpx;
}
.nav.on { background: #e8f8f2; }
.nav-ico { font-size: 24rpx; color: #0b8f6b; width: 32rpx; text-align: center; }
.nav-text { font-size: 26rpx; color: #333; }
.nav.on .nav-text { color: #0b8f6b; font-weight: 600; }
.sec-bottom { margin-top: auto; border-top: 1rpx solid #f0f2f5; padding-top: 18rpx; }
/* 桌面端也要能进任务中心（顶部铃铛 ≤900px 才显示） */
.task-entry {
  display: flex;
  align-items: center;
  gap: 14rpx;
  padding: 16rpx 12rpx;
  border-radius: 12rpx;
  margin-bottom: 4rpx;
  cursor: pointer;
}
.task-entry-dot {
  margin-left: auto;
  min-width: 32rpx;
  padding: 0 8rpx;
  border-radius: 999rpx;
  background: #d93025;
  color: #fff;
  font-size: 18rpx;
  text-align: center;
}
.mode-tip {
  display: block;
  padding: 6rpx 12rpx 0;
  font-size: 19rpx;
  color: #b0b6bd;
  line-height: 1.5;
}

/* ===== 内容区 ===== */
.content { flex: 1; min-width: 0; padding: 28rpx 24rpx 60rpx; }

/* ===== 移动端条 ===== */
.topbar { display: none; }

/* ===== 任务中心 ===== */
.mask {
  position: fixed;
  left: 0; top: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.28);
  z-index: 80;
}
.task-panel {
  position: fixed;
  right: 24rpx;
  top: 96rpx;
  width: 560rpx;
  max-width: calc(100vw - 48rpx);
  background: #fff;
  border-radius: 18rpx;
  padding: 24rpx;
  box-shadow: 0 16rpx 48rpx rgba(0, 0, 0, 0.14);
  z-index: 90;
}
.task-head { display: flex; align-items: center; justify-content: space-between; }
.task-title { font-size: 28rpx; font-weight: 700; }
.task-close { font-size: 22rpx; color: #0b8f6b; }
.task-sub { display: block; margin-top: 8rpx; font-size: 20rpx; color: #9aa0a6; line-height: 1.5; }
.task-empty { padding: 26rpx 0; text-align: center; font-size: 22rpx; color: #b0b6bd; }
.task-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14rpx 0;
  border-bottom: 1rpx solid #f2f4f7;
}
.task-group { margin-top: 10rpx; }
.task-group-label { display: block; font-size: 19rpx; color: #9aa0a6; margin: 6rpx 0 2rpx; }
.task-name { flex: 1; font-size: 23rpx; color: #333; }
.task-state { flex: none; font-size: 21rpx; color: #0b8f6b; }
.task-state.bad { color: #d93025; }
.task-state.dim { color: #9aa0a6; }
.task-foot { padding-top: 16rpx; text-align: right; font-size: 22rpx; color: #0b8f6b; }

/* ===== 窄屏（H5 手机 / 小程序）：侧栏收成抽屉 ===== */
@media (max-width: 900px) {
  .shell { display: block; }
  .topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 88rpx;
    padding: 0 24rpx;
    background: #fff;
    border-bottom: 1rpx solid #eef0f4;
  }
  .topbar-menu, .topbar-bell { font-size: 30rpx; color: #333; position: relative; }
  .bell-dot {
    position: absolute;
    top: -8rpx; right: -12rpx;
    min-width: 26rpx;
    height: 26rpx;
    line-height: 26rpx;
    border-radius: 13rpx;
    background: #f56c6c;
    color: #fff;
    font-size: 18rpx;
    text-align: center;
  }
  .topbar-title { font-size: 28rpx; font-weight: 600; }
  .sidebar {
    position: fixed;
    left: -460rpx;
    top: 0;
    bottom: 0;
    z-index: 90;
    transition: left 0.2s;
    width: 440rpx;
  }
  .sidebar.open { left: 0; }
  .content { padding: 20rpx 20rpx 60rpx; }
}
</style>
