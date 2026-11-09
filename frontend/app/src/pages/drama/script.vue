<template>
  <DramaAppShell>
    <view class="ds">
      <DramaProjectHeader :id="pid" current="script" :name="headerName" :chips="chips" />

      <view v-if="!cur" class="pgstate">正在加载项目…</view>

      <!-- 自动链接管（照竞品 `script/page.tsx:930-960`）：从新建页 `?auto=1` 进来时，
           跑片的这几分钟只显示一张进度卡，不让人对着 10 张卡找下一步 -->
      <view v-if="cur && autoTakeover" class="auto-mask">
        <view class="auto-box">
          <view class="auto-title">正在自动跑片</view>
          <view class="auto-now">当前：{{ pipeStageName }}</view>
          <view
            v-for="r in pipeRows"
            :key="'at' + r.key"
            :class="['auto-row', r.state === 'ok' ? 'done' : (r.state === 'now' ? 'on' : '')]"
          >{{ r.label }} · {{ r.note }}</view>
          <view class="auto-tip">用你上传的素材和商品图合成，不出 AI 画面、不花 AI 费用。跑完停在成片页。</view>
          <button class="btn-mini" @click="autoHide = true">看细节</button>
        </view>
      </view>

      <!-- AI 出片接管页（照竞品 `aiFilming` 那段）：按段提交＋本地合成，几分钟不能让人乱点 -->
      <view v-if="cur && busy === 'ai-film'" class="auto-mask">
        <view class="auto-box">
          <view class="auto-title">🎬 AI 出片中</view>
          <view class="auto-now">{{ aiStage || '正在提交…' }}</view>
          <view class="auto-tip">{{ aiMeta }}</view>
          <view class="auto-tip">这是预览里确认过的同一版计划；出完自动合成并跳导出，别退出页面。</view>
        </view>
      </view>

      <block v-if="cur && !autoTakeover && busy !== 'ai-film'">

      <!-- 入门视图（照竞品 script/page.tsx:1013-1085 的 simple 模式）：
           只有剧本全文 + 两个大按钮。看不懂专业面板的人在这里就能把片做完。 -->
      <block v-if="uiMode === 'simple'">
        <view class="simp-head">
          <view class="simp-title">剧本</view>
          <view class="simp-sub">看过没问题，选一条路把片做出来</view>
        </view>
        <view class="card">
          <view class="simp-card-head">
            <text class="simp-name">{{ simpTitle }}</text>
            <text class="simp-dur">{{ totalSeconds }}s</text>
          </view>
          <!-- D1（2026-11-08）：入门视图也得说 —— 大部分顾客停在这一档，专业卡里的提示他们看不到 -->
          <view v-if="scriptCardStale" class="film-warn">⚠ 结构卡改过了，这版剧本还是旧卡写的，重新生成剧本才对得上</view>
          <view v-for="l in simpLines" :key="'sl' + l.id" class="simp-line">{{ l.text }}</view>
          <view v-if="!simpLines.length" class="empty">还没有剧本，点下面「重新生成」</view>
        </view>

        <view class="simp-ops">
          <!-- 主按钮跟着新建页选的那条路走（2026-11-08）：选了 AI 就是 AI 做主，选了免费就免费做主 -->
          <view :class="['simp-btn', genPref === 'ai' ? 'simp-main' : '', { off: !!busy }]" @click="aiPreview">
            ✨ {{ busy === 'ai-film' ? '出片中…' : 'AI 生成画面（先看预览再扣费）' }}
          </view>
          <view :class="['simp-btn', genPref === 'ai' ? '' : 'simp-main', { off: pipeRunning || !!busy }]" @click="startPipeline">
            ⚡ {{ pipeRunning ? '正在跑…' : '商品图 + 字幕拼（不出 AI 画面）' }}
          </view>
        </view>
        <view class="simp-tip">
          <text class="simp-tip-row">✨ AI 生成画面：真的拍出戏，先出预览，确认后才扣费。</text>
          <text class="simp-tip-row">⚡ 商品图 + 字幕拼：不花 AI 费，但画面是商品图，不是戏。</text>
        </view>
        <view class="simp-links">
          <text class="simp-link" @click="regenSimple">重新生成</text>
          <text class="simp-link" @click="setUiMode('pro')">去专业模式 ›</text>
        </view>
        <view v-if="pipeRun.error" class="film-warn">{{ pipeRun.error }}</view>
        <view v-if="!pipeReady" class="empty">还没有分镜——先点「重新生成」把剧本和分镜写出来</view>
      </block>

      <!-- 专业视图（左右：脚本版本 + 编辑/判官/成片），板块沿用原来的 -->
      <block v-else>
      <view v-if="isTopic" class="card">
        <view class="card-head">
          <view class="card-title"><text class="card-no">话</text>话题片</view>
          <button class="btn-mini" :disabled="!!busy" @click="openTopic">再起一条</button>
        </view>
        <view class="merge-tip">内容向短视频：没有商品，不出现价格与购买引导</view>
        <view class="bible-row"><text class="k">主题</text>{{ cur.topic }}</view>
        <view class="bible-row"><text class="k">风格</text>{{ topicStyleName }}</view>
        <view class="bible-row">
          <text class="k">分镜</text>{{ topicShots.length }} 镜 · {{ totalSeconds }} 秒
        </view>
        <view v-for="s in topicShots" :key="'ts' + s.id" class="merge-tip">
          #{{ s.id }} {{ s.duration }}s {{ s.framing }} {{ s.camera }}｜{{ s.description }}｜「{{ s.dialogue }}」
        </view>
        <view class="merge-tip">往下就是「出片」；换稿在上面「脚本版本」里切。</view>
      </view>

      <!-- 带货流水线：话题项目不走这一段（A6 是另一个体裁） -->
      <block v-if="!isTopic">
      <!-- 0 商品资料（随时可改；图直接进步项目目录） -->

      <view class="card">
        <view class="card-head">
          <view class="card-title"><text class="card-no">0</text>商品资料</view>
          <button
            class="btn-mini"
            :disabled="!!busy"
            @click="editing ? cancelEdit() : startEdit()"
          >{{ editing ? '取消' : '编辑' }}</button>
        </view>

        <block v-if="!editing">
          <view class="pics">
            <view v-for="n in ((cur.product && cur.product.images) || [])" :key="n" class="pic">
              <image :src="picUrl(n)" class="pic-img" mode="aspectFill" />
              <view class="pic-del" @click="dropProjectPic(n)">×</view>
            </view>
            <view
              v-if="((cur.product && cur.product.images) || []).length < opt.max_pics"
              class="pic pic-add"
              @click="addProjectPics"
            >
              <text class="pic-plus">＋</text>
              <text class="pic-tip">上传</text>
            </view>
          </view>

          <view class="kv-list">
            <view class="kv"><text class="kv-k">品类</text><text class="kv-v">{{ cur.product.category || '—' }}</text></view>
            <view class="kv"><text class="kv-k">价格</text><text class="kv-v">{{ cur.product.price || '—' }}</text></view>
            <view class="kv"><text class="kv-k">人群</text><text class="kv-v">{{ cur.product.audience || '—' }}</text></view>
            <view class="kv"><text class="kv-k">平台</text><text class="kv-v">{{ cur.product.platform || '—' }}</text></view>
            <view class="kv"><text class="kv-k">模式</text><text class="kv-v">{{ cur.answers.mode || '—' }}</text></view>
            <view class="kv"><text class="kv-k">出镜人物</text><text class="kv-v">{{ cur.answers.presenter || '模型挑' }}</text></view>
          </view>

          <view v-if="(cur.product.points || []).length" class="pts">
            <text v-for="(x, i) in cur.product.points" :key="i" class="pt">{{ x }}</text>
          </view>
        </block>

        <block v-else>
          <view class="field">
            <view class="label">商品名称</view>
            <input v-model="form.name" class="input line" />
          </view>
          <view class="field">
            <view class="label">商品品类</view>
            <view class="opts">
              <view
                v-for="x in opt.categories"
                :key="x"
                :class="['opt', form.category === x ? 'on' : '']"
                @click="form.category = form.category === x ? '' : x"
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
            <view class="label">卖点<text class="label-tip">每行一条</text></view>
            <textarea v-model="form.points" class="input area" auto-height />
          </view>
          <view class="field">
            <view class="label">原始资料</view>
            <textarea v-model="form.facts" class="input area" auto-height />
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
          <view class="field">
            <view class="label">视频模式</view>
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
          <view v-if="peopleMode" class="field">
            <view class="label">出镜人物</view>
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
          <button class="btn-main btn-main--sm" :disabled="!!busy" @click="saveEdit">
            {{ busy === 'save' ? '保存中…' : '保存' }}
          </button>
        </block>
      </view>

      <view class="card">
        <view class="card-head">
          <view class="card-title"><text class="card-no">1</text>结构卡</view>
          <button class="btn-mini" :disabled="!!busy" @click="gen('card')">
            {{ busy === 'card' ? '生成中…' : (cur.card ? '重新生成' : '生成') }}
          </button>
        </view>
        <block v-if="cur.card_json">
          <view class="card-meta">
            <text class="cm">{{ cur.card_json.duration }} 秒</text>
            <text class="cm">{{ cur.card_json.scene_count }} 场</text>
            <text class="cm">{{ cur.card_json.character_count }} 人</text>
            <text class="cm">{{ cur.card_json.role }}</text>
          </view>

          <view class="logline-big">{{ cur.card_json.logline }}</view>

          <view class="conflict">
            <view class="cf-row">
              <text class="cf-tag up">一方</text>
              <text class="cf-name">{{ (cur.card_json.conflict || {}).side_a }}</text>
            </view>
            <view class="cf-row">
              <text class="cf-tag down">另一方</text>
              <text class="cf-name">{{ (cur.card_json.conflict || {}).side_b }}</text>
            </view>
            <view class="cf-stake">对立的是 —— {{ (cur.card_json.conflict || {}).stake }}</view>
          </view>

          <view class="hook-row">
            <text class="hook-badge">{{ (cur.card_json.hook || {}).type }}</text>
            <text class="hook-frame">{{ (cur.card_json.hook || {}).first_frame }}</text>
          </view>

          <view class="beats">
            <view v-for="b in cur.card_json.beats" :key="b.no" class="beat">
              <view class="beat-axis">
                <view class="beat-dot"></view>
                <view class="beat-bar"></view>
              </view>
              <view class="beat-body">
                <view class="beat-head">
                  <text class="beat-name">{{ b.name }}</text>
                  <text class="beat-time">{{ b.time }}</text>
                </view>
                <view class="beat-what">{{ b.what }}</view>
              </view>
            </view>
          </view>

          <view v-if="cur.card_json.renew_point" class="note-row">
            <text class="note-k">中段续命</text>
            <text class="note-v">{{ cur.card_json.renew_point }}</text>
          </view>
          <view class="note-row">
            <text class="note-k">CTA 中段</text>
            <text class="note-v">约 70% → {{ (cur.card_json.cta || {}).mid }}</text>
          </view>
          <view class="note-row">
            <text class="note-k">CTA 收尾</text>
            <text class="note-v">最后一镜 → {{ (cur.card_json.cta || {}).final }}</text>
          </view>
          <view class="why">
            <text class="why-k">为什么非它不可</text>
            <text class="why-v">{{ cur.card_json.why_product }}</text>
          </view>

          <view class="card-foot">
            <view v-if="cur.card_confirmed" class="stamp">✓ 已确认</view>
            <button
              v-else
              class="btn-main btn-main--sm"
              :disabled="!!busy"
              @click="confirmCard"
            >确认这张结构卡，开始写剧本</button>
          </view>
        </block>
        <!-- 老项目：只有文本、还没有结构化数据 -->
        <block v-else-if="cur.card">
          <view class="raw">{{ cur.card }}</view>
          <view class="card-foot">
            <view v-if="cur.card_confirmed" class="stamp">✓ 已确认</view>
            <button
              v-else
              class="btn-main btn-main--sm"
              :disabled="!!busy"
              @click="confirmCard"
            >确认这张结构卡，开始写剧本</button>
          </view>
        </block>
        <view v-else class="empty">先出结构卡。确认之后才允许写剧本。</view>
      </view>

      <view class="card">
        <view class="card-head">
          <view class="card-title"><text class="card-no">2</text>剧本</view>
          <button class="btn-mini" :disabled="!!busy || !cur.card_confirmed" @click="gen('script')">
            {{ busy === 'script' ? '写剧本…' : (cur.script ? '重新生成' : '写剧本') }}
          </button>
        </view>

        <block v-if="cur.script_json">
          <view v-if="cur.script_json.logline" class="logline">
            {{ cur.script_json.logline }}
            <text v-if="cur.script_json.hook" class="hook">开头策略 {{ cur.script_json.hook }}</text>
          </view>

          <scroll-view scroll-x class="chars" :show-scrollbar="false">
            <view
              v-for="(c, i) in cur.script_json.characters"
              :key="c.name"
              class="char"
            >
              <view class="char-top">
                <view class="char-dot" :style="{ background: color(i) }"></view>
                <text class="char-name">{{ c.name }}</text>
              </view>
              <view class="char-id">{{ c.identity }}</view>
              <view v-if="c.appearance" class="char-row"><text class="k">外观</text>{{ c.appearance }}</view>
              <view v-if="c.stance" class="char-row"><text class="k">立场</text>{{ c.stance }}</view>
              <view v-if="c.weakness" class="char-row"><text class="k">弱点</text>{{ c.weakness }}</view>
            </view>
          </scroll-view>

          <view
            v-for="s in cur.script_json.scenes"
            :key="s.no"
            class="scene"
          >
            <view class="scene-head">
              <text class="scene-no">第 {{ s.no }} 场</text>
              <text v-if="s.time" class="scene-meta">{{ s.time }}</text>
              <text v-if="s.location" class="scene-meta">· {{ s.location }}</text>
              <text v-if="s.product" class="scene-prod">商品出镜</text>
            </view>
            <view class="scene-what">{{ s.what }}</view>
            <view v-for="(l, j) in s.lines" :key="j" class="line">
              <text class="line-who">{{ l.who }}</text>
              <text class="line-text">{{ l.text }}</text>
            </view>
          </view>
        </block>
        <view v-else-if="cur.script" class="raw">{{ cur.script }}</view>
        <view v-else class="empty">{{ cur.card_confirmed ? '结构卡已确认，可以写剧本了。' : '结构卡确认后解锁。' }}</view>
      </view>

      <view class="card">
        <view class="card-head">
          <view class="card-title"><text class="card-no">3</text>分镜</view>
          <button class="btn-mini" :disabled="!!busy || !cur.script" @click="gen('storyboard')">
            {{ busy === 'storyboard' ? '排分镜…' : (cur.storyboard ? '重新生成' : '出分镜') }}
          </button>
        </view>

        <block v-if="cur.storyboard_json">
          <view class="shot-sum">
            共 <text class="em">{{ cur.storyboard_json.shots.length }}</text> 镜 ｜
            合计 <text class="em">{{ totalSeconds }}</text> 秒 ｜
            商品 <text class="em">{{ productShots }}/{{ cur.storyboard_json.shots.length }}</text> 镜
          </view>
          <!-- 剧本结构模板：这套节奏跑通了就存下来，下一个商品直接照节奏重写 -->
          <view class="ref-row">
            <text class="ref-now">
              {{ (cur.ref_template && cur.ref_template.name) ? '参考结构：' + cur.ref_template.name : '没参考结构（节奏由模型自己定）' }}
            </text>
            <text class="ref-act" @click="pickRefTemplate">选参考</text>
            <text class="ref-act" @click="saveAsScriptTpl">存为结构模板</text>
            <text v-if="cur.ref_template" class="ref-act danger" @click="setRefTemplate('')">取消参考</text>
          </view>
          <!-- 可生成性提示（C13 四禁 + S1/S2）：只提示不拦，改不改由人定 -->
          <view v-for="l in (cur.storyboard_lints || [])" :key="'sl' + l" class="film-warn">⚠ {{ l }}</view>
          <view v-for="s in cur.storyboard_json.shots" :key="s.id" class="shot">
            <view class="shot-no">{{ s.id }}</view>
            <view class="shot-body">
              <view class="shot-top">
                <text class="dur">{{ s.duration }}s</text>
                <text v-if="s.framing" class="meta">{{ s.framing }}</text>
                <text v-if="s.camera" class="meta">{{ s.camera }}</text>
                <text v-if="s.product" class="tag-prod">商品</text>
              </view>
              <view class="shot-desc">{{ s.description }}</view>
              <view v-if="s.dialogue" class="shot-line">「{{ s.dialogue }}」</view>
              <view v-if="s.purpose" class="shot-why">{{ s.purpose }}</view>
            </view>
          </view>
        </block>
        <view v-else-if="cur.storyboard" class="raw">{{ cur.storyboard }}</view>
        <view v-else class="empty">写完剧本后解锁。</view>
      </view>

      <view class="card">
        <view class="card-head">
          <view class="card-title"><text class="card-no">4</text>判官</view>
          <button class="btn-mini" :disabled="!!busy || !cur.storyboard_json" @click="runJudge">
            {{ busy === 'judge' ? '审稿中…' : (cur.judge ? '重新审' : '开始审稿') }}
          </button>
        </view>

        <block v-if="cur.judge">
          <view class="judge-sum">
            <view class="js-item bad">
              <text class="js-n">{{ cur.judge.counts.invariant }}</text>
              <text class="js-l">必须改</text>
            </view>
            <view class="js-item warn">
              <text class="js-n">{{ cur.judge.counts.default }}</text>
              <text class="js-l">建议改</text>
            </view>
            <view class="js-item grey">
              <text class="js-n">{{ cur.judge.counts.taste }}</text>
              <text class="js-l">参考</text>
            </view>
            <view class="js-item grey">
              <text class="js-n">{{ cur.judge.counts.dropped }}</text>
              <text class="js-l">已丢弃</text>
            </view>
          </view>
          <view v-if="cur.judge.summary" class="judge-summary">{{ cur.judge.summary }}</view>

          <view v-for="v in cur.judge.verdicts" :key="v.judge" class="vg">
            <view class="vg-head">
              <text class="vg-name">{{ judgeName(v.judge) }}</text>
              <text :class="['vg-score', scoreCls(v.score)]">{{ v.score }}/5</text>
            </view>
            <view v-if="v.note" class="vg-note">{{ v.note }}</view>
            <view v-if="!v.issues.length" class="vg-clean">没意见</view>
            <view v-for="(it, i) in v.issues" :key="i" class="issue">
              <view class="issue-top">
                <text :class="['tier', it.tier]">{{ tierLabel(it.tier) }}</text>
                <text v-if="it.shot_id" class="issue-shot">第 {{ it.shot_id }} 镜</text>
                <text v-if="it.field" class="issue-field">{{ fieldLabel(it.field) }}</text>
              </view>
              <view class="issue-problem">{{ it.problem }}</view>
              <view v-if="it.fix" class="issue-fix">{{ it.fix }}</view>
              <view v-if="it.new_text" class="issue-new">「{{ it.new_text }}」</view>
              <view v-if="it.new_text" class="issue-apply" @click="applyIssue(it)">应用这条 →</view>
            </view>
          </view>

          <button
            v-if="applicableCount"
            class="btn-main btn-main--sm"
            :disabled="!!busy"
            @click="applyAll"
          >应用全部可直接替换的（{{ applicableCount }} 条）</button>
          <view v-if="applicableCount" class="judge-tip">改完分镜就变了，建议重新审一遍。</view>
          <!-- 应用完把改动逐条摆出来（2026-11-08）：只弹一句「已应用 N 条」等于没说 -->
          <view v-if="applyLog.length" class="judge-tip">
            <view>✅ 本次应用了 {{ applyLog.length }} 处（已写进下面的分镜表）：</view>
            <view v-for="(d, i) in applyLog" :key="'ap' + i">
              镜 {{ d.shot }} {{ fieldLabel(d.field) }}：{{ d.from || '（空）' }} → {{ d.to || '（空）' }}
            </view>
          </view>
          <!-- 没有可直接替换的条目时必须说清楚（2026-11-08）：不然点完发现什么都没变，
               人会以为「审稿没用」。 -->
          <view v-else class="judge-tip">
            这 {{ judgeIssueCount }} 条都只有改法、没有可直接替换的句子，机器改不了 —— 得照意见手改分镜，
            或者点「重新审」让它再出一版带改法原句的意见。
          </view>
        </block>
        <view v-else class="empty">
          五个判官同时审：节奏 / 口语 / 创意 / 结构 / 画面。
          模型会把坏脚本拍得和好脚本一样漂亮——出片前先把脚本撕一遍。
        </view>
      </view>

      <view class="card">
        <view class="card-head">
          <view class="card-title"><text class="card-no">6</text>自检</view>
          <button class="btn-mini" :disabled="!!busy || !cur.storyboard" @click="gen('check')">
            {{ busy === 'check' ? '自检中…' : (cur.check ? '重新自检' : '开始自检') }}
          </button>
        </view>
        <view v-if="cur.check" class="raw">{{ cur.check }}</view>
        <!-- 分镜一改，后端就把上一版自检清空（2026-11-08）：这里要说清楚是「还没跑」
             而不是「没解锁」，否则人会以为自检卡坏了 -->
        <view v-else-if="cur.storyboard" class="empty">
          这一版分镜还没自检。分镜一改，之前的自检就作废了，重新跑一次。
        </view>
        <view v-else class="empty">出完分镜后解锁。十六条逐条过，任何一条不过都不交付。</view>
      </view>

      <!-- A3 商品库：跨项目复用商品卡（品类/卖点/受众/商品图） -->
      <view class="card">
        <view class="card-head">
          <view class="card-title"><text class="card-no">库</text>商品库</view>
          <button class="btn-mini" @click="toggleProductLib">{{ plOpen ? '收起' : '展开' }}</button>
        </view>
        <view v-if="plOpen" class="pl-box">
          <view class="tts-actions">
            <button class="btn-mini" :disabled="plBusy || !cur" @click="saveCurrentProduct">
              {{ plBusy ? '处理中…' : '把当前商品存进库' }}
            </button>
            <text v-if="plNote" class="tts-hint">{{ plNote }}</text>
          </view>
          <view v-for="it in plItems" :key="it.id" class="pl-row">
            <view class="pl-info">
              <text class="pl-name">{{ it.name }}</text>
              <text class="pl-meta">{{ it.category || '未分类' }}<text v-if="it.price"> · {{ it.price }}</text></text>
            </view>
            <text class="media-more" @click.stop="useProduct(it)">用这个</text>
            <text class="pl-del" @click.stop="removeProduct(it)">删</text>
          </view>
          <view v-if="!plItems.length" class="merge-tip">
            还没有商品卡。填好商品后点「把当前商品存进库」，下次换个项目就不用重填。
          </view>
        </view>
      </view>
      </block>
      <!-- 素材混剪成片（顾客自己传的图/视频 + 商品图合成，不调 AI 出画面） -->
      <view class="card pipe-card">
        <view class="card-head">
          <view class="card-title"><text class="card-no">▶</text>素材混剪成片</view>
          <button class="btn-mini" :disabled="!pipeReady || pipeRunning" @click="startPipeline">
            {{ pipeRunning ? '跑着…' : (pipeRun.status === 'done' ? '再跑一遍' : '开始') }}
          </button>
        </view>
        <view class="merge-tip">
          用上传的素材 / 商品图配画面 → 配音合成 → 直达成片｜服务端自己跑完、断点可续
        </view>
        <view class="pipe-from">
          <text class="pipe-from-label">从</text>
          <text
            v-for="s in pipeStages"
            :key="s.key"
            :class="['pipe-chip', pipeFrom === s.key ? 'on' : '']"
            @click="pipeFrom = s.key"
          >{{ s.label }}</text>
          <text class="pipe-from-label">起</text>
        </view>
        <view v-for="s in pipeRows" :key="s.key" class="pipe-row">
          <text :class="['pipe-mark', s.state]">{{ s.icon }}</text>
          <text class="pipe-name">{{ s.label }}</text>
          <text class="pipe-note">{{ s.note }}</text>
        </view>
        <view v-if="pipeRun.error" class="film-warn">⚠ {{ pipeRun.error }}</view>
        <view v-if="!pipeReady" class="empty">先把分镜做出来，流水线才有东西可跑</view>
      </view>

      <!-- AI 成片（付费）：竞品 `script/page.tsx:855-936` 的 dryRun 预览卡，独立一条路 -->
      <view class="card">
        <view class="card-head">
          <view class="card-title"><text class="card-no">🎬</text>AI 成片{{ aiOpen ? '预览' : '' }}</view>
          <button v-if="!aiOpen" class="btn-mini" :disabled="!pipeReady || !!busy" @click="aiPreview">
            看预览（免费）
          </button>
          <button v-else class="btn-mini" :disabled="!!busy" @click="aiConfirm">
            ✨ {{ busy === 'ai-film' ? '出片中…' : '确认出片' }}
          </button>
        </view>

        <block v-if="!aiOpen">
          <view class="merge-tip">
            先出预览（模型 / 段数 / 时长 / 参考图 / 花费），确认后才扣费；出完自动合成并跳导出。
          </view>
          <view v-if="!pipeReady" class="empty">先把分镜做出来，才有段可出</view>
        </block>

        <block v-else>
          <view class="merge-tip">{{ aiMeta }}</view>
          <view v-if="aiSwap" class="film-warn">{{ aiSwap }}</view>
          <view v-for="(w, i) in aiWarns" :key="i" class="film-warn">⚠ {{ w }}</view>
          <view class="merge-tip">花费：{{ aiPrice }}</view>
          <view class="pipe-row" @click="aiShowPrompt = !aiShowPrompt">
            <text class="pipe-mark ok">📄</text>
            <text class="pipe-name">要发出去的提示词</text>
            <text class="pipe-note">{{ aiShowPrompt ? '收起' : '展开' }}</text>
          </view>
          <view v-if="aiShowPrompt" class="ai-prompt">{{ aiPrompt }}</view>
          <view class="merge-tip">确认后由你自己平台的账号真扣费；出完自动合成，再跳导出页。</view>
          <button class="btn-mini" :disabled="!!busy" @click="aiBack">返回修改</button>
        </block>
      </view>

      <view class="card">
        <view class="card-head">
          <view class="card-title"><text class="card-no">稿</text>脚本版本</view>
          <button v-if="!isTopic" class="btn-mini" :disabled="!!busy" @click="importOpen = !importOpen">
            {{ importOpen ? '收起手写稿' : '导入手写稿' }}
          </button>
        </view>
        <view v-if="scriptCardStale" class="film-warn">⚠ 结构卡改过了，这版剧本还是旧卡写的，重新生成剧本才对得上</view>
        <view v-if="scriptStale" class="film-warn">⚠ 分镜还是按另一版剧本写的，重新出分镜才对得上</view>
        <view class="merge-tip">
          每生成一次存一版，最多留 12 版｜切版本只换当前剧本{{ isTopic ? '（话题片连分镜一起换）' : '' }}
        </view>
        <view v-for="s in scripts" :key="s.id" :class="['script-row', s.selected ? 'on' : '']">
          <view class="script-main" @click="switchScript(s.id)">
            <view class="script-title">v{{ s.version }} · {{ s.title || '未命名' }}</view>
            <view class="script-preview">{{ s.preview }}</view>
          </view>
          <text class="script-src">{{ s.source === 'import' ? '手写' : (s.source === 'topic' ? '话题' : 'AI') }}</text>
          <text class="script-del" @click.stop="removeScript(s)">删</text>
        </view>
        <view v-if="!scripts.length" class="empty">{{ isTopic ? '这一条还没有脚本' : '还没写剧本' }}</view>

        <block v-if="importOpen && !isTopic">
          <view class="merge-tip" style="margin-top:12rpx;">
            贴自己的口播稿：一句一镜切开，直接出分镜（不调模型、不花钱）；商品图会照常带上。
          </view>
          <input v-model="importTitle" class="input line" placeholder="标题（可留空）" />
          <textarea v-model="importText" class="input area" auto-height
                    placeholder="例：这也太快了吧！我抽一张纸按进水痕里，纸面居然没破。姐妹们都给我冲。" />
          <button class="btn-mini" :disabled="!!busy" @click="submitImport">
            {{ busy === 'import-script' ? '切分中…' : '导入并生成分镜' }}
          </button>
        </block>
      </view>
      </block>

      </block>
    </view>
  </DramaAppShell>
