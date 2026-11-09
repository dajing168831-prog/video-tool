<template>
  <DramaAppShell>
    <view class="ds">
      <view class="home">
        <!-- 主视觉（照竞品 start/page.tsx:662-665） -->
        <view class="hero-lite">
          <text class="eyebrow">AI 带货短视频工作台</text>
          <text class="h1">丢张商品图，<text class="hl">直接出片</text></text>
          <text class="sub">上传商品图，或说一句话主题。AI 自动写脚本、配画面、配音，合成竖屏成片——先开跑，要用到 AI 时再配 Key。</text>
        </view>

        <!-- 创建卡：三种模式页内直接建（照竞品 cf-card） -->
        <view class="mk">
          <!-- 忙碌接管：整卡变进度清单（竞品 start/page.tsx:668-693） -->
          <view v-if="running" class="prog">
            <view class="prog-title">
              <text class="spin">◌</text>
              <text>正在为你生成</text>
            </view>
            <view
              v-for="(s, i) in progSteps"
              :key="s"
              :class="['prog-step', progIdx > i ? 'done' : (progIdx === i ? 'on' : '')]"
            >
              <text class="ic">{{ progIdx > i ? '✓' : (progIdx === i ? '●' : (i + 1)) }}</text>
              <text class="prog-lbl">{{ s }}</text>
            </view>
            <text class="prog-hint">{{ progNow || '通常 20~60 秒 · 写完脚本会自动进入下一步，请别关页面' }}</text>
          </view>

          <block v-else>
            <!-- 三种起片方式（竞品 tabUpload / tabLink / tabTopic） -->
            <view class="tabs">
              <view :class="['tab', mode === 'upload' ? 'on' : '']" @click="mode = 'upload'">📷 上传商品图</view>
              <view :class="['tab', mode === 'link' ? 'on' : '']" @click="mode = 'link'">🔗 商品链接</view>
              <view :class="['tab', mode === 'topic' ? 'on' : '']" @click="mode = 'topic'">💬 一句话成片</view>
            </view>

            <block v-if="mode === 'upload'">
              <view class="drop" @click="pickPics">
                <text class="drop-ico">＋</text>
                <text class="drop-t">{{ busy === 'pic' ? '上传中…' : '点这里上传商品图' }}</text>
                <text class="drop-s">JPG / PNG，最多 {{ opt.max_pics }} 张</text>
              </view>
              <view v-if="form.images.length" class="thumbs">
                <view v-for="(im, i) in form.images" :key="im.name" class="thumb">
                  <image :src="im.url" class="thumb-img" mode="aspectFill" />
                  <view class="thumb-del" @click.stop="dropPic(i)">×</view>
                </view>
              </view>
              <input v-model="form.name" class="input line fld" placeholder="商品名称（必填，如：便携榨汁杯）" />
              <textarea
                v-model="form.points"
                class="input area fld"
                auto-height
                placeholder="核心卖点（选填）——填了脚本更精准"
              />
            </block>

            <block v-else-if="mode === 'link'">
              <input
                v-model="form.url"
                class="input line"
                placeholder="粘贴商品链接（淘宝/京东/拼多多/1688/独立站…）"
              />
              <text class="ds-hint">自动抓取商品标题、价格、主图，直接建项目并写带货脚本</text>
            </block>

            <block v-else>
              <textarea
                v-model="topic.topic"
                class="input area topic-area"
                auto-height
                placeholder="说个主题，如：3 个让租房变高级的小物 / 冬天必囤的护手霜"
              />
            </block>

            <!-- 出片方式：两条路先选清楚（照竞品首页两张卡）。
                 2026-11-08 主人踩过：一路走到出片才发现是商品图配字幕，因为这里写死成「只有 AI」。 -->
            <view class="genrow">
              <view class="gen" :class="{ on: genMode === 'free' }" @click="pickGen('free')">
                <text class="gen-b">⚡ 免费快剪</text>
                <text class="gen-s">商品图 + 字幕拼出来 · 全程 ¥0 · 不是拍的戏</text>
              </view>
              <view class="gen" :class="{ on: genMode === 'ai' }" @click="pickGen('ai')">
                <text class="gen-b">✨ AI 生成</text>
                <text class="gen-s">模型真的拍出画面 · 按秒计费 · 先预览再确认</text>
              </view>
            </view>

            <!-- 剧本形态 / 出镜人物 / 生产档位（竞品 772-800）。
                 两条路都要写剧本，所以形态两种模式都给；出镜人物只对 AI 有意义。 -->
            <block v-if="mode !== 'topic'">
              <!-- 做片路线（2026-11-08 主人定：两条线分开）
                   A = 竞品线：建完直接写稿，不经过「故事世界」
                   B = 创意故事：先挑世界，再写稿（话题路不走这条，故放在 block 内） -->
              <view class="frow">
                <text class="frow-lbl">做片路线</text>
                <view class="chips">
                  <view class="chip" :class="{ on: answers.line !== 'B' }" @click="answers.line = 'A'">快速出片</view>
                  <view class="chip" :class="{ on: answers.line === 'B' }" @click="answers.line = 'B'">创意故事</view>
                </view>
                <text class="frow-hint">快速出片 = 照商品直接写稿（原流程）；创意故事 = 先挑一个故事世界，不套形态模板，更不像广告。</text>
              </view>

              <!-- 片长：决定镜数，也决定要出几块分镜板（一张板只有 9 格）。
                   竞品 `project/new/page.tsx:44-48` durationOptions + `newProject.ts:114`。 -->
              <view v-if="(opt.durations || []).length" class="frow">
                <text class="frow-lbl">片长</text>
                <view class="chips">
                  <view
                    v-for="d in opt.durations"
                    :key="d"
                    :class="['chip', answers.duration === d ? 'on' : '']"
                    @click="answers.duration = d"
                  >{{ d }} 秒</view>
                </view>
                <text class="frow-hint">15 秒约 2–3 镜（一块板、一次出片）；30 秒约 5–7 镜；60 秒 8–15 镜，超过 9 镜会按段多出板。</text>
              </view>

              <!-- 视频模式 = 镜头怎么拍，和「剧本形态」（讲什么故事）是两层。
                   竞品 `project/new/page.tsx:52-57` 四种 + i18n `newProject.ts:116-123`。
                   后端 `services/drama_modes.py` 已把这四条写成硬指令，注入剧本/分镜。 -->
              <view v-if="opt.modes.length" class="frow">
                <text class="frow-lbl">视频模式</text>
                <view class="chips">
                  <view
                    v-for="m in opt.modes"
                    :key="m"
                    :class="['chip', answers.mode === m ? 'on' : '']"
                    @click="answers.mode = answers.mode === m ? '' : m"
                  >{{ m }}</view>
                </view>
                <text class="frow-hint">{{ modeHint }}</text>
              </view>

              <!-- 创意故事不套十形态 → 这一行整行不出现（说明写在上面「做片路线」里） -->
              <view v-if="answers.line !== 'B' && formRows.length" class="frow">
                <text class="frow-lbl">剧本形态</text>
                <view class="chips">
                  <view
                    v-for="f in formRows"
                    :key="f"
                    :class="['chip', answers.form === f ? 'on' : '']"
                    @click="pickForm(f)"
                  >{{ f }}</view>
                </view>
                <textarea
                  v-if="answers.form === '自定义'"
                  class="input area"
                  v-model="answers.form_note"
                  maxlength="300"
                  placeholder="写下你想要的剧情/结构，越具体越不会被套路框住"
                />
              </view>

              <!-- 出镜人物：免费路不生成画面、产品特写/图文混剪里也不出人 → 三种情况都不给这一行 -->
              <view v-if="genMode === 'ai' && peopleMode && presenterRows.length" class="frow">
                <text class="frow-lbl">出镜人物</text>
                <view class="chips">
                  <view class="chip" :class="{ on: !answers.presenter }" @click="answers.presenter = ''">让模型挑</view>
                  <view
                    v-for="p in presenterRows"
                    :key="p.name"
                    :class="['chip', answers.presenter === p.name ? 'on' : '']"
                    @click="answers.presenter = answers.presenter === p.name ? '' : p.name"
                  >{{ p.name }}</view>
                </view>
              </view>

              <view v-if="genMode === 'ai'" class="frow">
                <text class="frow-lbl">生产档位</text>
                <view class="profs">
                  <view
                    v-for="p in profRows"
                    :key="p.id"
                    :class="['prof', profile === p.id ? 'on' : '']"
                    @click="pickProfile(p)"
                  >
                    <text class="prof-n">{{ p.name }}</text>
                    <text class="prof-d">{{ p.desc }}</text>
                    <text class="prof-m">{{ p.meta }}</text>
                  </view>
                </view>
                <text class="frow-hint">只改清晰度 / 接缝 / 真实感三个默认值，不会换掉你已选的模型。</text>
              </view>
            </block>

            <button class="cta" :disabled="!canStart" @click="onStart">开始生成</button>
            <text v-if="err" class="err">{{ err }}</text>
            <text class="reassure">{{ genMode === 'free'
              ? '这条走免费快剪：商品图 + 字幕拼出来，全程不花生成费；想换成拍的戏，在上面选「AI 生成」。'
              : '这条走 AI 生成：模型真的拍画面，按秒计费，先看预览确认再扣费。' }}</text>
          </block>
        </view>

        <!-- 继续未完成的项目（竞品 recent） -->
        <view v-if="recent.length" class="recent">
          <view class="recent-head">
            <text class="recent-lbl">继续未完成的项目</text>
            <text class="recent-all" @click="toProjects">查看全部 →</text>
          </view>
          <view v-for="p in recent" :key="p.id" class="pj" @click="openProject(p.id)">
            <text class="pj-dot" />
            <view class="pj-col">
              <text class="pj-nm">{{ p.name || '未命名项目' }}</text>
              <text class="pj-meta">{{ p.done ? '已完成' : p.stage }}{{ p.updated ? ' · ' + p.updated : '' }}</text>
            </view>
          </view>
        </view>

        <!-- 🔥 今天发什么（竞品 trends） -->
        <view class="trends">
          <view class="trends-head">
            <text class="trends-lbl">🔥 今天发什么</text>
            <view class="trends-btns">
              <text class="trends-btn" @click="loadTrends('cn')">抖音热搜</text>
              <text class="trends-btn" @click="loadTrends('google')">海外(US)</text>
            </view>
          </view>
          <text v-if="trNote" class="trends-src">{{ trNote }}</text>

          <view v-if="trPick" class="trends-pick">
            <text class="trends-pick-t">今日一条：{{ trPick.topic.title }}</text>
            <text class="trends-btn go" @click="pickTrend(trPick.topic)">起片</text>
          </view>

          <view v-if="trCats.length > 1" class="trends-cats">
            <view :class="['cat', trCat === 'all' ? 'on' : '']" @click="trCat = 'all'">全部</view>
            <view
              v-for="c in trCats"
              :key="c"
              :class="['cat', trCat === c ? 'on' : '']"
              @click="trCat = c"
            >{{ trCatLabel(c) }}</view>
          </view>

          <view v-for="(t, i) in trShown" :key="(t.rank || 0) + t.title" class="trow">
            <text :class="['trk', (t.rank || (i + 1)) <= 3 ? 'hot' : '']">{{ t.rank || (i + 1) }}</text>
            <text class="ttl" @click="pickTrend(t)">{{ t.title }}</text>
            <text v-if="t.traffic" class="tv">{{ t.traffic }}</text>
          </view>

          <text v-if="!trTopics.length" class="trends-empty">{{ trBusy ? '正在拉取…' : '点上面的按钮拉一批热点' }}</text>
        </view>
      </view>
    </view>
  </DramaAppShell>
