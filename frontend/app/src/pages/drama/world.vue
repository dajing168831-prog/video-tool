<template>
  <view class="page">
    <view class="hd">
      <text class="ttl">你想把这个产品，拍成什么片？</text>
      <text class="sub">选一个类型，AI 只在这一类里想点子；不选就让它自己挑。</text>
    </view>

    <view class="picker">
      <view class="fam" v-for="g in genres" :key="g.name">
        <text class="fam-t">{{ g.name }}</text>
        <view class="chips">
          <text
            class="chip"
            :class="{ on: genre === it }"
            v-for="it in g.items"
            :key="it"
            @click="choose(it)"
          >{{ it }}</text>
        </view>
      </view>
    </view>

    <view v-if="loading" class="loading">
      <text class="spin">AI 正在按「{{ genre || '自己的判断' }}」想点子…</text>
      <text class="tip">大约 20 秒。</text>
    </view>

    <block v-if="!loading && cands.length">
      <view class="grp">
        <text class="grp-t">{{ genre ? '「' + genre + '」里的几条' : '这几条' }}</text>
        <text class="grp-s">点一条就用它写稿；都不喜欢就换一批。</text>
      </view>
      <view class="card" v-for="(c, i) in cands" :key="i" @click="pick(c)">
        <view class="row">
          <text class="tag">{{ tagOf(c) }}</text>
          <text class="go">就这个 ›</text>
        </view>
        <text class="world">{{ c.world }}</text>
        <text class="from">来路：{{ c.world_from }}</text>
        <text class="pitch" v-if="c.pitch">{{ c.pitch }}</text>
      </view>
    </block>

    <view class="ops" v-if="!busy">
      <button class="btn" v-if="cands.length" :disabled="loading" @click="reload">换一批</button>
      <button class="btn ghost" v-else-if="!genre" :disabled="loading" @click="anyway">不挑，随便来几条</button>
      <button class="btn ghost" :disabled="loading" @click="skip">跳过，直接写</button>
    </view>

    <view v-if="busy" class="mask">
      <text class="mask-t">正在按这个世界写稿…</text>
      <text class="mask-s">结构卡 → 剧本 → 分镜，大约 1–2 分钟</text>
    </view>
  </view>
</template>

<script>
import dramaPage from '@/mixins/dramaPage'
import { dramaWorldGenres, dramaWorlds, dramaPickWorld } from '@/api/request'

export default {
  mixins: [dramaPage],
  data() {
    return {
      pid: '',
      loading: false,
      busy: false,
      genres: [],
      genre: '',
      cands: [],
      gen: 'ai',
    }
  },
  onLoad(q) {
    this.pid = (q && q.id) || ''
    this.gen = (q && q.gen === 'free') ? 'free' : 'ai'
    if (!this.pid) {
      uni.showToast({ title: '项目不存在', icon: 'none' })
      return
    }
    this.loadGenres()
  },
  methods: {
    async loadGenres() {
      try {
        const r = await dramaWorldGenres()
        this.genres = (r && r.groups) || []
      } catch (e) {
        uni.showToast({ title: '类型没拉到', icon: 'none' })
      }
    },
    /** 挑了一个类型 → 只在这个类型里想 */
    async choose(it) {
      if (this.loading || this.busy) return
      this.genre = this.genre === it ? '' : it
      if (!this.genre) {
        this.cands = []
        return
      }
      await this.load(this.genre)
    },
    async reload() {
      if (this.loading || this.busy) return
      await this.load(this.genre)
    },
    /** 不挑类型，让 AI 自己选一个（两条路线各出几条） */
    async anyway() {
      if (this.loading || this.busy) return
      this.genre = ''
      await this.load('')
    },
    async load(genre) {
      this.loading = true
      this.cands = []
      try {
        const r = await dramaWorlds(this.pid, '', genre)
        const list = (r && r.candidates) || []
        if (!list.length) throw new Error('没想出可用的点子')
        this.cands = list
      } catch (e) {
        uni.showToast({ title: e.message || '没生成出来', icon: 'none' })
      } finally {
        this.loading = false
      }
    },
    /** 后台的法则是 L1/L2/L3，顾客看不懂，翻成人话 */
    tagOf(c) {
      const m = { L1: '让商品当主角', L2: '拿关系做文章', L3: '把它扔错地方' }
      return m[c.law] || (c.route === '煽情' ? '真实处境' : '点子')
    },
    async pick(c) {
      if (this.busy) return
      this.busy = true
      try {
        await dramaPickWorld(this.pid, {
          world: c.world,
          world_from: c.world_from,
          world_law: c.law,
          route: c.route,
        })
        await this.goDraft()
      } catch (e) {
        uni.showToast({ title: e.message || '没选上', icon: 'none' })
        this.busy = false
      }
    },
    async skip() {
      if (this.busy) return
      this.busy = true
      try {
        await this.goDraft()
      } catch (e) {
        uni.showToast({ title: e.message || '写稿失败', icon: 'none' })
        this.busy = false
      }
    },
    async goDraft() {
      const r = await this.bootDraft(this.pid)
      const warn = r.ok ? '' : '&draftfail=' + encodeURIComponent(r.failedAt || '写稿')
      uni.redirectTo({ url: `/pages/drama/script?id=${this.pid}&gen=${this.gen}${warn}` })
    },
  },
}
</script>

