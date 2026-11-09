<template>
  <view class="page">
    <view class="hero">
      <view class="hero-title">视频解析工具</view>
      <view class="hero-sub">去水印 · 复制文案 · 提取音频</view>
      <view class="hero-platforms">
        <text v-for="p in platforms" :key="p" class="ptag">{{ p }}</text>
      </view>
    </view>

    <view class="card">
      <view class="card-title">粘贴分享链接或整段分享文案</view>
      <textarea
        v-model="text"
        class="input"
        placeholder="例：复制抖音 / 快手 / 小红书 / B站 / TikTok 的分享链接，直接粘贴到这里"
        maxlength="-1"
        auto-height
        :show-confirm-bar="false"
      />
      <view class="row">
        <button class="btn-ghost" size="mini" @click="paste">粘贴</button>
        <button class="btn-ghost" size="mini" @click="clear">清空</button>
      </view>
      <button class="btn-primary" :loading="loading" :disabled="loading" @click="submit">
        {{ loading ? '解析中…' : '开始解析' }}
      </button>
    </view>

    <view class="clone-entry" @click="goClone">
      <view class="ce-left">
        <view class="ce-title">复刻爆款</view>
        <view class="ce-sub">拆解原片结构 → 换文案 → 出可发布的新片</view>
      </view>
      <view class="ce-arrow">›</view>
    </view>

    <view class="prompt-entry" @click="goPrompt">
      <view class="ce-left">
        <view class="ce-title">提示词优化</view>
        <view class="ce-sub">把想法整理成 H3 官方格式的提示词</view>
      </view>
      <view class="pe-arrow">›</view>
    </view>

    <view class="drama-entry" @click="goDrama">
      <view class="ce-left">
        <view class="ce-title">商品短剧</view>
        <view class="ce-sub">给一件商品，写成有角色、有冲突、有反转的短剧</view>
      </view>
      <view class="de-arrow">›</view>
    </view>

    <view class="tips">
      <view class="tip-title">使用说明</view>
      <view class="tip">· 请使用各平台 App 里的「分享 → 复制链接」，网页地址栏复制的链接常缺参数</view>
      <view class="tip">· 小红书链接有时效，复制后请尽快解析</view>
      <view class="tip">· 视频预览与下载由服务器代理，无需在本机做任何设置</view>
    </view>
  </view>
</template>

<script>
import { parseText } from '@/api/request'
import { setCurrent } from '@/store'
import { ENABLED_PLATFORMS, PLATFORM_LABEL } from '@/config'

export default {
  data() {
    return {
      text: '',
      loading: false,
      platforms: ENABLED_PLATFORMS.map((k) => PLATFORM_LABEL[k]),
    }
  },
  methods: {
    paste() {
      uni.getClipboardData({
        success: (res) => {
          if (res.data) this.text = res.data
        },
        fail: () => uni.showToast({ title: '读取剪贴板失败', icon: 'none' }),
      })
    },
    clear() {
      this.text = ''
    },
    goClone() {
      uni.navigateTo({ url: '/pages/clone/index' })
    },
    goPrompt() {
      uni.navigateTo({ url: '/pages/prompt/index' })
    },
    goDrama() {
      // 入口页：清栈进工作台（小程序页面栈上限 10 层）
      uni.reLaunch({ url: '/pages/drama/start' })
    },
    async submit() {
      const t = (this.text || '').trim()
      if (!t) {
        uni.showToast({ title: '请先粘贴链接', icon: 'none' })
        return
      }
      if (this.loading) return
      this.loading = true
      try {
        const data = await parseText(t)
        setCurrent(data)
        uni.navigateTo({ url: '/pages/result/result' })
      } catch (e) {
        uni.showModal({
          title: '解析失败',
          content: e.message || '请检查链接后重试',
          showCancel: false,
        })
      } finally {
        this.loading = false
      }
    },
  },
}
</script>

