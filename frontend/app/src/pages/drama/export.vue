<template>
  <DramaAppShell>
    <view class="ds">
      <DramaProjectHeader :id="pid" current="export" :name="headerName" :chips="chips" />

      <view v-if="!cur" class="pgstate">正在加载项目…</view>

      <block v-else>
        <!-- ① 完成横幅（照竞品 export/page.tsx:457-468） -->
        <view v-if="compOut.mp4" class="done">
          <text class="done-ico">✓</text>
          <text class="done-t">视频<text class="done-hl">生成完成</text></text>
          <text class="done-s">你的带货视频已准备就绪，可以下载或分享</text>
        </view>

        <!-- ② 成片预览（真实合成产物 + 信息条，竞品 471-502） -->
        <view v-if="compOut.mp4" class="card">
          <view class="prev-wrap">
            <video
              :src="compUrl"
              class="prev-video"
              :controls="true"
              :show-center-play-btn="true"
              object-fit="contain"
            />
          </view>
          <view class="prev-info">
            <text class="pi">{{ (plan && plan.resolution) || '—' }}</text>
            <text class="pi-dot" />
            <text class="pi">{{ (plan && plan.ratio) || '—' }}</text>
            <text class="pi-dot" />
            <text class="pi">{{ (plan && plan.total_seconds) || (compPlan && compPlan.total_seconds) || 0 }}s</text>
            <text class="pi-dot" />
            <text class="pi">MP4</text>
          </view>
        </view>

        <!-- ③ 主操作：下载 / 复制链接（竞品 504-520） -->
        <view v-if="compOut.mp4" class="act">
          <view class="act-main" @click="downloadVideo">⬇ 下载视频</view>
          <view class="act-sub" @click="copyVideoLink">🔗 复制视频链接</view>
        </view>

        <!-- 没成片：空态（竞品 425-440） -->
        <view v-else class="empty-card">
          <text class="empty-t">还没有合成视频</text>
          <text class="empty-d">「{{ headerName }}」尚未生成成片。请先到「视频」步骤完成合成，再回到这里导出。</text>
          <view class="act">
            <view class="act-main" @click="goVideo">去合成视频</view>
          </view>
        </view>

        <!-- ④ 历史成片：每次合成一条 + 变体矩阵产物（竞品 522-550） -->
        <view v-if="hisRows.length" class="card">
          <view class="card-head">
            <view class="card-title"><text class="card-no">史</text>历史成片</view>
            <text class="his-n">{{ hisRows.length }} 条</text>
          </view>
          <view v-for="h in hisRows" :key="h.key" class="his-row" @click="openHis(h)">
            <text class="his-no">{{ h.no }}</text>
            <view class="his-col">
              <text class="his-nm">{{ h.label }}</text>
              <text v-if="h.meta" class="his-meta">{{ h.meta }}</text>
            </view>
            <text class="seg-play">播放</text>
          </view>
          <view class="merge-tip">
            每次点「合成成片」都会留一条；变体只在视频页「变体矩阵」合成。
          </view>
        </view>

        <!-- ⑤ 发布文案（竞品 552-644） -->
        <view class="card">
          <view class="card-head">
            <view class="card-title"><text class="card-no">文</text>发布文案</view>
          </view>
          <view class="comp-row">
            <button class="btn-mini" :disabled="!!busy" @click="matPublish(false)">
              {{ busy === 'matpack' ? '生成中…' : '生成文案（免费）' }}
            </button>
            <button class="btn-mini" :disabled="!!busy" @click="matPublish(true)">
              {{ busy === 'matllm' ? '生成中…' : 'AI 生成标题/话题' }}
            </button>
          </view>
          <view v-if="!matPack" class="merge-tip">
            一键生成吸睛标题、#话题标签和种草文案，复制即可发布。
          </view>
          <view v-if="matPack" class="mat-pack">
            <view class="mat-sec-sm">标题（点击复制）</view>
            <view v-for="(t, i) in matPack.titles" :key="'pt' + i"
                  class="mat-line" @click="copyText(t)">· {{ t }}</view>
            <view class="mat-sec-sm">话题</view>
            <view class="mat-line" @click="copyTags">{{ (matPack.hashtags || []).join(' ') }}</view>
            <view class="mat-sec-sm">正文</view>
            <view class="mat-line" @click="copyText(matPack.caption)">{{ matPack.caption }}</view>
            <view v-if="matPack.shop_link" class="mat-line" @click="copyText(matPack.shop_link)">
              链接：{{ matPack.shop_link }}
            </view>
            <view class="mat-sec-sm">评论区</view>
            <view class="mat-line" @click="copyText(matPack.comment_kit && matPack.comment_kit.pinned)">
              置顶：{{ matPack.comment_kit && matPack.comment_kit.pinned }}
            </view>
            <view v-for="(o, i) in ((matPack.comment_kit && matPack.comment_kit.objections) || [])"
                  :key="'po' + i" class="mat-line" @click="copyText('Q:' + o.q + ' A:' + o.a)">
              {{ o.q }} → {{ o.a }}
            </view>
            <view class="mat-note">{{ matPack.comment_kit && matPack.comment_kit.notice }}</view>
            <view class="mat-note">{{ matPack.ai_declaration && matPack.ai_declaration.notice }}</view>
          </view>
        </view>

        <!-- ⑥ 发行物料：平台导出 / 二维码 / 图文卡 / 原生感 / 母版（竞品 PlatformExportPanel） -->
        <view class="card">
          <view class="card-head">
            <view class="card-title"><text class="card-no">发</text>发行物料</view>
          </view>
          <view class="merge-tip">除「AI 版文案」外全是本地处理，不额外花钱</view>

          <!-- 平台 + 构图 -->
          <view class="comp-row">
            <view v-for="p in matOpt.platforms" :key="'mp' + p.id"
                  :class="['mchip', mat.platform === p.id ? 'on' : '']"
                  @click="mat.platform = p.id">
              <text class="mchip-name">{{ p.name }}</text>
              <text class="mchip-sub">{{ p.ratio }} · ≤{{ p.max_video_kbps / 1000 }}Mbps</text>
            </view>
          </view>
          <view class="comp-row">
            <view v-for="f in matOpt.framing_modes" :key="'mf' + f.id"
                  :class="['mchip', mat.framing === f.id ? 'on' : '']"
                  @click="mat.framing = f.id">
              <text class="mchip-name">{{ f.label }}</text>
              <text class="mchip-sub">{{ f.desc }}</text>
            </view>
          </view>
          <view class="comp-row">
            <button class="btn-mini" :disabled="!!busy || !anyFilm" @click="matPreview">
              {{ busy === 'matpreview' ? '预览中…' : '看构图预览' }}
            </button>
            <button class="btn-mini" :disabled="!!busy || !anyFilm" @click="matExport">
              {{ busy === 'matexport' ? '导出中…' : ('导出 ' + matPlatformName(mat.platform) + ' 版') }}
            </button>
            <text v-if="matExportRec" class="seg-play" @click="openUrl(matExportUrl)">看导出片</text>
          </view>
          <image v-if="mat.preview" class="mat-img" :src="mat.preview" mode="widthFix" />
          <view v-if="matExportRec && matExportRec.report" class="mat-out">
            {{ matExportRec.report.message }}
          </view>

          <!-- 二维码 -->
          <view class="mat-sec">店铺二维码</view>
          <input v-model="mat.qrUrl" class="input line" placeholder="商品/店铺链接，如 https://…" />
          <view class="comp-check" @click="mat.qrBurn = !mat.qrBurn">
            <text class="comp-check-box">{{ mat.qrBurn ? '✓' : '' }}</text>
            <text>打算把这张码烧进成片（抖音会拦：站外导流）</text>
          </view>
          <view class="comp-row">
            <button class="btn-mini" :disabled="!!busy" @click="matQr">
              {{ busy === 'matqr' ? '生成中…' : '生成二维码' }}
            </button>
            <text v-if="matQrRec" class="seg-play" @click="openUrl(matQrUrl)">看二维码</text>
          </view>
          <view v-if="matQrRec && matQrRec.policy" class="mat-out">
            {{ matQrRec.policy.zh }}
          </view>
          <view v-if="matQrRec && matQrRec.link" class="mat-out">编码链接：{{ matQrRec.link }}</view>

          <!-- 图文卡 -->
          <view class="mat-sec">小红书图文卡</view>
          <view class="comp-row">
            <view v-for="t in matOpt.card_themes" :key="'mt' + t"
                  :class="['mchip', mat.theme === t ? 'on' : '']"
                  @click="mat.theme = t">
              <text class="mchip-name">{{ t }}</text>
            </view>
          </view>
          <view class="comp-row">
            <button class="btn-mini" :disabled="!!busy || !(cur.storyboard_json)" @click="matCards">
              {{ busy === 'matcards' ? '生成中…' : ('出图文卡（共 ' + ((cur.storyboard_json && cur.storyboard_json.shots) || []).length + ' 镜）') }}
            </button>
            <text v-if="matCardsRec" class="seg-play" @click="previewCards">
              看 {{ (matCardsRec.files || []).length }} 张
            </text>
          </view>

          <!-- 原生感 -->
          <view class="mat-sec">原生感（像手机随手拍）</view>
          <view class="comp-row">
            <view v-for="s in matOpt.native_strengths" :key="'mn' + s.id"
                  :class="['mchip', mat.strength === s.id ? 'on' : '']"
                  @click="mat.strength = s.id">
              <text class="mchip-name">{{ s.label }}</text>
              <text class="mchip-sub">{{ s.desc }}</text>
            </view>
          </view>
          <view class="comp-check" @click="mat.grain = !mat.grain">
            <text class="comp-check-box">{{ mat.grain ? '✓' : '' }}</text>
            <text>轻颗粒</text>
          </view>
          <view class="comp-check" @click="mat.vignette = !mat.vignette">
            <text class="comp-check-box">{{ mat.vignette ? '✓' : '' }}</text>
            <text>暗角</text>
          </view>
          <view class="comp-check" @click="mat.halation = !mat.halation">
            <text class="comp-check-box">{{ mat.halation ? '✓' : '' }}</text>
            <text>镜头光晕</text>
          </view>
          <view class="comp-check" @click="mat.phoneCompress = !mat.phoneCompress">
            <text class="comp-check-box">{{ mat.phoneCompress ? '✓' : '' }}</text>
            <text>平台二压感（更像已上传过一次）</text>
          </view>
          <view class="comp-row">
            <button class="btn-mini" :disabled="!!busy || !anyFilm" @click="matNative">
              {{ busy === 'matnative' ? '处理中…' : (matNativeRec ? '重做原生感' : '处理原生感') }}
            </button>
            <text v-if="matNativeRec" class="seg-play" @click="openUrl(matNativeUrl)">看成品</text>
          </view>

          <!-- 母版 -->
          <view class="mat-sec">母版精修（接缝体检 + 响度）</view>
          <view class="comp-row">
            <button class="btn-mini" :disabled="!!busy || !anyFilm" @click="matMasterAnalyze">
              {{ busy === 'matmastera' ? '体检中…' : '体检' }}
            </button>
            <button class="btn-mini" :disabled="!!busy || !anyFilm" @click="matMasterRender">
              {{ busy === 'matmasterr' ? '精修中…' : '精修出片' }}
            </button>
            <text v-if="matMasterRec" class="seg-play" @click="openUrl(matMasterUrl)">看精修片</text>
          </view>
          <view class="comp-check" @click="mat.normalize = !mat.normalize">
            <text class="comp-check-box">{{ mat.normalize ? '✓' : '' }}</text>
            <text>响度归一到 -14 LUFS</text>
          </view>
          <view class="comp-check" @click="mat.deflicker = !mat.deflicker">
            <text class="comp-check-box">{{ mat.deflicker ? '✓' : '' }}</text>
            <text>去闪烁</text>
          </view>
        </view>

        <!-- ⑦ 高级工具（默认收起；竞品 advanced details 649-657） -->
        <view class="adv">
          <view class="adv-head" @click="advOpen = !advOpen">
            <view class="adv-col">
              <text class="adv-t">高级工具</text>
              <text class="adv-s">发布自检 / 封面 / 多语言译制 / 结构自检 / 效果回流 / 授权清单</text>
            </view>
            <text class="adv-arrow">{{ advOpen ? '收起' : '展开' }}</text>
          </view>

          <block v-if="advOpen">
            <!-- 发布自检 + 门禁 -->
            <view class="card">
              <view class="card-head">
                <view class="card-title"><text class="card-no">检</text>发布自检</view>
                <button class="btn-mini" :disabled="!!busy || !(cur.storyboard_json)"
                        @click="readinessRun">
                  {{ busy === 'readiness' ? '自检中…' : '发布自检' }}
                </button>
                <button class="btn-mini" :disabled="!!busy || !(cur.storyboard_json)"
                        @click="gateRun">
                  {{ busy === 'gate' ? '过门禁…' : '发布门禁' }}
                </button>
              </view>
              <view class="merge-tip">脚本能改的先改；成片质检与语义验收会一起算进去｜不花钱</view>

              <view v-if="cur.readiness" class="gate-box">
                <view class="gate-head">
                  <text class="gate-title">自检</text>
                  <text class="qc-badge" :class="'v-' + readinessLevel(cur.readiness)">
                    {{ readinessLabel(cur.readiness) }}
                  </text>
                  <text class="qc-tip">
                    {{ cur.readiness.pass }} 过 / {{ cur.readiness.warn }} 提醒 /
                    {{ cur.readiness.fail }} 待改
                  </text>
                </view>
                <view v-for="i in cur.readiness.items" :key="'rd' + i.key" class="qc-dim">
                  <text class="qc-dim-name">{{ readinessName(i.key) }}</text>
                  <text class="qc-dim-score" :class="{ low: i.status === 'fail' }">
                    {{ i.status === 'pass' ? '✓' : (i.status === 'warn' ? '!' : '✗') }}
                  </text>
                  <text class="qc-dim-note">{{ i.message }}</text>
                </view>
              </view>

              <view v-if="cur.gate" class="gate-box">
                <view class="gate-head">
                  <text class="gate-title">门禁</text>
                  <text class="qc-badge" :class="'v-' + cur.gate.status">
                    {{ cur.gate.status === 'pass' ? '通过' : (cur.gate.status === 'warn' ? '有条件' : '未过') }}
                  </text>
                  <text class="qc-tip">{{ cur.gate.verdict }}</text>
                </view>
                <view v-for="g in cur.gate.items" :key="'gt' + g.id" class="gate-item">
                  <view class="qc-dim">
                    <text class="qc-dim-name">{{ gateName(g.id) }}</text>
                    <text class="qc-dim-score" :class="{ low: g.status === 'fail' }">
                      {{ g.status === 'pass' ? '✓' : (g.status === 'warn' ? '!' : '✗') }}
                    </text>
                    <text class="qc-dim-note">{{ g.message }}</text>
                  </view>
                  <view v-for="p in (g.problems || [])" :key="'gp' + g.id + p" class="gate-prob">
                    · {{ p }}
                  </view>
                </view>
              </view>
            </view>

            <!-- 封面 -->
            <view v-if="anyFilm" class="card">
              <view class="card-head">
                <view class="card-title"><text class="card-no">封</text>封面</view>
                <text v-if="cur.film && cur.film.cover" class="seg-play"
                      @click="openCover">看封面</text>
                <button class="btn-mini" :disabled="!!busy" @click="coverRun">
                  {{ busy === 'cover' ? '生成中…'
                     : (cur.film && cur.film.cover ? '重新生成' : '出封面') }}
                </button>
              </view>
              <view class="merge-tip">
                用「{{ (cur.product && cur.product.name) || '商品名' }}」当标题
                ｜ 本地抽帧，不额外花钱
              </view>
              <image v-if="cur.film && cur.film.cover" class="cover-img"
                     :src="coverUrl" mode="widthFix" @click="openCover" />
            </view>

            <!-- 多语言译制 -->
            <view class="card">
              <view class="card-head">
                <view class="card-title"><text class="card-no">译</text>多语言译制</view>
                <button class="btn-mini" @click="toggleDub">{{ dubOpen ? '收起' : '展开' }}</button>
              </view>
              <view v-if="dubOpen" class="dub-box">
                <picker :range="dubLabels" :value="dubLangIndex" @change="onDubLang">
                  <view class="tts-pick">{{ dubLabels[dubLangIndex] || '选目标语言' }}</view>
                </picker>
                <view class="tts-actions">
                  <button class="btn-mini" :disabled="dubBusy || !dubLangs.length" @click="runDub">
                    {{ dubBusy ? '译制中…' : '译制' }}
                  </button>
                  <text v-if="dubNote" class="tts-hint">{{ dubNote }}</text>
                </view>
                <view v-for="d in dubs" :key="d.lang" class="dub-row">
                  <text class="dub-name">{{ d.lang_name }} · {{ (d.summary || {}).shots || 0 }} 段</text>
                  <text class="media-more" @click.stop="applyDub(d)">应用到分镜</text>
                </view>
                <view v-if="dubCanRestore" class="tts-actions">
                  <text class="media-more" @click.stop="restoreDub">还原原文分镜</text>
                </view>
                <view class="merge-tip">
                  同一批画面只换台词与配音语言；构图 / 机位 / 画面描述原样保留。
                  译制版默认不改原分镜，点「应用到分镜」才写回（可一键还原）。
                </view>
              </view>
            </view>

            <!-- 结构自检 -->
            <view class="card">
              <view class="card-head">
                <view class="card-title"><text class="card-no">同</text>结构自检</view>
                <button class="btn-mini" @click="toggleHomogeneity">{{ hgOpen ? '收起' : '展开' }}</button>
              </view>
              <view v-if="hgOpen" class="sp-box">
                <view class="tts-actions">
                  <button class="btn-mini" :disabled="hgBusy" @click="refreshHomogeneity">
                    {{ hgBusy ? '比对中…' : '检查最近 8 条' }}
                  </button>
                  <text v-if="hg && hg.message" class="tts-hint">{{ hg.message }}</text>
                </view>
                <view v-for="(p, i) in hgPairs" :key="'hg' + i" class="pl-row">
                  <view class="pl-info">
                    <text class="pl-name">
                      {{ p.a.project_name || '未命名' }} ↔ {{ p.b.project_name || '未命名' }}
                    </text>
                    <text class="pl-meta">相似度 {{ p.score }}</text>
                  </view>
                </view>
                <view v-if="hg && hg.message && !hgPairs.length" class="merge-tip">
                  没有超过 75% 的配对。
                </view>
                <view class="merge-tip">
                  只比结构（风格 / 开场钩子 / 镜数 / 平均镜长 / 总时长），不评好坏；
                  相似度 ≥ 0.75 算同一个模板。
                </view>
              </view>
            </view>

            <!-- 效果回流 -->
            <view class="card">
              <view class="card-head">
                <view class="card-title"><text class="card-no">效</text>效果回流</view>
                <button class="btn-mini" @click="toggleFeedback">{{ fbOpen ? '收起' : '展开' }}</button>
              </view>
              <view v-if="fbOpen" class="sp-box">
                <view class="tts-actions">
                  <button class="btn-mini" :disabled="fbBusy || !(Number(fbForm.views) > 0)"
                          @click="saveMetric">
                    {{ fbBusy ? '保存中…' : '保存这条' }}
                  </button>
                  <text v-if="fbNote" class="tts-hint">{{ fbNote }}</text>
                </view>
                <view class="merge-tip">
                  发布后回填这条数据 → 学出哪种脚本风格更能卖，反哺后续剧本生成（「播放」必填）。
                </view>
                <view class="model-chips">
                  <view v-for="p in FB_PLATFORMS" :key="p.id" class="mchip"
                        :class="{ on: fbForm.platform === p.id }"
                        @click="fbForm.platform = p.id">
                    <text class="mchip-name">{{ p.label }}</text>
                  </view>
                </view>
                <view class="model-chips">
                  <view class="mchip" :class="{ on: !fbForm.hookId }" @click="fbForm.hookId = ''">
                    <text class="mchip-name">— 钩子 —</text>
                  </view>
                  <view v-for="h in FB_HOOKS" :key="h" class="mchip"
                        :class="{ on: fbForm.hookId === h }" @click="fbForm.hookId = h">
                    <text class="mchip-name">{{ h }}</text>
                  </view>
                </view>
                <view class="fb-nums">
                  <view v-for="f in FB_NUMS" :key="f.key" class="fb-num">
                    <text class="model-label">{{ f.label }}</text>
                    <input class="input line" type="number" v-model="fbForm[f.key]" placeholder="0" />
                  </view>
                </view>
                <input class="input line" v-model="fbForm.note"
                       placeholder="备注（可空）：这条投了什么、结果如何" />
                <view v-for="m in fbRows.slice(0, 5)" :key="m.id" class="pl-row">
                  <view class="pl-info">
                    <text class="pl-name">
                      {{ m.style }} · {{ m.platform || '—' }}{{ m.hookId ? ' · ' + m.hookId : '' }}
                    </text>
                    <text class="pl-meta">
                      播放 {{ m.views }} · 赞 {{ m.likes }} · 评 {{ m.comments }}
                      · 转 {{ m.shares }} · 成交 {{ m.orders }}
                    </text>
                  </view>
                </view>
                <view v-if="fbStyles.length" class="merge-tip">哪种风格更能卖（全部项目）</view>
                <view v-for="(it, i) in fbStyles" :key="'fs' + it.style" class="pl-row">
                  <view class="pl-info">
                    <text class="pl-name">{{ i === 0 ? '🏆 ' : '' }}{{ it.style }}</text>
                    <text class="pl-meta">
                      转化 {{ pct(it.conversionRate) }} · 互动 {{ pct(it.engagementRate) }}
                      · {{ it.samples }} 条样本
                    </text>
                  </view>
                </view>
                <view v-if="fbHooks.length" class="merge-tip">哪个钩子更能卖（全部项目）</view>
                <view v-for="(it, i) in fbHooks" :key="'fh' + it.hookId" class="pl-row">
                  <view class="pl-info">
                    <text class="pl-name">{{ i === 0 ? '🏆 ' : '' }}{{ it.hookId }}</text>
                    <text class="pl-meta">
                      转化 {{ pct(it.conversionRate) }} · 互动 {{ pct(it.engagementRate) }}
                      · {{ it.samples }} 条样本
                    </text>
                  </view>
                </view>
                <view class="merge-tip">
                  样本少于 2 条不评「最能卖」（避免一条爆款带偏）；反哺只写进新剧本的生成提示，
                  不改旧剧本、也不自动改配方。
                </view>
              </view>
            </view>

            <!-- 授权清单 -->
            <view class="card">
              <view class="card-head">
                <view class="card-title"><text class="card-no">授</text>授权清单</view>
                <button class="btn-mini" :disabled="!!busy" @click="loadCredits">
                  {{ credits ? '重新生成' : '生成清单' }}
                </button>
              </view>
              <view class="merge-tip">
                投流审核要的「素材来源证明」：谁拍的、什么许可、要不要署名，一次列清
              </view>
              <block v-if="credits">
                <view class="bible-row">
                  <text class="k">汇总</text>
                  共 {{ credits.summary.total }} 项 · 需署名 {{ credits.summary.needsAttribution }} ·
                  需复核 {{ credits.summary.needsReview }}
                </view>
                <view class="film-warn" v-if="!credits.summary.commercialSafe">
                  ⚠ 有 {{ credits.summary.needsReview }} 项许可不明或含 NC/ND，投流前先确认或替换
                </view>
                <view v-else class="merge-tip">✅ 没有商用受限素材</view>
                <view v-for="a in creditAttributions" :key="'ca' + a.shotId" class="mat-md">
                  {{ a.attributionLine }}
                </view>
                <button class="btn-mini" @click="copyCredits">复制 Markdown 清单</button>
              </block>
            </view>
          </block>
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
import { dramaComposeUrl, dramaVariantUrl } from '@/api/request'

