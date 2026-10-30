<template>
  <view class="page">
    <view class="hero">
      <view class="hero-title">复刻爆款</view>
      <view class="hero-sub">读懂结构 · 换掉文案 · 出可发布的新片</view>
      <view class="hero-steps">
        <view v-for="(s, i) in steps" :key="i" class="step">
          <text class="step-no">{{ i + 1 }}</text>
          <text class="step-tx">{{ s }}</text>
        </view>
      </view>
    </view>

    <view class="card">
      <view class="card-title">粘贴想复刻的爆款链接</view>
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
        {{ loading ? '准备中…' : '开始拆解结构' }}
      </button>
    </view>

    <view class="or"><text class="or-line" />或<text class="or-line" /></view>

    <view class="card">
      <view class="card-title">上传本地视频</view>
      <view class="up-hint">自己拍的、客户发你的都行，不经过平台解析</view>
      <button class="btn-upload" :loading="uploading" :disabled="uploading" @click="pickFile">
        {{ uploading ? uploadText : '选择视频文件' }}
      </button>
      <view class="up-bar" v-if="uploading">
        <view class="up-bar-in" :style="{ width: uploadPct + '%' }" />
      </view>
    </view>


    <view class="tips">
      <view class="tip-title">复刻的是什么</view>
      <view class="tip">· 复刻的是结构：几秒一个镜头、什么时候说话、哪一句在推进卖点、开头三秒怎么抓人</view>
      <view class="tip">· 只想换掉画面：在下一步勾「换什么」并传素材，系统会按素材重画，原片只当参考</view>
      <view class="tip">· 拆解一次可以出任意多版文案，不用重复分析</view>
      <view class="tip">· 出过的片都在「历史 → 复刻作品」里，多版本可以挨个比</view>
    </view>
  </view>
</template>

<script>
import { cloneAnalyze } from '@/api/request'
import { API_BASE } from '@/config'

