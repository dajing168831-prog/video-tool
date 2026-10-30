<template>
  <view class="page">
    <view class="hero">
      <view class="hero-title">从零写</view>
      <view class="hero-sub">没有原片也行：你写台词和画面，系统配音、生成、剪辑</view>
      <view class="hero-note">一行台词 = 一个镜头</view>
    </view>

    <view class="card">
      <view class="card-title">台词</view>
      <textarea
        v-model="script"
        class="input"
        placeholder="一行一个镜头，例：&#10;这家店开了三十年&#10;老板每天四点起来熬汤"
        maxlength="-1"
        auto-height
        :show-confirm-bar="false"
        @blur="scheduleEst"
      />
      <view class="count">{{ script.trim() ? script.trim().length : 0 }} 字</view>
    </view>

    <view class="card">
      <view class="card-title">画面</view>
      <view class="card-hint">一行一个镜头，和台词按顺序对应；只写一行就全片共用。</view>
      <textarea
        v-model="descs"
        class="input"
        placeholder="例：&#10;清晨的老街，锅里冒着热气&#10;老板低头添柴，火光映在脸上"
        maxlength="-1"
        auto-height
        :show-confirm-bar="false"
        @blur="scheduleEst"
      />
    </view>

    <view class="card">
      <view class="card-title">规格</view>

      <view class="label">画幅</view>
      <view class="chip-row">
        <view
          v-for="r in ratios"
          :key="r"
          class="chip"
          :class="{ on: ratio === r }"
          @click="ratio = r"
        >{{ r }}</view>
      </view>

      <view class="label">通道</view>
      <view class="chip-row">
        <view
          v-for="c in channels"
          :key="c.v"
          class="chip"
          :class="{ on: channel === c.v }"
          @click="pickChannel(c.v)"
        >{{ c.t }}</view>
      </view>

      <view class="label">型号</view>
      <view class="chip-row">
        <view
          v-for="m in modelOpts"
          :key="m.id || 'auto'"
          class="chip"
          :class="{ on: model === m.id }"
          @click="pickModel(m)"
        >{{ m.label }}</view>
      </view>

      <view class="label" v-if="resolOpts.length">清晰度</view>
      <view class="chip-row" v-if="resolOpts.length">
        <view
          v-for="r in resolOpts"
          :key="r"
          class="chip"
          :class="{ on: resolution === r }"
          @click="resolution = r"
        >{{ r }}</view>
      </view>

      <view class="label">配音</view>
      <view class="chip-row">
        <view
          v-for="l in langs"
          :key="l.v"
          class="chip"
          :class="{ on: lang === l.v }"
          @click="onLang(l.v)"
        >{{ l.t }}</view>
      </view>
      <picker mode="selector" :range="voiceLabels" :value="voiceIndex" @change="onVoice">
        <view class="pick-row">
          <text class="pick-label">音色</text>
          <text class="pick-value">{{ voiceLabel }} ›</text>
        </view>
      </picker>

      <view class="switch-row" @click="subtitle = !subtitle">
        <text class="switch-label">烧字幕</text>
        <switch :checked="subtitle" color="#ff5a3c" @change="onSub" />
      </view>
    </view>

    <!-- 花钱之前把"要生成几次、多长"摆出来，全是本地估算 -->
    <view class="est" v-if="est">
      <view class="est-main">
        <text class="est-num">{{ est.count }}</text>
        <text>个镜头 · 约 </text>
        <text class="est-num">{{ est.est_seconds }}</text>
        <text> 秒 · 生成 </text>
        <text class="est-num warn">{{ est.video_calls }}</text>
        <text> 次</text>
      </view>
      <view class="est-warn" v-if="est.blocked">{{ est.blocked }}</view>
      <view class="est-note" v-if="est.price && est.price.known">
        预估 ¥{{ est.price.amount }}（{{ est.price.note }}）
      </view>
      <view class="est-note" v-else>费用：单价未配置，这里不出金额</view>
    </view>

    <button class="btn-primary" :loading="submitting" :disabled="submitting" @click="submit">
      {{ submitting ? '提交中…' : '开始出片' }}
    </button>

    <view class="tips">
      <view class="tip">· 单段超过型号上限会被拦下，先把那一行拆成两行</view>
      <view class="tip">· 一句台词太短（不到 4 秒）时，画面会生成 4 秒再截到台词长度</view>
      <view class="tip">· 出完的片在「历史 → 复刻作品」里</view>
    </view>
  </view>
