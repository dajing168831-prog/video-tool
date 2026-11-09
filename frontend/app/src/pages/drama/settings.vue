<template>
  <DramaAppShell>
    <view class="ds">
      <view class="page-wrap">
        <view class="st-hero">
          <text class="st-t">设置</text>
          <text class="st-s">只影响还没单独存过设置的项目；在项目里调过的值以项目为准。</text>
        </view>

        <!-- 分区切换（照竞品 /settings 的 tab：providers / video / tts / 高级） -->
        <view class="st-tabs">
          <view
            v-for="t in tabs"
            :key="t.id"
            :class="['st-tab', stTab === t.id ? 'on' : '']"
            @click="stTab = t.id"
          >{{ t.label }}</view>
        </view>

        <!-- ① 模型与密钥（竞品 providers） -->
        <view v-if="stTab === 'providers'" class="card">
          <view class="card-head">
            <view class="card-title"><text class="card-no">钥</text>模型与密钥</view>
            <button class="btn-mini" :disabled="!!prBusy" @click="probeAll">
              {{ prBusy === 'all' ? '逐个测试中…' : '全部测一遍' }}
            </button>
          </view>
          <view v-for="k in stKeys" :key="k.name" class="pl-row">
            <view class="pl-info">
              <text class="pl-name">{{ k.label }}</text>
              <text class="pl-meta">{{ k.configured ? ('已配置 ' + k.masked) : '未配置（走环境变量）' }}</text>
              <text v-if="prNote(k.name)" class="pl-meta">{{ prNote(k.name) }}</text>
            </view>
            <text v-if="prSupported(k.name)" class="media-more" @click.stop="probeOne(k.name)">
              {{ prBusy === k.name ? '测试中…' : '测连通' }}
            </text>
          </view>
          <view v-if="!stKeys.length" class="st-empty">还没有读到密钥清单。</view>
          <view class="merge-tip">
            这里只显示「配置没配置」和掩码，不回整串 Key；Keys 改环境变量后需要重启后端。
          </view>
        </view>

        <!-- ② 成片（竞品 video） -->
        <view v-if="stTab === 'video'" class="card">
          <view class="card-head">
            <view class="card-title"><text class="card-no">片</text>成片默认</view>
          </view>

          <view class="model-row">
            <text class="model-label">字幕</text>
            <view class="model-chips">
              <view v-for="o in stOpts.caption_preset" :key="o.id" class="mchip"
                    :class="{ on: st.caption_preset === o.id }"
                    @click="st.caption_preset = o.id">
                <text class="mchip-name">{{ capLabel(o.id) }}</text>
                <text class="mchip-sub">{{ o.id === 'karaoke' ? '逐字高亮' : '普通' }}</text>
              </view>
            </view>
          </view>
          <view class="model-row">
            <text class="model-label">画质</text>
            <view class="model-chips">
              <view v-for="o in stOpts.render_preset" :key="o.id" class="mchip"
                    :class="{ on: st.render_preset === o.id }" @click="st.render_preset = o.id">
                <text class="mchip-name">{{ o.label }}</text>
              </view>
            </view>
          </view>
          <view class="model-row">
            <text class="model-label">转场</text>
            <view class="model-chips">
              <view v-for="o in stOpts.transition" :key="o.id" class="mchip"
                    :class="{ on: st.transition === o.id }" @click="st.transition = o.id">
                <text class="mchip-name">{{ o.label }}</text>
              </view>
            </view>
          </view>
          <view class="model-row">
            <text class="model-label">成片分辨率</text>
            <view class="model-chips">
              <view v-for="o in stOpts.film_resolution" :key="o.id" class="mchip"
                    :class="{ on: st.film_resolution === o.id }" @click="st.film_resolution = o.id">
                <text class="mchip-name">{{ o.label }}</text>
              </view>
            </view>
          </view>
          <view class="model-row">
            <text class="model-label">画面比例</text>
            <view class="model-chips">
              <view v-for="o in stOpts.film_ratio" :key="o.id" class="mchip"
                    :class="{ on: st.film_ratio === o.id }" @click="st.film_ratio = o.id">
                <text class="mchip-name">{{ o.label }}</text>
              </view>
            </view>
          </view>
          <view class="model-row">
            <text class="model-label">接缝默认</text>
            <view class="model-chips">
              <view v-for="o in stOpts.film_chain" :key="o.id" class="mchip"
                    :class="{ on: st.film_chain === o.id }" @click="st.film_chain = o.id">
                <text class="mchip-name">{{ o.label }}</text>
              </view>
            </view>
          </view>
          <view class="model-row">
            <text class="model-label">真实感默认</text>
            <view class="model-chips">
              <view v-for="o in stOpts.film_realism" :key="o.id" class="mchip"
                    :class="{ on: st.film_realism === o.id }" @click="st.film_realism = o.id">
                <text class="mchip-name">{{ o.label }}</text>
              </view>
            </view>
          </view>
          <view class="merge-tip">
            三个成片默认（分辨率 / 接缝 / 真实感）只对还没规划过的项目生效。
          </view>
        </view>

        <!-- ③ 配音与音乐（竞品 tts） -->
        <view v-if="stTab === 'tts'" class="card">
          <view class="card-head">
            <view class="card-title"><text class="card-no">音</text>配音与音乐</view>
          </view>
          <view class="model-row">
            <text class="model-label">配音音色</text>
            <view class="model-chips">
              <view v-for="o in stOpts.tts_voice" :key="o.id" class="mchip"
                    :class="{ on: st.tts_voice === o.id }" @click="st.tts_voice = o.id">
                <text class="mchip-name">{{ o.label }}</text>
              </view>
            </view>
          </view>
          <view class="comp-slider">
            <text class="model-label">BGM 音量 {{ Math.round((st.bgm_volume || 0) * 100) }}%</text>
            <slider :value="Math.round((st.bgm_volume || 0) * 100)" :min="5" :max="40" :step="1"
                    activeColor="#4f7cff" @change="onStVolume" />
          </view>
          <view class="comp-check" @click="st.bgm_duck = !st.bgm_duck">
            <text class="comp-check-box">{{ st.bgm_duck ? '✓' : '' }}</text>
            <text class="comp-check-text">有人声时压低 BGM（闪避）</text>
          </view>
          <view class="merge-tip">
            配音走免费 Edge；音色只影响新合成的片子，已合成的不会自动重配。
          </view>
        </view>

        <!-- ④ 高级（旧版导入） -->
        <view v-if="stTab === 'advanced'" class="card">
          <view class="card-head">
            <view class="card-title"><text class="card-no">迁</text>旧版导入</view>
            <button class="btn-mini" @click="stImportOpen = !stImportOpen">
              {{ stImportOpen ? '收起' : '展开' }}
            </button>
          </view>
          <view class="merge-tip">从旧安装 / 竞品搬设置：自动修好「装完正常、一生成就报错」的坏值。</view>
          <block v-if="stImportOpen">
            <textarea class="tts-text" v-model="stImportText" maxlength="20000"
                      placeholder="把旧设置整段 JSON 贴进来（含 { }），支持 {state,version} 包装或裸对象" />
            <view class="tts-actions">
              <button class="btn-mini" :disabled="stImportBusy" @click="importLegacySettings">
                {{ stImportBusy ? '迁移中…' : '导入并迁移' }}
              </button>
              <text v-if="stImportNote" class="tts-hint">{{ stImportNote }}</text>
            </view>
            <view v-for="(f, i) in stImportFixed" :key="'fx' + i" class="merge-tip">✓ {{ f }}</view>
            <view v-for="(d, i) in stImportDropped" :key="'dp' + i" class="merge-tip">· {{ d }}</view>
          </block>
        </view>

        <!-- 保存：三个设置 tab 共用（高级 tab 不需要） -->
        <view v-if="stTab !== 'advanced'" class="st-savebar">
          <view class="btn-main st-save" @click="saveSettings">{{ stBusy ? '保存中…' : '保存' }}</view>
          <text class="st-reset" @click="resetSettings">恢复默认</text>
          <text v-if="stNote" class="st-note">{{ stNote }}</text>
        </view>
      </view>
    </view>
  </DramaAppShell>
