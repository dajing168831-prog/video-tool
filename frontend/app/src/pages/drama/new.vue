<template>
  <DramaAppShell>
    <view class="ds">
      <view class="page-wrap">
    <view v-if="creating" class="sheet">
      <view class="sheet-top">
        <view>
          <view class="sheet-title">新建一条</view>
          <view class="sheet-sub">卖点只填真的有的，编了要担责</view>
        </view>
        <view class="sheet-cancel" @click="cancelNew">取消</view>
      </view>

      <!-- ① 商品链接（一键导入，省手打） -->
      <view class="field">
        <view class="label">商品链接<text class="label-tip">粘上可一键抓标题/描述/商品图</text></view>
        <view class="link-row">
          <input v-model="form.url" class="input line link-input" placeholder="https://…" />
          <view class="link-btn" @click="importUrl">
            {{ busy === 'import' ? '抓取中…' : '一键导入' }}
          </view>
        </view>
      </view>

      <!-- ② 商品图 -->
      <view class="field">
        <view class="label">商品图<text class="label-tip">最多 {{ opt.max_pics }} 张 · JPG/PNG/WebP</text></view>
        <view class="pics">
          <view v-for="(im, i) in form.images" :key="im.name" class="pic">
            <image :src="im.url" class="pic-img" mode="aspectFill" />
            <view class="pic-del" @click="dropPic(i)">×</view>
          </view>
          <view
            v-if="form.images.length < opt.max_pics"
            class="pic pic-add"
            @click="pickPics"
          >
            <text class="pic-plus">{{ busy === 'pic' ? '…' : '＋' }}</text>
            <text class="pic-tip">上传</text>
          </view>
        </view>
        <view class="hint">出片时当参考图用，商品在各镜头长得一样靠它</view>
      </view>

      <!-- ③ 商品名称 -->
      <view class="field">
        <view class="label">商品名称<text class="label-tip">必填</text></view>
        <input v-model="form.name" class="input line" placeholder="例：云柔加厚抽纸"
               @blur="refreshRec" />
      </view>

      <!-- ④ 卖点 -->
      <view class="field">
        <view class="label">卖点<text class="label-tip">每行一条，只写真有的</text></view>
        <textarea v-model="form.points" class="input area" placeholder="三层加厚，湿水不破" auto-height
                  @blur="refreshRec" />
      </view>

      <!-- ⑤ 怎么做成片：只有 AI 生成（没有免费档；自己的素材去「素材」页混剪） -->
      <view class="field">
        <view class="label">怎么做成片</view>
        <view class="opts">
          <view class="opt on">🎬 AI 生成</view>
        </view>
        <view class="hint">{{ genHint }}</view>
      </view>

      <!-- 做片路线（2026-11-08 主人定：两条线分开）
           A = 竞品线：建完直接写稿，一个字不经过「故事世界」
           B = 创意故事：先挑故事世界，再写稿，世界一路带到分镜
           🩸 必须放在「更多设置」折叠区外面 —— 它决定后面走哪套流程，不是可选高级项。 -->
      <view class="field">
        <view class="label">做片路线<text class="label-tip">决定用哪套流程</text></view>
        <view class="opts">
          <view class="opt" :class="{ on: answers.line !== 'B' }" @click="answers.line = 'A'">
            快速出片<text class="label-tip">照商品直接写稿 · 不挑世界</text>
          </view>
          <view class="opt" :class="{ on: answers.line === 'B' }" @click="answers.line = 'B'">
            创意故事<text class="label-tip">先挑一个故事世界 · 不套形态模板</text>
          </view>
        </view>
      </view>

      <!-- ⑥ 更多设置：不填也能出片，填了更贴品类 -->
      <view class="field">
        <view class="label" @click="moreOpen = !moreOpen">
          更多设置（可选）<text class="label-tip">{{ moreOpen ? '收起' : '展开：品类 / 剧本形态 / 片长 / 模板' }}</text>
        </view>
      </view>

      <block v-if="moreOpen">
      <view class="field">
        <view class="label">商品品类</view>
        <view class="opts">
          <view
            v-for="x in opt.categories"
            :key="x"
            :class="['opt', form.category === x ? 'on' : '']"
            @click="form.category = form.category === x ? '' : x; catTpl = ''; refreshRec()"
          >{{ x }}</view>
        </view>
      </view>

      <view v-if="catTplOptions.length" class="field">
        <view class="label">
          品类套路<text class="label-tip">不选 = 用该类目默认；只影响剧本写法</text>
        </view>
        <view class="opts">
          <view
            v-for="x in catTplOptions"
            :key="x"
            :class="['opt', catTpl === x ? 'on' : '']"
            @click="pickCatTpl(x)"
          >{{ x }}</view>
        </view>
      </view>

      <view class="field">
        <view class="label">价格定位</view>
        <view class="opts">
          <view
            v-for="x in opt.prices"
            :key="x"
            :class="['opt', form.price === x ? 'on' : '']"
            @click="form.price = form.price === x ? '' : x"
          >{{ x }}</view>
        </view>
      </view>

      <view class="field">
        <view class="label">原始资料<text class="label-tip">参数 / 认证 / 评价，没有就留空</text></view>
        <textarea v-model="form.facts" class="input area" placeholder="留空也可以 —— 不许编" auto-height />
      </view>

      <view class="field">
        <view class="label">目标人群</view>
        <view class="opts">
          <view
            v-for="x in opt.audiences"
            :key="x"
            :class="['opt', form.audience === x ? 'on' : '']"
            @click="form.audience = form.audience === x ? '' : x"
          >{{ x }}</view>
        </view>
      </view>

      <view class="field">
        <view class="label">投放平台</view>
        <view class="opts">
          <view
            v-for="x in opt.platforms"
            :key="x"
            :class="['opt', form.platform === x ? 'on' : '']"
            @click="form.platform = form.platform === x ? '' : x"
          >{{ x }}</view>
        </view>
      </view>

      <!-- 创意故事不套十形态 → 形态选择整块不出现（说明写在上面「做片路线」里） -->
      <view v-if="answers.line !== 'B' && formRows.length" class="field">
        <view class="label">剧本形态<text class="label-tip">决定这个故事怎么讲</text></view>
        <view class="opts">
          <view
            v-for="f in formRows"
            :key="f"
            :class="['opt', answers.form === f ? 'on' : '']"
            @click="pickForm(f)"
          >{{ f }}</view>
        </view>
        <textarea
          v-if="answers.form === '自定义'"
          class="input area"
          v-model="answers.form_note"
          maxlength="300"
          placeholder="写下你想要的剧情/结构，越具体越不会被套路框住（例：让一个外星人用这件商品拯救地球）"
        />
        <view class="hint">{{ formHint }}</view>
      </view>

      <view class="field">
        <view class="label">片长</view>
        <view class="opts">
          <view
            v-for="d in opt.durations"
            :key="d"
            :class="['opt', answers.duration === d ? 'on' : '']"
            @click="answers.duration = d"
          >{{ d }} 秒</view>
        </view>
      </view>

      <view class="field">
        <view class="label">视频模式<text class="label-tip">决定怎么拍，不是怎么发</text></view>
        <view class="opts">
          <view
            v-for="x in opt.modes"
            :key="x"
            :class="['opt', answers.mode === x ? 'on' : '']"
            @click="answers.mode = answers.mode === x ? '' : x"
          >{{ x }}</view>
        </view>
        <view class="hint">{{ modeHint }}</view>
      </view>

      <view v-if="hookRows.length" class="field">
        <view class="label">开场钩子<text class="label-tip">第一句话怎么炸；不选 = 模型自选</text></view>
        <view class="opts">
          <view class="opt" :class="{ on: !answers.preferred_hook }" @click="pickHook(null)">让模型选</view>
          <view
            v-for="h in hookRows"
            :key="h.code"
            :class="['opt', answers.preferred_hook === h.code ? 'on' : '']"
            @click="pickHook(h)"
          >{{ h.code }} · {{ h.name }}</view>
        </view>
        <view class="hint">{{ hookHint }}</view>
      </view>

      <view class="field">
        <view class="label">成片模板<text class="label-tip">可选；不选就按模式自由发挥</text></view>
        <view v-if="tpl.rec.length" class="tpl-rec">
          <view
            v-for="t in tpl.rec"
            :key="t.id"
            :class="['tpl-card', isSameTpl(tpl.draft, t) ? 'on' : '']"
            @click="pickTpl(t)"
          >
            <text class="tpl-emoji">{{ t.emoji }}</text>
            <view class="tpl-name">{{ t.name.zh }}</view>
            <view class="tpl-tag">{{ t.tagline.zh }}</view>
          </view>
        </view>
        <view class="opts">
          <view class="opt" @click="openTplPanel('lib')">选模板（{{ tplTotal }} 款）</view>
          <view class="opt" @click="openTplPanel('mine')">我的模板（{{ tpl.mine.length }}）</view>
          <view v-if="tpl.draft" class="opt" @click="tpl.draft = null">清掉</view>
        </view>
        <view v-if="tpl.draft" class="tpl-picked">
          已选：{{ tpl.draft.emoji }} <text class="b">{{ tpl.draft.name.zh }}</text>
          —— {{ tpl.draft.tagline.zh }}
        </view>
        <view v-else class="hint">不选模板，片子也能出；选了模板，运镜与光线会按配方走，每镜之后仍可改。</view>
      </view>

      <view v-if="scriptTpl.list.length" class="field">
        <view class="label">参考剧本结构<text class="label-tip">可选；照它的节奏重写，不照搬文案</text></view>
        <view class="opts">
          <view class="opt" :class="{ on: !scriptTpl.draftId }" @click="scriptTpl.draftId = ''">不用</view>
          <view v-for="t in scriptTpl.list" :key="t.id"
                :class="['opt', scriptTpl.draftId === t.id ? 'on' : '']"
                @click="scriptTpl.draftId = scriptTpl.draftId === t.id ? '' : t.id"
          >{{ t.name }}<text class="opt-sub">{{ t.shots_count }}镜/{{ t.total_duration }}s</text></view>
        </view>
      </view>

      <view v-if="peopleMode" class="field">
        <view class="label">出镜人物<text class="label-tip">不选 = 模型自己挑</text></view>
        <view class="opts">
          <view class="opt" :class="{ on: !answers.presenter }"
                @click="answers.presenter = ''">让模型挑</view>
          <view v-for="p in (opt.presenters || [])" :key="p.name"
                :class="['opt', answers.presenter === p.name ? 'on' : '']"
                @click="answers.presenter = answers.presenter === p.name ? '' : p.name"
          >{{ p.name }}</view>
        </view>
        <view class="hint">{{ presenterHint }}</view>
      </view>

      <view class="field">
        <view class="label">商品在剧情里扮演什么<text class="label-tip">决定戏怎么成立</text></view>
        <view class="opts">
          <view
            v-for="r in opt.roles"
            :key="r"
            :class="['opt', answers.role === r ? 'on' : '']"
            @click="answers.role = r"
          >{{ r }}</view>
        </view>
        <view class="hint">{{ roleHint }}</view>
      </view>
      </block>

      <button class="btn-main" :disabled="!!busy || !!bootStep" @click="create">
        {{ busy === 'create' ? '创建中…' : (bootStep ? 'AI 正在写稿…' : '创建') }}
      </button>
    </view>
      </view>

      <!-- 建完自动写稿（照竞品创建时的 live checklist：创建项目 → 上传商品图 → AI 写脚本）。
           这三步只调文本模型，不出片；写成什么样，进脚本页照样能改能重生成。 -->
      <view v-if="bootStep" class="boot-mask">
        <view class="boot-box">
          <view class="boot-title">AI 正在写稿</view>
          <view :class="['bs-row', bootStep === '结构卡' ? 'on' : '']">① 结构卡</view>
          <view :class="['bs-row', bootStep === '写剧本' ? 'on' : '']">② 写剧本</view>
          <view :class="['bs-row', bootStep === '出分镜' ? 'on' : '']">③ 出分镜</view>
          <view class="boot-tip">写完自动进脚本页；中途失败也不丢项目，进去可以重生成。</view>
        </view>
      </view>

      <!-- 成片模板选择弹层（原来 openTpl() 只置 tpl.open=true，没有页面渲染 → 按钮点了没反应） -->
      <view v-if="tplOpen" class="tpl-mask" @click="closeTpl">
        <view class="tpl-sheet" @click.stop>
          <view class="tpl-sheet-head">
            <view class="tpl-tabs">
              <view :class="['tpl-tab', tplTab === 'lib' ? 'on' : '']" @click="switchTplTab('lib')">模板库</view>
              <view :class="['tpl-tab', tplTab === 'mine' ? 'on' : '']" @click="switchTplTab('mine')">
                我的模板（{{ mineRows.length }}）
              </view>
            </view>
            <view class="tpl-close" @click="closeTpl">×</view>
          </view>

          <block v-if="tplTab === 'lib'">
            <view class="tpl-search">
              <input v-model="tplQuery" class="input line" placeholder="搜模板名 / 标签" @confirm="loadTplLib" />
              <view class="btn-mini" @click="loadTplLib">搜</view>
            </view>
            <view class="opts">
              <view
                v-for="g in groupRows"
                :key="g.id"
                :class="['opt', tplGroup === g.id ? 'on' : '']"
                @click="pickTplGroup(g.id)"
              >{{ g.name }}</view>
            </view>
            <view class="tpl-note">{{ tplNote }}</view>
            <view v-for="t in tplRows" :key="t.id" class="tpl-row" @click="chooseTpl(t, '')">
              <text class="tpl-emoji">{{ t.emoji }}</text>
              <view class="tpl-info">
                <view class="tpl-name">{{ t.label }}</view>
                <view class="tpl-tag">{{ t.tag }}</view>
              </view>
              <text class="tpl-go">选 ›</text>
            </view>
          </block>

          <block v-else>
            <view v-if="!mineRows.length" class="empty">还没有自建模板（AI 定制或导入的会出现在这）</view>
            <view v-for="t in mineRows" :key="t.id" class="tpl-row">
              <text class="tpl-emoji">{{ t.emoji }}</text>
              <view class="tpl-info" @click="chooseTpl(t, t.id)">
                <view class="tpl-name">{{ t.label }}</view>
                <view class="tpl-tag">{{ t.tag }}</view>
              </view>
              <text class="tpl-del" @click.stop="delMineTpl(t)">删</text>
            </view>
          </block>

          <view class="tpl-foot">
            <view class="btn-mini" @click="aiCustom">{{ customBusy ? '定制中…' : 'AI 定制一款' }}</view>
            <view class="btn-mini" @click="copyDraftJson">{{ tpl.draft ? '复制当前模板 JSON' : '先选一款' }}</view>
          </view>
          <view v-if="tplMsg" class="tpl-msg">{{ tplMsg }}</view>
        </view>
      </view>
    </view>
  </DramaAppShell>