</template>

<script>
import { onLoad, onShow } from '@dcloudio/uni-app'
import DramaAppShell from '@/components/drama/AppShell.vue'
import dramaPageBoot from '@/mixins/dramaPageBoot'
import { dramaList } from '@/api/request'

/**
 * 工作台（照竞品 `/start`）：三种起片方式**页内直接建**，建完立刻写稿 → 脚本页。
 *
 * 🩸 2026-11-07 重做：原来这里是「三张入口卡 → 跳新建页 → 再点创建」，
 * 竞品是在落地页一张卡里选 tab、填字段、点「开始生成」直接出稿
 * （`start/page.tsx:667-846`）。选项顺序也照抄：先选免费/AI，AI 档才问
 * 剧本形态 / 出镜人物 / 生产档位（`:762-800`）。
 */
export default {
  components: { DramaAppShell },
  mixins: [dramaPageBoot],
  data() {
    return {
      mode: 'upload',
      genMode: 'ai',
      // mp 端 v-for 只吃 data 顶层数组
      formRows: [],
      presenterRows: [],
      profile: '',
      profRows: [
        // 竞品 production-profiles.ts：rapid / balanced / cinematic
        // 我们后端只吃 resolution / chain / realism，所以只映射这三项
        { id: 'rapid', name: '极速试片', desc: '先用较低成本验证脚本和画面，适合快速测试多个创意。', meta: '720p · 独立镜头', res: '720p', chain: 'off', realism: 'constraints' },
        { id: 'balanced', name: '智能均衡', desc: '清晰度、稳定性与成本更均衡，适合大多数日常带货视频。', meta: '720p · 尾帧续拍', res: '720p', chain: 'tail', realism: 'auto' },
        { id: 'cinematic', name: '品牌大片', desc: '更长镜头、强运镜和连续镜头，适合重点商品与品牌内容。', meta: '1080p · 尾帧续拍', res: '1080p', chain: 'tail', realism: 'auto' },
      ],
      // 整卡进度接管
      running: false,
      progSteps: [],
      progIdx: 0,
      progNow: '',
      err: '',
      recent: [],
    }
  },
  computed: {
    canStart() {
      if (this.mode === 'topic') return (this.topic.topic || '').trim().length >= 2
      if (this.mode === 'link') return !!(this.form.url || '').trim()
      return !!(this.form.name || '').trim()
    },
  },
  onLoad(q) {
    const m = (q && q.mode) || 'upload'
    this.mode = ['upload', 'link', 'topic'].indexOf(m) >= 0 ? m : 'upload'
    this.boot('').then(() => {
      this.formRows = ((this.opt && this.opt.forms) || []).slice()
      if (this.formRows.indexOf('自定义') < 0) this.formRows.push('自定义')
      this.presenterRows = ((this.opt && this.opt.presenters) || []).map((p) => ({ name: p.name }))
      this.safe(this.loadTopicOptions)
    })
    this.loadRecent()
    this.loadTrends('cn')
  },
  // 从脚本页返回时，刚建的项目要出现在「继续未完成的项目」里
  onShow() {
    if (this.recent.length || this.cur) this.loadRecent()
  },
  methods: {
    async loadRecent() {
      try {
        const rows = (await dramaList()) || []
        this.recent = rows.slice(0, 4)
      } catch (e) {
        this.recent = []
      }
    },
    openProject(id) {
      uni.navigateTo({ url: `/pages/drama/script?id=${id}` })
    },
    toProjects() {
      uni.navigateTo({ url: '/pages/drama/projects' })
    },
    pickGen(g) {
      this.genMode = g
    },
    pickForm(f) {
      // 再点一次取消 → 回到「让模型自己挑」（不再默认情景短剧；自定义也能取消）
      // 🩸 取消自定义必须同时清空 form_note：后端 `_form_of` 只要 note 非空就当自定义。
      this.answers.form = (this.answers.form === f) ? '' : f
      if (!this.answers.form) this.answers.form_note = ''
    },
    /** 生产档位 = 写进全局默认；新项目打开时按它预填（竞品 applyProductionProfile 同语义） */
    pickProfile(p) {
      if (this.profile === p.id) return
      this.profile = p.id
      this.st.film_resolution = p.res
      this.st.film_chain = p.chain
      this.st.film_realism = p.realism
      this.saveSettings()
    },
    /** 热点 → 直接落成「一句话成片」的主题，不跳页 */
    pickTrend(t) {
      this.topic.topic = (t && t.title) || ''
      this.mode = 'topic'
    },
    async onStart() {
      if (!this.canStart || this.running || this.busy || this.bootStep) return
      this.err = ''
      this.running = true
      try {
        if (this.mode === 'topic') await this.startTopicFlow()
        else await this.startProductFlow()
      } catch (e) {
        this.err = (e && e.message) || '出错了，请重试'
      } finally {
        this.running = false
        this.progSteps = []
        this.progNow = ''
      }
    },
    /** 商品路：链接先抓（复用 importUrl，只填抓到的）→ 建项目 → 写稿 → 脚本页 */
    async startProductFlow() {
      if (this.mode === 'link') {
        this.progSteps = ['抓取商品信息…', '创建项目…', 'AI 写脚本…']
        this.progIdx = 0
        this.progNow = '正在抓取链接里的标题 / 价格 / 主图'
        await this.importUrl()
        if (!(this.form.name || '').trim()) {
          this.err = this.linkNoInfoHint(this.form.url)
          return
        }
      } else {
        this.progSteps = ['创建项目…', 'AI 写脚本…']
      }
      this.progIdx = this.progSteps.length - 2
      this.progNow = '创建项目…'
      this.cur = null
      await this.create()
      if (!this.cur || !this.cur.id) {
        this.err = '项目创建失败，请重试'
        return
      }
      // 2026-11-08：只有「创意故事」线才进 world 页。
      // A 线（快速出片）= 竞品原样流程，建完直接写稿，不经过这一步。
      // gen 一并带过去，否则世界页固定写 gen=ai，免费快剪这条路会被改掉
      if (this.needWorld()) {
        uni.navigateTo({ url: `/pages/drama/world?id=${this.cur.id}&gen=${this.genMode}` })
        return
      }
      // 建完立刻写稿：结构卡 → 确认 → 剧本 → 分镜（同批量作业那一串调用）
      this.progIdx = this.progSteps.length - 1
      this.progNow = 'AI 正在写脚本（结构卡 → 剧本 → 分镜）…'
      const r = await this.bootDraft(this.cur.id)
      // 写稿完成后停在脚本页，由顾客自己决定出片（AI 出片要预览确认付费；免费快剪点一下就跑）
      const qs = ['id=' + this.cur.id, this.genMode === 'free' ? 'gen=free' : 'gen=ai']
      if (!r.ok) qs.push('draftfail=' + encodeURIComponent(r.failedAt || '写稿'))
      uni.navigateTo({ url: '/pages/drama/script?' + qs.join('&') })
    },
    /** 话题路：一次模型调用写全稿（可选几版），建完同样带 auto=1 进脚本页 */
    async startTopicFlow() {
      this.progSteps = ['创建项目…', 'AI 写脚本…']
      this.progIdx = 1
      this.progNow = 'AI 正在写脚本…'
      this.cur = null
      await this.createTopic()
      if (!this.cur || !this.cur.id) {
        this.err = '生成失败，请检查 LLM 配置'
        return
      }
      const qs = ['id=' + this.cur.id, this.genMode === 'free' ? 'gen=free' : 'gen=ai']
      uni.navigateTo({ url: '/pages/drama/script?' + qs.join('&') })
    },
  },
}
</script>

