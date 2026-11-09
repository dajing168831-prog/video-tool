<template>
  <DramaAppShell>
    <view class="ds">
      <DramaProjectHeader :id="pid" current="video" :name="headerName" :chips="chips" />

      <view v-if="!cur" class="pgstate">正在加载项目…</view>

      <block v-else>
      <!-- ===== 视频时间线（照竞品 video 页左栏，放在最前） ===== -->
      <view class="card">
        <view class="card-head">
          <view class="card-title"><text class="card-no">线</text>视频时间线</view>
          <text class="tl-sum">{{ tlSum }}</text>
        </view>
        <view v-for="t in tlRows" :key="'tl' + t.no" class="tl-row"
              @click="openTimelineSeg(t.no)">
          <text class="tl-no">{{ t.label }}</text>
          <text class="tl-span">{{ t.span }}</text>
          <text class="tl-meta">{{ t.shots }} 镜 · {{ t.dur }}</text>
          <text :class="['tl-state', t.done ? 'ok' : (t.err ? 'bad' : 'dim')]">{{ t.state }}</text>
          <text v-if="t.done" class="seg-play">看这段</text>
        </view>
        <view v-if="!tlRows.length" class="empty">还没有出好的段——回素材页出一段就出现在这里</view>
      </view>

      <!-- ===== 画面：画幅 / 转场 / 渲染 ===== -->
      <view class="card">
        <view class="card-head">
          <view class="card-title"><text class="card-no">画</text>画面</view>
        </view>

        <view class="model-row">
          <text class="model-label">画面比例</text>
          <view class="model-chips">
            <view v-for="r in ratioRows" :key="'cr' + r.id" class="mchip"
                  :class="{ on: filmRatio === r.id }" @click="pickRatio(r.id)">
              <text class="mchip-name">{{ r.label }}</text>
            </view>
          </view>
        </view>
        <view class="merge-tip">改画幅会重算出片计划（不花钱）并让旧的合成计划作废。</view>

        <view class="model-row">
          <text class="model-label">转场</text>
          <view class="model-chips">
            <view v-for="t in compOpt.transitions" :key="t.id" class="mchip"
                  :class="{ on: comp.transition === t.id }"
                  @click="comp.transition = t.id">
              <text class="mchip-name">{{ t.label }}</text>
              <text class="mchip-sub">{{ t.local ? t.desc : '出片阶段 · 本地只能硬切' }}</text>
            </view>
          </view>
        </view>

        <view class="model-row">
          <text class="model-label">渲染</text>
          <view class="model-chips">
            <view v-for="r in compOpt.renders" :key="r.id" class="mchip"
                  :class="{ on: comp.render_preset === r.id }"
                  @click="comp.render_preset = r.id">
              <text class="mchip-name">{{ r.label }}</text>
              <text class="mchip-sub">{{ r.resolution }} · {{ r.video_preset }} · crf{{ r.crf }}</text>
            </view>
          </view>
        </view>
      </view>

      <!-- ===== 字幕 ===== -->
      <view class="card">
        <view class="card-head">
          <view class="card-title"><text class="card-no">字</text>字幕</view>
        </view>
        <view class="model-chips">
          <view v-for="c in compOpt.captions" :key="c.id" class="mchip"
                :class="{ on: comp.captions && comp.caption_preset === c.id }"
                @click="comp.captions = true; comp.caption_preset = c.id">
            <text class="mchip-name">{{ capLabel(c.id) }}</text>
            <text class="mchip-sub">{{ c.karaoke ? '逐字高亮' : ('字号 ' + Math.round(c.font_size_ratio * 100) + '%') }}</text>
          </view>
          <view class="mchip" :class="{ on: !comp.captions }" @click="comp.captions = false">
            <text class="mchip-name">不烧字幕</text>
            <text class="mchip-sub">只留人声</text>
          </view>
        </view>
      </view>

      <!-- ===== 背景音乐 ===== -->
      <view class="card">
        <view class="card-head">
          <view class="card-title"><text class="card-no">乐</text>背景音乐</view>
        </view>
        <view class="comp-row">
          <text class="comp-bgm-name">{{ compBgm ? compBgm.file : '未选（可不上）' }}</text>
          <button class="btn-mini" :disabled="!!busy" @click="pickBgm">
            {{ busy === 'bgm' ? '上传中…' : (compBgm ? '换一条' : '上传 BGM') }}
          </button>
          <button v-if="compBgm" class="btn-mini" :disabled="!!busy" @click="dropBgm">删掉</button>
        </view>
        <view class="merge-tip">mp3 / wav / aac / m4a，≤20MB；人声出现时自动压低（闪避）</view>
        <view class="comp-slider">
          <text class="model-label">音量 {{ Math.round(comp.bgm_volume * 100) }}%</text>
          <slider :value="Math.round(comp.bgm_volume * 100)" :min="5" :max="40" :step="1"
                  activeColor="#4f7cff" @change="onBgmVolume" />
        </view>
        <view class="comp-check" @click="comp.bgm_duck = !comp.bgm_duck">
          <text class="comp-check-box">{{ comp.bgm_duck ? '✓' : '' }}</text>
          <text>人声出现时压低 BGM（闪避）</text>
        </view>
      </view>

      <!-- ===== 人声 / 片尾 ===== -->
      <view class="card">
        <view class="card-head">
          <view class="card-title"><text class="card-no">声</text>人声与片尾</view>
        </view>

        <view class="comp-check" @click="comp.voice_ground = !comp.voice_ground">
          <text class="comp-check-box">{{ comp.voice_ground ? '✓' : '' }}</text>
          <text>人声落地（去播音腔 + 房间底噪）</text>
        </view>
        <view class="merge-tip">
          {{ voiceTrackCount
            ? ('配音轨 ' + voiceTrackCount + ' 句：有配音的段会用 TTS 替掉模型原生声，其余段照常')
            : '还没有配音轨 —— 去下方「配音」卡给整片配音；现在只会给原生声垫一层底噪' }}
        </view>

        <view class="comp-check" @click="comp.end_card = !comp.end_card">
          <text class="comp-check-box">{{ comp.end_card ? '✓' : '' }}</text>
          <text>片尾卡（图片 + CTA，只出现最后几秒）</text>
        </view>
        <block v-if="comp.end_card">
          <input v-model="comp.end_card_text" class="input line" placeholder="CTA 文案，如：点左下角下单" />
          <view class="model-chips" style="margin-top:10rpx;">
            <view class="mchip" :class="{ on: !comp.end_card_image }" @click="comp.end_card_image = ''">
              <text class="mchip-name">只放文字</text>
            </view>
            <view v-for="(im, i) in ((cur.product && cur.product.images) || [])"
                  :key="'ec' + im" class="mchip"
                  :class="{ on: comp.end_card_image === im }"
                  @click="comp.end_card_image = im">
              <text class="mchip-name">商品图 {{ i + 1 }}</text>
            </view>
          </view>
          <view class="merge-tip">想放店铺二维码：把二维码图当商品图上传一张，再选它</view>
        </block>
      </view>

      <!-- ===== 配音（试听 + 整片配音轨） ===== -->
      <view class="card">
        <view class="card-head">
          <view class="card-title"><text class="card-no">音</text>配音</view>
          <button class="btn-mini" @click="toggleTts">{{ ttsOpen ? '收起' : '展开' }}</button>
        </view>
        <view v-if="ttsOpen" class="tts-box">
          <picker :range="ttsVoiceLabels" :value="ttsVoiceIndex" @change="onTtsVoice">
            <view class="tts-pick">{{ ttsVoiceLabels[ttsVoiceIndex] || '选音色' }}</view>
          </picker>
          <textarea class="tts-text" v-model="ttsText" maxlength="200"
                    placeholder="输入要试听的台词（最多 200 字）" />
          <view class="tts-actions">
            <button class="btn-mini" :disabled="ttsBusy" @click="ttsPreview">
              {{ ttsBusy ? '合成…' : '试听' }}
            </button>
            <text v-if="ttsHint" class="tts-hint">{{ ttsHint }}</text>
          </view>
          <view class="merge-tip">免费 · 不用 Key（微软 Edge 朗读，11 个音色含中/英/日/韩/西）。</view>

          <view class="tts-actions" style="margin-top:16rpx;">
            <button class="btn-mini" :disabled="ttsBusy || !voiceLines" @click="buildVoiceTrack">
              {{ voiceBuilding ? '整片配音中…'
                : (voiceTrackCount ? ('重新配音（' + voiceTrackCount + ' 句）')
                                   : ('给整片配音（' + voiceLines + ' 句）')) }}
            </button>
            <button v-if="voiceTrackCount" class="btn-mini" :disabled="ttsBusy" @click="dropVoiceTrack">
              删掉配音轨
            </button>
            <text v-if="voiceNote" class="tts-hint">{{ voiceNote }}</text>
          </view>
          <view class="merge-tip">
            逐句合成、按镜头号落盘；合成时会走「去播音腔」链并给整条时间线垫房间底噪。
            {{ voiceLines ? '' : '（分镜里还没有台词）' }}
          </view>
        </view>
      </view>

      <!-- ===== 风格配方 ===== -->
      <view class="card">
        <view class="card-head">
          <view class="card-title"><text class="card-no">风</text>风格配方</view>
          <button class="btn-mini" @click="toggleStyles">{{ spOpen ? '收起' : '展开' }}</button>
        </view>
        <view v-if="spOpen" class="sp-box">
          <view v-for="b in spBuiltin" :key="b.name" class="pl-row">
            <view class="pl-info">
              <text class="pl-name">{{ b.name }}</text>
              <text class="pl-meta">{{ b.description }}</text>
            </view>
            <text class="media-more" @click.stop="applyStylePack(b)">用这个</text>
          </view>
          <view class="tts-actions">
            <button class="btn-mini" :disabled="spBusy || !cur" @click="exportStylePack">导出当前配方</button>
            <text v-if="spNote" class="tts-hint">{{ spNote }}</text>
          </view>
          <textarea v-model="spText" class="input area" auto-height
                    placeholder="把别人分享的配方 JSON 粘到这里，再点导入" />
          <view class="tts-actions">
            <button class="btn-mini" :disabled="spBusy || !cur" @click="importStylePack">
              {{ spBusy ? '处理中…' : '导入配方' }}
            </button>
            <text v-if="spDropped.length" class="tts-hint">这些字段这边用不了：{{ spDropped.join('、') }}</text>
          </view>
          <view class="merge-tip">
            配方只改合成设置（字幕样式 / BGM 音量与闪避 / 画质 / 片尾卡 / CTA），不碰分镜、也不会自动合成。
          </view>
        </view>
      </view>

      <!-- ===== 合成 ===== -->
      <view class="card">
        <view class="card-head">
          <view class="card-title"><text class="card-no">合</text>合成成片</view>
          <button class="btn-mini" :disabled="!!busy || !compReady" @click="composePlan">
            {{ busy === 'comp-plan' ? '规划中…' : (compPlan ? '重新规划' : '规划合成') }}
          </button>
        </view>
        <view class="merge-tip">
          本地 ffmpeg 加工已出好的段｜不花生成费｜字幕时间轴按实际段长等比对齐
        </view>

        <block v-if="compPlan">
          <view class="film-sum">
            <text class="cm">{{ compPlan.total_seconds }}s</text>
            <text class="cm">{{ (compPlan.segments || []).length }} 段</text>
            <text class="cm">{{ (compPlan.caption || {}).count || 0 }} 条字幕</text>
            <text class="cm">{{ ((compPlan.render || {}).label) || '' }}档</text>
          </view>
          <view v-for="e in (compPlan.errors || [])" :key="'ce' + e" class="film-err">{{ e }}</view>
          <view v-for="w in (compPlan.warnings || [])" :key="'cw' + w" class="film-warn">⚠ {{ w }}</view>
          <view class="merge-tip">
            切点：{{ (compPlan.boundaries || []).join(' / ') || '—' }} 秒
            ｜指纹 {{ compPlan.plan_hash }}
          </view>
        </block>

        <view class="comp-row" style="margin-top:14rpx;">
          <button class="btn-mini" :disabled="!!busy || !compPlan || (compPlan.errors || []).length"
                  @click="composeRun">
            {{ busy === 'comp-run' ? '合成中…' : '合成成片' }}
          </button>
          <text v-if="compOut.mp4" class="seg-play" @click="openCompose">看合成片</text>
          <button class="btn-mini" :disabled="!!busy || !compOut.mp4" @click="compSheet">
            {{ busy === 'sheet' ? '生成中…' : (compOut.sheet ? '重做速览' : '成片速览') }}
          </button>
          <text v-if="compOut.sheet" class="seg-play" @click="openSheet">看速览图</text>
          <button class="btn-mini" :disabled="!!busy || !compOut.mp4" @click="compGif">
            {{ busy === 'gif' ? '生成中…' : (compOut.gif ? '重做 GIF' : '预览 GIF') }}
          </button>
          <text v-if="compOut.gif" class="seg-play" @click="openGif">看 GIF</text>
        </view>
        <view class="comp-check" @click="compProxy = !compProxy">
          <text class="comp-check-box">{{ compProxy ? '✓' : '' }}</text>
          <text>速览同时出审片小样（短边 720 + 烧时间码，方便说「第几秒」）</text>
        </view>

        <view v-if="compOut.mp4" class="next-row">
          <view class="ab-btn ab-main" @click="goExport">下一步：导出 →</view>
        </view>
      </view>


          <view v-if="plan && (plan.segments || []).length" class="merge">
            <view class="merge-head">
              <text class="merge-title">变体矩阵（防同质化）</text>
              <button class="btn-mini" :disabled="!!busy || !!variant.busy" @click="variantPlan">
                {{ variant.busy === 'plan' ? '算…' : '出变体计划' }}
              </button>
            </view>
            <view class="merge-tip">
              同一批已出好的段，只换转场 / 字幕 / 渲染档 / BGM 重跑本地合成｜不花生成费｜主合成不会被覆盖
            </view>
            <view class="model-row">
              <text class="model-label">条数</text>
              <view class="model-chips">
                <view v-for="n in [2, 3, 4]" :key="'vn' + n" class="mchip"
                      :class="{ on: variant.count === n }" @click="variant.count = n">
                  <text class="mchip-name">{{ n }} 条</text>
                </view>
              </view>
            </view>
            <view class="model-row">
              <text class="model-label">随机种子</text>
              <view class="model-chips">
                <view v-for="n in [1, 2, 3]" :key="'vs' + n" class="mchip"
                      :class="{ on: variant.seed === n }" @click="variant.seed = n">
                  <text class="mchip-name">#{{ n }}</text>
                </view>
              </view>
            </view>
            <block v-if="variant.plan">
              <view v-for="sl in (variant.plan.slots || [])" :key="'vp' + sl.idx" class="mat-line">
                变体 {{ sl.idx + 1 }}｜{{ sl.summary }}
              </view>
            </block>
            <view class="comp-row" style="margin-top:14rpx;">
              <button class="btn-mini"
                      :disabled="!!busy || !compReady || !!variant.busy || !((variant.plan || {}).slots)"
                      @click="variantRender">
                {{ variant.busy === 'render' ? '逐条合成中…' : '合成全部变体' }}
              </button>
            </view>
            <view v-for="v in variantRows" :key="'vr' + v.idx" class="comp-row">
              <text class="mat-line">变体 {{ v.idx + 1 }}｜{{ v.summary }}</text>
              <text v-if="v.file" class="seg-play" @click="openVariant(v.idx + 1)">看片</text>
              <text v-else-if="v.error" class="film-err">{{ v.error }}</text>
            </view>
          </view>
      </block>
    </view>
  </DramaAppShell>
