<template>
  <DramaAppShell>
    <view class="ds">
      <view class="page-wrap">
        <view class="bt-hero">
          <text class="bt-t">批量作业</text>
          <text class="bt-s">一次选多个商品，跑到「分镜就绪」为止；出片要进各自项目自己点。</text>
        </view>

        <!-- 断点续跑 -->
        <view v-if="btResumable" class="card">
          <view class="bt-head">
            <text class="bt-title">上次没跑完</text>
            <text class="bt-note">已完成 {{ btDoneCount }}/{{ btJob.total }}</text>
          </view>
          <view class="bt-tip">继续会跳过已完成的条目，只补剩下的。</view>
          <view class="bt-ops">
            <view class="btn-mini" :disabled="btRunning" @click="resumeBatch">继续</view>
            <view class="btn-mini" :disabled="btRunning" @click="discardBatch">放弃这次</view>
          </view>
        </view>

        <!-- ① 选商品 -->
        <view class="card">
          <view class="bt-head">
            <text class="bt-title">选商品</text>
            <text class="bt-note">已选 {{ btPicked.length }} 个</text>
          </view>
          <view v-if="!btProducts.length" class="bt-empty">
            商品库还是空的 —— 先在项目里「存进商品库」，或直接去商品库添加。
          </view>
          <view v-for="p in btProducts" :key="p.id" class="bt-row" @click="togglePick(p.id)">
            <text :class="['bt-box', btPicked.includes(p.id) ? 'on' : '']">{{ btPicked.includes(p.id) ? '✓' : '' }}</text>
            <view class="bt-col">
              <text class="bt-name">{{ p.name }}</text>
              <text class="bt-meta">{{ p.category || '未分类' }} · {{ (p.images || []).length }} 张图</text>
            </view>
          </view>
        </view>

        <!-- ② 设置 -->
        <view class="card">
          <view class="bt-head"><text class="bt-title">设置</text></view>
          <text class="bt-lbl">片长</text>
          <view class="bt-chips">
            <view v-for="d in [15, 30, 60]" :key="'d' + d"
                  :class="['bt-chip', btDuration === d ? 'on' : '']"
                  @click="btDuration = d">{{ d }} 秒</view>
          </view>
          <text class="bt-lbl">防同质化</text>
          <view class="bt-chips">
            <view :class="['bt-chip', btAnti ? 'on' : '']" @click="btAnti = !btAnti">
              {{ btAnti ? '开 · 每条换开场/结构' : '关' }}
            </view>
          </view>
          <view class="bt-ops">
            <view class="btn-mini bt-main" :class="{ off: !btPicked.length || btBusy || btRunning }"
                  @click="startBatch">
              {{ btBusy ? '准备中…' : ('开始批量（' + btPicked.length + ' 条）') }}
            </view>
            <text v-if="btNote" class="bt-note">{{ btNote }}</text>
          </view>
        </view>

        <!-- ③ 进度 -->
        <view class="card">
          <view class="bt-head">
            <text class="bt-title">进度</text>
            <text class="bt-note">{{ btDoneCount }} / {{ (btItems || []).length }}</text>
          </view>
          <view v-if="btRunning" class="bt-ops">
            <view class="btn-mini" @click="abortBatch">停止（已发的会写完）</view>
            <text class="bt-note">并发 3 条；进度逐条写回。</text>
          </view>
          <view v-if="!btItems.length" class="bt-empty">还没开始过批量作业。</view>
          <view v-for="it in btItems" :key="it.id" class="bt-row">
            <text :class="['bt-dot', it.status === 'done' ? 'ok' : (it.status === 'failed' ? 'bad' : '')]" />
            <view class="bt-col">
              <text class="bt-name">{{ it.product_name }} · {{ btStatusText(it.status) }}</text>
              <text class="bt-meta">{{ it.variation || '未开轮换' }}<text v-if="it.error"> · {{ it.error }}</text></text>
            </view>
            <text v-if="it.project_id" class="bt-link" @click.stop="open(it.project_id)">打开</text>
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

/**
 * 批量作业（照竞品 /batch）：选商品 → 片长/防同质化 → 跑到分镜就绪。
 * 🩸 原来是「一张默认折叠的卡」——进来先看到一条标题，用户不知道下一步点哪。
 * 现在永远展开、按 选商品 / 设置 / 进度 三段排（和竞品 /batch 的分段一致）。
 */
export default {
  components: { DramaAppShell },
  mixins: [dramaPageBoot],
  async onLoad() {
    await this.boot('')
    await this.safe(this.loadList)
    // 页面常开：进来就把商品库和上一次作业拉出来
    this.btOpen = true
    await this.safe(this.loadBatch)
  },
}
</script>

<style scoped>
.bt-hero {
  padding: 8rpx 6rpx 24rpx;
}
.bt-t {
  display: block;
  font-size: 36rpx;
  font-weight: 700;
  color: #1b1f27;
}
.bt-s {
  display: block;
  margin-top: 8rpx;
  font-size: 22rpx;
  line-height: 1.6;
  color: #9aa3af;
}
.bt-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4rpx 0 14rpx;
}
.bt-title {
  font-size: 26rpx;
  font-weight: 600;
  color: #1b1f27;
}
.bt-note {
  font-size: 21rpx;
  color: #9aa3af;
}
.bt-tip {
  font-size: 21rpx;
  color: #b0b7c3;
  line-height: 1.5;
  padding-bottom: 12rpx;
}
.bt-empty {
  padding: 26rpx 0;
  font-size: 22rpx;
  color: #9aa3af;
  line-height: 1.6;
}
.bt-row {
  display: flex;
  align-items: center;
  gap: 16rpx;
  padding: 16rpx 0;
  border-top: 1rpx solid #f4f6f8;
}
.bt-box {
  width: 40rpx;
  height: 40rpx;
  line-height: 38rpx;
  text-align: center;
  border-radius: 10rpx;
  border: 1rpx solid #dfe3ea;
  font-size: 22rpx;
  color: #fff;
  flex: none;
}
.bt-box.on {
  background: #12b886;
  border-color: #12b886;
}
.bt-col {
  flex: 1;
  min-width: 0;
}
.bt-name {
  display: block;
  font-size: 25rpx;
  color: #1b1f27;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.bt-meta {
  display: block;
  margin-top: 4rpx;
  font-size: 20rpx;
  color: #9aa3af;
}
.bt-dot {
  width: 12rpx;
  height: 12rpx;
  border-radius: 999rpx;
  background: #d5dae1;
  flex: none;
}
.bt-dot.ok { background: #12b886; }
.bt-dot.bad { background: #e05252; }
.bt-link {
  flex: none;
  font-size: 22rpx;
  color: #0b8f6b;
}
.bt-lbl {
  display: block;
  margin: 6rpx 0 10rpx;
  font-size: 22rpx;
  color: #6b7280;
}
.bt-chips {
  display: flex;
  flex-wrap: wrap;
  margin-bottom: 10rpx;
}
.bt-chip {
  padding: 10rpx 24rpx;
  margin: 0 12rpx 12rpx 0;
  border-radius: 999rpx;
  background: #f2f4f8;
  border: 1rpx solid #e9ecf2;
  font-size: 23rpx;
  color: #4b5563;
}
.bt-chip.on {
  background: #e7f8f2;
  border-color: #12b886;
  color: #0b8f6b;
  font-weight: 600;
}
.bt-ops {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12rpx;
  padding: 10rpx 0 4rpx;
}
.bt-main {
  background: #12b886;
  color: #fff;
  border-color: #12b886;
}
.bt-main.off { opacity: 0.45; }
</style>