</template>

<script>
import { cloneModels, cloneVoices, cloneScratch, cloneScratchPlan } from '@/api/request'

export default {
  data() {
    return {
      script: '',
      descs: '',
      ratio: '9:16',
      channel: 'auto',
      model: '',
      resolution: '',
      lang: 'zh',
      voiceId: '',
      subtitle: true,
      submitting: false,
      est: null,
      models: [],
      voices: [],
      ratios: ['9:16', '16:9', '1:1'],
      channels: [
        { v: 'auto', t: '自动选' },
        { v: 'volc', t: '火山' },
        { v: 'minimax', t: 'MiniMax' },
      ],
      langs: [
        { v: 'zh', t: '中文' },
        { v: 'en', t: '英文' },
      ],
      timer: null,
    }
  },
  computed: {
    modelOpts() {
      const ch = this.channel
      const list = !ch || ch === 'auto'
        ? this.models
        : this.models.filter((m) => m.channel === ch)
      return [{ id: '', label: '默认', resolutions: [], channel: '' }].concat(list)
    },
    curModel() {
      return this.models.find((m) => m.id === this.model) || null
    },
    resolOpts() {
      return (this.curModel && this.curModel.resolutions) || []
    },
    voiceLabels() {
      return this.voices.map((v) => v.name || v.id)
    },
    voiceIndex() {
      const i = this.voices.findIndex((v) => v.id === this.voiceId)
      return i < 0 ? 0 : i
    },
    voiceLabel() {
      const v = this.voices.find((x) => x.id === this.voiceId) || this.voices[0]
      return v ? v.name || v.id : '默认'
    },
  },
  onLoad() {
    this.loadModels()
    this.loadVoices()
  },
  methods: {
    async loadModels() {
      try {
        this.models = await cloneModels()
      } catch (e) {
        this.models = []
      }
    },
    async loadVoices() {
      try {
        const d = await cloneVoices('', this.lang)
        this.voices = (d && d.voices) || []
        const def = (d && d.default) || ''
        if (!this.voices.some((v) => v.id === this.voiceId)) {
          this.voiceId = def || (this.voices[0] && this.voices[0].id) || ''
        }
      } catch (e) {
        this.voices = []
      }
    },
    pickChannel(v) {
      this.channel = v
      const m = this.models.find((x) => x.id === this.model)
      if (m && v !== 'auto' && m.channel !== v) this.model = ''
      this.fixRes()
    },
    pickModel(m) {
      this.model = m.id || ''
      if (m.channel) this.channel = m.channel
      this.fixRes()
    },
    fixRes() {
      if (this.resolution && this.resolOpts.indexOf(this.resolution) < 0) this.resolution = ''
    },
    onLang(v) {
      if (this.lang === v) return
      this.lang = v
      this.loadVoices()
    },
    onVoice(e) {
      const v = this.voices[Number((e.detail && e.detail.value) || 0)]
      if (v) this.voiceId = v.id
    },
    onSub(e) {
      this.subtitle = e.detail.value
    },
    // 边打字边估：不花钱，纯粹本地算，让人在按下去之前就知道要生成几次
    scheduleEst() {
      if (this.timer) clearTimeout(this.timer)
      this.timer = setTimeout(this.runEst, 300)
    },
    async runEst() {
      this.timer = null
      const body = this.body()
      if (!body.script.trim() || !body.descs.trim()) {
        this.est = null
        return
      }
      try {
        this.est = await cloneScratchPlan(body)
      } catch (e) {
        this.est = null
      }
    },
    body() {
      return {
        script: this.script,
        descs: this.descs,
        ratio: this.ratio,
        resolution: this.resolution,
        channel: this.channel,
        model: this.model,
        voice: this.voiceId,
        lang: this.lang,
        subtitle: this.subtitle,
      }
    },
    submit() {
      if (this.submitting) return
      if (!this.script.trim()) {
        uni.showToast({ title: '先写台词', icon: 'none' })
        return
      }
      if (!this.descs.trim()) {
        uni.showToast({ title: '先写画面', icon: 'none' })
        return
      }
      if (this.est && this.est.blocked) {
        uni.showModal({ title: '这次出不了', content: this.est.blocked, showCancel: false })
        return
      }
      const n = this.est ? this.est.count : 0
      uni.showModal({
        title: '确认出片',
        content: [
          `本次：${n || '若干'} 个镜头，每个镜头单独生成一段画面`,
          `画幅 ${this.ratio}${this.resolution ? ' · ' + this.resolution : ''}`,
          `配音 ${this.voiceLabel}`,
        ].join('\n'),
        confirmText: '开始',
        cancelText: '再看看',
        success: async (r) => {
          if (!r.confirm) return
          await this.doSubmit()
        },
      })
    },
    async doSubmit() {
      this.submitting = true
      try {
        const d = await cloneScratch(this.body())
        uni.redirectTo({ url: `/pages/clone/progress?cid=${d.id}&rid=${d.render_id}` })
      } catch (e) {
        uni.showModal({
          title: '提交失败',
          content: e.message || '请稍后重试',
          showCancel: false,
        })
      } finally {
        this.submitting = false
      }
    },
  },
}
</script>

