<template>
  <view class="page">
    <view class="ring">
      <view class="num">{{ d.pct || 0 }}<text class="pct">%</text></view>
      <view class="sub">{{ failed ? '出片失败' : done ? '出片完成' : stageText }}</view>
    </view>

    <view class="steps">
      <view v-for="s in steps" :key="s.key" class="step" :class="{ on: s.on, cur: s.cur }">
        <view class="dot">
          <text v-if="s.on">✓</text>
        </view>
        <text class="step-text">{{ s.label }}</text>
      </view>
    </view>

    <view v-if="failed" class="err-box">
      <view class="err">{{ d.error || '未知错误' }}</view>
      <button class="btn-ghost" @click="back">
        {{ kind === 'extend' ? '返回' : '返回修改文案' }}
      </button>
    </view>

    <view v-else-if="!done" class="hint">离开这个页面也不会中断，出完可以在历史里找到</view>
    <view v-else class="hint">正在打开成片…</view>
  </view>
</template>

<script>
import { cloneRenderDetail } from '@/api/request'

const ORDER = [
  { key: 'split', label: '拆分文案', pct: 5 },
  { key: 'tts', label: '合成配音', pct: 20 },
  { key: 'align', label: '对齐时间轴', pct: 45 },
  // 只有勾了换画面才出现这一步
  { key: 'regen', label: '换画面', pct: 50, regenOnly: true },
  { key: 'compose', label: '合成画面', pct: 80 },
]

const LABEL = {
  split: '拆分文案', tts: '合成配音', align: '对齐时间轴',
  compose: '合成画面', done: '完成',
}

export default {
  data() {
    return {
      cid: '',
      rid: '',
      // 延长走的是另一套阶段名（延长中 → 拼接中），步骤条要跟着换
      kind: '',
      d: { state: 'queued', pct: 0, stage: '', error: '' },
      timer: null,
      redirected: false,
    }
  },
  computed: {
    done() {
      return this.d.state === 'done'
    },
    failed() {
      return this.d.state === 'failed'
    },
    order() {
      if (this.kind === 'extend') {
        return [
          { key: '延长中', label: '生成延长段', pct: 5 },
          { key: '拼接中', label: '拼接成片', pct: 75 },
        ]
      }
      // 没勾换画面就不显示那一步；勾了就显示，并标出走的哪条通道
      const e = this.d.edit || {}
      const regen = !!(this.d.regen_prompt || '').trim()
        || !!(e.person || e.product || e.scene || e.wardrobe || e.style)
        || !!(e.extra || '').trim()
      return ORDER.filter((s) => !s.regenOnly || regen).map((s) => {
        if (s.key === 'regen' && this.d.regen_mode === 'whole') {
          return { ...s, label: '画面重制' }
        }
        if (s.key === 'regen' && this.d.regen_mode === 'auto') {
          return { ...s, label: '逐镜重制' }
        }
        return s
      })
    },
    stageText() {
      // 换画面阶段的 stage 是动态文案（"整片重制 1/2（MiniMax H3）"），直接显示
      return LABEL[this.d.stage] || this.d.stage || '排队中'
    },
    steps() {
      const pct = this.d.pct || 0
      const cur = this.d.stage
      const list = this.order
      // 当前进行到第几步：按 pct 落点判断，stage 只用来显示文字
      let curIdx = list.findIndex((s) => s.key === cur)
      if (curIdx < 0) curIdx = list.filter((s) => pct >= s.pct).length - 1
      return list.map((s, i) => ({
        key: s.key,
        label: s.label,
        on: this.done || i < curIdx,
        cur: !this.done && !this.failed && i === curIdx,
      }))
    },
  },
  onLoad(q) {
    this.cid = q.cid || ''
    this.rid = q.rid || ''
    this.kind = q.kind || ''
    if (!this.cid || !this.rid) {
      uni.showToast({ title: '缺少任务参数', icon: 'none' })
      return
    }
    this.tick()
    this.timer = setInterval(this.tick, 1200)
  },
  onUnload() {
    if (this.timer) clearInterval(this.timer)
  },
  methods: {
    async tick() {
      try {
        const d = await cloneRenderDetail(this.cid, this.rid)
        this.d = d
        if (d.state === 'done' && !this.redirected) {
          this.redirected = true
          if (this.timer) clearInterval(this.timer)
          setTimeout(() => {
            uni.redirectTo({ url: `/pages/clone/result?cid=${this.cid}&rid=${this.rid}` })
          }, 500)
        } else if (d.state === 'failed') {
          if (this.timer) clearInterval(this.timer)
        }
      } catch (e) {
        // 轮询失败继续重试
      }
    },
    back() {
      uni.navigateBack()
    },
  },
}
</script>

<style lang="scss" scoped>
.page {
  min-height: 100vh;
  padding: 100rpx 48rpx;
  text-align: center;
}
.ring {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 320rpx;
  height: 320rpx;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 16rpx 50rpx rgba(255, 90, 60, 0.16);
  border: 6rpx solid #ffe6e0;
}
.num {
  font-size: 76rpx;
  font-weight: 700;
  color: #ff5a3c;
  line-height: 1;
}
.pct {
  font-size: 30rpx;
  margin-left: 4rpx;
}
.sub {
  margin-top: 16rpx;
  font-size: 26rpx;
  color: #9aa0a6;
}
.steps {
  margin-top: 76rpx;
  text-align: left;
}
.step {
  display: flex;
  align-items: center;
  padding: 18rpx 0;
  opacity: 0.42;
}
.step.on,
.step.cur {
  opacity: 1;
}
.dot {
  width: 40rpx;
  height: 40rpx;
  line-height: 40rpx;
  text-align: center;
  border-radius: 50%;
  border: 2rpx solid #d9dce3;
  margin-right: 24rpx;
  font-size: 24rpx;
  color: #fff;
}
.step.on .dot {
  background: #22c55e;
  border-color: #22c55e;
}
.step.cur .dot {
  border-color: #ff5a3c;
  background: #ff5a3c;
}
.step-text {
  font-size: 28rpx;
  color: #1b1f27;
}
.hint {
  margin-top: 60rpx;
  font-size: 24rpx;
  color: #9aa0a6;
}
.err-box {
  margin-top: 60rpx;
}
.err {
  font-size: 26rpx;
  color: #e5484d;
  line-height: 1.8;
  margin-bottom: 40rpx;
}
.btn-ghost {
  width: 100%;
  height: 88rpx;
  line-height: 88rpx;
  border-radius: 999rpx;
  background: #ffefec;
  color: #ff5a3c;
  font-size: 30rpx;
}
</style>