export default {
  data() {
    return {
      text: '',
      loading: false,
      steps: ['拆解原片结构', '改写文案', '生成新片'],
      uploading: false,
      uploadPct: 0,
    }
  },
  computed: {
    uploadText() {
      return this.uploadPct > 0 ? `上传中 ${this.uploadPct}%` : '上传中…'
    },
  },
  methods: {
    pickFile() {
      if (this.uploading) return
      // #ifdef H5
      // 不用模板里的 <input>：uni-app 在 H5 会把它编译成 uni-input，
      // 不支持 type="file"，点了没反应。只能是动态造一个原生 input。
      const el = document.createElement('input')
      el.type = 'file'
      el.accept = 'video/*'
      el.onchange = () => {
        const f = el.files && el.files[0]
        if (f) this.uploadByBlob(f)
      }
      el.click()
      // #endif
      // #ifndef H5
      uni.chooseVideo({
        sourceType: ['album', 'camera'],
        maxDuration: 180,
        success: (res) => this.uploadByPath(res.tempFilePath),
        fail: () => {},
      })
      // #endif
    },
    // #ifdef H5
    uploadByBlob(file) {
      this.uploading = true
      this.uploadPct = 0
      const fd = new FormData()
      fd.append('file', file)
      // 用 XHR 而不是 fetch：fetch 拿不到上传进度，进度条就只是个装饰
      const xhr = new XMLHttpRequest()
      xhr.open('POST', `${API_BASE}/api/clone/upload`)
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) this.uploadPct = Math.floor((e.loaded / e.total) * 100)
      }
      xhr.onload = () => {
        let body = {}
        try {
          body = JSON.parse(xhr.responseText)
        } catch (e) {
          body = { msg: `服务返回异常（HTTP ${xhr.status}）` }
        }
        this.uploading = false
        this.uploadPct = 0
        this.handleUpload(body)
      }
      xhr.onerror = () => {
        this.uploading = false
        this.uploadPct = 0
        uni.showModal({ title: '上传失败', content: '网络异常，请检查后端是否启动', showCancel: false })
      }
      xhr.send(fd)
    },
    // #endif
    // #ifndef H5
    uploadByPath(tempFilePath) {
      this.uploading = true
      this.uploadPct = 0
      const task = uni.uploadFile({
        url: `${API_BASE}/api/clone/upload`,
        filePath: tempFilePath,
        name: 'file',
        // 默认 60s：几十兆的原片在 WiFi 下传不完就被掐断
        timeout: 600000,
        success: (res) => {
          let body = {}
          try {
            body = JSON.parse(res.data)
          } catch (e) {
            body = { msg: '服务返回异常' }
          }
          this.handleUpload(body)
        },
        fail: () => uni.showToast({ title: '上传失败', icon: 'none' }),
        complete: () => {
          this.uploading = false
          this.uploadPct = 0
        },
      })
      task.onProgressUpdate((r) => {
        this.uploadPct = r.progress
      })
    },
    // #endif
    handleUpload(body) {
      if (body && body.code === 200 && body.biz_code === 0 && body.data && body.data.id) {
        uni.navigateTo({ url: `/pages/clone/diagnose?cid=${body.data.id}` })
        return
      }
      uni.showModal({
        title: '无法使用这个视频',
        content: (body && body.msg) || '请换一个文件试试',
        showCancel: false,
      })
    },
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
    async submit() {
      const t = (this.text || '').trim()
      if (!t) {
        uni.showToast({ title: '请先粘贴链接', icon: 'none' })
        return
      }
      if (this.loading) return
      this.loading = true
      try {
        const data = await cloneAnalyze(t)
        uni.navigateTo({ url: `/pages/clone/diagnose?cid=${data.id}` })
      } catch (e) {
        uni.showModal({
          title: '拆解失败',
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
  background: linear-gradient(135deg, #ff6b4a 0%, #ff3d7f 100%);
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
  opacity: 0.9;
}
.hero-steps {
  margin-top: 28rpx;
  display: flex;
}
.step {
  display: flex;
  align-items: center;
  margin-right: 28rpx;
  font-size: 22rpx;
}
.step-no {
  width: 32rpx;
  height: 32rpx;
  line-height: 32rpx;
  text-align: center;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.24);
  margin-right: 10rpx;
}
.card {
  margin: 28rpx 28rpx 0;
  padding: 32rpx;
  background: #fff;
  border-radius: 24rpx;
  box-shadow: 0 12rpx 40rpx rgba(31, 45, 90, 0.1);
}
/* 只有第一张卡压在 hero 上，后面的卡正常排 */
.hero + .card {
  margin-top: -44rpx;
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
  background: #ffefec;
  color: #ff5a3c;
  border-radius: 999rpx;
  font-size: 24rpx;
}
.btn-primary {
  width: 100%;
  height: 92rpx;
  line-height: 92rpx;
  border-radius: 999rpx;
  background: linear-gradient(135deg, #ff6b4a 0%, #ff3d7f 100%);
  color: #fff;
  font-size: 32rpx;
  font-weight: 600;
}
.or {
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 36rpx 40rpx 28rpx;
  font-size: 24rpx;
  color: #b6bcc6;
}
.or-line {
  flex: 1;
  height: 1rpx;
  background: #e6e8ee;
  margin: 0 20rpx;
}
.up-hint {
  font-size: 24rpx;
  line-height: 1.7;
  color: #9aa0a6;
  margin-bottom: 24rpx;
}
.btn-upload {
  width: 100%;
  height: 88rpx;
  line-height: 88rpx;
  border-radius: 999rpx;
  background: #fff5f2;
  color: #ff5a3c;
  border: 1rpx solid #ffd9d0;
  font-size: 30rpx;
  font-weight: 600;
}
.btn-upload[disabled] {
  background: #f6f7fb;
  color: #b6bcc6;
  border-color: #eceef3;
}
.up-bar {
  margin-top: 20rpx;
  height: 8rpx;
  border-radius: 999rpx;
  background: #f0f1f5;
  overflow: hidden;
}
.up-bar-in {
  height: 100%;
  border-radius: 999rpx;
  background: linear-gradient(135deg, #ff6b4a 0%, #ff3d7f 100%);
  transition: width 0.2s linear;
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
