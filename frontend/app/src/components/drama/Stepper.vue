<template>
  <view class="stepper">
    <view
      v-for="(s, i) in STEPS"
      :key="s.path"
      :class="['pill', i === curIdx ? 'on' : '', i < curIdx ? 'past' : '']"
      @click="jump(s)"
    >
      <text class="dot">{{ i < curIdx ? '✓' : i + 1 }}</text>
      <text class="txt">{{ s.label }}</text>
    </view>
  </view>
</template>

<script>
/**
 * 项目四步进度条 —— 照竞品 components/project-stepper.tsx:8-13 的 STEPS
 *   script(脚本) → assets(素材) → video(视频) → export(导出)
 * 竞品每个 pill 都是真链接（可自由跳），当前高亮、已过打 ✓、未来灰。
 * uni-app 里改用 redirectTo 切步（replace 当前页，避免来回点把页面栈堆爆）。
 */
const STEPS = [
  { key: 'script', label: '脚本', path: '/pages/drama/script' },
  { key: 'assets', label: '素材', path: '/pages/drama/assets' },
  { key: 'video', label: '视频', path: '/pages/drama/video' },
  { key: 'export', label: '导出', path: '/pages/drama/export' },
]

export default {
  name: 'DramaStepper',
  props: {
    id: { type: String, default: '' },
    current: { type: String, default: 'script' },
  },
  data() {
    return { STEPS }
  },
  computed: {
    curIdx() {
      const i = STEPS.findIndex((s) => s.key === this.current)
      return i < 0 ? 0 : i
    },
  },
  methods: {
    jump(s) {
      if (s.key === this.current) return
      uni.redirectTo({ url: `${s.path}?id=${this.id}` })
    },
  },
}
</script>

<style scoped>
.stepper { display: flex; align-items: center; gap: 8rpx; }
.pill {
  display: flex;
  align-items: center;
  gap: 8rpx;
  padding: 10rpx 22rpx;
  border-radius: 999rpx;
  background: #f2f4f7;
}
.pill.on { background: #12b886; }
.pill.past { background: #e8f8f2; }
.dot {
  width: 30rpx;
  height: 30rpx;
  line-height: 30rpx;
  border-radius: 15rpx;
  background: #fff;
  color: #9aa0a6;
  font-size: 18rpx;
  text-align: center;
}
.pill.on .dot { background: rgba(255, 255, 255, 0.28); color: #fff; }
.pill.past .dot { background: #c8ecdd; color: #0b8f6b; }
.txt { font-size: 23rpx; color: #6b7280; }
.pill.on .txt { color: #fff; font-weight: 600; }
.pill.past .txt { color: #0b8f6b; }

@media (max-width: 900px) {
  .stepper { overflow-x: auto; }
  .pill { padding: 8rpx 16rpx; flex: none; }
  .txt { font-size: 21rpx; }
}
</style>