<style scoped>
.page {
  min-height: 100vh;
  background: #0e0f12;
  padding: 32rpx 24rpx 60rpx;
  box-sizing: border-box;
}
.hd { margin-bottom: 24rpx; }
.ttl { display: block; color: #f2f3f5; font-size: 40rpx; font-weight: 600; }
.sub { display: block; margin-top: 10rpx; color: #8b8f98; font-size: 24rpx; line-height: 1.5; }

.picker { margin-bottom: 12rpx; }
.fam { margin-bottom: 20rpx; }
.fam-t { display: block; margin-bottom: 10rpx; color: #6f747d; font-size: 22rpx; }
.chips { display: flex; flex-wrap: wrap; }
.chip {
  margin: 0 14rpx 14rpx 0;
  padding: 14rpx 24rpx;
  background: #17191d;
  border: 1rpx solid #24272d;
  border-radius: 999rpx;
  color: #c8ccd4;
  font-size: 26rpx;
}
.chip.on { background: #2f4f7a; border-color: #3d6aa3; color: #fff; }

.loading { padding: 60rpx 0; text-align: center; }
.spin { display: block; color: #cfd3da; font-size: 28rpx; }
.tip { display: block; margin-top: 12rpx; color: #6f747d; font-size: 22rpx; }

.grp { margin: 24rpx 0 14rpx; }
.grp-t { display: block; color: #f2f3f5; font-size: 30rpx; font-weight: 600; }
.grp-s { display: block; margin-top: 6rpx; color: #6f747d; font-size: 22rpx; }

.card {
  margin-bottom: 18rpx;
  padding: 24rpx;
  background: #17191d;
  border: 1rpx solid #24272d;
  border-radius: 16rpx;
}
.row { display: flex; align-items: center; justify-content: space-between; }
.tag {
  padding: 4rpx 12rpx;
  background: #23262c;
  color: #9aa0aa;
  font-size: 20rpx;
  border-radius: 8rpx;
}
.go { color: #6f747d; font-size: 22rpx; }
.world { display: block; margin-top: 14rpx; color: #eceef2; font-size: 28rpx; line-height: 1.6; }
.from { display: block; margin-top: 12rpx; color: #7c828c; font-size: 22rpx; line-height: 1.5; }
.pitch { display: block; margin-top: 10rpx; color: #5f646d; font-size: 22rpx; line-height: 1.5; }

.ops { margin-top: 36rpx; }
.btn {
  margin-bottom: 16rpx;
  background: #2a2e36;
  color: #e8eaee;
  font-size: 28rpx;
  border-radius: 14rpx;
}
.btn.ghost { background: transparent; color: #8b8f98; border: 1rpx solid #2a2e36; }
.btn[disabled] { opacity: 0.5; }

.mask {
  position: fixed;
  inset: 0;
  background: rgba(8, 9, 11, 0.86);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.mask-t { color: #f2f3f5; font-size: 30rpx; }
.mask-s { margin-top: 14rpx; color: #7c828c; font-size: 24rpx; }
</style>