</template>

<script>
import { onLoad } from '@dcloudio/uni-app'
import DramaAppShell from '@/components/drama/AppShell.vue'
import dramaPageBoot from '@/mixins/dramaPageBoot'
import dramaPage from '@/mixins/dramaPage'
import {
  dramaTemplates, dramaTemplatesMine, dramaTemplatesCustom, dramaTemplatesMineDelete,
} from '@/api/request'

/**
 * 新建项目（照竞品 /project/new）：商品来源 → 商品信息 → 剧本形态 → 视频配置。
 * 表单本体从旧单页原样搬来（drama/index.vue:402-618）；页内 sheet 常开（creating=true）。
 *
 * 剧本形态从 2026-11-07 起是 **10 选 1**（原来只有「情景短剧」，所以每条片同一骨架）；
 * 每种形态在 `D:/skills/product-drama/references/form_*.md` 有一份自己的结构规则，
 * 后端 `_system(form)` 按选中的形态读对应那份。
 */
// 每种形态的一句话说明（和后端 form_*.md 的「一句话」对齐，别自己加设定）
const FORM_HINT = {
  '情景短剧': '两个人因为一件小事顶上了，商品把局面掀翻。恰好 2 个角色。',
  '反转剧场': '先立一个观众会信的偏见，再用商品当面打脸。1–2 个角色。',
  '街头采访': '主持人抛话题 + 路人先嫌弃后真香。恰好 2 个角色。',
  '达人口播': '一个人对着镜头，先给结论再堆三条证据。恰好 1 个。',
  '开箱测评': '第一人称拆箱，必须主动挑一个无关痛痒的刺。不出脸。',
  '对比测评': '几个方案同台，用同一套维度比，最后指一个。1 人。',
  '剧情故事': '讲一件「上周发生的事」，商品是转折。1–2 个角色。',
  '痛点种草': '先说出每天都在受的那点罪，再让商品解决。1 人。',
  '场景安利': '把一个「刚好用上」的生活瞬间拍下来。1 人。',
  '物品拟人': '商品自己开口，先吐槽命苦再亮绝活。不出真人。',
}
export default {
  components: { DramaAppShell },
  mixins: [dramaPageBoot],
  data() {
    return {
      // 十种形态 + 五选一钩子：local data 顶层数组，mp 端 v-for 不用对象属性路径
      formRows: [],
      formHint: '',
      hookRows: [],
      hookHint: '',
      // 成片模板弹层：v-for 用本地顶层数组（mp 端不吃 tpl.list 这种对象路径）
      tplOpen: false,
      tplTab: 'lib',
      tplRows: [],
      mineRows: [],
      groupRows: [],
      tplGroup: 'all',
      tplQuery: '',
      tplNote: '',
      tplMsg: '',
      customBusy: false,
      // 成片方式：只有 AI（没有免费档）
      genMode: 'ai',
      // 更多设置默认收起（照竞品 start 页：只留 图/名/卖点 + 生成方式，其余可选）
      moreOpen: false,
      genHint: 'AI 按镜头出片（付费）· 创建后停在脚本页，看过预览确认才扣费',
    }
  },
  onLoad(q) {
    this.creating = true
    const mode = (q && q.mode) || 'upload'
    this.entryMode = mode
    // 选项拉完再填形态与钩子（都由 `/api/drama/options` 下发）
    this.boot('').then(() => {
      this.formRows = ((this.opt && this.opt.forms) || []).slice()
      // 「自定义」= 按顾客自己写的要求写（竞品 styleType="custom"）
      if (this.formRows.indexOf('自定义') < 0) this.formRows.push('自定义')
      this.formHint = this.answers.form
        ? (FORM_HINT[this.answers.form] || '按你写的自定义要求来，不套固定套路。')
        : '不选就让模型自己挑最贴合这个商品的形态（不会默认情景短剧）。'
      const hs = (this.opt && this.opt.hooks) || []
      const rows = []
      for (let i = 0; i < hs.length; i++) {
        rows.push({ code: hs[i].code, name: hs[i].name, condition: hs[i].condition || '' })
      }
      this.hookRows = rows
      if (this.answers.preferred_hook === undefined) this.answers.preferred_hook = ''
    })
  },
  methods: {
    /* ===== 成片模板弹层（竞品 newProject 的模板库 / 我的 / AI 定制 / 导出） ===== */
    openTplPanel(tab) {
      this.tplOpen = true
      this.tplMsg = ''
      this.switchTplTab(tab || 'lib')
    },
    closeTpl() {
      this.tplOpen = false
    },
    switchTplTab(tab) {
      this.tplTab = tab
      if (tab === 'mine') this.loadMineList()
      else this.loadTplLib()
    },
    /** 模板对象 → 弹层一行（name/tagline 是 {zh,en}，自建的可能是纯字符串） */
    toRow(t) {
      const zh = (v) => (v && typeof v === 'object' ? (v.zh || v.en || '') : (v || ''))
      return {
        id: t.id,
        emoji: t.emoji || '▣',
        label: zh(t.name) || '未命名',
        tag: zh(t.tagline) || '',
        raw: t,
      }
    },
    async loadTplLib() {
      try {
        const r = await dramaTemplates({
          group: this.tplGroup,
          category: this.form.category || '',
          q: (this.tplQuery || '').trim(),
        })
        const list = (r && r.templates) || []
        const rows = []
        for (let i = 0; i < list.length && i < 60; i++) rows.push(this.toRow(list[i]))
        this.tplRows = rows
        const gs = (r && r.groups) || []
        const grows = [{ id: 'all', name: '全部' }]
        for (let i = 0; i < gs.length; i++) grows.push({ id: gs[i].id, name: gs[i].name })
        this.groupRows = grows
        this.tplNote = '共 ' + ((r && r.total) || list.length) + ' 款，这里列前 ' + rows.length + ' 款'
      } catch (e) {
        this.tplRows = []
        this.tplMsg = '模板库读取失败：' + (e.message || '')
      }
    },
    async loadMineList() {
      try {
        const list = (await dramaTemplatesMine()) || []
        const rows = []
        for (let i = 0; i < list.length; i++) rows.push(this.toRow(list[i]))
        this.mineRows = rows
      } catch (e) {
        this.mineRows = []
        this.tplMsg = '我的模板读取失败：' + (e.message || '')
      }
    },
    pickTplGroup(gid) {
      this.tplGroup = gid
      this.loadTplLib()
    },
    chooseTpl(t, mineId) {
      this.tpl.draft = t.raw
      this.tpl.draftMineId = mineId || ''
      this.tplOpen = false
      uni.showToast({ title: '已选：' + t.label, icon: 'none' })
    },
    delMineTpl(t) {
      uni.showModal({
        title: '删掉这个模板？',
        content: '「' + t.label + '」删了就找不回来。',
        success: async (r) => {
          if (!r.confirm) return
          try {
            await dramaTemplatesMineDelete(t.id)
            await this.loadMineList()
            uni.showToast({ title: '已删除', icon: 'none' })
          } catch (e) {
            uni.showModal({ title: '删除失败', content: e.message || '', showCancel: false })
          }
        },
      })
    },
    /** AI 定制（花一次模型调用）：按商品名/品类/卖点生成一款配方 */
    async aiCustom() {
      if (this.customBusy) return
      if (!(this.form.name || '').trim()) {
        uni.showToast({ title: '先填商品名称', icon: 'none' })
        return
      }
      this.customBusy = true
      this.tplMsg = ''
      try {
        const t = await dramaTemplatesCustom({
          name: this.form.name.trim(),
          category: this.form.category || '',
          points: this.form.points || '',
        })
        this.tplMsg = '已生成，可以选了'
        this.tplTab = 'mine'
        await this.loadMineList()
        if (t && t.id) {
          const row = this.toRow(t)
          this.mineRows = [row].concat(this.mineRows.filter((x) => x.id !== row.id))
        }
      } catch (e) {
        this.tplMsg = '定制失败：' + (e.message || '')
      }
      this.customBusy = false
    },
    /** 导出当前选中的配方 JSON（小程序没有文件下载，走剪贴板） */
    copyDraftJson() {
      const d = this.tpl.draft
      if (!d) {
        uni.showToast({ title: '先选一款', icon: 'none' })
        return
      }
      try {
        uni.setClipboardData({ data: JSON.stringify(d) })
      } catch (e) {
        uni.showToast({ title: '复制失败', icon: 'none' })
      }
    },
    pickForm(f) {
      // 再点一次取消选择 → 回到「让模型自己挑」（自定义也能取消）
      // 🩸 取消自定义必须同时清空 form_note：后端 `_form_of` 只要 note 非空就当自定义，
      //   不清就会「界面显示没选、后端仍按自定义写」。
      this.answers.form = (this.answers.form === f) ? '' : f
      if (!this.answers.form) this.answers.form_note = ''
      this.formHint = this.answers.form
        ? (FORM_HINT[this.answers.form] || '按你写的自定义要求来，不套固定套路。')
        : '不选就让模型自己挑最贴合这个商品的形态（不会默认情景短剧）。'
    },
    pickGen(m) {
      // 只保留 AI 一种成片方式（没有免费档）
      this.genMode = 'ai'
      this.genHint = 'AI 按镜头出片（付费）· 创建后停在脚本页，看过预览确认才扣费'
    },
    pickHook(h) {
      this.answers.preferred_hook = h ? h.code : ''
      this.hookHint = h
        ? ('第一帧就得成立：' + h.condition)
        : '不指定时模型自己挑 —— 实测很容易每次都挑同一个，剧本看着就一个样。'
    },
    cancelNew() {
      this.creating = false
      uni.navigateBack()
    },
    async create() {
      await dramaPage.methods.create.call(this)
      if (!this.cur || !this.cur.id) return
      // 2026-11-08：只有「创意故事」线才进 world 页。
      // A 线（快速出片）= 竞品原样流程，建完直接写稿，不经过这一步。
      if (this.needWorld()) {
        uni.redirectTo({ url: `/pages/drama/world?id=${this.cur.id}` })
        return
      }
      // 照竞品 `start/page.tsx:402-424`：创建时就调模型把稿子写好（结构卡→剧本→分镜），
      // 再跳 `?auto=1`。失败不拦，进页面还能重生成。
      const r = await this.bootDraft(this.cur.id)
      const warn = r.ok ? '' : '&draftfail=' + encodeURIComponent(r.failedAt || '写稿')
      // 没有免费档：写稿完停在脚本页，由顾客看过预览再决定是否出片
      uni.redirectTo({ url: `/pages/drama/script?id=${this.cur.id}&gen=ai${warn}` })
    },
  },
}
</script>

