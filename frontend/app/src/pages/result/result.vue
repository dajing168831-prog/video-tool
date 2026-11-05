<template>
  <view class="page">
    <view v-if="!data" class="empty">加载中…</view>

    <block v-else>
      <!-- 视频预览：走后端代理，直链会过期/防盗链 -->
      <view v-if="data.is_video" class="preview">
        <video
          class="video"
          :src="videoSrc"
          :poster="coverSrc"
          controls
          object-fit="contain"
          :show-center-play-btn="true"
        />
      </view>

      <!-- 图集 -->
      <view v-else class="gallery">
        <view v-for="(img, i) in imageSrcs" :key="i" class="gallery-item">
          <image class="gallery-img" :src="img" mode="widthFix" @click="preview(img)" />
          <view class="gallery-save" @click="saveImage(img, i)">保存</view>
        </view>
      </view>

      <view class="card">
        <view class="head">
          <text class="badge">{{ platformLabel }}</text>
          <text v-if="data.duration" class="dur">{{ fmtDur(data.duration) }}</text>
        </view>
        <view class="title">{{ data.title || '（无标题）' }}</view>
        <view v-if="data.author" class="author">@{{ data.author }}</view>
        <view v-if="data.tags && data.tags.length" class="tags">
          <text v-for="t in data.tags" :key="t" class="tag">#{{ t }}</text>
        </view>
      </view>

      <view class="actions">
        <button v-if="data.is_video" class="btn-primary" @click="saveVideo">保存视频</button>
        <button class="btn-ghost" @click="copyText">复制作品文案</button>
        <button v-if="data.is_video" class="btn-ghost" @click="extractTranscript">
          {{ trLoading ? '正在识别…' : (transcript ? '重新提取口播文案' : '提取口播文案') }}
        </button>
        <button v-if="data.is_video" class="btn-ghost" @click="saveAudio">保存音频</button>
      </view>

      <view class="desc-card">
        <view class="desc-title">作品文案（标题 / 简介 / 话题）</view>
        <text class="desc" :user-select="true">{{ displayText || '（无文案）' }}</text>
      </view>

      <!-- 口播文案：视频里真正说出来的话（语音识别），和上面的作品文案不是一回事 -->
      <view v-if="data.is_video" class="desc-card">
        <view class="desc-head">
          <text class="desc-title">口播文案（视频里说的话）</text>
          <text v-if="transcript" class="desc-count">{{ transcript.chars }} 字</text>
        </view>
        <text v-if="trErr" class="desc-err">{{ trErr }}</text>
        <text v-else-if="trLoading" class="desc-tip">正在识别…（视频越长越久）</text>
        <text v-else-if="transcript" class="desc" :user-select="true">{{ transcript.text }}</text>
        <text v-else class="desc-tip">
          点上方「提取口播文案」，把这支视频里说的话转成文字（较长视频需要等一会儿）
        </text>
        <button v-if="transcript" class="btn-mini" @click="copyTranscript">复制口播文案</button>
      </view>
    </block>
  </view>
</template>

<script>
import { getTask, fileUrl, peekTranscript, makeTranscript } from '@/api/request'
import { store } from '@/store'
import { PLATFORM_LABEL } from '@/config'