<style scoped>
.home {
  max-width: 1120rpx;
  margin: 0 auto;
}
.hero-lite {
  padding: 48rpx 8rpx 40rpx;
  text-align: center;
}
.eyebrow {
  display: block;
  font-size: 21rpx;
  letter-spacing: 0.22em;
  color: #0b8f6b;
  opacity: 0.85;
  margin-bottom: 18rpx;
}
.h1 {
  display: block;
  font-size: 52rpx;
  font-weight: 700;
  line-height: 1.15;
  color: #1b1f27;
}
.h1 .hl {
  color: #0b8f6b;
}
.sub {
  display: block;
  margin-top: 20rpx;
  padding: 0 24rpx;
  font-size: 25rpx;
  line-height: 1.7;
  color: #8a93a0;
}

.mk {
  background: #fff;
  border-radius: 22rpx;
  padding: 24rpx;
  box-shadow: 0 24rpx 60rpx -40rpx rgba(15, 23, 42, 0.35);
}
.tabs {
  display: flex;
  gap: 8rpx;
  background: #f2f4f8;
  border-radius: 16rpx;
  padding: 8rpx;
  margin-bottom: 22rpx;
}
.tab {
  flex: 1;
  padding: 18rpx 8rpx;
  text-align: center;
  font-size: 24rpx;
  color: #6b7280;
  border-radius: 12rpx;
}
.tab.on {
  background: #fff;
  color: #1b1f27;
  font-weight: 600;
  box-shadow: 0 4rpx 14rpx -8rpx rgba(15, 23, 42, 0.4);
}

