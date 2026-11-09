<template>
  <DramaAppShell>
    <view class="ds">
      <view class="page-wrap">
        <view class="tp-head">
          <view class="tp-title">说一个话题</view>
          <view class="tp-sub">没有商品也能起片：写一句话主题，模型按这个话题写几版内容向脚本给你挑。</view>
        </view>

        <!-- 1 主题 -->
        <view class="card">
          <view class="card-head">
            <view class="card-title"><text class="card-no">题</text>主题</view>
          </view>
          <textarea
            v-model="topicText"
            class="input area"
            placeholder="例：为什么老一辈的酱油要晒足 180 天"
            auto-height
          />
          <view class="tp-tip">2 个字以上。不用写卖点 —— 按话题自己找角度。</view>
        </view>

        <!-- 2 旁白风格 -->
        <view v-if="styleRows.length" class="card">
          <view class="card-head">
            <view class="card-title"><text class="card-no">风</text>旁白风格</view>
          </view>
          <view class="opts">
            <view
              v-for="s in styleRows"
              :key="s.id"
              :class="['opt', style === s.id ? 'on' : '']"
              @click="pickStyle(s)"
            >{{ s.label }}</view>
          </view>
          <view class="tp-tip">{{ styleHint }}</view>
        </view>

        <!-- 3 片长与版本数 -->
        <view class="card">
          <view class="card-head">
            <view class="card-title"><text class="card-no">长</text>片长 / 版本数</view>
          </view>
          <view class="opts">
            <view
              v-for="d in durationRows"
              :key="d"
              :class="['opt', duration === d ? 'on' : '']"
              @click="duration = d"
            >{{ d }} 秒</view>
          </view>
          <view class="opts">
            <view
              v-for="n in countRows"
              :key="n"
              :class="['opt', count === n ? 'on' : '']"
              @click="count = n"
            >{{ n }} 版</view>
          </view>
          <view class="tp-tip">一次调用写出 N 版，回脚本页可以逐版比、逐版切。</view>
        </view>

        <!-- 怎么做成片：只有 AI 生成（没有免费档） -->
        <view class="card">
          <view class="card-head">
            <view class="card-title"><text class="card-no">做</text>怎么做成片</view>
          </view>
          <view class="opts">
            <view class="opt on">🎬 AI 生成</view>
          </view>
          <view class="tp-tip">{{ genHint }}</view>
        </view>

        <view class="tp-cta" @click="start">{{ busy ? '生成中…' : '开始写（花一次模型调用）' }}</view>
        <view class="tp-tip">这一步会调一次模型；不点不花钱。</view>
      </view>
    </view>
  </DramaAppShell>
</template>

<script>
/**
 * 话题起片（照竞品 `app/project/topic/page.tsx`）
 *
 * 竞品这页是「话题 + 旁白风格（5）+ 片长（15/25/40）+ 示例话题」。
 * 我们的等价能力早就有（`POST /api/drama/topic`，一次调用写 N 版），但一直塞在
 * 工作台的弹层里 —— 主人「不要把所有页面都全部放在一起」，所以拆成独立页。
 *
 * 🩸 唯一花钱的入口之一（一次模型调用）：只由用户点「开始写」触发，不自动重试。
 * 🩸 mp-weixin 规矩：v-for 数组（styleRows / durationRows / countRows）都是 data 顶层。
 */
import { onLoad } from '@dcloudio/uni-app'
import DramaAppShell from '@/components/drama/AppShell.vue'
import { dramaTopicOptions, dramaTopicCreate } from '@/api/request'

export default {
  components: { DramaAppShell },
  data() {
    return {
      topicText: '',
      styleRows: [],
      style: '',
      styleHint: '',
      durationRows: [],
      duration: 30,
      countRows: [],
      count: 1,
      busy: false,
      // 成片方式：只有 AI（没有免费档）
      genMode: 'ai',
      genHint: 'AI 按镜头出片（付费）· 停在脚本页，看过预览确认才扣费',
    }
  },
  onLoad() {
    this.loadOptions()
  },
  methods: {
    pickGen(m) {
      // 只保留 AI 一种成片方式（没有免费档）
      this.genMode = 'ai'
      this.genHint = 'AI 按镜头出片（付费）· 停在脚本页，看过预览确认才扣费'
    },
    async loadOptions() {
      try {
        const o = (await dramaTopicOptions()) || {}
        const st = o.styles || []
        const rows = []
        for (let i = 0; i < st.length; i++) {
          rows.push({ id: st[i].id, label: st[i].label || st[i].id, desc: st[i].desc || '' })
        }
        this.styleRows = rows
        this.durationRows = (o.durations || []).slice()
        const lo = Number(o.min_count) || 1
        const hi = Number(o.max_count) || 5
        const nums = []
        for (let n = lo; n <= hi; n++) nums.push(n)
        this.countRows = nums

        const ds = o.default_style || (rows[0] && rows[0].id) || ''
        this.style = ds
        this.styleHint = this.hintOf(ds)
        const dd = Number(o.default_duration) || 30
        this.duration = dd
        this.count = lo
      } catch (e) {
        uni.showToast({ title: '选项拉不到', icon: 'none' })
      }
    },
    hintOf(id) {
      for (let i = 0; i < this.styleRows.length; i++) {
        if (this.styleRows[i].id === id) return this.styleRows[i].desc
      }
      return ''
    },
    pickStyle(s) {
      this.style = s.id
      this.styleHint = s.desc || ''
    },
    async start() {
      if (this.busy) return
      const t = (this.topicText || '').trim()
      if (t.length < 2) {
        uni.showToast({ title: '先写一句话主题', icon: 'none' })
        return
      }
      this.busy = true
      try {
        const r = await dramaTopicCreate({
          topic: t,
          narration_style: this.style,
          duration: this.duration,
          count: this.count,
        })
        const p = (r && r.project) || null
        if (p && p.id) {
          // 没有免费档：停在脚本页，看过预览再决定出片
          uni.redirectTo({ url: '/pages/drama/script?id=' + p.id + '&gen=ai' })
        } else {
          uni.showToast({ title: '已生成，去「我的项目」看', icon: 'none' })
        }
      } catch (e) {
        uni.showModal({ title: '起片失败', content: e.message || '', showCancel: false })
      }
      this.busy = false
    },
  },
}
</script>

<style scoped>
.tp-head { padding: 4rpx 0 18rpx; }
.tp-title { font-size: 34rpx; font-weight: 700; color: #1b1f27; }
.tp-sub { margin-top: 8rpx; font-size: 21rpx; color: #9aa0a6; line-height: 1.6; }
.tp-tip { font-size: 20rpx; color: #9aa0a6; line-height: 1.6; padding: 8rpx 0; }
.tp-cta {
  margin: 20rpx 0 12rpx;
  padding: 26rpx;
  text-align: center;
  border-radius: 16rpx;
  background: linear-gradient(150deg, #12b886 0%, #0b8f6b 100%);
  color: #fff;
  font-size: 27rpx;
  font-weight: 600;
}
</style>
