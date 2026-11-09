<template>
  <DramaAppShell>
    <view class="ds">
<view class="page-wrap">
    <view class="card">
      <view class="card-head">
        <view class="card-title"><text class="card-no">解</text>媒体解构</view>
        <button class="btn-mini" :disabled="mlBusy" @click="toggleMediaLab">
          {{ mlOpen ? '收起' : '展开' }}
        </button>
      </view>
      <view v-if="mlOpen" class="sp-box">
        <view class="tts-actions">
          <button class="btn-mini" :disabled="mlBusy" @click="pickLabMedia('image')">选图片</button>
          <button class="btn-mini" :disabled="mlBusy" @click="pickLabMedia('video')">选视频</button>
          <text class="tts-hint">{{ mlFileLabel() || 'JPG/PNG/WebP ≤15MB；MP4/WebM/MOV ≤80MB、≤3 分钟' }}</text>
        </view>
        <view class="tts-actions">
          <button class="btn-mini" :disabled="!mlFile || mlBusy" @click="analyzeMedia">
            {{ mlBusy ? '解构中…' : '开始解构' }}
          </button>
          <text v-if="mlNote" class="tts-hint">{{ mlNote }}</text>
        </view>
        <view v-if="mlResult">
          <view class="label">摘要</view>
          <view class="merge-tip">{{ mlResult.summary || '—' }}</view>
          <view v-if="mlResult.subjects && mlResult.subjects.length" class="fb-tags">
            <text v-for="t in mlResult.subjects" :key="t" class="fb-tag">{{ t }}</text>
          </view>
          <view class="label">画面</view>
          <view class="pl-row"><text class="pl-name">光线</text><text class="pl-meta">{{ mlResult.visual_style.lighting || '—' }}</text></view>
          <view class="pl-row"><text class="pl-name">色彩</text><text class="pl-meta">{{ mlResult.visual_style.palette || '—' }}</text></view>
          <view class="pl-row"><text class="pl-name">构图</text><text class="pl-meta">{{ mlResult.visual_style.composition || '—' }}</text></view>
          <view class="pl-row"><text class="pl-name">镜头</text><text class="pl-meta">{{ mlResult.visual_style.camera || '—' }}</text></view>
          <template v-if="mlResult.motion">
            <view class="label">动效</view>
            <view class="pl-row"><text class="pl-name">节奏</text><text class="pl-meta">{{ mlResult.motion.pacing || '—' }}</text></view>
            <view class="pl-row"><text class="pl-name">镜头运动</text><text class="pl-meta">{{ (mlResult.motion.camera_moves || []).join(' · ') || '—' }}</text></view>
            <view class="pl-row"><text class="pl-name">剪辑节奏</text><text class="pl-meta">{{ mlResult.motion.scene_rhythm || '—' }}</text></view>
          </template>
          <view class="label">可复用提示词</view>
          <view class="merge-tip">{{ mlResult.reusable_prompt || '—' }}</view>
          <view v-if="mlResult.negative_prompt" class="merge-tip">避开：{{ mlResult.negative_prompt }}</view>
          <view v-if="mlResult.suggested_uses && mlResult.suggested_uses.length" class="merge-tip">
            适用：{{ mlResult.suggested_uses.join(' · ') }}
          </view>
          <view class="tts-actions">
            <button class="btn-mini" :disabled="!mlResult.reusable_prompt" @click="copyReusablePrompt">复制提示词</button>
            <picker :range="mlProjectNames" @change="mlPickProject">
              <button class="btn-mini">{{ mlProjectId ? '换项目' : '选项目' }}</button>
            </picker>
            <button class="btn-mini" :disabled="!mlProjectId || mlSaving" @click="saveMediaInsight">
              {{ mlSaving ? '保存中…' : '存进项目' }}
            </button>
          </view>
        </view>
        <view class="merge-tip">
          视频会自动抽 8 帧拼成速览再看；只描述画面事实，不认人、不猜身份。
        </view>
      </view>
    </view>
</view>
    </view>
  </DramaAppShell>
</template>

<script>
import { onLoad } from '@dcloudio/uni-app'
import DramaAppShell from '@/components/drama/AppShell.vue'
import dramaPageBoot from '@/mixins/dramaPageBoot'

/** 媒体解构（照竞品 /media-lab）：图/视频 → 风格结论 + 可复用提示词 */
export default {
  components: { DramaAppShell },
  mixins: [dramaPageBoot],
  onLoad() {
    this.boot('')
    // 「存进项目」的项目下拉要项目列表（旧单页是 onShow 里 loadList 带出来的）
    this.safe(this.loadList)
  },
}
</script>