.drop {
  border: 2rpx dashed #7dd3b8;
  border-radius: 18rpx;
  background: #f6fdfa;
  padding: 46rpx 24rpx 40rpx;
  text-align: center;
}
.drop-ico {
  display: block;
  font-size: 48rpx;
  color: #0b8f6b;
  line-height: 1;
}
.drop-t {
  display: block;
  margin-top: 14rpx;
  font-size: 27rpx;
  font-weight: 600;
  color: #1b1f27;
}
.drop-s {
  display: block;
  margin-top: 8rpx;
  font-size: 21rpx;
  color: #9aa3af;
}
.thumbs {
  display: flex;
  flex-wrap: wrap;
  margin-top: 16rpx;
}
.thumb {
  position: relative;
  width: 120rpx;
  height: 120rpx;
  margin: 0 14rpx 14rpx 0;
  border-radius: 14rpx;
  overflow: hidden;
  border: 1rpx solid #ebedf3;
}
.thumb-img {
  width: 100%;
  height: 100%;
}
.thumb-del {
  position: absolute;
  top: 4rpx;
  right: 4rpx;
  width: 34rpx;
  height: 34rpx;
  line-height: 32rpx;
  text-align: center;
  border-radius: 10rpx;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  font-size: 22rpx;
}
.fld {
  margin-top: 18rpx;
}
.ds-hint {
  display: block;
  margin-top: 12rpx;
  font-size: 22rpx;
  color: #9aa3af;
  line-height: 1.6;
}
.topic-area {
  min-height: 200rpx;
}

