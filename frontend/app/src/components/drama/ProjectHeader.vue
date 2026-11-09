<template>
  <view class="ph">
    <view class="ph-left">
      <text class="ph-name">{{ name }}</text>
      <view class="ph-chips">
        <text v-if="chips.length" v-for="(c, i) in chips" :key="i" class="ph-chip">{{ c }}</text>
      </view>
    </view>
    <view class="ph-right">
      <DramaStepper :id="id" :current="current" />
      <!-- 导演台是二级页（照竞品：不进侧栏，从项目页进） -->
      <text v-if="id && current !== 'production'" class="ph-prod" @click="goProd">导演台 ›</text>
    </view>
  </view>
</template>

<script>
import DramaStepper from './Stepper.vue'

/** 项目页统一头部：项目名 + 关键信息 + 四步条（竞品每个阶段页顶部就是「项目名 + 步骤条」） */
export default {
  name: 'DramaProjectHeader',
  components: { DramaStepper },
  props: {
    id: { type: String, default: '' },
    current: { type: String, default: 'script' },
    name: { type: String, default: '未命名' },
    chips: { type: Array, default: () => [] },
  },
  methods: {
    goProd() {
      if (!this.id) return
      // 二级页用 redirectTo：不堆栈（小程序页面栈上限 10 层）
      uni.redirectTo({ url: `/pages/drama/production?id=${this.id}` })
    },
  },
}
</script>

<style scoped>
.ph {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20rpx;
  padding: 20rpx 24rpx;
  margin-bottom: 20rpx;
  background: #fff;
  border-radius: 16rpx;
}
.ph-left { min-width: 0; }
.ph-name {
  display: block;
  font-size: 30rpx;
  font-weight: 700;
  color: #1f2329;
  max-width: 720rpx;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.ph-right { display: flex; flex-direction: column; align-items: flex-end; gap: 8rpx; }
.ph-prod { font-size: 22rpx; color: #0b8f6b; padding: 4rpx 8rpx; }
.ph-chips { display: flex; flex-wrap: wrap; gap: 8rpx; margin-top: 8rpx; }
.ph-chip {
  padding: 4rpx 14rpx;
  border-radius: 999rpx;
  background: #f2f4f7;
  font-size: 20rpx;
  color: #6b7280;
}

@media (max-width: 900px) {
  .ph { flex-direction: column; align-items: flex-start; gap: 12rpx; }
  .ph-name { max-width: 100%; }
}
</style>
