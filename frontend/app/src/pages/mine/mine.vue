<template>
  <view class="page">
    <view class="header">
      <view class="avatar">VT</view>
      <view class="who">
        <view class="name">游客</view>
        <view class="sub">历史保存在这台设备上，换设备不同步</view>
      </view>
    </view>

    <view class="group">
      <view class="group-title">支持平台</view>
      <view class="platforms">
        <text v-for="p in platforms" :key="p.key" class="ptag">{{ p.name }}</text>
      </view>
    </view>

    <view class="group">
      <view class="row" @click="usage">
        <text class="row-label">使用说明</text>
        <text class="row-arrow">›</text>
      </view>
      <view class="row" @click="clearCache">
        <text class="row-label">清除本机记录</text>
        <text class="row-value">{{ historyCount }} 条</text>
      </view>
      <view class="row" @click="about">
        <text class="row-label">关于</text>
        <text class="row-value">v{{ version }}</text>
      </view>
    </view>

    <view class="footer">解析与下载由服务器完成，本机无需任何设置</view>
  </view>
</template>

<script>
import { getHistory, clearHistory } from '@/store'
import { ENABLED_PLATFORMS, PLATFORM_LABEL } from '@/config'

const VERSION = '1.0.0'

export default {
  data() {
    return {
      version: VERSION,
      historyCount: 0,
      platforms: ENABLED_PLATFORMS.map((k) => ({ key: k, name: PLATFORM_LABEL[k] })),
    }
  },
  onShow() {
    this.historyCount = getHistory().length
  },
  methods: {
    usage() {
      uni.showModal({
        title: '使用说明',
        content:
          '1. 在各平台 App 里点「分享 → 复制链接」\n2. 回到本工具粘贴，点「开始解析」\n3. 结果页可保存视频/图集、复制作品文案、提取口播文案、下载音频\n\n小红书等平台链接有时效，复制后请尽快解析。',
        showCancel: false,
      })
    },
    about() {
      uni.showModal({
        title: '关于',
        content: `视频解析工具 v${VERSION}\n去水印 · 复制文案 · 提取音频`,
        showCancel: false,
      })
    },
    clearCache() {
      if (!this.historyCount) {
        uni.showToast({ title: '没有记录', icon: 'none' })
        return
      }
      uni.showModal({
        title: '清除本机记录？',
        content: '仅清除列表，不影响已下载的文件',
        success: (r) => {
          if (!r.confirm) return
          clearHistory()
          this.historyCount = 0
          uni.showToast({ title: '已清除', icon: 'success' })
        },
      })
    },
  },
}
</script>

<style lang="scss" scoped>
.page {
  min-height: 100vh;
  padding-bottom: 60rpx;
}
.header {
  display: flex;
  align-items: center;
  padding: 56rpx 40rpx 64rpx;
  background: linear-gradient(135deg, #4f7cff 0%, #7b5cff 100%);
}
.avatar {
  width: 112rpx;
  height: 112rpx;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.2);
  color: #fff;
  font-size: 34rpx;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}
.who {
  margin-left: 26rpx;
}
.name {
  font-size: 34rpx;
  font-weight: 600;
  color: #fff;
}
.sub {
  margin-top: 10rpx;
  font-size: 22rpx;
  color: rgba(255, 255, 255, 0.8);
}
.group {
  margin: 24rpx 28rpx 0;
  padding: 8rpx 28rpx;
  background: #fff;
  border-radius: 20rpx;
}
.group-title {
  padding: 20rpx 0 4rpx;
  font-size: 24rpx;
  color: #9aa0a6;
}
.platforms {
  display: flex;
  flex-wrap: wrap;
  padding: 12rpx 0 24rpx;
}
.ptag {
  font-size: 22rpx;
  color: #4f7cff;
  background: #eef1fb;
  padding: 8rpx 20rpx;
  border-radius: 999rpx;
  margin: 0 16rpx 16rpx 0;
}
.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 100rpx;
  border-bottom: 1rpx solid #f0f1f5;
}
.row:last-child {
  border-bottom: none;
}
.row-label {
  font-size: 28rpx;
  color: #1b1f27;
}
.row-value {
  font-size: 24rpx;
  color: #9aa0a6;
}
.row-arrow {
  font-size: 32rpx;
  color: #c7cbd4;
}
.footer {
  margin-top: 48rpx;
  text-align: center;
  font-size: 22rpx;
  color: #b6bac2;
}
</style>
