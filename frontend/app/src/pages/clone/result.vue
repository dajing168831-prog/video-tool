<template>
  <view class="page">
    <view class="player">
      <video
        v-if="videoUrl"
        class="video"
        :src="videoUrl"
        :poster="coverUrl"
        controls
        object-fit="contain"
        :show-center-play-btn="true"
        enable-progress-gesture
      />
      <view v-else class="player-empty">成片加载中…</view>
    </view>

    <view class="meta">
      <view class="meta-left">
        <view class="meta-title">{{ partial ? '片段预览' : '复刻成片' }}</view>
        <view class="meta-sub">时长 {{ duration }} · 文案 {{ segments.length }} 句</view>
        <view class="meta-sub warn" v-if="partial">{{ partialNote }}</view>
        <view class="meta-sub" v-if="regenNote">{{ regenNote }}</view>
        <view class="meta-sub" v-if="voiceNote">{{ voiceNote }}</view>
        <view class="meta-sub warn" v-if="qcNote">{{ qcNote }}</view>
        <view class="meta-sub" :class="{ warn: idBad }" v-if="idNote">{{ idNote }}</view>
        <view class="meta-sub" :class="{ warn: contractBad }" v-if="contractNote">{{ contractNote }}</view>
      </view>
      <view class="meta-tag" :class="{ warn: !qcOk }">{{ qcOk ? '可发布' : '需复核' }}</view>
    </view>

    <view class="versions" v-if="versions.length > 1">
      <text class="v-label">这个作品共 {{ versions.length }} 版</text>
      <view class="v-chips">
        <text
          v-for="(v, i) in versions"
          :key="v.id"
          class="v-chip"
          :class="{ on: v.id === rid }"
          @click="switchVersion(v)"
        >v{{ i + 1 }}</text>
      </view>
    </view>

    <view class="actions">
      <button v-if="partial" class="btn-primary" :loading="continuing"
              :disabled="continuing" @click="continueAll">
        {{ continuing ? '提交中…' : '继续出全部（已出的段不重复扣费）' }}
      </button>
      <button class="btn-ghost" @click="saveVideo">保存到本地</button>
      <button class="btn-ghost" @click="again">再出一版</button>
    </view>

    <view class="card" v-if="segments.length">
      <view class="card-title">逐句文案</view>
      <view class="line dim">哪句不满意就点「改这段」——只把和它重叠的镜头送去重画，其余不动。</view>
      <view v-for="(s, i) in segments" :key="i" class="seg">
        <text class="seg-t">{{ s.start.toFixed(1) }}s</text>
        <text class="seg-x">{{ s.text }}</text>
        <text class="seg-go" @click="editSeg(s)">改这段</text>
      </view>
    </view>

    <view class="tips">
      <view class="tip">· 这条作品在「历史 → 复刻作品」里，随时回来重播、换版本、继续改</view>
      <view class="tip">· 成片会保留 3 天，请及时保存</view>
      <view class="tip">· 发布前请按平台要求勾选「AI 生成内容」标识</view>
    </view>
  </view>
</template>

<script>
import {
  cloneFileUrl,
  cloneRenderDetail,
  cloneRenderContinue,
  cloneDetail,
} from '@/api/request'