<style lang="scss" scoped>
.page {
  min-height: 100vh;
  padding-bottom: 40rpx;
}
.hero {
  padding: 48rpx 40rpx 72rpx;
  background: linear-gradient(135deg, #4f7cff 0%, #7b5cff 100%);
  color: #fff;
}
.hero-title {
  font-size: 44rpx;
  font-weight: 700;
  letter-spacing: 1rpx;
}
.hero-sub {
  margin-top: 12rpx;
  font-size: 26rpx;
  opacity: 0.88;
}
.hero-platforms {
  margin-top: 28rpx;
  display: flex;
  flex-wrap: wrap;
}
.ptag {
  font-size: 22rpx;
  padding: 6rpx 16rpx;
  margin: 0 12rpx 12rpx 0;
  border-radius: 999rpx;
  background: rgba(255, 255, 255, 0.18);
}
.card {
  margin: -44rpx 28rpx 0;
  padding: 32rpx;
  background: #fff;
  border-radius: 24rpx;
  box-shadow: 0 12rpx 40rpx rgba(31, 45, 90, 0.1);
}
.card-title {
  font-size: 28rpx;
  font-weight: 600;
  color: #1b1f27;
  margin-bottom: 20rpx;
}
.input {
  width: 100%;
  min-height: 200rpx;
  padding: 24rpx;
  font-size: 28rpx;
  line-height: 1.6;
  background: #f6f7fb;
  border-radius: 16rpx;
}
.row {
  display: flex;
  margin: 20rpx 0 28rpx;
}
.btn-ghost {
  margin-right: 20rpx;
  background: #eef1fb;
  color: #4f7cff;
  border-radius: 999rpx;
  font-size: 24rpx;
}
.btn-primary {
  width: 100%;
  height: 92rpx;
  line-height: 92rpx;
  border-radius: 999rpx;
  background: linear-gradient(135deg, #4f7cff 0%, #7b5cff 100%);
  color: #fff;
  font-size: 32rpx;
  font-weight: 600;
}
.clone-entry {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 24rpx 28rpx 0;
  padding: 32rpx;
  border-radius: 24rpx;
  background: linear-gradient(135deg, #ff6b4a 0%, #ff3d7f 100%);
  box-shadow: 0 12rpx 36rpx rgba(255, 61, 127, 0.24);
}
.ce-title {
  font-size: 32rpx;
  font-weight: 700;
  color: #fff;
}
.ce-sub {
  margin-top: 10rpx;
  font-size: 24rpx;
  color: rgba(255, 255, 255, 0.88);
}
.ce-arrow {
  font-size: 44rpx;
  color: #fff;
  opacity: 0.9;
}
/* 提示词优化：与「复刻爆款」同款卡片，换蓝紫区分功能（一个是出片，一个只出提示词） */
.prompt-entry {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 20rpx 28rpx 0;
  padding: 32rpx;
  border-radius: 24rpx;
  background: linear-gradient(135deg, #5b6cff 0%, #7a4dff 100%);
  box-shadow: 0 12rpx 36rpx rgba(91, 108, 255, 0.24);
}
.pe-arrow {
  font-size: 44rpx;
  color: #fff;
  opacity: 0.9;
}
/* 商品短剧：同款卡片，绿色区分（只出剧本与分镜，不出片） */
.drama-entry {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 20rpx 28rpx 0;
  padding: 32rpx;
  border-radius: 24rpx;
  background: linear-gradient(135deg, #12b886 0%, #0b8f6b 100%);
  box-shadow: 0 12rpx 36rpx rgba(18, 184, 134, 0.24);
}
.de-arrow {
  font-size: 44rpx;
  color: #fff;
  opacity: 0.9;
}
.tips {
  margin: 40rpx 40rpx 0;
}
.tip-title {
  font-size: 26rpx;
  font-weight: 600;
  color: #6b7280;
  margin-bottom: 12rpx;
}
.tip {
  font-size: 24rpx;
  line-height: 1.9;
  color: #9aa0a6;
}
</style>