</template>

<script>
import { onLoad, onUnload } from '@dcloudio/uni-app'
import DramaAppShell from '@/components/drama/AppShell.vue'
import DramaProjectHeader from '@/components/drama/ProjectHeader.vue'
import dramaPageBoot from '@/mixins/dramaPageBoot'
import {
  dramaComposePlan, dramaComposeRun, dramaFilmRender,
  dramaPipelineStart, dramaPipelineState,
} from '@/api/request'

/**
 * 商品短剧 · 脚本 步（照竞品 app/project/[id]/script/page.tsx 的分工）
 *
 * 本页模板块是**从旧单页 drama/index.vue 原样搬过来**的（逐行区间见
 * docs/DRAMA-UI-RESTRUCTURE.md），逻辑全部来自 mixins/dramaPageBoot。
 * 下一步再按「只留本步要用的 state」收窄，不在搬迁轮里顺手改业务。
 */
export default {
  components: { DramaAppShell, DramaProjectHeader },
  mixins: [dramaPageBoot],
  data() {
    return {
      // 没有免费档：默认只合成（用已上传的素材/商品图），不再自动搜免费图库
      pipeFrom: 'compose',
      pipeRun: { status: 'idle', stage: '', stages: [], results: {}, error: '' },
      pipeTimer: null,
      // 不再提供「配画面」档：盲目搜免费图库只会配到空镜（红凳子/古版画）。
      // 画面用顾客自己上传的素材/商品图；配画面只在素材页手动做。
      pipeStages: [
        { key: 'judge', label: '判官' },
        { key: 'compose', label: '合成' },
      ],
      // 从新建页带过来的两条路：竞品 `start/page.tsx:371` → `script/page.tsx:347-349/494-500`
      autoMode: false,        // ?auto=1：hands-off，进来就自己跑
      genPref: 'ai',          // 新建页选的那条路：'ai' | 'free'，只改主按钮，不自动跑
      autoTriggered: false,   // 只触发一次
      autoHide: false,        // 接管页上点了「看细节」就退回编辑器
      // AI 成片的 dryRun 预览（照 `script/page.tsx:858-936`，预览是卡不是弹窗）
      aiOpen: false,
      aiMeta: '',
      aiPrice: '',
      aiPrompt: '',
      aiWarns: [],
      aiSwap: '',
      aiShowPrompt: false,
      aiStage: '',            // 出片时的当前动作（接管页上显示）
      // 入门/专业两档（照竞品 script/page.tsx 的 simple / pro）
      // 2026-11-08：改成本地存储，跨页共享 —— 剧本页切了 pro，素材页不能又变回 simple
      uiMode: uni.getStorageSync('dramaUiMode') || 'simple',
      simpTitle: '',
      simpLines: [],
    }
  },
  async onLoad(q) {
    const qq = q || {}
    this.autoMode = String(qq.auto || '') === '1'
    // 没带 gen（列表/克隆/转写等入口）按 AI 路显示主按钮；只有明确 gen=free 才把免费快剪设为主
    this.genPref = qq.gen === 'free' ? 'free' : 'ai'
    await this.boot(qq.id || '')
    this.buildSimple()
    // 创建时自动写稿如果断在某一步，进页面直接说清楚是哪一步断了（不弹窗、不拦路）
    const df = String(qq.draftfail || '')
    if (df && this.cur) {
      uni.showToast({ title: decodeURIComponent(df) + '没写成，在这里点「重新生成」', icon: 'none', duration: 3500 })
    }
    // 先接上已存在的流水线，再接「自动开跑」——否则会把正在跑的又起一遍
    await this.resumePipeline()
    this.maybeAutoRun()
  },
  onUnload() {
    this.stopPipePoll()
  },
  watch: {
    'cur.storyboard_json': { deep: true, handler() { this.buildSimple() } },
  },
  computed: {
    pipeRunning() {
      return this.pipeRun.status === 'running'
    },
    /** 自动链接管：只有「从新建页带 auto=1 进来 + 免费路 + 正在跑」才盖住编辑器 */
    autoTakeover() {
      // 入门视图点「用我的素材合成」和 ?auto=1 是同一条路：跑的时候都盖成一张进度卡
      const handsOff = this.autoMode || this.uiMode === 'simple'
      return handsOff && this.genPref !== 'ai' && this.pipeRunning && !this.autoHide
    },
    pipeStageName() {
      const st = this.pipeRun || {}
      for (let i = 0; i < this.pipeStages.length; i++) {
        if (this.pipeStages[i].key === st.stage) return this.pipeStages[i].label
      }
      return '准备中'
    },
    pipeReady() {
      return !!((this.cur || {}).storyboard_json || {}).shots && ((this.cur || {}).storyboard_json || {}).shots.length > 0
    },
    pipeRows() {
      const st = this.pipeRun || {}
      const stages = st.stages || []
      const okDone = st.status === 'done'
      return this.pipeStages.map((s) => {
        const inPlan = stages.indexOf(s.key) >= 0
        const done = !!((st.results || {})[s.key])
        let state = 'wait'
        let note = inPlan ? '待跑' : '不在本轮'
        if (done) {
          state = 'ok'
          note = (st.results[s.key] || {}).summary || '完成'
        } else if (inPlan && st.stage === s.key && st.status === 'running') {
          state = 'now'
          note = '正在跑…'
        } else if (inPlan && (st.status === 'failed' || st.status === 'interrupted') && st.stage === s.key) {
          state = 'bad'
          note = st.status === 'failed' ? '这一步失败' : '进程没了，可续跑'
        } else if (inPlan && okDone) {
          state = 'ok'
        }
        const icon = state === 'ok' ? '✓' : (state === 'bad' ? '!' : (state === 'now' ? '●' : '○'))
        return { key: s.key, label: s.label, note, state, icon }
      })
    },
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
    /** 入门 / 专业切换：写本地存储，素材页等其它页读到的是同一个值 */
    setUiMode(m) {
      this.uiMode = m === 'pro' ? 'pro' : 'simple'
      try { uni.setStorageSync('dramaUiMode', this.uiMode) } catch (e) { /* 忽略 */ }
    },
    async startPipeline() {
      if (!this.pid || this.pipeRunning) return
      if (!this.pipeReady) {
        uni.showToast({ title: '先做分镜', icon: 'none' })
        return
      }
      this.autoHide = false   // 手动再跑一遍时，接管页重新盖住（和自动跑一致）
      try {
        this.pipeRun = await dramaPipelineStart(this.pid, this.pipeFrom)
      } catch (e) {
        uni.showToast({ title: e.message || '起不来流水线', icon: 'none' })
        return
      }
      this.startPipePoll()
    },
    /** 进页时接上还没跑完的流水线（断点续跑靠它） */
    async resumePipeline() {
      if (!this.pid) return
      try {
        const r = await dramaPipelineState(this.pid)
        if (r && r.status && r.status !== 'idle') this.pipeRun = r
        if (this.pipeRunning) this.startPipePoll()
      } catch (e) { /* 拉不到就当没在跑 */ }
    },
    /** 入门视图用的台词行（只有文字，不暴露分镜字段） */
    buildSimple() {
      const doc = this.cur || {}
      const shots = ((doc.storyboard_json || {}).shots) || []
      const list = this.scripts || []
      let title = ''
      for (let i = 0; i < list.length; i++) {
        if (list[i].selected) { title = list[i].title || ''; break }
      }
      this.simpTitle = title || (doc.product && doc.product.name) || '当前剧本'
      const rows = []
      for (let i = 0; i < shots.length; i++) {
        const s = shots[i] || {}
        const t = String(s.dialogue || s.description || '').trim()
        if (t) rows.push({ id: s.id, text: t })
      }
      this.simpLines = rows
    },
    /** 入门视图「重新生成」：重写剧本 + 分镜（会花模型调用，先问一句） */
    async regenSimple() {
      if (!this.cur || this.busy) return
      const ok = await new Promise((res) => uni.showModal({
        title: '重新生成剧本',
        content: '现在的剧本和分镜会被新的替掉（会调用模型）。',
        confirmText: '重新生成',
        success: (x) => res(x.confirm),
      }))
      if (!ok) return
      await this.gen('script')
      await this.gen('storyboard')
      this.buildSimple()
    },
    /** ?auto=1 进来要不要自己跑：竞品 `script/page.tsx:494-500` —— 只有免费路自动跑 */
    maybeAutoRun() {
      if (!this.autoMode || this.autoTriggered) return
      if (!this.pipeReady) return
      this.autoTriggered = true
      if (this.genPref === 'ai') return          // AI 路停在脚本页，等主人看预览再花钱
      if (this.pipeRunning || this.pipeRun.status === 'done') return
      this.startPipeline()
    },
    /** AI 成片第一步：dryRun 预览（纯计算、不花钱）—— 竞品 `script/page.tsx:533-575` */
    async aiPreview() {
      if (!this.cur || this.busy) return
      await this.filmPlan()
      const p = this.plan || {}
      const segs = p.segments || []
      if (!p.plan_hash || !segs.length) return
      const total = segs.reduce((a, s) => a + Number(s.seconds || 0), 0)
      const refs = segs.reduce(
        (a, s) => a + (s.prod_count || 0) + (s.board ? 1 : 0) + (s.cast_count || 0), 0)
      this.aiMeta = `${segs.length} 段 · 共 ${total} 秒 · ${refs} 张参考图`
      this.aiPrice = this.priceText
      this.aiSwap = ''
      this.aiWarns = []
      for (const e of (p.errors || [])) this.aiWarns.push('出不了：' + e)
      for (const w of (p.warnings || []).slice(0, 4)) this.aiWarns.push(w)
      // 竞品把「要发出去的提示词」原样摊开；我们按段拼，段与段之间标清楚
      this.aiPrompt = segs
        .map((s) => `【第 ${s.no} 段 · ${s.seconds || '?'} 秒】\n${s.prompt || ''}`)
        .join('\n\n')
      this.aiShowPrompt = false
      this.aiOpen = true
    },
    /** 第二步：确认这一版才真花钱（竞品 `script/page.tsx:578-676` confirmAiFilm） */
    async aiConfirm() {
      if (!this.cur || this.busy) return
      const p = this.plan || {}
      const segs = p.segments || []
      if (!p.plan_hash || !segs.length) {
        uni.showToast({ title: '先看预览', icon: 'none' })
        return
      }
      if ((p.errors || []).length) {
        uni.showModal({ title: '这版出不了片', content: p.errors[0], showCancel: false })
        return
      }
      const pid = this.pid || this.cur.id
      this.busy = 'ai-film'
      this.aiStage = `${segs.length} 段逐段提交，模型正在出片…`
      try {
        // no=0：按顺序把每一段都出了（后端同一份 plan_hash 二次核对）
        this.cur = await dramaFilmRender(pid, 0, this.filmResolution, p.plan_hash)
        // 出完就地合成（本地 ffmpeg，零生成费）—— 竞品出片后直接进导出页，
        // 我们多一步合成才能「看到一条完整片」，所以连着做完再跳。
        this.aiStage = '各段都出好了，正在本地合成整片…'
        this.cur = await dramaComposePlan(pid, { ...this.compPayload(), plan_hash: '' })
        this.cur = await dramaComposeRun(pid, this.compPayload())
        this.aiOpen = false
        uni.showToast({ title: '成片好了', icon: 'success' })
        setTimeout(() => uni.redirectTo({ url: `/pages/drama/export?id=${pid}` }), 800)
      } catch (e) {
        uni.showModal({ title: 'AI 成片没跑完', content: e.message || '请稍后重试', showCancel: false })
      } finally {
        this.busy = ''
        this.aiStage = ''
      }
    },
    aiBack() {
      this.aiOpen = false
      this.aiShowPrompt = false
    },
    startPipePoll() {
      this.stopPipePoll()
      this.pipeTimer = setInterval(() => { this.pollPipeline() }, 2000)
    },
    stopPipePoll() {
      if (this.pipeTimer) {
        clearInterval(this.pipeTimer)
        this.pipeTimer = null
      }
    },
    async pollPipeline() {
      if (!this.pid) return
      try {
        const r = await dramaPipelineState(this.pid)
        this.pipeRun = r || this.pipeRun
        if (this.pipeRun.status !== 'running') {
          this.stopPipePoll()
          if (this.pipeRun.status === 'done') {
            // 判官/配画面/合成都落在项目文档里，重拉一次让页面上的对应卡片跟着更新
            await this.safe(this.open, this.pid)
            uni.showToast({ title: '跑完了', icon: 'none' })
          }
        }
      } catch (e) { /* 轮询失败下一轮再来，不打断 */ }
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

/* 一键跑完：三段状态条 */
.pipe-from { display: flex; align-items: center; flex-wrap: wrap; gap: 8rpx; margin: 12rpx 0 6rpx; }
.pipe-from-label { font-size: 21rpx; color: #9aa0a6; }
.pipe-chip {
  padding: 4rpx 14rpx;
  border-radius: 999rpx;
  background: #f0f2f5;
  font-size: 21rpx;
  color: #666;
}
.pipe-chip.on { background: #0b8f6b; color: #fff; }
.ai-prompt {
  margin: 8rpx 0; padding: 16rpx; border-radius: 10rpx;
  background: #f2f4f7; color: #3a4149; font-size: 21rpx; line-height: 1.65;
  white-space: pre-wrap; word-break: break-all;
  max-height: 520rpx; overflow-y: auto;
}
.pipe-row { display: flex; align-items: center; gap: 10rpx; padding: 7rpx 0; font-size: 22rpx; }
.pipe-mark { flex: none; width: 26rpx; text-align: center; color: #b0b6bd; }
.pipe-mark.ok { color: #0b8f6b; }
.pipe-mark.now { color: #e08f00; }
.pipe-mark.bad { color: #d93025; }
.pipe-name { flex: none; color: #333; }
.pipe-note { flex: 1; color: #9aa0a6; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* 自动链接管页：跑片时只给人一张进度卡 */
.auto-mask {
  position: fixed;
  left: 0; right: 0; top: 0; bottom: 0;
  background: rgba(17, 24, 39, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 60;
}
.auto-box {
  width: 560rpx;
  padding: 34rpx 30rpx 28rpx;
  background: #fff;
  border-radius: 24rpx;
}
.auto-title { font-size: 30rpx; font-weight: 700; color: #1b1f27; }
.auto-now { margin-top: 10rpx; font-size: 24rpx; color: #0b8f6b; }
.auto-row {
  margin-top: 10rpx;
  font-size: 22rpx;
  color: #9aa0a6;
  line-height: 1.5;
}
.auto-row.on { color: #e08f00; font-weight: 600; }
.auto-row.done { color: #0b8f6b; }
.auto-tip { margin-top: 16rpx; font-size: 20rpx; color: #9aa0a6; line-height: 1.6; }

/* 入门视图（照竞品 simple 模式：剧本全文 + 两个大按钮） */
.simp-head { padding: 8rpx 0 16rpx; text-align: center; }
.simp-title { font-size: 34rpx; font-weight: 700; color: #1b1f27; }
.simp-sub { margin-top: 6rpx; font-size: 22rpx; color: #9aa0a6; }
.simp-card-head {
  display: flex; align-items: center; justify-content: space-between;
  padding-bottom: 12rpx; border-bottom: 1rpx solid #f2f4f7;
}
.simp-name { font-size: 26rpx; font-weight: 600; color: #1b1f27; }
.simp-dur { font-size: 21rpx; color: #9aa0a6; }
.simp-line { margin-top: 14rpx; font-size: 25rpx; color: #333; line-height: 1.7; }
.simp-ops { display: flex; flex-direction: column; gap: 14rpx; margin-top: 22rpx; }
.simp-btn {
  padding: 24rpx 0;
  border-radius: 14rpx;
  border: 1rpx solid #dfe3e8;
  background: #fff;
  text-align: center;
  font-size: 27rpx;
  color: #1b1f27;
}
.simp-btn.simp-main { background: #0b8f6b; border-color: #0b8f6b; color: #fff; font-weight: 600; }
.simp-btn.off { opacity: 0.45; }
.simp-tip { margin-top: 14rpx; font-size: 20rpx; color: #9aa0a6; line-height: 1.6; text-align: center; }
.simp-tip-row { display: block; }
.simp-links { display: flex; justify-content: center; gap: 40rpx; margin-top: 20rpx; }
.simp-link { font-size: 22rpx; color: #0b8f6b; }
</style>