export default {
  data() {
    return {
      cid: '',
      rid: '',
      d: null,
      versions: [],
      // 预览片段「继续出全部」提交中
      continuing: false,
    }
  },
  computed: {
    videoUrl() {
      return this.cid && this.rid ? cloneFileUrl(this.cid, 'out', this.rid) : ''
    },
    coverUrl() {
      return this.cid && this.rid ? cloneFileUrl(this.cid, 'cover', this.rid) : ''
    },
    segments() {
      return (this.d && this.d.segments) || []
    },
    // 🩸 只出了前 N 段（预览）：这不是成片，标题和提示都要说清楚，
    //   否则用户会以为整条片子就这么短、或者后面几段被吞了。
    partial() {
      return !!(this.d && this.d.partial)
    },
    partialNote() {
      const m = (this.d && this.d.regen_meta) || {}
      const done = m.done_segments || 1
      const total = m.total_segments || 0
      return `这是前 ${done} 段${total ? `（共 ${total} 段）` : ''}的预览，不是完整成片。`
        + '满意就点「继续出全部」——已出的这一段会复用，不重复扣费；'
        + '觉得不对就回去改提示词再出，避免后面的段白花钱。'
    },
    duration() {
      const s = (this.d && this.d.duration) || 0
      return s ? `${s.toFixed(1)} 秒` : '—'
    },
    // 用的是哪个音色；被替换过就一并说清为什么（选了没生效最让人困惑）
    voiceNote() {
      const m = (this.d && this.d.voice_meta) || {}
      if (!m.voice_label) return ''
      const lang = m.lang === 'en' ? '英文' : '中文'
      return m.voice_note
        ? `配音：${m.voice_label}（${m.voice_note}）`
        : `配音：${m.voice_label} · ${lang}`
    },
    // 质检没通过就不该标"可发布"：旧记录没有 qc 字段（{}）按可发布处理，
    // 新记录以 qc.ok 为准。
    qcOk() {
      const q = (this.d && this.d.qc) || {}
      // 成品契约（口型）不合格也不该标「可发布」——技术指标全绿但嘴对不上，
      // 就是旧版那套「工具全绿、成片是废的」。旧记录没有 contract 字段，按通过处理。
      const c = (this.d && this.d.contract) || {}
      return q.ok !== false && c.ok !== false
    },
    // 成片质检：定格 / 音画时长差 / 总时长偏离。后端本地 ffmpeg 跑的，不额外花钱。
    // 有问题先说清楚，别让用户自己播到一半才发现。
    qcNote() {
      const q = (this.d && this.d.qc) || {}
      const issues = q.issues || []
      if (issues.length) return '质检未通过：' + issues[0]
      const warns = q.warnings || []
      if (warns.length) return '质检提醒：' + warns[0]
      return ''
    },
    // 身份核对：**换脸到底换上了没有**。后端本地 OpenCV 算的（SFace 余弦，
    // ≥0.363 判同人），零成本、每次出片自动跑。写成数出来的值而不是我的观感 ——
    // 10-25 双人换人那次，我盯着 480p 截图判错了两次（先说两个都换上了）。
    idBad() {
      const it = (this.d && this.d.identity) || {}
      return (it.people || []).some((p) => p.verdict === 'not_swapped')
    },
    idNote() {
      const it = (this.d && this.d.identity) || {}
      // 没换人 / 模型没装 / 跑不起来：不打扰，这一行不出现
      if (it.skipped) return ''
      const ps = it.people || []
      if (!ps.length) return ''
      const who = (p) => (/^person(\d+)?$/.test(p.slot)
        ? `人物${p.slot === 'person' ? 1 : p.slot.replace('person', '')}`
        : p.slot)
      const th = it.threshold || 0.363
      const bad = ps.filter((p) => p.verdict === 'not_swapped')
      if (bad.length) {
        const b = bad[0]
        return `⚠ 换脸可能没成功：${bad.map(who).join('、')}最像的一帧只有 ${b.best_sim}，`
          + `九成帧不超过 ${b.p90}（同人线 ${th}）`
      }
      const ok = ps.filter((p) => p.verdict === 'swapped')
      if (ok.length) {
        const o = ok[0]
        return `身份核对：${ok.map(who).join('、')}已换上（最像的一帧在第 ${o.at} 秒，相似度 ${o.best_sim}）`
      }
      if (ps.some((p) => p.verdict === 'no_face')) {
        return '身份核对：片子里没找到人脸，这一版核对不了'
      }
      if (ps.some((p) => p.verdict === 'no_ref')) {
        return '身份核对：参考图里认不出人脸，这一版核对不了'
      }
      return ''
    },
    // 成品契约（第 3 步）：口型跟没跟上原声。后端本地算的，零成本、每片自动跑。
    // 只有口型有判据（|滞后| ≤300ms 且包络相关 ≥0.3）；段间身份和背景仍是只报数，
    // 标定样本不够，不在这里打勾 —— 见 `backend/app/services/contract.py` 顶部。
    contractBad() {
      const c = (this.d && this.d.contract) || {}
      return (c.items || []).some((i) => i.verdict === 'fail')
    },
    contractNote() {
      const c = (this.d && this.d.contract) || {}
      const lips = (c.items || []).filter((i) => String(i.key || '').startsWith('lip'))
      if (!lips.length) return ''
      const bad = lips.filter((i) => i.verdict === 'fail')
      if (bad.length) {
        return '⚠ 口型没跟上原声：'
          + bad.map((i) => `${i.label}滞后 ${Math.abs(i.lag_ms)}ms`).join('、')
          + '（超过 300ms 就算对不上）'
      }
      const ok = lips.filter((i) => i.verdict === 'pass')
      if (ok.length) {
        return `口型核对：${ok.length} 段都跟上了原声（滞后 ${ok.map((i) => `${i.lag_ms}ms`).join(' / ')}）`
      }
      return ''
    },
    // 换画面是拆成几段做的：段数 + 用的哪一款哪一档 + 段间靠不靠尾帧接上。
    // 用户最关心"30 秒的片子到底能不能出"和"我测的到底是哪一款"，这一行就是答案。
    regenNote() {
      const m = (this.d && this.d.regen_meta) || {}
      if (m.mode !== 'whole' && m.mode !== 'auto') return ''
      const n = Number(m.segments || 0)
      if (n <= 1) return ''
      const used = [m.label, m.resolution].filter(Boolean).join(' · ')
      return `画面重制 ${n} 段${used ? '（' + used + '）' : ''}${
        m.boundary ? '，段间用尾帧衔接' : ''}`
    },
  },
  onLoad(q) {
    this.cid = q.cid || ''
    this.rid = q.rid || ''
    this.refresh()
  },
  methods: {
    async refresh() {
      try {
        this.d = await cloneRenderDetail(this.cid, this.rid)
      } catch (e) {
        /* 播放器本身能出画面，详情失败不阻塞 */
      }
      this.loadVersions()
    },
    // 同一作品出过几版：只在页内换 rid，不用退回列表再点进来
    async loadVersions() {
      if (!this.cid) return
      try {
        const t = await cloneDetail(this.cid)
        this.versions = (t.renders || []).filter((r) => r.state === 'done')
      } catch (e) {
        this.versions = []
      }
    },
    switchVersion(v) {
      if (!v || v.id === this.rid) return
      uni.redirectTo({ url: `/pages/clone/result?cid=${this.cid}&rid=${v.id}` })
    },
    // 改这一段：把时间区间带回去，诊断页只处理这一段，其余镜头保持原样
    editSeg(s) {
      const a = Number(s.start || 0).toFixed(2)
      const b = Number(s.end || 0).toFixed(2)
      uni.navigateTo({
        url: `/pages/clone/diagnose?cid=${this.cid}&rid=${this.rid}&only=${a}-${b}`,
      })
    },
    saveVideo() {
      const url = this.videoUrl
      if (!url) return
      // #ifdef H5
      const a = document.createElement('a')
      a.href = url
      a.download = '复刻成片.mp4'
      a.target = '_blank'
      a.click()
      // #endif
      // #ifndef H5
      uni.showLoading({ title: '下载中' })
      uni.downloadFile({
        url,
        success: (res) => {
          uni.hideLoading()
          if (res.statusCode !== 200) {
            uni.showToast({ title: '下载失败', icon: 'none' })
            return
          }
          uni.saveVideoToPhotosAlbum({
            filePath: res.tempFilePath,
            success: () => uni.showToast({ title: '已保存到相册' }),
            fail: () => uni.showToast({ title: '保存失败，请检查相册权限', icon: 'none' }),
          })
        },
        fail: () => {
          uni.hideLoading()
          uni.showToast({ title: '下载失败', icon: 'none' })
        },
      })
      // #endif
    },
    again() {
      uni.navigateBack()
    },
    // 🩸 继续出全部：后端拿这一版存下来的参数原地重跑，已生成的段命中缓存
    //   （缓存键含每段最终提示词），不重复扣费。前端不需要重填任何东西。
    async continueAll() {
      if (this.continuing) return
      this.continuing = true
      try {
        const r = await cloneRenderContinue(this.cid, this.rid)
        uni.redirectTo({
          url: `/pages/clone/progress?cid=${r.id}&rid=${r.render_id}`,
        })
      } catch (e) {
        uni.showModal({ title: '提交失败', content: e.message, showCancel: false })
      } finally {
        this.continuing = false
      }
    },
  },
}
</script>