/**
 * 商品短剧 · 导出 步（照竞品 app/project/[id]/export/page.tsx 的分工）
 *
 * 🩸 2026-11-07 重排：竞品这一页**先把成片摆出来**——完成横幅 → 成片播放器 →
 * 下载 / 复制链接 → 历史成片 → 发布文案 → 平台导出 → 高级工具（折叠）。
 * 我们原来是从「发布自检」开头、成片藏在别处，主操作找不到。
 * 高级工具里的自检 / 封面 / 译制 / 同质化 / 回流 / 授权清单都是原有能力，只换位置。
 */
export default {
  components: { DramaAppShell, DramaProjectHeader },
  mixins: [dramaPageBoot],
  data() {
    return { advOpen: false }
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
    /**
     * 历史成片 = 每次合成的记录（`compose.history`，后端起）+ 变体矩阵产物。
     * 老项目没有 history 时退回「当前 outputs.mp4」一条，不让页面空掉。
     */
    hisRows() {
      const c = this.cur
      if (!c || !c.id) return []
      const comp = c.compose || {}
      const out = []
      const hist = (comp.history || []).filter((h) => h && h.mp4)
      if (hist.length) {
        for (let i = 0; i < hist.length; i++) {
          const h = hist[i]
          const meta = [h.at, h.resolution, (h.seconds ? h.seconds + 's' : '')]
            .filter(Boolean).join(' · ')
          out.push({
            key: 'h' + i,
            no: i + 1,
            label: h.label || '常规合成',
            meta,
            url: dramaComposeUrl(c.id, h.mp4),
            file: h.mp4,
          })
        }
      } else if ((comp.outputs || {}).mp4) {
        out.push({
          key: 'h0',
          no: 1,
          label: '常规合成',
          meta: comp.at || '',
          url: dramaComposeUrl(c.id),
          file: comp.outputs.mp4,
        })
      }
      const vs = this.variantRows || []
      for (let i = 0; i < vs.length; i++) {
        const v = vs[i]
        if (!v.file) continue
        out.push({
          key: 'v' + i,
          no: out.length + 1,
          label: '变体 ' + (Number(v.idx) + 1) + '｜' + (v.summary || ''),
          meta: v.at || '',
          url: dramaVariantUrl(c.id, Number(v.idx) + 1),
          file: v.file,
        })
      }
      return out
    },
  },
  methods: {
    openHis(h) {
      if (!h || !h.url) return
      this.previewFile(h.url, h.file || '成片.mp4', 'video')
    },
    goVideo() {
      if (!this.cur) return
      uni.navigateTo({ url: '/pages/drama/video?id=' + this.cur.id })
    },
    /** 下载成片到相册（小程序端）；H5 走 <a download> */
    downloadVideo() {
      const url = this.compUrl
      if (!url) return
      // #ifdef H5
      const a = document.createElement('a')
      a.href = url
      a.download = '带货成片.mp4'
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
    copyVideoLink() {
      if (this.compUrl) this.copyText(this.compUrl)
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

/* 完成横幅 */
.done {
  padding: 36rpx 24rpx 30rpx;
  text-align: center;
}
.done-ico {
  display: inline-block;
  width: 88rpx;
  height: 88rpx;
  line-height: 88rpx;
  border-radius: 999rpx;
  background: #e7f8f2;
  color: #12b886;
  font-size: 44rpx;
  font-weight: 700;
}
.done-t {
  display: block;
  margin-top: 16rpx;
  font-size: 36rpx;
  font-weight: 700;
  color: #1b1f27;
}
.done-hl {
  color: #0b8f6b;
}
.done-s {
  display: block;
  margin-top: 8rpx;
  font-size: 23rpx;
  color: #9aa3af;
}

/* 成片预览 */
.prev-wrap {
  background: #000;
  border-radius: 16rpx;
  overflow: hidden;
}
.prev-video {
  width: 100%;
  height: 760rpx;
}
.prev-info {
  display: flex;
  align-items: center;
  padding: 16rpx 6rpx 4rpx;
}
.pi {
  font-size: 21rpx;
  color: #9aa3af;
}
.pi-dot {
  width: 6rpx;
  height: 6rpx;
  border-radius: 999rpx;
  background: #d5dae1;
  margin: 0 14rpx;
}

/* 主操作 */
.act {
  display: flex;
  flex-direction: column;
  gap: 14rpx;
  margin: 6rpx 0 26rpx;
}
.act-main {
  height: 92rpx;
  line-height: 92rpx;
  text-align: center;
  border-radius: 18rpx;
  background: linear-gradient(100deg, #12b886, #0b8f6b);
  color: #fff;
  font-size: 29rpx;
  font-weight: 600;
}
.act-sub {
  height: 84rpx;
  line-height: 84rpx;
  text-align: center;
  border-radius: 18rpx;
  background: #fff;
  border: 1rpx solid #e9ecf2;
  color: #4b5563;
  font-size: 25rpx;
}

/* 空态 */
.empty-card {
  background: #fff;
  border-radius: 18rpx;
  padding: 48rpx 28rpx 28rpx;
  text-align: center;
  margin-bottom: 20rpx;
}
.empty-t {
  display: block;
  font-size: 30rpx;
  font-weight: 600;
  color: #1b1f27;
}
.empty-d {
  display: block;
  margin: 12rpx 0 26rpx;
  font-size: 23rpx;
  line-height: 1.6;
  color: #9aa3af;
}

/* 历史成片 */
.his-n {
  font-size: 21rpx;
  color: #9aa3af;
}
.his-row {
  display: flex;
  align-items: center;
  gap: 14rpx;
  padding: 16rpx 0;
  border-top: 1rpx solid #f4f6f8;
}
.his-no {
  width: 48rpx;
  flex: none;
  font-size: 21rpx;
  color: #b0b7c3;
  text-align: center;
}
.his-col {
  flex: 1;
  min-width: 0;
}
.his-nm {
  display: block;
  font-size: 24rpx;
  color: #333;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.his-meta {
  display: block;
  margin-top: 4rpx;
  font-size: 19rpx;
  color: #9aa3af;
}

/* 高级工具 */
.adv {
  margin-top: 4rpx;
}
.adv-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-radius: 18rpx;
  padding: 22rpx 24rpx;
  margin-bottom: 20rpx;
}
.adv-col {
  min-width: 0;
  flex: 1;
}
.adv-t {
  display: block;
  font-size: 25rpx;
  font-weight: 600;
  color: #1b1f27;
}
.adv-s {
  display: block;
  margin-top: 4rpx;
  font-size: 20rpx;
  color: #9aa3af;
}
.adv-arrow {
  flex: none;
  font-size: 22rpx;
  color: #0b8f6b;
}

@media (min-width: 900px) {
  .act {
    flex-direction: row;
    justify-content: center;
  }
  .act-main {
    padding: 0 60rpx;
  }
  .act-sub {
    padding: 0 40rpx;
  }
}
</style>