.genrow {
  display: flex;
  flex-direction: column;
  gap: 12rpx;
  margin-top: 20rpx;
}
.gen {
  padding: 20rpx 22rpx;
  border: 1rpx solid #ebedf3;
  border-radius: 16rpx;
  background: #fafbfd;
}
.gen-b {
  display: block;
  font-size: 27rpx;
  font-weight: 600;
  color: #1b1f27;
}
.gen-s {
  display: block;
  margin-top: 6rpx;
  font-size: 22rpx;
  line-height: 1.55;
  color: #9aa3af;
}
.gen.on {
  border-color: #12b886;
  background: #eefaf5;
}
.gen.on .gen-b {
  color: #0b8f6b;
}

.frow {
  margin-top: 22rpx;
}
.frow-lbl {
  display: block;
  margin-bottom: 12rpx;
  font-size: 23rpx;
  font-weight: 600;
  color: #6b7280;
}
.chips {
  display: flex;
  flex-wrap: wrap;
}
.chip {
  padding: 10rpx 22rpx;
  margin: 0 12rpx 12rpx 0;
  border-radius: 999rpx;
  border: 1rpx solid #e9ecf2;
  background: #f2f4f8;
  font-size: 23rpx;
  color: #4b5563;
}
.chip.on {
  background: #e7f8f2;
  border-color: #12b886;
  color: #0b8f6b;
  font-weight: 600;
}
.frow-hint {
  display: block;
  margin-top: 6rpx;
  font-size: 21rpx;
  color: #9aa3af;
  line-height: 1.5;
}
.profs {
  display: flex;
  flex-direction: column;
  gap: 12rpx;
}
.prof {
  padding: 18rpx 20rpx;
  border: 1rpx solid #ebedf3;
  border-radius: 16rpx;
  background: #fafbfd;
}
.prof-n {
  display: block;
  font-size: 25rpx;
  font-weight: 600;
  color: #1b1f27;
}
.prof-d {
  display: block;
  margin-top: 4rpx;
  font-size: 21rpx;
  line-height: 1.55;
  color: #9aa3af;
}
.prof-m {
  display: block;
  margin-top: 6rpx;
  font-size: 20rpx;
  color: #0b8f6b;
}
.prof.on {
  border-color: #12b886;
  background: #eefaf5;
}