<style lang="scss" scoped>
.page {
  min-height: 100vh;
  background: #0f1115;
  padding-bottom: 60rpx;
}
.player {
  width: 100%;
  background: #000;
}
.video {
  width: 100%;
  height: 900rpx;
}
.player-empty {
  height: 900rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #6b7280;
  font-size: 26rpx;
}
.meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 32rpx;
  background: #0f1115;
}
.meta-title {
  font-size: 32rpx;
  font-weight: 600;
  color: #fff;
}
.meta-sub {
  margin-top: 8rpx;
  font-size: 24rpx;
  color: #8b909a;
}
.meta-sub.warn {
  color: #f59e0b;
}
.meta-tag {
  font-size: 22rpx;
  color: #22c55e;
  border: 1rpx solid #22c55e;
  border-radius: 999rpx;
  padding: 6rpx 18rpx;
}
.meta-tag.warn {
  color: #f59e0b;
  border-color: #f59e0b;
}
.versions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  padding: 0 32rpx 24rpx;
}
.v-label {
  margin-right: 16rpx;
  font-size: 22rpx;
  color: #8b909a;
}
.v-chips {
  display: flex;
  flex-wrap: wrap;
}
.v-chip {
  margin-right: 12rpx;
  padding: 6rpx 20rpx;
  font-size: 22rpx;
  color: #8b909a;
  border: 1rpx solid #2a2f39;
  border-radius: 999rpx;
}
.v-chip.on {
  color: #ff7a5c;
  border-color: #ff5a3c;
  background: rgba(255, 90, 60, 0.12);
}
.actions {
  display: flex;
  padding: 0 32rpx 24rpx;
}
.btn-ghost {
  flex: 1;
  height: 84rpx;
  line-height: 84rpx;
  margin-right: 20rpx;
  border-radius: 999rpx;
  background: #1c2029;
  color: #ff7a5c;
  font-size: 28rpx;
}
.btn-ghost:last-child {
  margin-right: 0;
}
.card {
  margin: 16rpx 32rpx 0;
  padding: 28rpx;
  background: #171a21;
  border-radius: 24rpx;
}
.card-title {
  font-size: 28rpx;
  font-weight: 600;
  color: #fff;
  margin-bottom: 18rpx;
}
.line {
  font-size: 24rpx;
  line-height: 1.7;
}
.line.dim {
  color: #8b909a;
  margin-bottom: 20rpx;
}.seg {
  display: flex;
  padding: 12rpx 0;
  border-bottom: 1rpx solid #23272f;
}
.seg:last-child {
  border-bottom: none;
}
.seg-t {
  width: 110rpx;
  flex-shrink: 0;
  font-size: 22rpx;
  color: #ff7a5c;
}
.seg-x {
  flex: 1;
  font-size: 25rpx;
  line-height: 1.6;
  color: #c7ccd4;
}
.seg-go {
  flex-shrink: 0;
  align-self: center;
  margin-left: 12rpx;
  padding: 6rpx 16rpx;
  font-size: 22rpx;
  color: #ff5a3c;
  border: 1rpx solid #ff5a3c;
  border-radius: 999rpx;
}
.tips {
  margin: 40rpx 40rpx 0;
}
.tip {
  font-size: 23rpx;
  line-height: 1.9;
  color: #5f6570;
}
</style>