</template>

<script>
import { onLoad } from '@dcloudio/uni-app'
import DramaAppShell from '@/components/drama/AppShell.vue'
import DramaProjectHeader from '@/components/drama/ProjectHeader.vue'
import dramaPageBoot from '@/mixins/dramaPageBoot'

/**
 * 商品短剧 · 视频 步（照竞品 app/project/[id]/video/page.tsx 的分工）
 *
 * 本页模板块是**从旧单页 drama/index.vue 原样搬过来**的（逐行区间见
 * docs/DRAMA-UI-RESTRUCTURE.md），逻辑全部来自 mixins/dramaPageBoot。
 * 下一步再按「只留本步要用的 state」收窄，不在搬迁轮里顺手改业务。
 */
export default {
  components: { DramaAppShell, DramaProjectHeader },
  mixins: [dramaPageBoot],
  data() {
    // 时间线行必须是 data 顶层数组：绑 computed / 对象路径在 mp 端会让整页 setData 停更
    return { tlRows: [], tlTotal: 0, tlSum: '' }
  },
  watch: {
    // 出片计划一变（改型号/清晰度/画幅/重出）就重算这条时间线
    plan: {
      handler() { this.syncTimeline() },
      immediate: true,
    },
  },
  onLoad(q) {
    this.boot((q && q.id) || '')
  },
  computed: {
    headerName() {
      const c = this.cur || {}
      return (c.product && c.product.name) || c.topic || '未命名'
    },
    chips() {
      const a = ((this.cur || {}).answers) || {}
      const out = []
      if (a.duration) out.push(a.duration + ' 秒')
      if (a.form) out.push(a.form)
      if (a.role) out.push(a.role)
      return out
    },
  },
  methods: {
    goExport() {
      if (!this.pid) return
      uni.redirectTo({ url: `/pages/drama/export?id=${this.pid}` })
    },
    /** 片段时间线（照竞品 video 页左栏）：第 N 段 · 起止秒 · 出没出 · 出错原因 */
    syncTimeline() {
      const segs = (this.plan && this.plan.segments) || []
      const files = (this.cur && this.cur.film && this.cur.film.files) || {}
      const rows = []
      let acc = 0
      for (let i = 0; i < segs.length; i++) {
        const s = segs[i]
        const sec = Number(s.seconds || 0)
        const f = files[String(s.no)] || {}
        const start = acc
        const end = acc + sec
        acc = end
        rows.push({
          no: s.no,
          label: '第 ' + s.no + ' 段',
          span: start.toFixed(1) + '–' + end.toFixed(1) + ' 秒',
          dur: sec.toFixed(1) + 's',
          shots: (s.shots || []).length,
          done: !!f.name,
          state: f.name ? '已出' : (f.error ? '失败' : '未出'),
          err: f.error || '',
        })
      }
      this.tlRows = rows
      this.tlTotal = acc
      // 汇总文案在 JS 里算好：模板里调 toFixed 在 mp 端不可靠
      this.tlSum = rows.length + ' 段 · 共 ' + acc.toFixed(1) + 's'
    },
    /** 点时间线看这一段（走 mixin 的统一预览：小程序原生 video） */
    openTimelineSeg(no) {
      if (!this.cur) return
      const row = this.tlRows.filter((x) => x.no === no)[0]
      if (!row || !row.done) return
      this.openFilm(no)
    },
  },
}
</script>

<style scoped>
.pgstate {
  padding: 60rpx;
  text-align: center;
  color: #9aa0a6;
  font-size: 24rpx;
}

/* 片段时间线 */
.tl-sum { margin-left: auto; font-size: 20rpx; color: #9aa0a6; }
.tl-row {
  display: flex;
  align-items: center;
  gap: 12rpx;
  padding: 14rpx 0;
  border-bottom: 1rpx solid #f2f4f7;
}
.tl-no { flex: none; width: 110rpx; font-size: 23rpx; font-weight: 600; color: #1b1f27; }
.tl-span { flex: none; width: 180rpx; font-size: 21rpx; color: #4b5563; }
.tl-meta { flex: 1; min-width: 0; font-size: 20rpx; color: #9aa0a6; }
.tl-state { flex: none; font-size: 20rpx; }
.tl-state.ok { color: #0b8f6b; }
.tl-state.bad { color: #c62828; }
.tl-state.dim { color: #b0b6bd; }
</style>