<style lang="scss" scoped>
.page {
  min-height: 100vh;
  padding-bottom: 60rpx;
}
.hero {
  padding: 44rpx 40rpx 60rpx;
  background: linear-gradient(135deg, #ff6b4a 0%, #ff3d7f 100%);
  color: #fff;
}
.hero-title {
  font-size: 42rpx;
  font-weight: 700;
}
.hero-sub {
  margin-top: 12rpx;
  font-size: 25rpx;
  line-height: 1.6;
  opacity: 0.92;
}
.hero-note {
  margin-top: 18rpx;
  font-size: 22rpx;
  opacity: 0.8;
}
.card {
  margin: 24rpx 28rpx 0;
  padding: 30rpx;
  background: #fff;
  border-radius: 22rpx;
}
.hero + .card {
  margin-top: -36rpx;
}
.card-title {
  font-size: 27rpx;
  font-weight: 600;
  color: #1b1f27;
  margin-bottom: 16rpx;
}
.card-hint {
  margin: -8rpx 0 16rpx;
  font-size: 22rpx;
  line-height: 1.6;
  color: #9aa0a6;
}
.input {
  width: 100%;
  min-height: 180rpx;
  padding: 22rpx;
  font-size: 27rpx;
  line-height: 1.7;
  background: #f6f7fb;
  border-radius: 14rpx;
  box-sizing: border-box;
}
.count {
  margin-top: 10rpx;
  text-align: right;
  font-size: 21rpx;
  color: #b6bac2;
}
.label {
  margin: 22rpx 0 12rpx;
  font-size: 23rpx;
  color: #6b7280;
}
.chip-row {
  display: flex;
  flex-wrap: wrap;
}
.chip {
  margin: 0 12rpx 12rpx 0;
  padding: 10rpx 24rpx;
  font-size: 24rpx;
  color: #4b5563;
  background: #f6f7fb;
  border-radius: 999rpx;
}
.chip.on {
  color: #fff;
  background: linear-gradient(135deg, #ff6b4a 0%, #ff3d7f 100%);
}
.pick-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10rpx;
  padding: 20rpx 22rpx;
  background: #f6f7fb;
  border-radius: 14rpx;
}
.pick-label {
  font-size: 25rpx;
  color: #4b5563;
}
.pick-value {
  font-size: 25rpx;
  color: #ff5a3c;
}
.switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 22rpx;
}
.switch-label {
  font-size: 25rpx;
  color: #1b1f27;
}
.est {
  margin: 24rpx 28rpx 0;
  padding: 24rpx 28rpx;
  background: #fff7f4;
  border-left: 8rpx solid #ff5a3c;
  border-radius: 14rpx;
}
.est-main {
  font-size: 24rpx;
  color: #6b7280;
}
.est-num {
  font-size: 30rpx;
  font-weight: 700;
  color: #1b1f27;
}
.est-num.warn {
  color: #ff5a3c;
}
.est-warn {
  margin-top: 10rpx;
  font-size: 23rpx;
  line-height: 1.6;
  color: #e5484d;
}
.est-note {
  margin-top: 10rpx;
  font-size: 22rpx;
  color: #9aa0a6;
}
.btn-primary {
  margin: 30rpx 28rpx 0;
  height: 92rpx;
  line-height: 92rpx;
  border-radius: 999rpx;
  background: linear-gradient(135deg, #ff6b4a 0%, #ff3d7f 100%);
  color: #fff;
  font-size: 32rpx;
  font-weight: 600;
}
.tips {
  margin: 36rpx 40rpx 0;
}
.tip {
  font-size: 23rpx;
  line-height: 1.9;
  color: #9aa0a6;
}
</style>
