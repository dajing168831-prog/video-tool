<template>
  <view class="pv">
    <view class="pv-bar">
      <text class="pv-name">{{ name || '预览' }}</text>
      <text class="pv-copy" @click="copyLink">复制链接</text>
    </view>

    <view v-if="err" class="pv-err">{{ err }}</view>

    <template v-else>
      <!-- 视频：小程序原生 video 组件直接播 http(s) 地址 -->
      <video v-if="kind === 'video'" class="pv-video" :src="url" controls autoplay object-fit="contain" />

      <!-- 图片：gif 在 image 组件里会动 -->
      <image v-else-if="kind === 'image'" class="pv-image" :src="url" mode="widthFix" show-menu-by-longpress />

      <!-- 文本（md / srt / vtt / json）：拉下来显示，可整段复制 -->
      <scroll-view v-else scroll-y class="pv-text-wrap">
        <text v-if="loading" class="pv-tip">加载中…</text>
        <text v-else class="pv-text" selectable>{{ text }}</text>
      </scroll-view>
    </template>

    <view v-if="kind === 'text' && !err" class="pv-foot">
      <button class="pv-btn" size="mini" @click="copyText">复制全文</button>
      <text class="pv-hint">共 {{ text.length }} 字</text>
    </view>
  </view>
</template>

<script>
import { guessFileKind } from '@/utils/file-kind'

/**
 * 跨端文件预览页 —— 小程序没有「新标签页」，`window.open` 那些入口
 * 在小程序里等于点了没反应。统一走这个页面用原生组件打开：
 * video / image / text 三类覆盖成片、封面、分镜表、片段、md、srt。
 * H5 仍走 window.open（能下载），不进这里。
 */
export default {
  data() {
    return {
      url: '',
      name: '',
      kind: 'video',
      text: '',
      loading: false,
      err: '',
    }
  },
  onLoad(q) {
    const url = decodeURIComponent((q && q.url) || '')
    this.name = decodeURIComponent((q && q.name) || '')
    this.url = url
    this.kind = (q && q.kind) || guessFileKind(this.name || url)
    if (!url) {
      this.err = '没有文件地址'
      return
    }
    if (this.kind === 'text') this.fetchText()
  },
  methods: {
    copyLink() {
      if (!this.url) return
      uni.setClipboardData({ data: this.url })
    },
    copyText() {
      uni.setClipboardData({ data: this.text })
    },
    fetchText() {
      if (this.loading) return
      this.loading = true
      uni.request({
        url: this.url,
        method: 'GET',
        timeout: 60000,
        success: (res) => {
          if (res.statusCode !== 200) {
            this.err = `取文件失败（HTTP ${res.statusCode}）`
            return
          }
          const d = res.data
          this.text = typeof d === 'string' ? d : JSON.stringify(d, null, 2)
        },
        fail: () => {
          this.err = '取文件失败，请检查网络'
        },
        complete: () => {
          this.loading = false
        },
      })
    },
  },
}
</script>

<style scoped>
.pv {
  min-height: 100vh;
  background: #0f1115;
  display: flex;
  flex-direction: column;
}
.pv-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20rpx 24rpx;
  background: #161a21;
}
.pv-name {
  flex: 1;
  font-size: 26rpx;
  color: #e6e9ef;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.pv-copy {
  flex: none;
  margin-left: 20rpx;
  font-size: 24rpx;
  color: #2ec4a6;
}
.pv-video {
  width: 100%;
  height: 60vh;
  background: #000;
}
.pv-image {
  width: 100%;
}
.pv-text-wrap {
  flex: 1;
  height: 76vh;
  padding: 20rpx 24rpx;
  box-sizing: border-box;
}
.pv-text {
  font-size: 24rpx;
  line-height: 1.7;
  color: #cfd5df;
  word-break: break-all;
}
.pv-tip {
  font-size: 24rpx;
  color: #8b93a1;
}
.pv-err {
  padding: 60rpx 24rpx;
  font-size: 26rpx;
  color: #ff7b72;
  text-align: center;
}
.pv-foot {
  display: flex;
  align-items: center;
  gap: 20rpx;
  padding: 18rpx 24rpx 32rpx;
  background: #161a21;
}
.pv-btn {
  margin: 0;
  background: #1f6f5f;
  color: #fff;
  font-size: 24rpx;
}
.pv-hint {
  font-size: 22rpx;
  color: #8b93a1;
}
</style>