.cta {
  margin-top: 26rpx;
  height: 92rpx;
  line-height: 92rpx;
  border-radius: 18rpx;
  background: linear-gradient(100deg, #12b886, #0b8f6b);
  color: #fff;
  font-size: 29rpx;
  font-weight: 600;
  border: 0;
}
.cta[disabled] {
  opacity: 0.45;
}
.err {
  display: block;
  margin-top: 14rpx;
  font-size: 22rpx;
  color: #d9534f;
  line-height: 1.5;
}
.reassure {
  display: block;
  margin-top: 14rpx;
  font-size: 21rpx;
  color: #9aa3af;
  line-height: 1.5;
}

/* 进度接管 */
.prog {
  padding: 16rpx 8rpx 8rpx;
}
.prog-title {
  display: flex;
  align-items: center;
  gap: 12rpx;
  font-size: 28rpx;
  font-weight: 600;
  color: #1b1f27;
  margin-bottom: 22rpx;
}
.spin {
  color: #12b886;
}
.prog-step {
  display: flex;
  align-items: center;
  gap: 14rpx;
  padding: 12rpx 0;
  font-size: 24rpx;
  color: #b0b7c3;
}
.prog-step .ic {
  width: 40rpx;
  height: 40rpx;
  line-height: 40rpx;
  text-align: center;
  border-radius: 999rpx;
  background: #f2f4f8;
  font-size: 21rpx;
  color: #b0b7c3;
}
.prog-step.on .ic {
  background: #e7f8f2;
  color: #0b8f6b;
}
.prog-step.done .ic {
  background: #12b886;
  color: #fff;
}
.prog-step.on .prog-lbl {
  color: #1b1f27;
  font-weight: 600;
}
.prog-step.done .prog-lbl {
  color: #6b7280;
}
.prog-hint {
  display: block;
  margin-top: 18rpx;
  font-size: 21rpx;
  color: #9aa3af;
  line-height: 1.5;
}

/* 最近项目 */
.recent {
  margin-top: 26rpx;
}
.recent-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12rpx;
  padding: 0 6rpx;
}
.recent-lbl {
  font-size: 23rpx;
  color: #8a93a0;
}
.recent-all {
  font-size: 22rpx;
  color: #8a93a0;
}
.pj {
  display: flex;
  align-items: center;
  gap: 14rpx;
  padding: 18rpx 20rpx;
  background: #fff;
  border-radius: 16rpx;
  margin-bottom: 10rpx;
}
.pj-dot {
  width: 12rpx;
  height: 12rpx;
  border-radius: 999rpx;
  background: #12b886;
  flex: none;
}
.pj-col {
  min-width: 0;
  flex: 1;
}
.pj-nm {
  display: block;
  font-size: 25rpx;
  color: #1b1f27;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.pj-meta {
  display: block;
  margin-top: 4rpx;
  font-size: 20rpx;
  color: #9aa3af;
}