<style scoped>
/* ===== 成片模板弹层 ===== */
.tpl-mask {
  position: fixed;
  left: 0; right: 0; top: 0; bottom: 0;
  background: rgba(17, 24, 39, 0.45);
  z-index: 900;
  display: flex;
  align-items: flex-end;
}
.tpl-sheet {
  width: 100%;
  max-height: 78vh;
  overflow-y: auto;
  background: #fff;
  border-radius: 22rpx 22rpx 0 0;
  padding: 24rpx 24rpx 40rpx;
  box-sizing: border-box;
}
.tpl-sheet-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 16rpx;
}
.tpl-tabs { display: flex; gap: 10rpx; }
.tpl-tab {
  font-size: 24rpx;
  padding: 8rpx 20rpx;
  border-radius: 999rpx;
  background: #f0f2f5;
  color: #4b5563;
}
.tpl-tab.on { background: #e8f8f2; color: #0b8f6b; font-weight: 600; }
.tpl-close { font-size: 36rpx; color: #9aa0a6; padding: 0 12rpx; }
.tpl-search { display: flex; align-items: center; gap: 12rpx; padding: 10rpx 0; }
.tpl-search .input { flex: 1; }
.tpl-note { font-size: 20rpx; color: #9aa0a6; padding: 6rpx 0 10rpx; }
.tpl-row {
  display: flex;
  align-items: center;
  gap: 14rpx;
  padding: 16rpx 0;
  border-bottom: 1rpx solid #f2f4f7;
}
.tpl-emoji { font-size: 32rpx; }
.tpl-info { flex: 1; min-width: 0; }
.tpl-name { font-size: 25rpx; color: #1b1f27; font-weight: 600; }
.tpl-tag { margin-top: 4rpx; font-size: 20rpx; color: #9aa0a6; }
.tpl-go { font-size: 22rpx; color: #0b8f6b; }
.tpl-del { font-size: 21rpx; color: #c62828; padding: 6rpx 12rpx; }
.tpl-foot { display: flex; gap: 12rpx; padding-top: 20rpx; }
.tpl-msg { margin-top: 12rpx; font-size: 21rpx; color: #a06400; }

/* 建完自动写稿的全屏等待（这一步在调文本模型，不能让人以为卡死了） */
.boot-mask {
  position: fixed;
  left: 0; right: 0; top: 0; bottom: 0;
  background: rgba(17, 24, 39, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 60;
}
.boot-box {
  width: 520rpx;
  padding: 36rpx 32rpx 30rpx;
  background: #fff;
  border-radius: 24rpx;
}
.boot-title { font-size: 30rpx; font-weight: 700; color: #1b1f27; margin-bottom: 20rpx; }
.bs-row {
  font-size: 25rpx;
  color: #9aa0a6;
  padding: 12rpx 0;
  border-bottom: 1rpx solid #f2f4f7;
}
.bs-row.on { color: #0b8f6b; font-weight: 600; }
.boot-tip { margin-top: 18rpx; font-size: 20rpx; color: #9aa0a6; line-height: 1.6; }
</style>