</template>

<script>
import { onLoad } from '@dcloudio/uni-app'
import DramaAppShell from '@/components/drama/AppShell.vue'
import dramaPageBoot from '@/mixins/dramaPageBoot'

/**
 * 设置中心（照竞品 /settings 的分区）：模型与密钥 / 成片 / 配音与音乐 / 高级。
 *
 * 竞品是 7 个 tab（providers / llm / image / video / tts / characters / brand）；
 * 我们后端只有「密钥状态 + 成片默认 + 免费配音音色 + BGM」这几组值，
 * 所以只开四个对得上的分区 —— 不凭竞品的 tab 名放假开关。
 * 🩸 保存/恢复默认是三个设置 tab 共用的同一个接口，所以放在页面底部一条。
 */
export default {
  components: { DramaAppShell },
  mixins: [dramaPageBoot],
  data() {
    return {
      stTab: 'providers',
      tabs: [
        { id: 'providers', label: '模型与密钥' },
        { id: 'video', label: '成片' },
        { id: 'tts', label: '配音与音乐' },
        { id: 'advanced', label: '高级' },
      ],
    }
  },
  async onLoad() {
    await this.boot('')
    this.stOpen = true
  },
}
</script>

<style scoped>
.st-hero { padding: 8rpx 6rpx 20rpx; }
.st-t { display: block; font-size: 36rpx; font-weight: 700; color: #1b1f27; }
.st-s { display: block; margin-top: 8rpx; font-size: 22rpx; line-height: 1.6; color: #9aa3af; }
.st-tabs {
  display: flex;
  flex-wrap: wrap;
  margin-bottom: 18rpx;
}
.st-tab {
  padding: 12rpx 26rpx;
  margin: 0 12rpx 12rpx 0;
  border-radius: 999rpx;
  background: #fff;
  border: 1rpx solid #e9ecf2;
  font-size: 23rpx;
  color: #4b5563;
}
.st-tab.on {
  background: #e7f8f2;
  border-color: #12b886;
  color: #0b8f6b;
  font-weight: 600;
}
.st-empty { padding: 24rpx 0; font-size: 22rpx; color: #9aa3af; }
.st-savebar {
  display: flex;
  align-items: center;
  gap: 20rpx;
  padding: 10rpx 4rpx 30rpx;
}
.st-save {
  flex: none;
  width: auto;
  padding: 0 64rpx;
  margin-top: 0;
}
.st-reset { font-size: 23rpx; color: #9aa3af; }
.st-note { font-size: 21rpx; color: #0b8f6b; }
</style>