/* 今天发什么 */
.trends {
  margin-top: 26rpx;
  background: #fff;
  border-radius: 18rpx;
  padding: 22rpx 24rpx;
}
.trends-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.trends-lbl {
  font-size: 25rpx;
  font-weight: 600;
  color: #1b1f27;
}
.trends-btns {
  display: flex;
  gap: 14rpx;
}
.trends-btn {
  font-size: 21rpx;
  color: #0b8f6b;
  padding: 6rpx 14rpx;
  border-radius: 999rpx;
  background: #eefaf5;
}
.trends-btn.go {
  flex: none;
}
.trends-src {
  display: block;
  margin-top: 10rpx;
  font-size: 20rpx;
  color: #b0b7c3;
}
.trends-pick {
  display: flex;
  align-items: center;
  gap: 14rpx;
  margin-top: 14rpx;
  padding: 14rpx 16rpx;
  border-radius: 14rpx;
  background: #f6fdfa;
}
.trends-pick-t {
  flex: 1;
  font-size: 22rpx;
  color: #0b8f6b;
  line-height: 1.5;
}
.trends-cats {
  display: flex;
  flex-wrap: wrap;
  margin-top: 14rpx;
}
.cat {
  padding: 8rpx 18rpx;
  margin: 0 10rpx 10rpx 0;
  border-radius: 999rpx;
  background: #f2f4f8;
  font-size: 21rpx;
  color: #6b7280;
}
.cat.on {
  background: #e7f8f2;
  color: #0b8f6b;
  font-weight: 600;
}
.trow {
  display: flex;
  align-items: center;
  gap: 14rpx;
  padding: 14rpx 0;
  border-top: 1rpx solid #f4f6f8;
}
.trk {
  width: 44rpx;
  flex: none;
  text-align: center;
  font-size: 21rpx;
  color: #b0b7c3;
}
.trk.hot {
  color: #f08c00;
  font-weight: 700;
}
.ttl {
  flex: 1;
  font-size: 24rpx;
  color: #333;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.tv {
  flex: none;
  font-size: 20rpx;
  color: #b0b7c3;
}
.trends-empty {
  display: block;
  padding: 20rpx 0;
  font-size: 22rpx;
  color: #9aa3af;
}

@media (min-width: 900px) {
  .genrow {
    flex-direction: row;
  }
  .gen {
    flex: 1;
  }
  .profs {
    flex-direction: row;
  }
  .prof {
    flex: 1;
  }
}
</style>