export default {
  data() {
    return {
      data: null,
      token: '',
      // 口播文案（语音转写）：null = 还没提取过
      transcript: null,
      trLoading: false,
      trErr: '',
    }
  },
  computed: {
    videoSrc() {
      return this.token ? fileUrl(this.token, 'video') : ''
    },
    coverSrc() {
      return this.data?.cover && this.token ? fileUrl(this.token, 'cover') : ''
    },
    platformLabel() {
      return PLATFORM_LABEL[this.data?.platform] || this.data?.platform || ''
    },
    /** 图集也走服务器代理：平台 CDN 有防盗链，小程序还要求域名白名单 */
    imageSrcs() {
      const list = this.data?.images || []
      return list.map((_, i) => fileUrl(this.token, `image/${i}`))
    },
    fullText() {
      if (!this.data) return ''
      const parts = []
      if (this.data.title) parts.push(this.data.title)
      if (this.data.desc && this.data.desc !== this.data.title) parts.push(this.data.desc)
      if (this.data.tags && this.data.tags.length) {
        parts.push(this.data.tags.map((t) => `#${t}`).join(' '))
      }
      return parts.join('\n')
    },
    /**
     * 展示用文案。抖音博主常拿 U+2800「⠀」（盲文空白）堆空行做排版，
     * 在 App 里是看不见的间距，搬到网页上就是几百像素的大空洞。
     * 这里把「只含空白字符的行」折掉；**复制仍走 fullText 原文**，不改用户拿到的内容。
     */
    displayText() {
      const t = this.fullText
      if (!t) return ''
      return t
        .replace(/\r\n?/g, '\n')
        .replace(/\n(?:[ \t⠀]*\n)+/g, '\n')
        .replace(/[ \t⠀]+$/gm, '')
        .replace(/^⠀+/gm, '')
    },
  },
  onLoad(query) {
    const qToken = query && query.token
    // 带 token 进来（历史页点开）→ 以 token 为准，避免显示成上一次的解析结果
    if (qToken) {
      if (store.current && store.current.token === qToken) {
        this.data = store.current
      } else {
        this.load(qToken)
      }
      this.token = qToken
      this.peekTranscript()
      return
    }
    if (store.current) {
      this.data = store.current
      this.token = store.current.token
      this.peekTranscript()
    } else {
      uni.showToast({ title: '没有解析数据', icon: 'none' })
    }
  },
  methods: {
    async load(token) {
      try {
        this.data = await getTask(token)
        this.peekTranscript()
      } catch (e) {
        uni.showModal({ title: '加载失败', content: e.message, showCancel: false })
      }
    },

    // ---------------- 口播文案（语音转写） ----------------
    /** 只看缓存：转过就显示，没转过什么都不做（不花钱） */
    async peekTranscript() {
      if (!this.token || !this.data || !this.data.is_video) return
      try {
        const t = await peekTranscript(this.token)
        if (t && t.text) this.transcript = t
      } catch (e) {
        /* 缓存读不到不影响页面，点按钮时还会再试一次 */
      }
    },
    async extractTranscript() {
      if (this.trLoading || !this.token) return
      this.trErr = ''
      this.trLoading = true
      uni.showLoading({ title: '正在识别…', mask: true })
      try {
        const t = await makeTranscript(this.token, !!this.transcript)
        this.transcript = t
        uni.hideLoading()
        uni.showToast({ title: '提取完成', icon: 'success' })
      } catch (e) {
        uni.hideLoading()
        this.trErr = e.message || '提取失败'
        uni.showToast({ title: this.trErr, icon: 'none', duration: 3000 })
      } finally {
        this.trLoading = false
      }
    },
    copyTranscript() {
      const text = this.transcript && this.transcript.text
      if (!text) {
        uni.showToast({ title: '还没有口播文案', icon: 'none' })
        return
      }
      uni.setClipboardData({
        data: text,
        success: () => uni.showToast({ title: '口播文案已复制', icon: 'success' }),
      })
    },
    fmtDur(s) {
      const n = Math.round(Number(s) || 0)
      const m = Math.floor(n / 60)
      const sec = n % 60
      return `${m}:${String(sec).padStart(2, '0')}`
    },
    preview(url) {
      uni.previewImage({ urls: this.imageSrcs, current: url })
    },
    copyText() {
      const text = this.fullText
      if (!text) {
        uni.showToast({ title: '没有可复制的文案', icon: 'none' })
        return
      }
      uni.setClipboardData({
        data: text,
        success: () => uni.showToast({ title: '文案已复制', icon: 'success' }),
      })
    },

    // ---------------- 下载 ----------------
    saveVideo() {
      const url = fileUrl(this.token, 'video')
      const name = this.safeName()
      // #ifdef H5
      this.h5Download(url, `${name}.mp4`)
      // #endif
      // #ifndef H5
      this.mpDownload(url, 'video', `${name}.mp4`)
      // #endif
    },
    saveAudio() {
      const url = fileUrl(this.token, 'audio')
      const name = this.safeName()
      // #ifdef H5
      this.h5Download(url, `${name}.m4a`)
      // #endif
      // #ifndef H5
      this.mpDownload(url, 'audio', `${name}.m4a`)
      // #endif
    },
    saveImage(url, i) {
      // #ifdef H5
      this.h5Download(url, `${this.safeName()}_${i + 1}.jpg`)
      // #endif
      // #ifndef H5
      this.mpDownload(url, 'image', `${this.safeName()}_${i + 1}.jpg`)
      // #endif
    },

    async h5Download(url, filename) {
      // 跨域时 <a download> 会被浏览器忽略（只会新开页播放），必须 fetch 成 blob 再下载
      uni.showLoading({ title: '下载中…', mask: true })
      try {
        const res = await fetch(url)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const blob = await res.blob()
        const href = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = href
        a.download = filename
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        // 大文件写盘需要时间，太早 revoke 会中断下载
        setTimeout(() => URL.revokeObjectURL(href), 60000)
        uni.hideLoading()
        uni.showToast({ title: '已开始下载', icon: 'success' })
      } catch (e) {
        uni.hideLoading()
        uni.showToast({ title: `下载失败：${e.message}`, icon: 'none' })
      }
    },

    mpDownload(url, kind, filename) {
      uni.showLoading({ title: '下载中…', mask: true })
      uni.downloadFile({
        url,
        timeout: 600000,
        success: (res) => {
          if (res.statusCode !== 200) {
            uni.hideLoading()
            uni.showToast({ title: '下载失败', icon: 'none' })
            return
          }
          const filePath = res.tempFilePath
          if (kind === 'video') {
            uni.saveVideoToPhotosAlbum({
              filePath,
              success: () => {
                uni.hideLoading()
                uni.showToast({ title: '已保存到相册', icon: 'success' })
              },
              fail: () => {
                uni.hideLoading()
                uni.showModal({
                  title: '保存失败',
                  content: '请在系统设置中允许访问相册',
                  showCancel: false,
                })
              },
            })
          } else if (kind === 'image') {
            uni.saveImageToPhotosAlbum({
              filePath,
              success: () => {
                uni.hideLoading()
                uni.showToast({ title: '已保存到相册', icon: 'success' })
              },
              fail: () => {
                uni.hideLoading()
                uni.showToast({ title: '保存失败，请检查相册权限', icon: 'none' })
              },
            })
          } else {
            // 音频：小程序无法直接存相册，存到本地文件后提示
            uni.saveFile({
              tempFilePath: filePath,
              success: (r) => {
                uni.hideLoading()
                uni.showModal({
                  title: '音频已保存',
                  content: `文件位置：${r.savedFilePath}`,
                  confirmText: '复制路径',
                  success: (m) => {
                    if (m.confirm) uni.setClipboardData({ data: r.savedFilePath })
                  },
                })
              },
              fail: () => {
                uni.hideLoading()
                uni.showToast({ title: '保存失败', icon: 'none' })
              },
            })
          }
        },
        fail: () => {
          uni.hideLoading()
          uni.showToast({ title: '下载失败，请重试', icon: 'none' })
        },
      })
    },

    safeName() {
      const raw = this.data?.title || 'video'
      return raw.replace(/[\\/:*?"<>|\s]+/g, '_').slice(0, 40) || 'video'
    },
  },
}
</script>

<style lang="scss" scoped>
.page {
  min-height: 100vh;
  padding: 24rpx 28rpx 60rpx;
}
.empty {
  padding: 120rpx 0;
  text-align: center;
  color: #9aa0a6;
}
.preview {
  border-radius: 20rpx;
  overflow: hidden;
  background: #000;
}
.video {
  width: 100%;
  height: 420rpx;
}
/* 图文多为竖图（如 1599×2763）：以前两列 + 固定 320rpx 高 + aspectFill 会裁成一条横幅，
   只露出中间一截。改成单列、宽度自适应、高度跟着原图比例走，整张图完整展开。 */
.gallery {
  display: flex;
  flex-direction: column;
  align-items: center;
}
.gallery-item {
  position: relative;
  width: 100%;
  max-width: 640px; /* 桌面 H5 不至于一张竖图铺满整个屏幕；手机上 100% 生效 */
  margin-bottom: 24rpx;
  border-radius: 16rpx;
  overflow: hidden;
  background: #fff;
}
.gallery-img {
  width: 100%;
  display: block;
}
.gallery-save {
  position: absolute;
  right: 12rpx;
  bottom: 12rpx;
  padding: 8rpx 20rpx;
  font-size: 22rpx;
  color: #fff;
  background: rgba(0, 0, 0, 0.55);
  border-radius: 999rpx;
}
.card {
  margin-top: 24rpx;
  padding: 28rpx;
  background: #fff;
  border-radius: 20rpx;
}
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.badge {
  font-size: 22rpx;
  color: #4f7cff;
  background: #eef1fb;
  padding: 6rpx 16rpx;
  border-radius: 999rpx;
}
.dur {
  font-size: 22rpx;
  color: #9aa0a6;
}
.title {
  margin-top: 16rpx;
  font-size: 32rpx;
  font-weight: 600;
  line-height: 1.5;
}
.author {
  margin-top: 10rpx;
  font-size: 24rpx;
  color: #6b7280;
}
.tags {
  margin-top: 16rpx;
  display: flex;
  flex-wrap: wrap;
}
.tag {
  font-size: 22rpx;
  color: #4f7cff;
  margin: 0 12rpx 10rpx 0;
}
.actions {
  margin-top: 24rpx;
}
.btn-primary {
  width: 100%;
  height: 92rpx;
  line-height: 92rpx;
  border-radius: 999rpx;
  background: linear-gradient(135deg, #4f7cff 0%, #7b5cff 100%);
  color: #fff;
  font-size: 30rpx;
  font-weight: 600;
  margin-bottom: 20rpx;
}
.btn-ghost {
  width: 100%;
  height: 88rpx;
  line-height: 88rpx;
  border-radius: 999rpx;
  background: #fff;
  color: #1b1f27;
  font-size: 28rpx;
  margin-bottom: 20rpx;
  border: 1rpx solid #e7e9f0;
}
.desc-card {
  margin-top: 8rpx;
  padding: 28rpx;
  background: #fff;
  border-radius: 20rpx;
}
.desc-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}
.desc-title {
  font-size: 26rpx;
  font-weight: 600;
  color: #6b7280;
  margin-bottom: 16rpx;
}
.desc-count {
  font-size: 22rpx;
  color: #9aa0a6;
}
.desc-tip {
  font-size: 24rpx;
  line-height: 1.7;
  color: #9aa0a6;
}
.desc-err {
  font-size: 24rpx;
  line-height: 1.7;
  color: #e5484d;
}
.btn-mini {
  margin-top: 20rpx;
  width: 100%;
  height: 72rpx;
  line-height: 72rpx;
  border-radius: 999rpx;
  background: #f3f5ff;
  color: #4f7cff;
  font-size: 26rpx;
}
.desc {
  display: block; /* uni-text 默认 inline，宽度只按最长一行算，和上面的卡片对不齐 */
  font-size: 26rpx;
  line-height: 1.8;
  color: #1b1f27;
  word-break: break-all;
}
</style>
