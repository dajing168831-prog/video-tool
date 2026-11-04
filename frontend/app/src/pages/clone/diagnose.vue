<template>
  <view class="page">
    <!-- 分析中 -->
    <view v-if="busy" class="block">
      <view class="pulse">正在拆解原片结构</view>
      <view class="bar"><view class="bar-in" :style="{ width: (d.pct || 0) + '%' }" /></view>
      <view class="stage">{{ stageText }}</view>
      <view class="hint">一条 60 秒的片子通常 10 秒内拆完</view>
    </view>

    <!-- 失败 -->
    <view v-else-if="d.state === 'failed'" class="block">
      <view class="bad">拆解失败</view>
      <view class="err">{{ d.error || '未知错误' }}</view>
      <button class="btn-primary" @click="restart">重新拆解</button>
    </view>

    <!-- 结构卡 -->
    <block v-else-if="d.state === 'analyzed'">
      <view class="hero-card">
        <image class="cover" :src="coverUrl" mode="aspectFill" @error="coverFail = true" v-if="hasCover && !coverFail" />
        <view class="hero-info">
          <view class="title">{{ d.meta.title || '参考片' }}</view>
          <view class="author">{{ d.meta.author || d.meta.platform }}</view>
          <view class="badge" v-if="d.meta.truncated">已截取前段分析</view>
        </view>
      </view>

      <view class="grid">
        <view class="cell">
          <view class="cell-v">{{ fmt(d.summary.duration) }}</view>
          <view class="cell-k">时长</view>
        </view>
        <view class="cell">
          <view class="cell-v">{{ d.summary.ratio || '—' }}</view>
          <view class="cell-k">画幅</view>
        </view>
        <view class="cell">
          <view class="cell-v">{{ d.summary.shot_count }}</view>
          <view class="cell-k">镜头数</view>
        </view>
        <view class="cell">
          <view class="cell-v">{{ d.summary.rhythm.cuts_per_10s }}</view>
          <view class="cell-k">每10秒切</view>
        </view>
      </view>

      <view class="card">
        <view class="card-title">节奏</view>
        <view class="line">平均每镜 <text class="em">{{ d.summary.rhythm.avg_shot }}</text> 秒，
          每 10 秒切 <text class="em">{{ d.summary.rhythm.cuts_per_10s }}</text> 次</view>
        <view class="line" v-if="d.summary.hook && d.summary.hook.text">
          开头 {{ d.summary.hook.at }}s 的钩子：<text class="em">{{ d.summary.hook.text }}</text>
        </view>
        <view class="line dim" v-else>这条片子前 3 秒没有识别到语音钩子，靠画面抓人</view>
      </view>

      <view class="card" v-if="keyframes.length">
        <view class="card-title">镜头样本（前 {{ keyframes.length }} 镜）</view>
        <scroll-view class="strip" scroll-x>
          <image
            v-for="k in keyframes"
            :key="k.i"
            class="kf"
            :src="k.url"
            mode="aspectFill"
          />
        </scroll-view>
      </view>

      <view class="card">
        <view class="card-title">全片联系表</view>
        <view class="line dim">每格左上角是原片时间；一屏看完节奏和画面变化。</view>
        <image
          v-if="sheetOn"
          class="sheet"
          :src="sheetUrl"
          mode="widthFix"
          @load="onSheetLoad"
          @error="onSheetError"
        />
        <button class="sheet-btn" size="mini" :loading="sheetLoading" @click="loadSheet(true)">
          {{ sheetOn ? '重新生成' : '生成联系表' }}
        </button>
      </view>

      <!-- 从成片页点「改这段」进来时，只处理那一段，其余镜头一个像素都不动 -->
      <view class="card only" v-if="onlySpan">
        <view class="card-title">只改这一段</view>
        <view class="line dim">{{ onlyInfo }}</view>
        <view class="line dim">
          只把和这一段重叠的镜头送去重画；模型有最短时长，实际重出的时间段以下面清单为准。
        </view>
        <button class="sheet-btn" size="mini" @click="clearOnly">取消限定，改整条</button>
      </view>

      <view class="card">
        <view class="card-title">新文案</view>
        <view class="orig" v-if="d.speech_text">
          <view class="orig-k">原片文案</view>
          <view class="orig-v">{{ d.speech_text }}</view>
        </view>
        <!-- 逐句台词：原片每一句话一行，左边是说话人。
             改哪一行的输入框，改的就是那个人说的那句话。 -->
        <!-- 只重配其中几个人：勾中谁就只换谁的声音，其他人保留原片原声 -->
        <view class="dub-box"
              v-if="spkAligned && edit.audio !== 'original' && spkGroups.length > 1">
          <view class="dub-title">重新配音给谁配</view>
          <view class="chip-row">
            <view
              v-for="g in spkGroups"
              :key="g.key"
              class="chip"
              :class="{ on: dubPick.indexOf(g.key) >= 0 }"
              @click="toggleDub(g.key)"
            >{{ g.label }} · {{ g.lines.length }} 句</view>
          </view>
          <view class="dub-note" v-if="dubLines">
            只重配勾选的人，其他人保留原片原声；没勾的那几句不进提示词。
          </view>
          <!-- 每个人各用一个音色：不选就跟随上面那个整片音色 -->
          <view class="dv-row" v-if="voices.length">
            <view class="dv-item" v-for="g in spkGroups" :key="'v' + g.key">
              <text class="dv-k">{{ g.label }}</text>
              <picker
                mode="selector"
                :range="voiceLabels"
                :value="groupVoiceIndex(g.key)"
                @change="onGroupVoice(g.key, $event)"
              >
                <view class="dv-v">{{ groupVoiceName(g.key) }} ›</view>
              </picker>
            </view>
          </view>
        </view>
        <view class="spk-list" v-if="spkAligned && edit.audio !== 'original'">
          <view class="spk-note" v-if="spkBlind">
            原片没分出说话人（可能只有一个人、或者两人一直在同一画面里），
            只能整片一起重配。
          </view>
          <view class="spk-row" v-for="(r, i) in speechRows" :key="i">
            <view class="spk-tag" :class="'spk-c' + (spkColor(r) % 4)">
              {{ spkLabel(r) }}
            </view>
            <textarea
              v-model="r.text"
              class="input spk-input"
              auto-height
              maxlength="500"
              :show-confirm-bar="false"
              @input="onRowEdit"
            />
          </view>
        </view>
        <textarea
          v-else
          v-model="script"
          class="input"
          :placeholder="edit.audio === 'original'
            ? '保留原声时不用填。这条片子不重新配音，文案不参与出片。'
            : '写你要讲的内容，按句号断句。系统会按原片的镜头节奏把每句话安到对应位置。'"
          maxlength="2000"
          auto-height
          :show-confirm-bar="false"
        />
        <view class="counter">{{ script.length }} / 2000</view>
        <view class="sec-note" v-if="edit.audio === 'original'">
          声音用原片，不调配音；文案填了也不会用到。
        </view>

        <!-- C6 多语种配音：只换音色的效果是「外语腔念中文」——
             台词内容本身得是目标语言，所以这里做逐句翻译，行数一一对应。 -->
        <view class="sub-row" v-if="edit.audio !== 'original'">
          <view class="sub-txt">
            <view class="sub-k">{{ trK }}</view>
            <view class="sub-v">{{ trHint }}</view>
          </view>
          <button
            class="sub-btn"
            size="mini"
            :loading="trBusy"
            :disabled="trBusy || !script.trim() || trCode === 'zh'"
            @click="doTranslate"
          >{{ trLang && trLang === trCode ? '重译' : '翻译文案' }}</button>
        </view>
        <view class="switch-row" @click="maskBottom = !maskBottom">
          <text class="switch-label">遮住原片底部字幕</text>
          <switch :checked="maskBottom" color="#ff5a3c" @change="onMaskChange" />
        </view>

        <!-- 声音：和画面独立。只改文案也能保留原片 BGM -->
        <view class="sec">
          <view class="sec-head">
            <text class="sec-title">声音</text>
            <text class="sec-note">{{ audioHint }}</text>
          </view>
          <view class="chip-row">
            <view
              v-for="a in audios"
              :key="a.v"
              class="chip"
              :class="{ on: edit.audio === a.v }"
              @click="onAudioPick(a.v)"
            >{{ a.t }}</view>
          </view>

          <!-- 原片声音怎么处理（C4）：只影响成片混音 —— 不改画面、不进提示词。
               tts 模式原片声音整条不要，所以「保留原片」那档不出现。 -->
          <view class="chip-row">
            <view
              v-for="b in bgmOpts"
              :key="b.v"
              class="chip"
              :class="{ on: edit.bgm === b.v }"
              @click="onBgmPick(b.v)"
            >{{ b.t }}</view>
          </view>
          <view class="sec-note">{{ bgmHint }}</view>
          <view v-if="edit.bgm === 'replace'" class="sub-row">
            <view class="sub-txt">
              <view class="sub-k">背景音乐文件{{ hasBgmFile ? '（已上传）' : '（还没传）' }}</view>
              <view class="sub-v">会循环或裁到成片时长，垫在新配音下面</view>
            </view>
            <button
              class="sub-btn"
              size="mini"
              :loading="slotLoading === 'bgm'"
              :disabled="!!slotLoading"
              @click="pickAudio('bgm')"
            >{{ hasBgmFile ? '换一首' : '上传' }}</button>
            <button
              v-if="hasBgmFile"
              class="sub-btn"
              size="mini"
              :disabled="!!slotLoading"
              @click="clearAudio('bgm')"
            >删除</button>
          </view>

          <view class="chip-row">
            <view
              v-for="s in sfxOpts"
              :key="s.v"
              class="chip"
              :class="{ on: edit.sfx === s.v }"
              @click="onSfxPick(s.v)"
            >{{ s.t }}</view>
          </view>
          <view v-if="edit.sfx === 'add'" class="sub-row">
            <view class="sub-txt">
              <view class="sub-k">音效文件{{ hasSfxFile ? '（已上传）' : '（还没传）' }}</view>
              <view class="sub-v">按上传长度叠加进成片，不循环</view>
            </view>
            <button
              class="sub-btn"
              size="mini"
              :loading="slotLoading === 'sfx'"
              :disabled="!!slotLoading"
              @click="pickAudio('sfx')"
            >{{ hasSfxFile ? '换一段' : '上传' }}</button>
            <button
              v-if="hasSfxFile"
              class="sub-btn"
              size="mini"
              :disabled="!!slotLoading"
              @click="clearAudio('sfx')"
            >删除</button>
          </view>

          <!-- 说话人：官方口径 —— 说话的人按顺序拿稳定的 (S1)(S2) 号，
               不说话的人不给号；口型只跟着这条配音走。只有 H3 提示词里用得上。 -->
          <view v-if="edit.audio !== 'original' && effChannel === 'minimax'" class="inv-box">
            <view class="inv-head">
              <text class="inv-title">谁在说话</text>
              <text class="inv-note">
                {{ edit.speaker_ids.length ? '指定了 ' + edit.speaker_ids.length + ' 位' : '不选 = 画面主体自己说' }}
              </text>
              <text class="inv-refresh" @click.stop="loadInventory()">
                {{ invLoading ? '' : (inv.ready ? '重新识别' : '识别') }}
              </text>
            </view>
            <view v-if="invPeople.length" class="chip-row">
              <view
                v-for="p in invPeople"
                :key="p.id"
                class="chip"
                :class="{ on: edit.speaker_ids.indexOf(p.id) >= 0 }"
                @click="pickSpeaker(p.id)"
              >{{ p.desc_zh }}</view>
            </view>
            <view v-else class="inv-empty">先识别一遍原片，再指定是哪一位在说话</view>
            <view class="sec-note">多人对话可多选；不说话的配角不会被分到说话人号。</view>
          </view>

        </view>

        <!-- 配音音色：语言决定默认音色，也能自己挑。
             音色 ID 全部来自火山官方 2.0 音色表，不是我们自己编的 -->
        <view class="sec" v-if="edit.audio !== 'original' && voices.length">
          <view class="sec-head">
            <text class="sec-title">配音音色</text>
            <text class="sec-note">{{ langAutoText }}</text>
          </view>
          <view class="chip-row">
            <view
              v-for="l in langs"
              :key="l.v"
              class="chip"
              :class="{ on: langPick === l.v }"
              @click="onLangPick(l.v)"
            >{{ l.t }}</view>
            <!-- 小语种收在第二层：常用的一键可选，其余点开再挑 -->
            <view
              class="chip"
              :class="{ on: langMore || isMoreLang }"
              @click="langMore = !langMore"
            >{{ isMoreLang ? langName(langPick) + ' ▾' : '更多 ›' }}</view>
          </view>
          <view class="chip-row" v-if="langMore || isMoreLang">
            <view
              v-for="l in moreLangs"
              :key="l.v"
              class="chip"
              :class="{ on: langPick === l.v }"
              @click="onLangPick(l.v)"
            >{{ l.t }}</view>
          </view>
          <!-- 音色分类：先收窄再选，不然中文 90 个一个下拉翻到底 -->
          <view class="chip-row" v-if="voiceCats.length > 2">
            <view
              v-for="c in voiceCats"
              :key="'c' + c.k"
              class="chip"
              :class="{ on: voiceCat === c.k }"
              @click="onVoiceCat(c.k)"
            >{{ c.t }} {{ c.n }}</view>
          </view>
          <!-- 方言 = 一级筛子：顾客想听粤语，直接点「粤语」，下面的音色自己收窄到会说粤语的，
               不用先知道哪个音色会说。官方约束：用 explicit_dialect 时 speaker 必须是
               支持该方言的音色，所以点方言时音色会一起落到会说的人上。 -->
          <view class="chip-row" v-if="dialectOptions.length">
            <view
              v-for="t in dialectOptions"
              :key="'d' + t"
              class="chip"
              :class="{ on: dialect === dialectCode[t] }"
              @click="onVoiceDialect(t)"
            >{{ t }}</view>
          </view>
          <view class="sec-note" v-if="dialectOptions.length">
            {{ dialect === '' ? '方言：不选就是标准普通话；想要地方口音点一个，音色自动只留会说的'
              : `方言：${dialectName(dialect)}。下面只列会说${dialectName(dialect)}的音色，不选方言就回到标准普通话` }}
          </view>
          <picker
            mode="selector"
            :range="voiceLabels"
            :value="voiceIndex"
            @change="onVoicePick"
          >
            <view class="pick-row">
              <text class="pick-label">音色</text>
              <text class="pick-value">{{ voiceLabel }} ›</text>
            </view>
          </picker>
          <view class="sec-note">{{ voiceHint }}</view>

          <!-- 试听：真调 TTS、按字符计费 —— 音色 demo 全站缓存，文案试听按
               「文案+音色+语速」缓存，所以同一条听第二遍不花钱。
               实测秒数比估算靠谱：语速调没调对，听一遍就知道 -->
          <view class="sub-row">
            <view class="sub-txt">
              <view class="sub-k">试听</view>
              <view class="sub-v">{{ rateText }}</view>
            </view>
            <button
              class="sub-btn"
              size="mini"
              :loading="vdBusy"
              :disabled="vdBusy || pvBusy"
              @click="playVoiceDemo"
            >听音色</button>
            <button
              class="sub-btn"
              size="mini"
              :loading="pvBusy"
              :disabled="vdBusy || pvBusy || !script.trim()"
              @click="playVoicePreview"
            >听文案</button>
          </view>
          <view class="rate-row">
            <text class="rate-label">语速</text>
            <slider
              class="rate-slider"
              :min="-30"
              :max="30"
              :step="5"
              :value="rateOn ? rateVal : 0"
              activeColor="#ff5a3c"
              @change="onRate"
            />
            <view class="chip" :class="{ on: !rateOn }" @click="resetRate">自动</view>
          </view>
          <view class="sec-note" v-if="pvText">{{ pvText }}</view>
          <view v-if="playUrl">
            <view class="sec-note">正在试听：{{ playWhat }}</view>
            <audio :src="playUrl" controls />
          </view>

          <!-- 声音复刻：用一段人声训练自己的音色（音色槽位在控制台开通） -->
          <view class="variant-row">
            <view class="chip" :class="{ on: vcOn }" @click="vcOn = !vcOn">
              {{ vcOn ? '声音复刻：开' : '复刻自己的音色' }}
            </view>
          </view>
          <block v-if="vcOn">
            <input
              v-model="vcSpeaker"
              class="asset-input"
              placeholder="音色槽位 ID（S_ 开头，控制台「声音复刻」里创建）"
              :adjust-position="false"
            />
            <view class="variant-row">
              <button class="sub-btn" size="mini" :loading="vcUploading" @click="pickVoiceAudio">
                选一段人声
              </button>
              <text class="sec-note" v-if="vcStatus">{{ vcStatus }}</text>
            </view>
            <view class="sec-note">
              10–30 秒干净人声；每次训练消耗一次复刻额度（官方：每个资源最多 15 次）。
            </view>
            <audio v-if="vcDemo" :src="vcDemo" controls />
          </block>
        </view>

        <!-- 配音时长：出片前先告诉你够不够，别等配完了才发现对不上 -->
        <view class="sec" v-if="edit.audio !== 'original' && est && script.trim()">
          <view class="sec-head">
            <text class="sec-title">配音时长</text>
            <text class="sec-note">估算 {{ fmt(est.est_seconds) }} / 原片 {{ fmt(est.target_seconds) }}</text>
          </view>
          <view class="est-bar">
            <view class="est-fill" :class="est.verdict" :style="{ width: estPct + '%' }" />
            <view class="est-mark" />
          </view>
          <view class="sec-note">{{ estAdvice }}</view>
          <view
            class="switch-row tight"
            v-if="est.verdict !== 'ok'"
            @click="allowStretch = !allowStretch"
          >
            <text class="switch-label">仍然出片（结尾会补静音或冻帧）</text>
            <switch :checked="allowStretch" color="#ff5a3c" @change="onStretchChange" />
          </view>
        </view>

        <!-- 读音校正：识别原文不动，只换送 TTS 那一份的念法 -->
        <view class="sec" v-if="edit.audio !== 'original' && pronCandidates.length">
          <view class="sec-head">
            <text class="sec-title">读音校正</text>
            <text class="sec-note">左边原样显示，右边是配音念的</text>
          </view>
          <view v-for="w in pronCandidates" :key="w" class="pron-row">
            <text class="pron-k">{{ w }}</text>
            <input
              class="pron-v"
              :value="pronounce[w] || ''"
              :placeholder="`${w} 怎么念（不填就按原样）`"
              @input="onPronInput(w, $event)"
            />
          </view>
        </view>

        <view class="regen">
          <view class="regen-head">
            <text class="regen-title">换画面</text>
            <text class="regen-note">{{ modeHint }}</text>
          </view>

          <!-- 档位不再让用户选：换不换由「换什么」决定，怎么换由系统逐镜分诊。
               这里只留"改哪儿"——整条都改，还是只动开头。 -->
          <view class="mode-row" :class="{ muted: !wantRegen }">
            <view class="mode" :class="{ on: !openingOn && wantRegen }" @click="pickScope(false)">改整条</view>
            <view class="mode" :class="{ on: openingOn && wantRegen }" @click="pickScope(true)">只换开头</view>
          </view>
          <!-- 点完必须看得出"变了什么"：只说结论（动几个镜头、留几个），不讲机制 -->
          <view class="scope-line" v-if="scopeLine">{{ scopeLine }}</view>

          <!-- 🩸 别用裸 <block> 包一片内容：H5 里它会被编译成真的 <template> 元素，
               Vue 把子节点塞进 template.content，页面上一个字都不显示（没有 v-if 就不会降级成 Fragment）。
               换什么 / 风格 / 补充说明 / 通道型号 曾经整块因此消失过。 -->
            <!-- 换开头：只重制开头几秒，后面一个像素都不动 —— 广告换钩子重跑用 -->
            <view class="sec" v-if="openingOn">
              <view class="sec-head">
                <text class="sec-title">开头多长</text>
                <text class="sec-note">{{ openingInfo }}</text>
              </view>
              <view class="chip-row">
                <view
                  v-for="o in openingOpts"
                  :key="o.v"
                  class="chip"
                  :class="{ on: openingSec === o.v }"
                  @click="openingSec = o.v"
                >{{ o.t }}</view>
              </view>
              <view class="sec-note">
                只重制这几秒，后面的画面、动作、节奏全部保留原片。
                换钩子重跑用这个：主体不动，只换开场。
              </view>

              <!-- 多版本：同一个开头按几个方向各出一版，方便挑（方向由用户自己写） -->
              <view class="variant-row">
                <view class="chip" :class="{ on: multiOn }" @click="multiOn = !multiOn">
                  {{ multiOn ? '一次出多版：开' : '一次出多版：关' }}
                </view>
                <text class="sec-note" v-if="multiOn">每填一个方向出一版，按顺序跑；中间失败就停。</text>
              </view>
              <block v-if="multiOn">
                <input
                  v-for="(v, i) in variantDirs"
                  :key="i"
                  v-model="variantDirs[i]"
                  class="field"
                  :placeholder="`第 ${i + 1} 版开头怎么改（自己写）`"
                  :adjust-position="false"
                />
              </block>
            </view>

            <!-- 处理哪些镜头：不勾的原样保留，这是最直接的成本与保真控制 -->
            <view class="sec" v-if="!openingOn && shotPicker.length">
              <view class="sec-head">
                <text class="sec-title">处理哪些镜头</text>
                <text class="sec-note">{{ excludedShots.length ? `已排除 ${excludedShots.length} 镜` : '默认全部参与' }}</text>
              </view>
              <scroll-view class="pick-strip" scroll-x>
                <view
                  v-for="s in shotPicker"
                  :key="s.i"
                  class="pick"
                  :class="{ off: !s.picked }"
                  @click="toggleShot(s.i)"
                >
                  <image v-if="s.url" class="pick-img" :src="s.url" mode="aspectFill" />
                  <view v-else class="pick-img pick-noimg">{{ s.i + 1 }}</view>
                </view>
              </scroll-view>
              <view class="sec-note">
                没勾的镜头直接保留原片；勾了的镜头把原片整段交给模型重制。
              </view>
            </view>

            <!-- 换什么 -->
            <view class="sec">
              <view class="sec-head">
                <text class="sec-title">换什么</text>
                <text class="sec-note">勾了才换，没勾的保持原样</text>
              </view>

              <view v-for="s in slots" :key="s.k" class="slot">
                <view class="slot-head" @click="toggleSlot(s.k)">
                  <view class="chk" :class="{ on: edit[s.k] }" />
                  <text class="slot-name">{{ s.t }}</text>
                  <text class="slot-sub">{{ s.sub }}</text>
                </view>

                <view v-if="edit[s.k]" class="slot-body">
                  <view v-if="s.img && !(s.k === 'wardrobe' && wardrobeRows.length)" class="sub-row">
                    <image
                      v-if="hasRefImg(s.k)"
                      class="sub-img"
                      :src="slotImg(s.k)"
                      mode="aspectFill"
                    />
                    <view class="sub-txt">
                      <view class="sub-k">{{ slotTitle(s.k, s.t) }}</view>
                      <view class="sub-v">{{ s.imgHint }}</view>
                    </view>
                    <button
                      class="sub-btn"
                      size="mini"
                      :loading="slotLoading === s.k"
                      :disabled="slotLoading === s.k"
                      @click="chooseRef(s.k, s.t)"
                    >{{ hasRefImg(s.k) ? '换一张' : '上传' }}</button>
                  </view>

                  <!-- 换装没选具体的人（= 画面里全体一起换）时，同样可以只写一句话 -->
                  <view v-if="s.k === 'wardrobe' && !wardrobeRows.length" class="wd-row">
                    <input
                      class="wd-input"
                      :value="edit.wardrobe_desc || ''"
                      :maxlength="40"
                      placeholder="没图就写清换成什么，如「米色风衣」「红色连衣裙」"
                      @input="onWardrobeDesc('', $event)"
                    />
                  </view>

                  <!-- 多人换人：第 2、3 个人各自一张图（一人一槽，图号按顺序排） -->
                  <view v-if="s.k === 'person' && extraPeople.length">
                    <view v-for="pp in extraPeople" :key="pp.slot" class="sub-row">
                      <image
                        v-if="hasRefImg(pp.slot)"
                        class="sub-img"
                        :src="slotImg(pp.slot)"
                        mode="aspectFill"
                      />
                      <view class="sub-txt">
                        <view class="sub-k">{{ pp.label }}的参考图{{ hasRefImg(pp.slot) ? '（已上传）' : '（没图就不换这个人）' }}</view>
                        <view class="sub-v">这一个人在画面里出现时，换成他这张脸</view>
                        <view v-if="!pp.bound" class="sub-v">
                          分析完在「画面里有谁」里点选，按你点选的顺序排图号
                        </view>
                        <view v-if="hasRefImg(pp.slot) && !pp.bound" class="sub-v warn">
                          这张图还没有对应的人，出片时不会用到
                        </view>
                      </view>
                      <button
                        class="sub-btn"
                        size="mini"
                        :loading="slotLoading === pp.slot"
                        :disabled="slotLoading === pp.slot"
                        @click="chooseRef(pp.slot, pp.label)"
                      >{{ hasRefImg(pp.slot) ? '换一张' : '上传' }}</button>
                    </view>
                  </view>

                  <input
                    v-if="s.k === 'person'"
                    v-model="subjectAsset"
                    class="asset-input"
                    placeholder="或填火山资产 ID（虚拟人像库 / 已授权真人素材）"
                    :adjust-position="false"
                  />

                  <!-- 火山官方限制：不收直接上传的真人脸。别等提交了再被 400 打回来 -->
                  <view v-if="s.k === 'person' && volcRealFaceWarn" class="asset-hint warn">
                    火山通道不收真人照片（官方限制）。换真人请选「MiniMax」，或把照片走火山授权入库后填上面的素材 ID。
                  </view>

                  <!-- 有 ph 才有描述框：人物那项故意不给（长相只认参考图） -->
                  <input
                    v-if="s.ph"
                    v-model="edit[s.k + '_desc']"
                    class="field"
                    :placeholder="s.ph"
                    :adjust-position="false"
                  />

                  <!-- 换画面里的哪一件：一句话「把产品换掉」在有多件东西的画面里
                       没有唯一解，得点名是哪一件（盘点给的外观当定位词）。 -->
                  <view v-if="s.k === 'product'" class="inv-box">
                    <view class="inv-head">
                      <text class="inv-title">换画面里的哪一件</text>
                      <text v-if="invLoading" class="inv-note">识别中…</text>
                      <text v-else-if="inv.ready" class="inv-note">
                        {{ edit.product_target || '不选 = 画面里那件产品' }}
                      </text>
                      <text v-else class="inv-note">{{ invReason || '还没识别' }}</text>
                      <text class="inv-refresh" @click.stop="loadInventory(true)">
                        {{ invLoading ? '' : (inv.ready ? '重新识别' : '识别') }}
                      </text>
                    </view>
                    <view v-if="inv.products && inv.products.length" class="chip-row">
                      <view
                        v-for="(o, i) in inv.products"
                        :key="i"
                        class="chip"
                        :class="{ on: edit.product_target === o.desc_zh }"
                        @click="pickProduct(o)"
                      >{{ o.desc_zh }}</view>
                    </view>
                    <view v-else class="inv-empty">没识别到具体物品，按你写的描述换</view>
                  </view>

                  <!-- 换装按人：只换某几个人的衣服时，逐人各传一张服装图。
                       不选人 = 老语义（画面里全体一起换）。 -->
                  <view v-if="s.k === 'wardrobe'" class="inv-box">
                    <view class="inv-head">
                      <text class="inv-title">换谁的服装</text>
                      <text v-if="invLoading" class="inv-note">识别中…</text>
                      <text v-else-if="inv.ready" class="inv-note">
                        {{ wardrobeRows.length ? '换 ' + wardrobeRows.length + ' 个人' : '不选 = 画面里全体一起换' }}
                      </text>
                      <text v-else class="inv-note">{{ invReason || '还没识别' }}</text>
                      <text class="inv-refresh" @click.stop="loadInventory(true)">
                        {{ invLoading ? '' : (inv.ready ? '重新识别' : '识别') }}
                      </text>
                    </view>
                    <view v-if="invPeople.length" class="chip-row">
                      <view
                        v-for="p in invPeople"
                        :key="p.id"
                        class="person-chip"
                        :class="{ on: edit.wardrobe_ids.indexOf(p.id) >= 0 }"
                        @click="pickWardrobe(p.id)"
                      >
                        <view class="pc-name">{{ p.desc_zh }}</view>
                        <view class="pc-time">{{ fmtSpan(p.appearances) }}</view>
                      </view>
                    </view>
                    <view v-else class="inv-empty">点「识别」先看清原片里有谁，再选换谁的服装</view>
                    <view v-for="w in wardrobeRows" :key="w.slot" class="wd-block">
                      <view class="sub-row">
                        <image
                          v-if="hasRefImg(w.slot)"
                          class="sub-img"
                          :src="slotImg(w.slot)"
                          mode="aspectFill"
                        />
                        <view class="sub-txt">
                          <view class="sub-k">{{ w.label }}的服装{{ hasRefImg(w.slot) ? '（已上传）' : '（也可以只写文字）' }}</view>
                          <view class="sub-v">只换这个人的衣服，脸和发型不动</view>
                        </view>
                        <button
                          class="sub-btn"
                          size="mini"
                          :loading="slotLoading === w.slot"
                          :disabled="slotLoading === w.slot"
                          @click="chooseRef(w.slot, w.label + '的服装')"
                        >{{ hasRefImg(w.slot) ? '换一张' : '上传' }}</button>
                      </view>
                      <!-- 🩸 2026-10-27：没有服装图时，用户可以**只写一句话**说换成什么
                           （官方 `guide:39`「将其中的<原特征>修改为<新特征>」的 `<新特征>`
                           本来就允许是文字）。文案以前写了这条路，但界面上没有输入框
                           —— 用户照着文案找填的地方找不到，硬提交又被拦下。 -->
                      <view class="wd-row">
                        <input
                          class="wd-input"
                          :value="edit.wardrobe_desc_by_id[w.id] || ''"
                          :maxlength="40"
                          placeholder="没图就写清换成什么，如「米色风衣」「红色连衣裙」"
                          @input="onWardrobeDesc(w.id, $event)"
                        />
                      </view>
                    </view>
                  </view>

                  <!-- 视觉盘点：原片里有谁、各在第几秒。多人画面里"换人"必须落到具体某一个 -->
                  <view v-if="s.k === 'person'" class="inv-box">
                    <view class="inv-head">
                      <text class="inv-title">画面里有谁</text>
                      <text v-if="invLoading" class="inv-note">识别中…</text>
                      <text v-else-if="inv.ready" class="inv-note">{{ invPickable.length }} 个人</text>
                      <text v-else class="inv-note">{{ invReason || '还没识别' }}</text>
                      <text class="inv-refresh" @click.stop="loadInventory(true)">
                        {{ invLoading ? '' : (inv.ready ? '重新识别' : '识别') }}
                      </text>
                    </view>
                    <view v-if="inv.ready && invPickable.length" class="chip-row">
                      <view
                        v-for="p in invPickable"
                        :key="p.id"
                        class="person-chip"
                        :class="{ on: pickedIds.indexOf(p.id) >= 0 }"
                        @click="pickPerson(p)"
                      >
                        <view class="pc-name">{{ p.desc_zh }}</view>
                        <view class="pc-time">{{ fmtSpan(p.appearances) }}<text v-if="p.main"> · 主角</text></view>
                      </view>
                    </view>
                    <view v-if="inv.ready && invPickable.length" class="pick-note">
                      <text>可多选：点一个换一个，再点取消。当前{{ pickedIds.length ? '换 ' + pickedIds.length + ' 个人' : '按主角换' }}（{{ subjectLimit.label }}：{{ subjectLimit.stable }} 人内最稳，最多 {{ subjectLimit.max }} 人）</text>
                      <text v-if="pickedIds.length" class="inv-clear" @click="clearPicked">清空</text>
                    </view>
                    <view v-else-if="inv.ready" class="inv-empty">没识别到人物，按你写的描述换</view>
                    <view v-else class="inv-empty">点选要换的人；不选默认换主角。识别一次约一分钱，结果会缓存</view>
                  </view>
                </view>
              </view>

              <!-- 整体风格 -->
              <view class="chip-row style-row">
                <view
                  v-for="st in styles"
                  :key="st.v"
                  class="chip"
                  :class="{ on: edit.style === st.v }"
                  @click="edit.style = st.v"
                >{{ st.t }}</view>
              </view>

              <!-- 风格参考（A9）：图 / 视频二选一。上面那排风格词是"方向"，
                   参考素材是"观感"，两者叠加；传了参考素材就以素材为准 -->
              <view class="sub-row">
                <image
                  v-if="hasRefImg('style_ref')"
                  class="sub-img"
                  :src="slotImg('style_ref')"
                  mode="aspectFill"
                />
                <view class="sub-txt">
                  <view class="sub-k">
                    风格参考图{{ hasRefImg('style_ref') ? '（已上传）' : '（可选）' }}
                  </view>
                  <view class="sub-v">
                    按这张图的色调、光影和质感重新上色，不取图里的主体和构图。
                    和上面的风格词叠加，参考图定观感
                  </view>
                </view>
                <button
                  class="sub-btn"
                  size="mini"
                  :loading="slotLoading === 'style_ref'"
                  :disabled="!!slotLoading"
                  @click="chooseRef('style_ref', '风格参考')"
                >{{ hasRefImg('style_ref') ? '换一张' : '上传' }}</button>
              </view>

              <view class="sub-row">
                <view class="sub-txt">
                  <view class="sub-k">
                    风格参考视频{{ hasStyleVideo ? '（已上传）' : '（可选）' }}
                  </view>
                  <view class="sub-v">{{ styleVideoHint }}</view>
                </view>
                <button
                  class="sub-btn"
                  size="mini"
                  :loading="slotLoading === 'style_video'"
                  :disabled="!!slotLoading"
                  @click="pickStyleVideo"
                >{{ hasStyleVideo ? '换一段' : '上传' }}</button>
                <button
                  v-if="hasStyleVideo"
                  class="sub-btn"
                  size="mini"
                  :disabled="!!slotLoading"
                  @click="clearStyleVideo"
                >删除</button>
              </view>


            </view>

            <!-- 「保什么」收进内部：六个开关默认全保，用户不需要回答"动作要不要留"
                 —— 没被勾选要改的东西，本来就不该动。要改就勾「换什么」。 -->

            <!-- 补充说明 -->
            <view class="sec">
              <view class="sec-head">
                <text class="sec-title">补充说明</text>
                <text class="sec-note">可选，原样拼进提示词</text>
              </view>
              <textarea
                v-model="edit.extra"
                class="regen-input"
                placeholder="例：画面整体更亮一点，人物表情更放松"
                maxlength="200"
                auto-height
                :show-confirm-bar="false"
              />
              <!-- 「一次只改一类」（2026-11-03）：默认关，用户自己开。
                   出处：官方《Doubao Seedance 2.5 提示词指南》「复杂任务效果不稳定」——
                   「一次生成同时承担多项参考、编辑要求时，整体效果不稳定。将复杂任务
                   拆解为多个简单任务，分多次生成或编辑完成」。 -->
              <view class="switch-row tight">
                <text class="switch-label">一次只改一类（同时勾 2 类以上会被拦）</text>
                <switch
                  :checked="edit.one_change"
                  color="#ff5a3c"
                  @change="onOneChange"
                />
              </view>
            </view>

            <!-- 成片规格：edit 任务锁死了画幅和时长，这里只展示 -->
            <view class="spec-line">
              分辨率 {{ resLabel }} · 画幅 跟原片 · 时长 跟原片
            </view>

            <view class="adv-toggle" @click="adv = !adv">
              {{ adv ? '收起通道 / 型号 / 清晰度' : '通道 / 型号 / 清晰度（选模型）' }}
            </view>
            <view v-if="adv" class="adv">
              <view v-if="!wantRegen" class="chan-hint">
                现在不动画面，这里选什么都不会生效 —— 先在「换什么」里勾一项。
              </view>
              <view class="adv-label">通道</view>
              <view v-if="openingOn" class="chan-hint">
                换开头是逐镜「抽帧→重画→图生视频」，走图生视频链路，
                通道/型号/清晰度都不适用
              </view>
              <view v-else class="chip-row">
                <view
                  v-for="c in channels"
                  :key="c.v"
                  class="chan"
                  :class="{ on: regenChannel === c.v }"
                  @click="pickChannel(c.v)"
                >{{ c.t }}</view>
              </view>

              <view v-if="!openingOn" class="adv-label">型号</view>
              <view v-if="!openingOn" class="chip-row">
                <view
                  v-for="m in modelOpts"
                  :key="m.id || 'auto'"
                  class="chan"
                  :class="{ on: regenModel === m.id }"
                  @click="pickModel(m)"
                >{{ m.label }}</view>
              </view>
              <view v-if="!openingOn" class="chan-hint">
                {{ modelHint }}
              </view>

              <view v-if="!openingOn" class="adv-label">清晰度</view>
              <view v-if="!openingOn" class="chip-row">
                <view
                  v-for="r in resolOpts"
                  :key="r.v"
                  class="chip"
                  :class="{ on: edit.resolution === r.v }"
                  @click="edit.resolution = r.v"
                >{{ r.t }}</view>
              </view>

              <!-- 🔓 2026-11-03 接回 H3 机械版：通道说明恢复。 -->
              <view v-if="regenChannel === 'minimax'" class="chan-hint">
                MiniMax H3 走官方 `[video editing]` 任务类型（源片直接修改），也支持续写；
                但官方没有像素级保留承诺 —— 要 1:1 保原片，优先选「火山」
              </view>
              <view class="chan-hint">
                按秒计费。点出片前，上面那份清单会逐段说清哪几段复用、哪几段要重新生成、为什么。
              </view>
            </view>

          <!-- 没勾「换什么」不是错误，是"只换声音"的正常选择，别用红字吓人 -->
          <view class="regen-hint" v-if="wantRegen === false">
            现在只换配音，画面一个像素都不动。想换画面就点上面的「换什么」。
          </view>

          <!-- 花钱之前先把"哪些不用再花钱"摆出来。这份清单是本地算的，
               不调任何模型；点下去之后发出去的请求段数必须和这里对得上。 -->
          <view class="reuse" v-if="wantRegen && reuse">
            <view class="reuse-head">
              <text class="reuse-title">这次要生成什么</text>
              <text class="reuse-note" v-if="reuseLoading">计算中…</text>
            </view>
            <view class="reuse-line">
              <text class="reuse-num">{{ reuse.totals.reuse_units }}</text>
              <text>段直接复用</text>
              <text class="reuse-sep">·</text>
              <text class="reuse-num warn">{{ reuse.totals.request_units }}</text>
              <text>段要重新生成</text>
            </view>
            <view class="reuse-why" v-for="r in reuse.requests.slice(0, 4)" :key="r.unit">
              <!-- 🩸 后端给的是秒数（`0.0–14.2s`），只显示秒数看不出"这是第几段"。
                   段号 + 秒数一起给，别让人以为没有分段。 -->
              <text class="reuse-shot">第 {{ r.unit + 1 }} 段 · {{ r.label }}</text>
              <text>{{ r.why }}</text>
            </view>
            <view class="reuse-why" v-if="reuse.requests.length > 4">
              <text>…另外 {{ reuse.requests.length - 4 }} 段</text>
            </view>
            <view class="reuse-foot">
              复用的段不会重复扣费；要重新生成的段才会调用模型。
            </view>
          </view>
        </view>

        <view class="pick-line" v-if="wantRegen">这次用：{{ modelLine }}</view>

        <!-- 出片前把「每段发出去的提示词 + 有没有挂音频」摊开：不花钱，先核对再付费 -->
        <view class="peek" v-if="wantRegen">
          <view class="peek-head" @click="togglePeek">
            <text class="peek-title">{{ peekOn ? '收起' : '查看' }}每段要发给模型的提示词</text>
            <text class="peek-sub">（本地算，不花钱）</text>
          </view>
          <view class="peek-body" v-if="peekOn">
            <view class="peek-tip" v-if="peekLoading">正在算…</view>
            <view class="peek-tip" v-else-if="!peekSegments.length">
              这次没有要重画的视频段（画面全保留原片、或只做静帧重绘）。
            </view>
            <view class="peek-item" v-for="(seg, i) in peekSegments" :key="i">
              <view class="peek-tag">
                第 {{ i + 1 }} 段 · {{ seg.start }}–{{ seg.end }} 秒（{{ seg.duration }} 秒）·
                {{ seg.audio ? '带音频' : '不带音频' }} ·
                {{ seg.prompt_source === 'agent' ? '官方 skill 现写'
                   : (seg.prompt_source === 'ir' ? '出片时由官方改写器生成（下面这版只是参考，不会发出）'
                      : '机器按规则拼') }}
              </view>
              <!-- 🩸 uni-app H5 全局 `html,body{user-select:none}` ⇒ 提示词默认选不中、
                   复制不了。这是要看的东西，不是装饰：`selectable` 让它能被划选，
                   旁边再给一键复制（手机上划选长文本很难用）。 -->
              <text class="peek-text" selectable>{{ seg.prompt }}</text>
              <view class="peek-copy" v-if="seg.prompt_source !== 'ir'"
                    @click="copyPrompt(seg.prompt)">复制这段提示词</view>
            </view>
            <view class="peek-tip" v-if="peekAllIr">
              这一家的提示词由官方改写器在出片时按「这一段真正的原片 + 在场的参考图 + 配音切片 + 边界帧」重写；
              出片后在渲染目录的 request_00N.json 里能看到真正发出去的那一份。
            </view>
            <!-- 机器拼的版本每段句式一样，换人时容易"两张脸不一样、动作也对不上"。
                 点这里让 agent 读官方 skill 逐段现写，写完整份落盘，出片直接用这一版。 -->
            <view class="peek-ai" v-if="peekSegments.length && !peekAllIr">
              <button class="peek-ai-btn" :loading="peekAiLoading"
                      :disabled="peekAiLoading" @click="genPeekPrompts(false)">
                {{ peekAiLoading ? '官方 skill 正在写…' : '用官方 skill 逐段重写（会调一次模型）' }}
              </button>
              <text class="peek-ai-tip" v-if="peekAiMsg">{{ peekAiMsg }}</text>
            </view>
            <view class="peek-tip" v-if="peek && peek.blocked">{{ peek.blocked }}</view>
          </view>
        </view>

        <!-- 🩸 强制重跑（2026-11-02）：同样的输入本来**永远命中段缓存**，
             模型一次都不调 —— 省钱，但也意味着效果不满意时再点一次没用
             （实测三次渲染拿回同一个 476,680 字节的旧片）。
             默认关；打开后逐段缓存失效、重新调模型，**会再扣一次费**。 -->
        <view class="force-row" v-if="wantRegen">
          <label class="force-lab" @click="forceRerun = !forceRerun">
            <checkbox :checked="forceRerun" style="transform:scale(0.7)" />
            <text class="force-text">
              强制重跑（不复用已生成的段，会重新扣费）
            </text>
          </label>
        </view>
        <button class="btn-primary" :loading="submitting" :disabled="submitting" @click="render">
          {{ submitting ? '提交中…' : (wantRegen ? '开始出片（含换画面）' : '开始出片') }}
        </button>
        <!-- 🩸 只出第 1 段（2026-11-01 主人要的）：先看效果再付后面的钱。
             继续出全部时用同样的参数再点「开始出片」，第 1 段命中缓存不再扣费。 -->
        <button v-if="wantRegen && canPreviewOne"
                class="btn-ghost" :loading="submitting"
                :disabled="submitting" @click="render(1)">
          先出第 1 段看看（确认后再出全部）
        </button>
        <view class="recipe-link" @click="exportRecipe">导出配方（镜头表 / 时间轴 / 参数）</view>
      </view>
    </block>
  </view>
</template>

<script>
import {
  cloneDetail, clonePlan, clonePrompts, cloneRender, cloneFileUrl, cloneModels,
  cloneUploadRef,
  cloneDeleteRef, cloneUploadStyleVideo, cloneDeleteStyleVideo,
  cloneUploadAudio, cloneDeleteAudio,
  cloneReusePlan,
  cloneEstimate, cloneVoices, cloneRecipe, cloneInventory, cloneRenderDetail,
  cloneTrainVoice, cloneVoiceStatus, cloneTranslate,
  cloneVoiceDemo, cloneVoicePreview, cloneAudioUrl,
} from '@/api/request'

const STAGES = {
  probe: '读取画面参数',
  shots: '识别镜头切换',
  speech: '识别语音',
  keyframes: '抽取关键帧',
  done: '拆解完成',
}

export default {
  data() {
    return {
      cid: '',
      d: { state: 'queued', pct: 0, stage: '', summary: null, meta: {} },
      timer: null,
      script: '',
      // 逐句台词（后端 `speech_lines`）：每一行 = 原片的一句话 + 说话人。
      // 有它就走逐句列表（改哪行就是改那句），没有就退回整段 textarea。
      speechRows: [],
      // 逐句只在分析完成后铺一次，之后用户改的内容不能被轮询覆盖
      speechLoaded: false,
      // 重新配音给谁配：勾中的说话人 key（`person` / `speaker` / `__none__`）。
      // 默认全勾 = 整片重配；取消某个人就只重配其他人。
      dubPick: [],
      // 每个说话人各用什么音色（key → 音色 ID）。空 = 全片用上面选的那个。
      groupVoices: {},
      submitting: false,
      // 🩸 2026-10-29 主人拍板默认关：底 20% 是实心硬黑边（无羽化，亮度 57→2.4），
      // 而且无差别盖全片（重绘段也被压黑），位置又跟真实字幕对不上 ——
      // 实测一条真实成片字幕在 61%，黑边什么都没盖住。开关留着，谁要谁开。
      maskBottom: false,
      coverFail: false,
      // 全片联系表（本地 ffmpeg 生成，不花钱）
      sheetOn: false,
      sheetLoading: false,
      sheetUrl: '',
      sheetVer: 0,
      // 从成片页「改这段」进来：只处理这一段（时间区间），其余镜头排除
      onlySpan: null,
      onlyApplied: false,
      fromRid: '',
      // off 不换 / auto 逐镜分诊 / shots 混剪 / whole 整片重制
      // 怎么换不再由用户选：有改动就走逐镜分诊，没改动就只换配音
      openingOn: false,
      // 花钱前的那张单子：这次哪几段复用、哪几段要重新生成
      reuse: null,
      reuseLoading: false,
      // 出片前预览：这一段到底会发给模型什么（不花钱，点了才算）
      peekOn: false,
      peekLoading: false,
      peek: null,
      peekAiLoading: false,
      peekAiMsg: '',
      reuseTimer: null,
      // 要排除的镜头（空 = 全部参与）。用"排除法"而不是"选中法"，
      // 这样默认全选，用户点一下就是取消一镜，不用先把所有镜勾一遍
      excludedShots: [],
      regenChannel: 'auto',
      // 空 = 用该通道的默认型号；填了就是界面上选的那一款
      regenModel: '',
      // 后端 /clone/models 下发的型号表（含每款各自收的清晰度档位）
      models: [],
      // 默认展开：模型是出片前最该看一眼的东西，藏起来等于没有
      adv: true,
      // 火山认可的肖像来源 ID（asset://xxx 或纯 id），填了就优先走火山
      subjectAsset: '',
      // 视觉盘点：画面里有几个人、各在第几秒（后端缓存，重复打开不花钱）
      inv: { ready: false, people: [], products: [], scenes: [] },
      invLoading: false,
      invReason: '',
      slotLoading: '',
      // 换图后加个时间戳绕开图片缓存，否则前端还是显示旧图
      refVer: 0,
      // 读音校正：显示词 → 念法。识别原文始终不动
      pronounce: {},
      // 后端挑出来的"可能需要校正"的词（英文词/缩写、带币种的数字）
      pronCandidates: [],
      // 文案估时长（后端本地算，不花钱）
      est: null,
      estTimer: null,
      // 配音和画面差太多时是否允许强行对齐
      allowStretch: false,
      // 🩸 强制重跑：跳过逐段产物缓存、重新调模型（会再扣费）。
      //   默认关 —— 同样输入永远命中缓存；效果不满意要再抽一次才打开。
      forceRerun: false,
      // 配音音色：列表来自后端（火山官方 2.0 音色表），按语言过滤
      voices: [],
      voiceId: '',
      // 音色分类（'' = 全部）；中文 90 个不分类翻起来太累
      voiceCat: '',
      // 方言代码（火山 explicit_dialect）——空 = 标准普通话
      dialect: '',
      // 官方取值，来源 `www.volcengine.com/docs/6561/2534913` 的 explicit_dialect；
      // 名字与音色表里的 `dialects` 字段一一对应
      dialectCode: {
        北京: 'beijing', 东北: 'dongbei', 河南: 'henan', 陕西: 'shaanxi',
        上海: 'shanghai', 四川: 'sichuan', 天津: 'tianjin', 粤语: 'yue',
      },
      // 声音复刻：音色槽位 ID + 训练状态（消耗复刻额度，必须用户主动点）
      vcOn: false,
      vcSpeaker: '',
      vcUploading: false,
      vcStatus: '',
      vcDemo: '',
      // 空 = 跟随分析阶段的判定（英文原片自动用英文音色）
      langPick: '',
      recLang: '',
      // C6 多语种配音：译文的逐行版本。null = 没翻过（出片时后端自己切句）；
      // 有值就原样送后端 —— 外语按 14 字硬切会被切成碎片，总时长能涨到 1.7 倍
      scriptLines: null,
      trBusy: false,
      trRatio: 0,
      // 译文是哪个语种的，用来判断它和现在选的音色还配不配
      trLang: '',
      // 试听：音色 demo（全站缓存）+ 文案试听（按 文案/音色/语速 缓存）
      // 共用一个播放器：点哪个放哪个，不叠一屏 audio 控件
      playUrl: '',
      playWhat: '',
      vdBusy: false,
      pvBusy: false,
      // 文案试听的**实测**秒数，和原片比 —— 比估算靠谱
      pvSec: 0,
      pvDiff: 0,
      // 试听的是不是整段文案：只念了一部分时，拿它跟整条原片比会误导
      pvFull: false,
      // 语速：默认自动（后端按估算定）；动了滑块才算手动
      rateOn: false,
      rateVal: 0,
      langs: [
        { v: '', t: '自动' },
        { v: 'zh', t: '中文' },
        { v: 'en', t: '英文' },
      ],
      // 小语种（第二层）：由 /clone/voices 的 languages 填充；接口拿不到时用这份兜底，
      // 和 `voice_catalog.LANGS` 保持一致 —— 只列官方音色表里真实存在的语言。
      langMore: false,
      moreLangs: [
        { v: 'id', t: '印尼语' }, { v: 'ms', t: '马来语' },
        { v: 'th', t: '泰语' }, { v: 'vi', t: '越南语' },
        { v: 'tl', t: '菲律宾语' }, { v: 'ja', t: '日语' }, { v: 'ko', t: '韩语' },
        { v: 'es', t: '西班牙语' }, { v: 'mx', t: '西语（拉美）' },
        { v: 'pt', t: '葡萄牙语' }, { v: 'ru', t: '俄语' }, { v: 'ar', t: '阿拉伯语' },
        { v: 'de', t: '德语' }, { v: 'fr', t: '法语' }, { v: 'it', t: '意大利语' },
      ],
      // 换画面的结构化规格：换什么 / 保什么 / 声音 / 成片规格
      edit: {
        person: false,
        product: false,
        scene: false,
        wardrobe: false,
        // 视觉盘点里选中的人（P1/P2…），**可多选**：点一个加一个，再点取消。
        // 空 = 自动取主角；`person_id` 恒等于第一个，只为老接口保留。
        person_ids: [],
        person_id: '',
        person_desc: '',
        product_desc: '',
        // 画面里被换的是哪一件（盘点给的外观，点选；不选 = 画面里那件产品）
        product_target: '',
        product_target_en: '',
        scene_desc: '',
        wardrobe_desc: '',
        /**
         * 按人写的服装描述：`{人物 id: "米色风衣"}`。
         * 🩸 2026-10-27：后端换装一直支持「没图就用一句话说换成什么」
         * （`edit_spec` 的 `elif desc:` 分支，官方 `guide:39` 的 `<新特征>`），
         * 但前端从来没有过输入框 —— 槽位文案写着「不传图就只用文字描述」，
         * 用户照着找却找不到，提交又被拦。这里补上，一人一个。
         */
        wardrobe_desc_by_id: {},
        // 换装名单：第 i 个人 → wardrobe / wardrobe2 … 各一张图；空 = 换全体
        wardrobe_ids: [],
        // 谁在说话（MiniMax H3 用）：只有名单里的人拿 (S1)(S2) 号
        speaker_ids: [],
        style: '',
        // 风格参考（A9）：图和视频二选一，后端收到一个就删掉另一个。
        // 没有勾选框 —— 传上文件就算开（`refresh` 按文件同步这两个开关）
        style_ref: false,
        style_video: false,
        // 「保什么」六个开关不在界面上，也不下发：保什么由后端按默认编译进提示词
        // 🩸 2026-10-28 主人：「默认首选这里」（截图圈的是「保留原声」）。
        //   以前默认 tts，实际最常用的是保留原声 —— 忘了点就白配一条音。
        //   真要重新配音时手动点「全新配音」即可。
        audio: 'original',
        // 原片声音的后期处理（C4）：只影响成片混音，不改画面、不进提示词。
        //   bgm keep 保留原片背景音乐 / drop 去掉 / replace 换成上传的音乐
        //   sfx keep 保留原片音效 / add 再叠一段上传的音效
        bgm: 'keep',
        sfx: 'keep',
        // 尾帧锁定（B6）：逐镜重绘的镜头把结尾也锁回原片那一帧。
        // 只作用于静帧重绘的生成链（编辑链发参考视频，与首尾帧互斥）。
        // 默认关 = 老行为；开了每镜多一次图生图。
        // 🩸 2026-10-23 主人拍板「也不烧字幕」：subtitle 字段删除，成片不带任何字幕
        resolution: 'auto',
        extra: '',
        // 「一次只改一类」（2026-11-03）：默认关。开了以后同时勾 2 类改动会被后端拦下。
        // 官方《2.5 提示词指南》「复杂任务效果不稳定」→ 拆成多个简单任务。
        one_change: false,
      },
      // 换开头只重制前几秒（hypit：换钩子重跑，主体不动）
      openingSec: 3,
      // 多版本：同一个开头按几个方向各出一版（方向由用户写，不替用户编）
      multiOn: false,
      variantDirs: ['', '', ''],
      openingOpts: [
        { v: 3, t: '前 3 秒' },
        { v: 5, t: '前 5 秒' },
        { v: 8, t: '前 8 秒' },
      ],
      // 🩸 2026-10-31：通道列表改由后端型号表推导（见 computed.channels）。
      //   以前这里写死三项，跟后端 `model_specs.MODELS` 不同源 ——
      //   冻结一个通道（比如 H3）要改两处，漏一处界面上还留着入口。
      slots: [
        // 🩸 人物**不给描述框**：换人后的长相只认参考图（`<Picture N>`），
        // 文字不参与生成（`edit_spec._clauses` 人物分支根本没用 person_desc）。
        // 2026-10-21 实测：用文字定义身份 → 衣服/发型换了，脸还是原片那个人。
        // 留一个填了不生效的框 = 误导，所以这里不给 `ph`（没有 ph 就不渲染输入框）。
        // 🩸 一个人**只传一张**，系统不裁、不追加第二张（2026-10-26 台账 D48）。
        // 主人口头禁令（同日）：「不做而且删除或者记住永远不要再提示」——
        // **任何形态**的「再传一张 / 脸太小换半身照」提示都不许出现。
        // 唯一要告知的官方限制：**禁用人物多视图 / 三视图**（多视图会脸崩、出双胞胎）。
        { k: 'person', t: '人物', sub: '换脸 / 换人', img: true,
          imgHint: '传一张这个人的照片就行；'
            + '别传三视图 / 多角度拼图（官方明确会脸崩、出双胞胎）。'
            + 'asset ID 是火山认可的肖像来源' },
        { k: 'product', t: '产品', sub: '换商品 / 换道具', img: true,
          imgHint: '产品图越干净越好，别带原包装上的文字',
          ph: '描述产品，例：一只白色陶瓷咖啡杯' },
        { k: 'scene', t: '场景', sub: '换背景 / 换地点', img: true,
          imgHint: '不传图也行，用文字描述场景',
          ph: '描述场景，例：黄昏的海边栈道' },
        { k: 'wardrobe', t: '服装造型', sub: '换衣服 / 换发型', img: true,
          imgHint: '传商品图就按图里的款式换；不传图就用文字描述',
          ph: '描述服装，例：米色风衣 + 低马尾' },
      ],
      styles: [
        { v: '', t: '风格不变' },
        { v: 'live', t: '实拍' },
        { v: 'anime', t: '动漫' },
        { v: '3d', t: '3D' },
        { v: 'film', t: '胶片' },
        { v: 'sketch', t: '手绘' },
      ],
      // 🩸 2026-10-28 主人：「保留原声放在最前面，我自己都经常会忘记点，
      //   需要改动的才会去看后面」。常用档放第一位；默认值也改成
      //   `original`（见 data 里 `edit.audio`），顺序与默认值是两件事。
      audios: [
        { v: 'original', t: '保留原声' },
        { v: 'tts', t: '全新配音' },
        { v: 'mix', t: '配音 + 背景音' },
      ],
    }
  },
  computed: {
    busy() {
      return this.d.state === 'queued' || this.d.state === 'analyzing'
    },
    // 通道列表 = 后端 `/clone/models` 里**真实出现过**的通道。
    // 🩸 单一真相源是 `model_specs.MODELS`：那里没有的通道，这里就不会出现。
    //   2026-10-31 冻结 H3 = 后端清空 `MODELS["minimax"]`，前端自动跟着消失，
    //   不用再记得改两处。中文名只是显示用，认不出来的通道直接显示原名。
    channels() {
      // 🔓 2026-11-03 接回 H3 机械版：minimax 回到后端列表，中文名一起还给它。
      const labels = { volc: '火山', minimax: 'MiniMax H3' }
      const out = [{ v: 'auto', t: '自动' }]
      for (const m of (this.models || [])) {
        if (m.channel && !out.some((x) => x.v === m.channel)) {
          out.push({ v: m.channel, t: labels[m.channel] || m.channel })
        }
      }
      return out
    },
    // 出片预览里的逐段提示词（后端已经把 "带不带音频" 也算好了）
    peekSegments() {
      return (this.peek && this.peek.segments) || []
    },
    // 这一家的提示词由官方改写器在出片时生成：界面不能把"参考版"当成要发的东西，
    // 「用官方 skill 逐段重写」这个按钮对它们也没有意义（点了花钱、词还不会被用）。
    peekAllIr() {
      return this.peekSegments.length > 0 &&
        this.peekSegments.every((s) => s.prompt_source === 'ir')
    },
    // 🩸 只出第 1 段：只有「要换画面」且**不止一段视频**时才给这个按钮。
    //   单段的单子本来一次就出完，预览没有意义。
    //   🩸 2026-11-02 主人截图问「之前那个分段的按键哪里去了」：以前段数取的是
    //   `peek.segments` —— 那是点开「查看每段要发给模型的提示词」才算出来的，
    //   没点开 ⇒ `peek` 是 null ⇒ 这个按钮永远不渲染（代码有、界面上没有）。
    //   改用页面上**已经算好**的复用清单：`reuse.requests` 和真跑共用同一份
    //   `_desired_units`（backend/app/services/work.py:627），只数 `engine: "video"`
    //   —— 静帧重绘不吃 `max_segments`（clone_pipeline.py:1502 截的是视频 `spans`）。
    canPreviewOne() {
      if (!this.wantRegen) return false
      const reqs = (this.reuse && this.reuse.requests) || []
      return reqs.filter((r) => r.engine === 'video').length > 1
    },
    // 逐句列表只在「当前文案就是这些行拼出来的」时显示。
    // 翻译、恢复历史版本这些操作会把整段文案换掉 —— 那时列表还挂在那儿，
    // 显示的就是旧原文，用户会以为改的是新译文。对不上就退回整段输入框。
    spkAligned() {
      if (!this.speechRows.length) return false
      return this.speechRows.map((r) => String(r.text || '').trim()).join('\n')
        === String(this.script || '').trim()
    },
    // 按说话人把行分组 —— 勾人就是勾这些组
    spkGroups() {
      const map = new Map()
      this.speechRows.forEach((r, i) => {
        const k = String(r.person || r.speaker || '__none__')
        if (!map.has(k)) {
          map.set(k, { key: k, label: this.spkLabel(r), lines: [] })
        }
        map.get(k).lines.push(i)
      })
      return Array.from(map.values())
    },
    // 每个人各用什么音色 → 摊到每一行（后端按行号取音色合成）。
    // 没给某人选过就留空 —— 空 = 跟随上面那个整片音色。
    dubVoices() {
      const out = {}
      this.spkGroups.forEach((g) => {
        const v = this.groupVoices[g.key]
        if (!v) return
        g.lines.forEach((i) => { out[String(i)] = v })
      })
      return out
    },
    // 只重配哪几行。全勾（或只有一组）返回 null = 走老的整片重配路径。
    dubLines() {
      const groups = this.spkGroups
      if (groups.length < 2) return null
      if (this.dubPick.length >= groups.length) return null
      return groups.filter((g) => this.dubPick.indexOf(g.key) >= 0)
        .flatMap((g) => g.lines)
        .sort((a, b) => a - b)
    },
    // 分不出说话人：所有句子连一个编号都没分出来，或者分出来的编号不足两个。
    // 这时候逐句列表只能当"整段按句拆开"，要跟用户说清楚。
    spkBlind() {
      const keys = new Set()
      for (const r of this.speechRows) {
        const k = String(r.person || r.speaker || '')
        if (k) keys.add(k)
      }
      return keys.size < 2
    },
    // 火山官方限制：不收直接上传的真人脸。选了火山 + 传了人物图 + 没填素材 ID → 提前说，
    // 别等提交了让接口 400 打回来（那种报错用户还得自己翻译一遍）
    volcRealFaceWarn() {
      return this.regenChannel === 'volc'
        && this.hasRefImg('person')
        && !this.subjectAsset.trim()
    },
    // 选中的人（多选，按点击顺序 = 槽位顺序 = 提示词图号顺序）
    pickedIds() {
      return this.edit.person_ids || []
    },
    /** 第 2 个起的人各占一个槽位：person2 / person3 … 上限跟着型号走。
     *
     * 🩸 2026-11-04 主人：「你只有出了这个描述才能上传第二张图呀，这里本来就是 BUG，
     *   上传复刻视频之前人的心里肯定就已经有答案要换谁和谁了」。
     *   以前这里只从 `pickedIds` 里取 —— 而能点的人 chip 要等识别跑完才有，
     *   于是「传第 2 张脸」被绑死在「分析出人物」之后。后端 `_save_ref` 对所有
     *   `PERSON_SLOTS` 一视同仁，从来不要求先分析，纯粹是前端把入口藏了。
     *   现在改成**按已传的图滚雪球**：传了第 1 张就冒出第 2 格，第 2 格有图就冒出第 3 格；
     *   已勾选的人更多时也照样显示（保持老行为）。`bound` = 这格有没有绑到具体的人。
     */
    extraPeople() {
      const picked = this.pickedIds
      const cap = this.subjectLimit.max
      // 最靠后的那个「已有图」的槽位（person → person2 → …）。
      // 🩸 不 break：删掉第 1 张、只留第 2 张时，第 2 格必须还看得见 ——
      //   否则那张图在界面上消失，用户既看不到也删不掉。
      let refs = 0
      for (let i = 1; i <= cap; i += 1) {
        const slot = i === 1 ? 'person' : `person${i}`
        if (this.hasRefImg(slot)) refs = i
      }
      // 有图就再往后留一格，方便「先传图、后选人」；勾的人多时以勾的人数为准
      const want = Math.min(cap, Math.max(picked.length, refs ? refs + 1 : 0))
      const out = []
      for (let i = 1; i < want; i += 1) {
        const id = picked[i] || ''
        const p = (this.inv.people || []).find((x) => x.id === id)
        out.push({
          slot: `person${i + 1}`,
          id,
          bound: !!id,
          label: (p && p.desc_zh) || `第${i + 1}个人`,
        })
      }
      return out
    },
    /** 当前型号能换几个人：稳定线 / 硬上限（来自 /clone/models） */
    subjectLimit() {
      const cur = this.models.find((x) => x.id === this.regenModel)
        || this.models.find((x) => x.default
          && (!this.regenChannel || this.regenChannel === 'auto'
            || x.channel === this.regenChannel))
        || this.models.find((x) => (!this.regenChannel || this.regenChannel === 'auto'
          || x.channel === this.regenChannel))
      return {
        stable: (cur && cur.stable_subjects) || 4,
        max: (cur && cur.max_subjects) || 4,
        label: (cur && cur.label) || '当前型号',
      }
    },
    /** 风格参考视频传了没有（没有勾选框，以文件为准） */
    hasStyleVideo() {
      return !!(this.d.ref_videos && this.d.ref_videos.style)
    },
    /** 当前型号的参考视频总时长上限（秒）；型号没定就返回 0 = 不显示具体数字 */
    styleVideoCap() {
      const cur = this.models.find((x) => x.id === this.regenModel)
      if (cur) return Number(cur.ref_video_total_sec) || 15
      const d = this.models.find((x) => x.default
        && (!this.regenChannel || this.regenChannel === 'auto'
          || x.channel === this.regenChannel))
      return d ? (Number(d.ref_video_total_sec) || 15) : 0
    },
    styleVideoHint() {
      if (!this.hasStyleVideo) {
        return '单段 2–15 秒、≤50MB，3 秒左右就够读出调性；和上面的参考图二选一'
      }
      const cap = this.styleVideoCap
      if (!cap) {
        return '已上传。出片前会按型号核对：母版片段 + 风格片段不能超过参考视频总时长上限'
      }
      return `已上传。这个型号的参考视频总共 ${cap} 秒，母版片段和风格片段要一起装下：`
        + `最长一段超过 ${Math.max(0, cap - 3)} 秒就放不下（会拦下，改用参考图或换上限 30 秒的 2.5）`
        + '。用视频参考时整片都会重画（静帧吃不到视频参考）'
    },
    /** 人数超了该切到哪一款：上限比当前高、且是能接住的那个 */
    subjectSwitch() {
      const cap = this.subjectLimit.max
      return this.models.find((m) => (m.max_subjects || 4) > cap) || null
    },
    modeHint() {
      if (this.openingOn) return '只换开头，后面的原片不动'
      if (!this.wantRegen) return '不勾就不动画面，只换配音'
      return '没勾的镜头保留原片，勾了的整段重制'
      return '只换文案，画面不动'
    },
    // 镜头选择条：带关键帧、自动分诊标注、是否参与
    shotPicker() {
      const shots = this.d.shots || []
      return shots.map((s) => ({
        i: s.i,
        url: s.i < 12 ? cloneFileUrl(this.cid, 'kf', `kf_${String(s.i).padStart(3, '0')}.jpg`) : '',
        picked: this.excludedShots.indexOf(s.i) < 0,
      }))
    },
    // 换开头：落在开头 N 秒里的镜头（至少一镜，最多全部）
    openingShots() {
      const shots = this.d.shots || []
      const picked = shots.filter((s) => Number(s.start) < this.openingSec)
      if (picked.length) return picked.map((s) => s.i)
      return shots.length ? [shots[0].i] : []
    },
    openingInfo() {
      const n = this.openingShots.length
      const shots = this.d.shots || []
      if (!n || !shots.length) return ''
      const last = shots.find((s) => s.i === this.openingShots[n - 1])
      const end = last ? Number(last.end) : this.openingSec
      return `覆盖 ${n} 镜 · 约 ${end.toFixed(1)} 秒`
    },
    // 两个范围按钮点完到底改了什么 —— 不给这句，用户会觉得"点了没反应"
    scopeLine() {
      const shots = (this.d && this.d.shots) || []
      if (!shots.length) return ''
      if (this.openingOn) {
        const keep = this.openingShots.length
        const last = shots.find((s) => s.i === this.openingShots[keep - 1])
        const end = last ? Number(last.end).toFixed(1) : this.openingSec
        return `只重画前 ${end} 秒里的 ${keep} 个镜头，后面 ${shots.length - keep} 个原样保留`
      }
      const n = this.excludedShots.length
      if (n) return `全部 ${shots.length} 个镜头里，已排除 ${n} 个，只处理 ${shots.length - n} 个`
      return `全部 ${shots.length} 个镜头逐镜判断：能保原片就保，动作镜才重画`
    },
    // 「只改这一段」说清到底动多大范围：用户点的是 3 秒，模型可能最少收 4 秒
    onlyInfo() {
      if (!this.onlySpan) return ''
      const a = this.onlySpan[0]
      const b = this.onlySpan[1]
      const shots = (this.d && this.d.shots) || []
      const n = shots.filter(
        (s) => Number(s.end) > a + 0.05 && Number(s.start) < b - 0.05
      ).length
      return `${a.toFixed(1)}–${b.toFixed(1)} 秒 · ${n} 个镜头`
    },
    // 这次要不要动画面：勾了「换什么」或写了补充说明，或者一次出多版
    wantRegen() {
      const dirs = this.multiOn
        ? this.variantDirs.map((x) => (x || '').trim()).filter(Boolean)
        : []
      return !!(this.hasAnyChange || dirs.length)
    },
    // 换画面的方式**不再由用户选**：有改动就走逐镜分诊，只换开头是另一条范围
    regenMode() {
      if (!this.wantRegen) return 'off'
      return this.openingOn ? 'opening' : 'auto'
    },
    // 至少勾了一项「换什么」，或者写了补充说明
    hasAnyChange() {
      const e = this.edit
      return !!(e.person || e.product || e.scene || e.wardrobe || e.style
        || e.style_ref || e.style_video)
        || !!(e.extra || '').trim()
    },
    /** 实际会走哪条通道（「自动」时按有没有本地人物图判，规则同后端 pick_channel）。
     *  🩸 2026-11-03 复刻下架 H3：自动分支必须**先看这条通道还在不在售**。
     *    后端 `pick_channel` 会跳过 `Caps.frozen` 的家族；这里若把 minimax 写死，
     *    冻结后界面仍按「有图 → MiniMax」显示，与后端实际走的（火山）不符。
     *    判据同上：单一真相源是 `model_specs.MODELS` —— 没在列表里 = 不可选。 */
    effChannel() {
      const ch = this.regenChannel
      if (ch && ch !== 'auto') return ch
      const hasMinimax = (this.models || []).some((m) => m.channel === 'minimax')
      return (hasMinimax && (this.hasRefImg('person') || this.subjectAsset.trim()))
        ? 'minimax' : 'volc'
    },
    /** 可点的盘点人物。
     *  🩸 2026-10-27：视觉盘点偶尔把**一群人**识别成一个"人"（真实样本
     *  `2ddd8959` 的 P3：「多名身着日常休闲服饰的普通民众，部分手持手机拍摄」，
     *  `face_visible=false`、`position=unknown`）。这种项点进去换不了任何人 ——
     *  编译器连「画面左侧的人物」这种指认短语都拼不出来，后端只会跳过，
     *  用户却以为已经选了。列表阶段就藏掉，比出片后才发现好。
     *  注意**不能**按 `face_visible=false` 过滤：真实盘点里 9 个无脸项只有 1 个
     *  是群体，其余 8 个都是能明确指认的单人（背影/侧脸），误杀会少掉正常目标。 */
    invPickable() {
      const GROUP = /多名|数名|几名|若干|一群|众人|人群|民众|路人|背景人物/
      return (this.inv.people || []).filter(
        (p) => !GROUP.test(String(p.desc_zh || '')))
    },
    /** 换装名单 → 每人一行（槽位 wardrobe / wardrobe2 …） */
    wardrobeRows() {
      return (this.edit.wardrobe_ids || []).map((id, i) => {
        const p = (this.inv.people || []).find((x) => x.id === id)
        return {
          id,
          slot: i === 0 ? 'wardrobe' : `wardrobe${i + 1}`,
          label: (p && p.desc_zh) || id,
        }
      })
    },
    /** 参与指认的人：换装/道具/说话人的候选都来自视觉盘点 */
    invPeople() {
      return this.inv.ready ? (this.inv.people || []) : []
    },
    audioHint() {
      if (this.edit.audio === 'original') return '唱歌 / 跳舞 / 原口播：声音就是内容，不重新配音'
      if (this.edit.audio === 'mix') return '新配音 + 原片 BGM / 音效；原片对白会被分离掉'
      return '完全换成新配音，原片声音不要了'
    },
    // —— 原片声音处理（C4）：BGM / 音效 ——
    hasBgmFile() {
      return !!(this.d && this.d.audio_refs && this.d.audio_refs.bgm)
    },
    hasSfxFile() {
      return !!(this.d && this.d.audio_refs && this.d.audio_refs.sfx)
    },
    bgmOpts() {
      // tts 模式原片声音整条不要，「保留原片」没有意义
      return this.edit.audio === 'tts'
        ? [{ v: 'keep', t: '不加音乐' }, { v: 'replace', t: '加我上传的音乐' }]
        : [
          { v: 'keep', t: '保留原片' },
          { v: 'drop', t: '不要背景音乐' },
          { v: 'replace', t: '换成我上传的' },
        ]
    },
    sfxOpts() {
      return this.edit.audio === 'tts'
        ? [{ v: 'keep', t: '不加音效' }, { v: 'add', t: '加一段音效' }]
        : [{ v: 'keep', t: '保留原片' }, { v: 'add', t: '再加一段' }]
    },
    bgmHint() {
      if (this.edit.bgm === 'drop') return '原对白、环境音和动作音都留下，只去掉背景音乐'
      if (this.edit.bgm === 'replace') return '原背景音乐换掉，对白和环境音照旧'
      if (this.edit.audio === 'tts') return '全新配音默认不带原片任何声音；要音乐就上传一首'
      return '原片背景音乐照旧'
    },
    resLabel() {
      if (this.edit.resolution === 'auto') return '跟原片'
      return this.edit.resolution
    },
    // 型号选项：通道定了就只列那一家的；通道是「自动」就两家都列
    modelOpts() {
      const ch = this.regenChannel
      const list = (!ch || ch === 'auto')
        ? this.models
        : this.models.filter((m) => m.channel === ch)
      return [{ id: '', label: '默认', max_sec: 0 }].concat(list.map((m) => ({
        id: m.id, label: m.label, channel: m.channel,
        resolutions: m.resolutions || [],
        max_sec: m.max_sec || 0,
      })))
    },
    // 出片按钮上方那行：不管你折叠没折叠，这次到底用哪家、哪款、几档，一眼看见
    modelLine() {
      if (this.openingOn) return '逐镜抽帧重画，不走通道 / 型号'
      const ch = { auto: '自动选通道', volc: '火山' }[this.regenChannel]
        || '自动选通道'
      const m = this.modelOpts.find((x) => x.id === this.regenModel)
      const name = m && m.id ? m.label : '默认型号'
      return `${ch} · ${name} · ${this.resLabel()}`
    },
    // 长片不是"只有 2.5 能做"：任何型号超过单段上限都会按镜头切段再拼。
    // 这句是给用户看的，别让人以为选了 2.0 就出不了 30 秒的片子。
    modelHint() {
      const m = this.modelOpts.find((x) => x.id === this.regenModel)
      const lim = this.subjectLimit
      const subj = `换人 ${lim.stable} 人内最稳、最多 ${lim.max} 人`
      if (!m || !m.max_sec) {
        return `${subj}；超过单段上限会自动按镜头切段、逐段生成再拼接`
      }
      return `${subj}；单段最长 ${m.max_sec} 秒，更长的片子会自动切段拼接`
    },
    // 清晰度跟着型号走：能出哪几档由型号自己的 `resolutions` 决定
    // （`/clone/models` 每个型号都带着）。
    // 🩸 型号选「默认」时，按**这一单实际会用的型号**列 —— 也就是所选通道的型号。
    //   以前这里写死了一张「720p / 1080p」的兜底表，专门给"没选型号"用；
    //   2.0/H3 下架后那张表没人更新，2.5 的 **480p 直接被它挡掉了**
    //   （2026-10-31 主人指出）。兜底只能来自型号自己的表，不能再写死。
    resolOpts() {
      const m = this.models.find((x) => x.id === this.regenModel)
        || this.models.find((x) => x.channel === this.regenChannel)
        || this.models[0]
      if (!m || !(m.resolutions || []).length) {
        return [{ v: 'auto', t: '自动' }]
      }
      return [{ v: 'auto', t: '自动' }].concat(
        (m.resolutions || []).map((r) => ({ v: r, t: r }))
      )
    },
    stageText() {
      return STAGES[this.d.stage] || '准备中'
    },
    hasCover() {
      return !!(this.d.meta && this.d.meta.cover)
    },
    coverUrl() {
      return cloneFileUrl(this.cid, 'srccover')
    },
    keyframes() {
      const shots = (this.d.shots || []).slice(0, 12)
      return shots.map((s) => ({
        i: s.i,
        url: cloneFileUrl(this.cid, 'kf', `kf_${String(s.i).padStart(3, '0')}.jpg`),
      }))
    },
    // 配音时长条：按 2 倍目标时长排布 —— 目标点正好落在条子中间，
    // 超出去的部分一眼能看出来；没到中间说明文案不够长
    estPct() {
      const e = this.est
      if (!e || !e.target_seconds) return 0
      return Math.max(2, Math.min(100, (Number(e.est_seconds) / e.target_seconds) * 50))
    },
    // 音色分类：中文有 90 个，一个下拉翻起来太累，先按用途收窄。
    // 分类项由当前语言的音色实际有什么决定 —— 没有的类不显示（点了是空的更糟）。
    voiceCats() {
      const vs = this.voices || []
      const out = [{ k: '', t: '全部', n: vs.length }]
      const cnt = (fn) => vs.filter(fn).length
      const female = cnt((v) => v.gender === 'female')
      const male = cnt((v) => v.gender === 'male')
      if (female) out.push({ k: 'female', t: '女声', n: female })
      if (male) out.push({ k: 'male', t: '男声', n: male })
      const role = cnt((v) => (v.scene || []).indexOf('角色扮演') >= 0)
      if (role) out.push({ k: 'role', t: '角色扮演', n: role })
      const vid = cnt((v) => (v.scene || []).indexOf('视频配音') >= 0)
      if (vid) out.push({ k: 'video', t: '视频配音', n: vid })
      // 方言不在这里 —— 它是一级筛子（见 dialectOptions），单独一行。
      // 两个入口指向同一批音色只会让人多一次点击。
      return out
    },
    // 当前分类 + 方言下真正要列出来的音色
    voiceShown() {
      let vs = this.voices || []
      const c = this.voiceCat
      if (c === 'female') vs = vs.filter((v) => v.gender === 'female')
      else if (c === 'male') vs = vs.filter((v) => v.gender === 'male')
      else if (c === 'role') vs = vs.filter((v) => (v.scene || []).indexOf('角色扮演') >= 0)
      else if (c === 'video') vs = vs.filter((v) => (v.scene || []).indexOf('视频配音') >= 0)
      // 🩸 选了方言就只留说这个方言的音色 —— 顾客想听粤语，点「粤语」一步到位，
      // 不用先知道哪个音色会说。
      if (this.dialect) {
        const name = this.dialectName(this.dialect)
        if (name) vs = vs.filter((v) => (v.dialects || []).indexOf(name) >= 0)
      }
      return vs
    },
    // 选音色用的下拉项：名字 + 性别，够分辨了；ID 太长塞不进一行
    voiceLabels() {
      return this.voiceShown.map((v) => {
        const g = v.gender === 'female' ? '（女）' : v.gender === 'male' ? '（男）' : ''
        return `${v.name}${g}`
      })
    },
    voiceIndex() {
      const i = this.voiceShown.findIndex((v) => v.id === this.voiceId)
      return i < 0 ? 0 : i
    },
    // 当前语言下能说的所有方言（中文名并集）。空 = 这个语言没有方言能力，整行不出现。
    // 🩸 不看「当前音色」—— 方言是**一级筛子**，顾客先点「粤语」，音色下拉自己收窄；
    // 要是跟着选中音色走，顾客得先知道哪个音色会说，等于把题库答案先告诉他。
    dialectOptions() {
      const out = []
      ;(this.voices || []).forEach((v) => {
        ;(v.dialects || []).forEach((t) => {
          if (out.indexOf(t) < 0) out.push(t)
        })
      })
      return out
    },
    voiceLabel() {
      const v = (this.voices || []).find((x) => x.id === this.voiceId)
      if (v) {
        const g = v.gender === 'female' ? '（女）' : v.gender === 'male' ? '（男）' : ''
        return `${v.name}${g}`
      }
      // 手填的私有音色（S_ 开头）不在目录里，原样显示
      return this.voiceId || '默认'
    },
    // 选中的是不是第二层的小语种（决定「更多」按钮怎么显示、第二行要不要展开）
    isMoreLang() {
      return !!this.langPick && this.langPick !== 'zh' && this.langPick !== 'en'
    },
    langAutoText() {
      if (this.langPick) return ''
      return `自动判定为${this.langName(this.recLang || 'zh')}`
    },
    voiceHint() {
      const code = this.langPick || this.recLang || 'zh'
      const name = this.langName(code)
      if (code === 'en') return '英文原片默认用英文音色；中文音色念英文会有口音'
      if (code === 'zh') return '音色只影响配音，不影响画面的语言'
      // 小语种：中文/英文音色念出来是"外国人学这门外语"
      return `${name}原片要用${name}音色；拿中文或英文音色念会有口音`
    },
    // 配音要念的语种：界面选的 > 分析阶段判的 > 中文
    trCode() {
      return this.langPick || this.recLang || 'zh'
    },
    // 出片用的语速：null = 自动（后端按估算定）；动过滑块才是手动值
    speechRate() {
      return this.rateOn ? this.rateVal : null
    },
    rateText() {
      if (!this.rateOn) return '自动（按文案长度定）'
      if (this.rateVal === 0) return '原速'
      return this.rateVal > 0 ? `快 ${this.rateVal}%` : `慢 ${-this.rateVal}%`
    },
    // 试听结果：实测秒数 vs 原片时长。**只有念的是整段文案才比** ——
    // 只念一句就跟整条原片比，会得出「差 -85%」这种毫无意义的数
    pvText() {
      if (!this.pvSec) return ''
      const src = (this.est && this.est.target_seconds) || 0
      if (this.pvFull && src > 0) {
        const sign = this.pvDiff > 0 ? '长' : '短'
        return `这段念完 ${this.fmt(this.pvSec)} 秒 / 原片 ${this.fmt(src)} 秒`
          + `（${sign} ${Math.abs(this.pvDiff)}%）`
      }
      return `这段念完 ${this.fmt(this.pvSec)} 秒`
    },
    trK() {
      const code = this.trCode
      if (code === 'zh') return '文案语种：中文'
      if (this.trLang === code) return `文案已译成${this.langName(code)}`
      if (this.trLang) {
        return `文案是${this.langName(this.trLang)}，和配音语种不一致`
      }
      return `文案还是中文，配音要念${this.langName(code)}`
    },
    trHint() {
      const code = this.trCode
      if (code === 'zh') return '选外语才需要翻译'
      if (this.trLang === code) {
        return this.trRatio > 0
          ? `逐句一一对应。译文估算时长 = 原片的 ${this.trRatio.toFixed(2)} 倍`
          : '逐句一一对应；改译文后按句重新切分'
      }
      return '不翻的话，音色会用外语腔念中文'
    },
    estAdvice() {
      const e = this.est
      if (!e) return ''
      if (e.verdict === 'long') {
        return `太长了：就算把语速调快，还多出约 ${e.trim_chars || 0} 个字，建议先删`
      }
      if (e.verdict === 'short') {
        return `太短了：还差约 ${e.add_chars || 0} 个字，建议补几句，否则成片结尾会被截掉`
      }
      return '长度对得上，语速只会做小幅微调'
    },
  },
  watch: {
    // 打字时别每敲一个字就打一次接口 —— 停手 700ms 再估
    script() {
      this.scheduleEstimate()
      this.scheduleReuse()
      // 译文被改过就跟着重切：出片送的是 scriptLines，不重切就和文本框对不上。
      // 只按句末标点/换行断 —— 外语按字数硬切会把句子切碎（见后端 translate.py）。
      // 🩸 和译文自身拼出来的一样就不动：译文里可能合法地含 `!`（「Wow! 真便宜」），
      // 无脑重切会把一句拆两句，凭空多出一道 TTS 头尾静音。
      if (this.scriptLines && this.script !== this.scriptLines.join('\n')) {
        const out = this.splitLines(this.script)
        this.scriptLines = out.length ? out : null
      }
      if (!this.script.trim()) {
        this.trLang = ''
        this.trRatio = 0
      }
    },
    // 换画面的输入一变，复用清单就得跟着变 —— 那份单子写的是钱
    edit: {
      deep: true,
      handler() {
        this.scheduleReuse()
      },
    },
    regenChannel() {
      this.scheduleReuse()
    },
    regenModel() {
      this.scheduleReuse()
    },
    openingOn() {
      this.scheduleReuse()
    },
    excludedShots: {
      deep: true,
      handler() {
        this.scheduleReuse()
      },
    },
  },
  onLoad(q) {
    this.cid = q.cid || ''
    if (!this.cid) {
      uni.showToast({ title: '缺少任务号', icon: 'none' })
      return
    }
    // 成片页点「改这段」带过来的时间区间：12.30-15.00
    const m = /^([\d.]+)-([\d.]+)$/.exec(q.only || '')
    if (m) this.onlySpan = [Number(m[1]), Number(m[2])]
    this.fromRid = q.rid || ''
    this.refresh()
    this.loadModels()
    this.loadSheet(false)
    this.timer = setInterval(() => {
      if (this.busy) this.refresh()
    }, 1200)
  },
  onUnload() {
    if (this.timer) clearInterval(this.timer)
    if (this.estTimer) clearTimeout(this.estTimer)
    if (this.reuseTimer) clearTimeout(this.reuseTimer)
  },
  methods: {
    fmt(v) {
      const n = Number(v) || 0
      return n >= 60 ? `${Math.floor(n / 60)}分${Math.round(n % 60)}秒` : `${n.toFixed(1)}秒`
    },
    // 联系表由后端本地生成（ffmpeg，不花钱）；这里只负责换地址绕图片缓存
    loadSheet(refresh) {
      if (!this.cid) return
      this.sheetLoading = true
      // 先把图挂上去才会发请求；404 时 @error 会把它收起来
      this.sheetOn = true
      this.sheetVer += 1
      const head = cloneFileUrl(this.cid, 'sheet')
      const q = `refresh=${refresh ? 1 : 0}&t=${Date.now()}-${this.sheetVer}`
      this.sheetUrl = `${head}?${q}`
    },
    onSheetLoad() {
      this.sheetLoading = false
      this.sheetOn = true
    },
    onSheetError() {
      this.sheetLoading = false
      this.sheetOn = false
    },
    // 文案一变就重估（防抖）。这是本地计算，不花钱，但也不该每敲一个字打一次
    scheduleEstimate() {
      if (this.estTimer) clearTimeout(this.estTimer)
      this.estTimer = setTimeout(this.loadEstimate, 700)
    },
    // 复用清单：本地算的，一次也就几十毫秒，但要防抖 —— 别每敲一个字打一次
    scheduleReuse() {
      if (this.reuseTimer) clearTimeout(this.reuseTimer)
      this.reuseTimer = setTimeout(this.loadReuse, 600)
    },
    // 出片前预览：把每段的完整提示词摊出来。点开才调，敲字时不占用带宽
    togglePeek() {
      if (this.peekOn) {
        this.peekOn = false
        return
      }
      this.peekOn = true
      this.loadPeek()
    },
    async loadPeek() {
      if (!this.wantRegen) {
        this.peek = null
        return
      }
      this.peekLoading = true
      try {
        const s = (this.script || '').trim()
        const opts = this.buildRenderOpts(this.openingOn ? this.openingShots : null, s)
        this.peek = await clonePlan(this.cid, s || (this.d.speech_text || ''), opts)
      } catch (e) {
        // 预览算不出来不该挡住出片；真跑时后端还会再判一次
        this.peek = null
      } finally {
        this.peekLoading = false
      }
    },
    // 官方 skill 逐段重写：这一下会调一次对话模型（**花钱**），写完落盘。
    // 落盘后出片读的就是这一版；勾选/参考图/文案/型号任一变了签名就变，
    // 出片会回落到上面的机器版 —— 所以改完参数再点一次。
    async genPeekPrompts(force) {
      if (this.peekAiLoading) return
      this.peekAiLoading = true
      this.peekAiMsg = ''
      try {
        const s = (this.script || '').trim()
        const opts = this.buildRenderOpts(this.openingOn ? this.openingShots : null, s)
        this.peek = await clonePrompts(
          this.cid, s || (this.d.speech_text || ''), opts, !!force)
        this.peekAiMsg = '已写入，出片会用这一版'
      } catch (e) {
        this.peekAiMsg = (e && e.message) ? e.message : '没写成，出片仍用机器版'
      } finally {
        this.peekAiLoading = false
      }
    },
    // 提示词是给人核对用的：选中难（H5 有全局 user-select:none），这里给一键复制
    copyPrompt(text) {
      const data = String(text || '')
      if (!data) return
      uni.setClipboardData({
        data,
        success: () => uni.showToast({ title: '提示词已复制', icon: 'none' }),
        fail: () => uni.showToast({ title: '复制失败', icon: 'none' }),
      })
    },
    async loadReuse() {
      if (!this.wantRegen) {
        this.reuse = null
        return
      }
      this.reuseLoading = true
      try {
        const s = (this.script || '').trim()
        const opts = this.buildRenderOpts(this.openingOn ? this.openingShots : null, s)
        this.reuse = await cloneReusePlan(this.cid, s, opts)
      } catch (e) {
        // 清单算不出来不该挡住出片：清空即可，后端出片时还会再判一次
        this.reuse = null
      } finally {
        this.reuseLoading = false
      }
    },
    async loadEstimate() {
      const text = (this.script || '').trim()
      if (!text) {
        this.est = null
        this.pronCandidates = []
        return
      }
      try {
        // request() 已经把信封拆开，这里拿到的就是 data 本身
        const d = (await cloneEstimate(this.cid, text)) || {}
        this.est = d
        // 候选词由后端挑（英文词/缩写/带币种的数字），念法一律留给人填
        this.pronCandidates = d.candidates || []
        // 候选表变了就只保留还存在的词，别让已删掉的字还挂着念法
        const next = {}
        Object.keys(this.pronounce || {}).forEach((k) => {
          if (this.pronCandidates.indexOf(k) >= 0) next[k] = this.pronounce[k]
        })
        this.pronounce = next
      } catch (e) {
        // 估算失败不该挡住出片，静默即可
        this.est = null
      }
    },
    // 和后端 `translate.split_sentences` 同一条规则：只按句末标点和换行断，
    // 不合并短句、不按字数硬切（外语要保住整句的语气）
    splitLines(t) {
      return String(t || '')
        .split(/[。！？!?；;\n]+/)
        .map((s) => s.trim())
        .filter(Boolean)
    },
    // ---- 逐句台词（C7）--------------------------------------------------
    // 说话人标签：能落到具体的人就写那个人，只有声纹编号就写「说话人N」，
    // 两样都没有就写「说不准」。**绝不把判不出的写成某个人**。
    spkLabel(r) {
      const pid = String((r && r.person) || '')
      if (pid) {
        const p = (this.inv.people || []).find((x) => x.id === pid)
        const d = String((p && (p.desc_zh || p.label)) || '')
        if (d) return d.slice(0, 8)
        return '人物' + pid.replace(/^P/, '')
      }
      const spk = String((r && r.speaker) || '')
      if (spk) return '说话人' + spk
      return '说不准'
    },
    // 同一个说话人全程一个颜色：用编号取模，不是随机
    spkColor(r) {
      const key = String((r && (r.person || r.speaker)) || '')
      let h = 0
      for (let i = 0; i < key.length; i += 1) h = (h * 31 + key.charCodeAt(i)) % 997
      return h
    },
    toggleDub(key) {
      const i = this.dubPick.indexOf(key)
      if (i >= 0) this.dubPick.splice(i, 1)
      else this.dubPick.push(key)
    },
    // 改一行 = 改这个人说的这句话。逐行结果直接作为 `scriptLines` 交给后端，
    // 这样每行仍跟原片那一句一一对应（后端按 `speech_spans` 逐段合成）。
    // 🩸 有行被清空就不传逐行（长度对不上会错位），退回后端自动切句。
    onRowEdit() {
      const rows = this.speechRows.map((r) => String(r.text || '').trim())
      this.script = rows.join('\n')
      this.scriptLines = rows.some((t) => !t) ? null : rows
    },
    // C6：把上面的中文文案逐句翻成配音语种。翻译是**独立一步** —— 先出译文
    // 给人看/改，再拿译文去出片；塞在出片里改一个字就要重翻一遍，还看不到内容。
    async doTranslate() {
      const text = (this.script || '').trim()
      const lang = this.trCode
      if (!text) {
        uni.showToast({ title: '先写文案', icon: 'none' })
        return
      }
      if (lang === 'zh') {
        uni.showToast({ title: '先在「配音音色」里选个外语', icon: 'none' })
        return
      }
      this.trBusy = true
      try {
        const d = (await cloneTranslate(this.cid, text, lang)) || {}
        const lines = (d.lines || []).filter((s) => (s || '').trim())
        if (!lines.length) throw new Error('没有译出内容')
        this.trLang = d.lang || lang
        this.trRatio = Number(d.ratio) || 0
        // 一行一行摆进文本框：能逐句核对，也能直接改。
        // 用换行连接是有意的 —— 出片时按换行断句，改了也还是一行对一行
        this.scriptLines = lines
        this.script = lines.join('\n')
      } catch (e) {
        uni.showToast({ title: e.message || '翻译失败', icon: 'none' })
      } finally {
        this.trBusy = false
      }
    },
    // 音色试听：一句固定演示句，全站按音色缓存 —— 第一个人点过之后都免费
    async playVoiceDemo() {
      if (this.vdBusy) return
      this.vdBusy = true
      try {
        const d = (await cloneVoiceDemo(this.cid, this.voiceId)) || {}
        this.playUrl = cloneAudioUrl(d.path)
        this.playWhat = `音色 ${d.label || this.voiceLabel}`
        // 音色 demo 是固定句，不代表自己文案的时长，清掉上一次的实测值
        this.pvSec = 0
        this.pvDiff = 0
      } catch (e) {
        uni.showToast({ title: e.message || '试听失败', icon: 'none' })
      } finally {
        this.vdBusy = false
      }
    },
    // 文案试听：真念一遍，返回**实测**秒数 —— 语速调得对不对，看这个数
    async playVoicePreview() {
      if (this.pvBusy) return
      let text = (this.script || '').trim()
      if (!text) {
        uni.showToast({ title: '先写文案', icon: 'none' })
        return
      }
      // 后端单次试听上限 600 字：超了就念前面一段，并**明说只念了一部分**
      // （只念了一部分还跟整条原片比时长，得出的百分比毫无意义）
      let partial = false
      if (text.length > 600) {
        text = text.slice(0, 550)
        partial = true
      }
      this.pvBusy = true
      try {
        const rate = this.speechRate === null ? 0 : this.speechRate
        const d = (await cloneVoicePreview(this.cid, text, {
          voice: this.voiceId,
          rate,
          lang: this.langPick,
        })) || {}
        this.playUrl = cloneAudioUrl(d.path)
        this.playWhat = `文案 ${d.voice_label || this.voiceLabel}`
        this.pvSec = Number(d.seconds) || 0
        // 后端只认识原片总长；是不是整段由前端判（它知道完整文案有多长）
        this.pvFull = !partial
        this.pvDiff = this.pvFull ? (Number(d.diff_pct) || 0) : 0
        // 音色被后端换掉（语言不匹配）时说清楚，别让人以为选的那个生效了
        if (d.voice && this.voiceId && d.voice !== this.voiceId) {
          uni.showToast({ title: '音色和语种不匹配，已换默认音色', icon: 'none' })
        } else if (partial) {
          uni.showToast({ title: '文案太长，只念了前 550 字', icon: 'none' })
        }
      } catch (e) {
        uni.showToast({ title: e.message || '试听失败', icon: 'none' })
      } finally {
        this.pvBusy = false
      }
    },
    // 动了滑块就算手动语速（0 也算手动=原速，和「自动」不是一回事：
    // 自动可能挑 -12，而 0 是明确要求别动）；只有点「自动」才回到估算
    onRate(e) {
      const v = Number((e.detail && e.detail.value) || 0)
      this.rateVal = v
      this.rateOn = true
      // 语速变了，上一次的实测秒数就不是这段的时长了
      this.pvSec = 0
      this.pvDiff = 0
    },
    resetRate() {
      this.rateOn = false
      this.rateVal = 0
      this.pvSec = 0
      this.pvDiff = 0
    },
    onPronInput(word, e) {
      const v = (e.detail && e.detail.value) || ''
      this.pronounce = Object.assign({}, this.pronounce, { [word]: v })
    },
    onStretchChange(e) {
      this.allowStretch = !!(e.detail && e.detail.value)
    },
    // 「一次只改一类」：纯开关，拦截在后端 `video_edit._prepare`（单一真相源）。
    // 这里只负责把值带进 payload —— 载荷是 `{...this.edit}`，不用另外拼。
    onOneChange(e) {
      this.edit.one_change = !!(e.detail && e.detail.value)
    },
    async refresh() {
      try {
        const d = await cloneDetail(this.cid)
        const wasBusy = this.busy
        this.d = d
        // 风格参考没有勾选框：传上来就算开，删掉就关 —— 以文件为准，
        // 否则刷新页面后缩略图还在、提示词里却没有那句风格参考
        const rv = !!(d.ref_videos && d.ref_videos.style)
        const ri = !!(d.refs && d.refs.style_ref)
        this.edit.style_video = rv
        this.edit.style_ref = ri && !rv
        // C4：BGM / 音效以文件为准 —— 文件没了就把开关落回「保留原片」，
        // 否则刷新后开关停在「换成我上传的」，出片前又被拦一次
        const af = d.audio_refs || {}
        if (!af.bgm && this.edit.bgm === 'replace') this.edit.bgm = 'keep'
        if (!af.sfx && this.edit.sfx === 'add') this.edit.sfx = 'keep'
        // 分析刚跑完，或者刷新页面进来 —— 两种都要把逐句铺开。
        // 只铺一次（`speechLoaded`）：铺过之后用户改过的内容不能被轮询冲掉。
        if (d.state === 'analyzed' && !this.speechLoaded) {
          this.speechLoaded = true
          if (!this.script) this.loadSpeechRows(d)
          if (wasBusy && this.timer) clearInterval(this.timer)
        }
        // 「只改这一段」：镜头表和上一次的文案都到手了才落
        this.applyOnly()
        // 分析完才知道原片是中文还是英文 —— 音色列表要那时才拉得准
        if (d.state === 'analyzed' && !this.voices.length) this.loadVoices()
        if (d.state === 'failed' && this.timer) clearInterval(this.timer)
      } catch (e) {
        // 轮询失败不打断用户，下一次接着试
      }
    },
    // 分析完把原片台词按句铺开（后端 `speech_lines`）。
    // 顺带把 `scriptLines` 设成原片逐句 —— 不改文案直接出片时，每行正好跟
    // 原片那一句对齐；不设的话后端会按 14 字重切，句子和口型对不上。
    loadSpeechRows(d) {
      const rows = ((d && d.speech_lines) || [])
        .filter((r) => String((r && r.text) || '').trim())
        .map((r) => ({
          text: String(r.text || '').trim(),
          speaker: String(r.speaker || ''),
          person: String(r.person || ''),
        }))
      this.speechRows = rows
      // 默认全部都重配 —— 用户不碰这个开关时，行为和以前一模一样
      const keys = []
      rows.forEach((r) => {
        const k = String(r.person || r.speaker || '__none__')
        if (keys.indexOf(k) < 0) keys.push(k)
      })
      this.dubPick = keys
      if (rows.length) {
        const texts = rows.map((r) => r.text)
        this.script = texts.join('\n')
        this.scriptLines = texts
      } else {
        this.script = (d && d.speech_text) || ''
        this.scriptLines = null
      }
    },
    // 只处理带过来的那一段：与之重叠的镜头保留，其余全部排除
    applyOnly() {
      if (!this.onlySpan || this.onlyApplied || !this.d || !this.d.shots) return
      const a = this.onlySpan[0]
      const b = this.onlySpan[1]
      const shots = this.d.shots || []
      const keep = shots
        .filter((s) => Number(s.end) > a + 0.05 && Number(s.start) < b - 0.05)
        .map((s) => s.i)
      this.excludedShots = shots.filter((s) => keep.indexOf(s.i) < 0).map((s) => s.i)
      // 文案沿用上一版，不从原片 ASR 重来 —— 用户看到的成片就是他改之前的稿子
      if (!this.script && this.fromRid) {
        const r = (this.d.renders || []).find((x) => x.id === this.fromRid)
        if (r && r.script) this.script = r.script
      }
      this.onlyApplied = true
      if (!keep.length) {
        // 这一段没对上任何镜头（比如一句文案跨了切镜边界）：说清楚，别装作限定成功
        this.onlySpan = null
        uni.showToast({ title: '这一段没有对应镜头，已改回整条', icon: 'none' })
      }
    },
    clearOnly() {
      this.onlySpan = null
      this.onlyApplied = false
      this.excludedShots = []
    },
    // 出片前的授权确认：说清这次要生成什么，不是拦着不让点
    // 出片和预览共用同一份参数，避免"预览是一套、真跑是另一套"
    buildRenderOpts(pickedShots, s) {
      const wantRegen = this.wantRegen
      return {
        maskBottom: this.maskBottom,
        regenShots: wantRegen ? pickedShots : null,
        // 换开头走的就是混剪那条路（只把开头几镜选出来），后端不用加新分支
        // 🩸 2026-11-02 静帧链路已删：换开头也只是「勾了开头几镜」，
        //    走自动分诊 + 视频重制
        regenMode: 'auto',
        regenChannel: this.regenChannel,
        regenModel: wantRegen ? this.regenModel : '',
        subjectAsset: wantRegen ? this.subjectAsset.trim() : '',
        // 规格整包下发：换什么 / 声音 / 成片规格（"保什么"归后端默认）
        edit: { ...this.edit },
        // 读音校正只作用于配音；保留原声时没有配音可校正
        pronounce: this.edit.audio === 'original' ? null : this.pronounce,
        // 只有用户明确打开"仍然出片"才允许强行对齐
        allowStretch: this.edit.audio !== 'original' && this.allowStretch,
        // 配音音色 + 语言：保留原声时没有配音，两个都不传
        ttsVoice: this.edit.audio === 'original' ? '' : this.voiceId,
        lang: this.edit.audio === 'original' ? '' : this.langPick,
        // 翻译过的逐行文案：给了后端就不再按 14 字硬切（外语切碎会让总时长翻倍）
        scriptLines: this.edit.audio === 'original' ? null : this.scriptLines,
        // 只重配其中几个人；null = 整片重配（全勾 / 分不出说话人）
        dubLines: this.edit.audio === 'original' ? null : this.dubLines,
        // 每个人各用哪个音色（行号 → 音色）；空 = 全部用上面那个
        dubVoices: this.edit.audio === 'original' ? null : this.dubVoices,
        // 方言代码（火山 explicit_dialect）；空 = 标准普通话
        ttsDialect: this.edit.audio === 'original' ? '' : this.dialect,
        // 试听里手动调好的语速：必须带到出片，否则前台调了半天出片又变回自动
        speechRate: this.edit.audio === 'original' ? null : this.speechRate,
        // 🩸 强制重跑：默认不传（老请求体形状不变）。同样输入本来会命中
        //   逐段缓存、模型一次不调；效果不满意要再抽一次才需要它。
        force: this.forceRerun === true,
      }
    },
    confirmScope(pickedShots, plan) {
      let scope = '只重新配音，画面全部用原片'
      if (this.openingOn) {
        scope = `只重制开头 ${this.openingShots.length} 镜（${this.openingInfo}），其余画面保留原片`
      } else if (this.wantRegen) {
        scope = '逐镜分诊：能保的原片像素就保，静态镜重绘、动作镜交给视频模型'
      }
      // 文案长度会被后端拦下：先说清楚，别让人点了"开始"才看到报错
      if (plan && plan.blocked) {
        return new Promise((resolve) => {
          uni.showModal({
            title: '这次出不了',
            content: plan.blocked,
            showCancel: false,
            confirmText: '去改文案',
            success: () => resolve(false),
            fail: () => resolve(false),
          })
        })
      }
      const lines = [`本次：${scope}`]
      if (plan) {
        const c = plan.change || {}
        const a = plan.audio || {}
        // 🩸 只出前 N 段：后端按**前 N 段**报数（`change.partial`），弹窗必须照它写。
        //   以前点了「先出第 1 段」还显示「2 段 / 共 18.067 秒」—— 说的不是这一下要干的事。
        if (c.partial) {
          lines.push(`只出前 ${c.video_calls} 段（整片共 ${c.total_video_calls} 段 / ${c.total_video_seconds} 秒），其余这次不生成`)
        }
        if (c.video_calls) lines.push(`视频模型：${c.video_calls} 段 / 共 ${c.video_seconds} 秒`)
        if (c.still_calls) lines.push(`静帧重绘：${c.still_calls} 镜 / 共 ${c.still_seconds} 秒`)
        if (c.mode === 'none') lines.push('画面：全部保留原片')
        if (c.partial) {
          // 只出前 N 段时 `render` 在生成完那几段就返回了：不配音、不合成。
          // 这时候还写「配音约 18 秒」是在报一件不会发生的事。
          lines.push('声音：这次不配音、不合成，先看画面片段')
        } else if (a.mode === 'original') {
          lines.push('声音：保留原声')
        } else {
          lines.push(`配音：约 ${a.voice_seconds} 秒（语速 ${a.speech_rate > 0 ? '+' : ''}${a.speech_rate}%）`)
        }
        const k = plan.contract || {}
        if (k.duration) {
          // 只出前 N 段时交付的是片段、不是成片（后端也不拼接），别写成"成片"
          lines.push(`${c.partial ? '这一段' : '成片'}：约 ${k.duration} 秒 · ${k.frames} 帧 · ${k.audio_sample_rate}Hz`)
        }
        // 报价按请求分组报，未知的那组继续显示 —— 不能拿已知几组的和冒充总价
        const p = plan.price || {}
        ;(p.groups || []).forEach((g) => {
          const rate = g.known ? `¥${g.rate}/${g.unit}` : '单价未配置'
          lines.push(`${g.label}：${g.requests} 次 / ${g.units} ${g.unit}（${rate}）`)
        })
        if (p.known) {
          lines.push(`预估：¥${p.amount}${p.note ? '（' + p.note + '）' : ''}`)
        } else {
          // 单价没配就不报数字：写一个"预估 ¥0"比不报价更坏 —— 用户会照着 0 去点
          const miss = (p.unknown || []).join('、')
          lines.push(`费用：单价未配置${miss ? '（缺 ' + miss + '）' : ''}，这里不出金额`)
        }
        if ((plan.warnings || []).length) lines.push(`注意：${plan.warnings[0]}`)
        // 提示词偏长（官方建议中文 ≤500 字）：**只提醒不拦**，单独一行，别被上面那条挤掉
        if (plan.prompt_advice) lines.push(`提示：${plan.prompt_advice}`)
      }
      lines.push('出片后还能改文案重跑：上面标"复用"的段不用重生成，只算要重画的那几段。')
      return new Promise((resolve) => {
        uni.showModal({
          title: '确认出片',
          content: lines.join('\n'),
          confirmText: '开始',
          cancelText: '再看看',
          success: (r) => resolve(!!r.confirm),
          fail: () => resolve(false),
        })
      })
    },
    // 导出配方：任务目录只留 3 天，但"这一版怎么切的"值得留着
    async exportRecipe() {
      try {
        const d = await cloneRecipe(this.cid)
        const text = JSON.stringify(d, null, 2)
        // #ifdef H5
        const blob = new Blob([text], { type: 'application/json' })
        const a = document.createElement('a')
        a.href = URL.createObjectURL(blob)
        a.download = `克隆配方-${this.cid.slice(0, 8)}.json`
        a.click()
        setTimeout(() => URL.revokeObjectURL(a.href), 3000)
        uni.showToast({ title: '已导出', icon: 'none' })
        // #endif
        // #ifndef H5
        uni.setClipboardData({
          data: text,
          success: () => uni.showToast({ title: '配方已复制到剪贴板', icon: 'none' }),
          fail: () => uni.showToast({ title: '导出失败', icon: 'none' }),
        })
        // #endif
      } catch (e) {
        uni.showToast({ title: e.message || '导出失败', icon: 'none' })
      }
    },
    async loadModels() {
      try {
        this.models = await cloneModels()
      } catch (e) {
        // 拉不到就只留「默认」，不影响出片
        this.models = []
      }
    },
    // 音色列表跟着语言走：英文原片默认给英文音色，中文给中文
    async loadVoices(lang) {
      const pick = lang === undefined ? this.langPick : lang
      try {
        const d = (await cloneVoices(this.cid, pick)) || {}
        this.voices = d.voices || []
        // 第二层语言由后端给（数据源是官方音色表），前端不维护第二份
        if (Array.isArray(d.languages) && d.languages.length) this.moreLangs = d.languages
        this.recLang = d.lang || this.recLang
        this.voiceId = d.default || (this.voices[0] && this.voices[0].id) || ''
        // 换语言后旧的分类可能在新列表里一个都没有（英文没「角色扮演」），
        // 留着会筛成空下拉 —— 一律回到「全部」
        this.voiceCat = ''
      } catch (e) {
        // 拉不到就不显示这一块，出片仍然走后端默认音色
        this.voices = []
        this.voiceId = ''
      }
    },
    // 语言代码 → 中文名（第二层里挑过的语言，一级按钮上要显示名字）
    langName(code) {
      const hit = (this.moreLangs || []).find((x) => x.v === code)
      if (hit) return hit.t
      return { zh: '中文', en: '英文' }[code] || code || '中文'
    },
    // 方言代码 → 中文名（音色表的 `dialects` 用的就是中文名，两边要能对上）
    dialectName(code) {
      const hit = Object.keys(this.dialectCode || {})
        .find((k) => this.dialectCode[k] === code)
      return hit || ''
    },
    onLangPick(v) {
      if (this.langPick === v) return
      this.langPick = v
      // 选了小语种就保持展开，用户能看清自己选的是哪一个
      if (v && v !== 'zh' && v !== 'en') this.langMore = true
      // 方言是中文音色才有的能力，换语言一律清掉 —— 留着会让后端收到方言+外语音色
      this.dialect = ''
      // 换语言必须换音色：中文音色念英文、英文音色念中文都有口音
      this.loadVoices(v)
    },
    // 点方言 = 一级筛选。再点一次取消（回标准普通话）。
    // 🩸 取消时**不动音色**：顾客只是不想带口音，不是想换人。
    onVoiceDialect(t) {
      const code = (this.dialectCode || {})[t] || ''
      if (!code) return
      if (this.dialect === code) {
        this.dialect = ''
        return
      }
      this.dialect = code
      // 分类和方言是两道筛子，叠起来可能筛成空列表 —— 点方言就放开分类
      this.voiceCat = ''
      // 当前音色不会说这个方言 → 落到第一个会说的，不然下面显示的名字和实际不符
      if (!this.voiceShown.some((v) => v.id === this.voiceId)) {
        const first = this.voiceShown[0]
        if (first) this.voiceId = first.id
      }
    },
    onVoicePick(e) {
      const i = Number((e.detail && e.detail.value) || 0)
      // 下拉列的是**分类 + 方言过滤后**的音色，取值必须用同一份列表
      const v = this.voiceShown[i]
      if (!v) return
      this.voiceId = v.id
      // 换到不支持方言的音色时，把已选的方言清掉 —— 火山那边会直接报参数错误
      if (!(v.dialects || []).length) this.dialect = ''
    },
    onVoiceCat(k) {
      this.voiceCat = k
      // 当前音色不在新分类里就落到第一个，别让下面显示一个列表外的名字
      if (!this.voiceShown.some((v) => v.id === this.voiceId)) {
        const first = this.voiceShown[0]
        if (first) this.voiceId = first.id
      }
      // 新分类里没人会说这个方言 → 清掉（不然请求体带着方言、音色却不会说，火山报错）
      if (this.dialect) {
        const name = this.dialectName(this.dialect)
        if (!this.voiceShown.some((v) => (v.dialects || []).indexOf(name) >= 0)) {
          this.dialect = ''
        }
      }
    },
    // ---- 每个人各用哪个音色 ----
    onGroupVoice(key, e) {
      const i = Number((e.detail && e.detail.value) || 0)
      const v = this.voices[i]
      if (!v) return
      this.groupVoices = Object.assign({}, this.groupVoices, { [key]: v.id })
    },
    groupVoiceName(key) {
      const id = this.groupVoices[key]
      if (!id) return '跟随上面的音色'
      const v = (this.voices || []).find((x) => x.id === id)
      return v ? v.name : id
    },
    groupVoiceIndex(key) {
      const id = this.groupVoices[key]
      const i = (this.voices || []).findIndex((x) => x.id === id)
      return i < 0 ? 0 : i
    },
    // 范围按钮：没有要换的东西时点它什么也不会发生 —— 那就别让它看起来像已经选了
    pickScope(open) {
      if (!this.wantRegen) {
        uni.showToast({ title: '先在下面勾一项「换什么」', icon: 'none' })
        return
      }
      this.openingOn = open
    },
    // 选通道：跨家族选过的型号要清掉，否则会把 MiniMax 的型号发给火山
    pickChannel(v) {
      this.regenChannel = v
      const m = this.models.find((x) => x.id === this.regenModel)
      if (m && v !== 'auto' && m.channel !== v) this.regenModel = ''
      this.fixResolution()
    },
    // 选型号：型号自带通道，选了它就把通道一起带过去
    pickModel(m) {
      this.regenModel = m.id || ''
      if (m.channel) this.regenChannel = m.channel
      this.fixResolution()
    },
    // 换型号/通道后，原来选的清晰度可能不在新档位里 → 退回自动
    fixResolution() {
      const ok = this.resolOpts.some((r) => r.v === this.edit.resolution)
      if (!ok) this.edit.resolution = 'auto'
    },
    onMaskChange(e) {
      this.maskBottom = e.detail.value
    },
    onAudioPick(v) {
      this.edit.audio = v
      if (v === 'original') {
        // 唱歌 / 跳舞：原片多半自带歌词字幕，遮罩会把画面内容一起盖掉 → 默认不遮
        this.maskBottom = false
      }
      // tts 模式原片声音整条不要，「不要背景音乐」这一档随之不成立
      if (v === 'tts' && this.edit.bgm === 'drop') this.edit.bgm = 'keep'
      // 换回配音时要重新估时长（保留原声时不配音，估了也没用）
      if (v === 'original') this.est = null
      else this.scheduleEstimate()
    },
    hasRefImg(slot) {
      return !!(this.d.refs && this.d.refs[slot])
    },
    slotImg(slot) {
      return cloneFileUrl(this.cid, `slot:${slot}`) + `?t=${this.refVer}`
    },
    toggleSlot(k) {
      this.edit[k] = !this.edit[k]
      // 勾上「人物」就把原片看一遍：多人画面里"换人"必须落到具体某一个
      if (k === 'person') {
        if (!this.edit.person) this.clearPicked()
        else if (!this.inv.ready && !this.invLoading) this.loadInventory()
      }
      // 换产品/换装都要指名"换哪一个"，同样得先认出画面里有什么
      if (k === 'product') {
        if (!this.edit.product) {
          this.edit.product_target = ''
          this.edit.product_target_en = ''
        } else if (!this.inv.ready && !this.invLoading) this.loadInventory()
      }
      if (k === 'wardrobe') {
        if (!this.edit.wardrobe) this.edit.wardrobe_ids = []
        else if (!this.inv.ready && !this.invLoading) this.loadInventory()
      }
    },
    /** 视觉盘点：结果缓存在后端，重复打开/重跑都不再花钱 */
    async loadInventory(refresh = false) {
      if (!this.cid || this.invLoading) return
      this.invLoading = true
      this.invReason = ''
      try {
        const r = await cloneInventory(this.cid, refresh)
        this.inv = r || { ready: false, people: [], products: [], scenes: [] }
        if (!this.inv.ready) this.invReason = (r && r.reason) || '没识别到画面内容'
      } catch (e) {
        this.inv = { ready: false, people: [], products: [], scenes: [] }
        this.invReason = e.message || '识别失败'
      } finally {
        this.invLoading = false
      }
    },
    pickPerson(p) {
      // 多选：点一下加进名单，再点一下移除；清空 = 回到"自动取主角"
      // 🩸 这里**只记「换谁」**。别再往 person_desc 里写 p.desc_zh ——
      // 那是原片里那个人的描述，被当成「换成谁」用就会变成「替换为他自己」。
      const ids = this.pickedIds.slice()
      const k = ids.indexOf(p.id)
      const cap = this.subjectLimit.max
      if (k >= 0) ids.splice(k, 1)
      else if (ids.length < cap) ids.push(p.id)
      else {
        // 到硬上限：说清是型号限制，并给"切到 2.5"这条路（官方口径 2.5 能到 12）
        const t = this.subjectSwitch
        if (!t) {
          uni.showToast({ title: `${this.subjectLimit.label}最多换 ${cap} 个人`, icon: 'none' })
          return
        }
        uni.showModal({
          title: `这个型号最多换 ${cap} 个人`,
          content: `${this.subjectLimit.label}的官方稳定线是 ${this.subjectLimit.stable} 人。`
            + `要换 ${ids.length + 1} 个人，请切到 ${t.label}（1–8 人稳，9–12 人可尝试）。`,
          confirmText: `切到 ${t.label}`,
          cancelText: '先算了',
          success: (res) => {
            if (!res.confirm) return
            this.regenChannel = t.channel
            this.regenModel = t.id
            ids.push(p.id)
            this.edit.person_ids = ids
            this.edit.person_id = ids[0] || ''
          },
        })
        return
      }
      this.edit.person_ids = ids
      // 老字段同步成第一个人：老接口/老记录只认它
      this.edit.person_id = ids[0] || ''
    },
    clearPicked() {
      this.edit.person_ids = []
      this.edit.person_id = ''
    },
    /** 删行后槽位会顺移：把受影响的参考图清掉重传，别让图错位换错人/物 */
    async clearRefSlots(slots) {
      for (const s of slots) {
        if (!this.hasRefImg(s)) continue
        try {
          await cloneDeleteRef(this.cid, s)
          if (this.d.refs) this.d.refs[s] = false
        } catch (e) {
          // 清不掉不拦出片：出片前的"槽位没图"检查会兜住
        }
      }
      this.refVer = Date.now()
    },
    /** 点一下指名"换的是画面里哪一件"，再点取消（不选 = 画面里那件产品） */
    pickProduct(o) {
      const same = this.edit.product_target === o.desc_zh
      this.edit.product_target = same ? '' : (o.desc_zh || '')
      this.edit.product_target_en = same ? '' : (o.desc_en || '')
    },
    /**
     * 换装文字描述：`id` 为空 = 没选具体的人（全体一起换，写进 `wardrobe_desc`）；
     * 有 id = 这个人的那一套（写进 `wardrobe_desc_by_id`）。
     * 用 `$set` 是因为 `wardrobe_desc_by_id` 的键是动态加进来的，Vue 2 不给新键装响应式。
     */
    onWardrobeDesc(id, e) {
      const v = ((e && e.detail && e.detail.value) || '').trim()
      if (!id) {
        this.edit.wardrobe_desc = v
        return
      }
      if (v) this.$set(this.edit.wardrobe_desc_by_id, id, v)
      else this.$delete(this.edit.wardrobe_desc_by_id, id)
    },
    /** 换装按人：点一下加入名单，再点移除；名单为空 = 老语义（全体一起换） */
    pickWardrobe(id) {
      const ids = (this.edit.wardrobe_ids || []).slice()
      const k = ids.indexOf(id)
      if (k < 0) {
        ids.push(id)
        this.edit.wardrobe_ids = ids
        return
      }
      const slots = []
      for (let j = k; j < ids.length; j += 1) {
        slots.push(j === 0 ? 'wardrobe' : `wardrobe${j + 1}`)
      }
      ids.splice(k, 1)
      this.edit.wardrobe_ids = ids
      if (slots.length) this.clearRefSlots(slots)
    },
    /** 说话人：官方 base-en:127 —— 只有说话的人拿号，不说话的不给号 */
    pickSpeaker(id) {
      const ids = (this.edit.speaker_ids || []).slice()
      const k = ids.indexOf(id)
      if (k >= 0) ids.splice(k, 1)
      else ids.push(id)
      this.edit.speaker_ids = ids
    },
    /** 人物槽的标题：选了人就把"第几位、是谁"写出来，别让用户自己数 */
    slotTitle(k, t) {
      if (k !== 'person') {
        return this.hasRefImg(k) ? `已上传${t}参考图` : `传一张${t}图（可选）`
      }
      const ids = this.pickedIds
      const p = ids.length ? (this.inv.people || []).find((x) => x.id === ids[0]) : null
      const who = p ? `第 1 位：${p.desc_zh}` : '人物'
      if (ids.length > 1) return `${who}（共换 ${ids.length} 人）`
      return this.hasRefImg(k) ? `已上传${who}参考图` : `传一张${who}图（可选）`
    },
    fmtSpan(list) {
      const one = (a) => `${a.start.toFixed(1)}–${a.end.toFixed(1)}s`
      return (list || []).map(one).join('、')
    },
    toggleShot(i) {
      const k = this.excludedShots.indexOf(i)
      if (k >= 0) this.excludedShots.splice(k, 1)
      else this.excludedShots.push(i)
    },
    // 风格参考视频（A9）：H5 用文件选择，小程序用相册/拍摄（按端编译）
    pickStyleVideo() {
      if (this.slotLoading) return
      const go = (paths) => {
        const p = (paths || [])[0]
        if (p) this.uploadStyleVideo(p)
      }
      // #ifdef H5
      uni.chooseFile({
        count: 1,
        extension: ['.mp4', '.mov', '.m4v'],
        success: (r) => go(r.tempFilePaths),
      })
      // #endif
      // #ifndef H5
      uni.chooseVideo({
        sourceType: ['album', 'camera'],
        compressed: true,
        maxDuration: 15,
        success: (r) => go([r.tempFilePath]),
      })
      // #endif
    },
    async uploadStyleVideo(filePath) {
      this.slotLoading = 'style_video'
      try {
        const d = await cloneUploadStyleVideo(this.cid, filePath)
        // 和后端一致：风格只有一个来源，传了视频就不再有图
        this.edit.style_video = true
        this.edit.style_ref = false
        await this.refresh()
        uni.showToast({ title: `风格视频已上传（${d.duration} 秒）`, icon: 'success' })
      } catch (e) {
        uni.showModal({ title: '上传失败', content: e.message, showCancel: false })
      } finally {
        this.slotLoading = ''
      }
    },
    async clearStyleVideo() {
      if (this.slotLoading) return
      this.slotLoading = 'style_video'
      try {
        await cloneDeleteStyleVideo(this.cid)
        this.edit.style_video = false
        await this.refresh()
      } catch (e) {
        uni.showModal({ title: '删除失败', content: e.message, showCancel: false })
      } finally {
        this.slotLoading = ''
      }
    },
    // 原片声音处理（C4）：选「换成我上传的 / 加一段音效」时直接弹选择，
    // 少点一步（选完没文件等于没选，出片前还会被拦一次）
    onBgmPick(v) {
      if (v === 'replace' && !this.hasBgmFile) {
        this.edit.bgm = 'replace'
        this.pickAudio('bgm')
        return
      }
      this.edit.bgm = v
    },
    onSfxPick(v) {
      if (v === 'add' && !this.hasSfxFile) {
        this.edit.sfx = 'add'
        this.pickAudio('sfx')
        return
      }
      this.edit.sfx = v
    },
    pickAudio(kind) {
      if (this.slotLoading) return
      const go = (paths) => {
        const p = (paths || [])[0]
        if (p) this.uploadAudio(kind, p)
      }
      // #ifdef H5
      uni.chooseFile({
        count: 1,
        extension: ['.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg', '.opus'],
        success: (r) => go(r.tempFilePaths),
      })
      // #endif
      // #ifndef H5
      uni.chooseMessageFile({
        count: 1,
        type: 'file',
        extension: ['mp3', 'wav', 'm4a', 'aac', 'flac', 'ogg', 'opus'],
        success: (r) => go((r.tempFiles || []).map((f) => f.path)),
      })
      // #endif
    },
    async uploadAudio(kind, filePath) {
      this.slotLoading = kind
      try {
        const d = await cloneUploadAudio(this.cid, kind, filePath)
        await this.refresh()
        uni.showToast({
          title: `${kind === 'bgm' ? '背景音乐' : '音效'}已上传（${d.duration} 秒）`,
          icon: 'success',
        })
      } catch (e) {
        // 传失败就把开关落回去，别让界面显示"已选"但盘上没有文件
        if (kind === 'bgm') this.edit.bgm = this.hasBgmFile ? 'replace' : 'keep'
        if (kind === 'sfx') this.edit.sfx = this.hasSfxFile ? 'add' : 'keep'
        uni.showModal({ title: '上传失败', content: e.message, showCancel: false })
      } finally {
        this.slotLoading = ''
      }
    },
    async clearAudio(kind) {
      if (this.slotLoading) return
      this.slotLoading = kind
      try {
        await cloneDeleteAudio(this.cid, kind)
        if (kind === 'bgm') this.edit.bgm = 'keep'
        if (kind === 'sfx') this.edit.sfx = 'keep'
        await this.refresh()
      } catch (e) {
        uni.showModal({ title: '删除失败', content: e.message, showCancel: false })
      } finally {
        this.slotLoading = ''
      }
    },
    chooseRef(slot, label) {
      if (this.slotLoading) return
      uni.chooseImage({
        count: 1,
        sizeType: ['compressed'],
        sourceType: ['album', 'camera'],
        success: async (res) => {
          const p = (res.tempFilePaths || [])[0]
          if (!p) return
          this.slotLoading = slot
          try {
            await cloneUploadRef(this.cid, slot, p)
            // 传了图就默认勾上这个槽位 —— 用户传图的意图就是要换它
            this.edit[slot] = true
            this.refVer = Date.now()
            await this.refresh()
            uni.showToast({ title: `${label}图已上传`, icon: 'success' })
          } catch (e) {
            uni.showModal({ title: '上传失败', content: e.message, showCancel: false })
          } finally {
            this.slotLoading = ''
          }
        },
      })
    },
    // 选一段人声去训练复刻音色（H5 和小程序的文件选择 API 不一样，按端编译）
    pickVoiceAudio() {
      const go = (paths) => {
        const p = (paths || [])[0]
        if (p) this.trainVoice(p)
      }
      // #ifdef H5
      uni.chooseFile({
        count: 1,
        extension: ['.wav', '.mp3', '.m4a', '.aac', '.ogg'],
        success: (r) => go(r.tempFilePaths),
      })
      // #endif
      // #ifndef H5
      uni.chooseMessageFile({
        count: 1,
        type: 'file',
        extension: ['wav', 'mp3', 'm4a', 'aac', 'ogg'],
        success: (r) => go((r.tempFiles || []).map((f) => f.path)),
      })
      // #endif
    },
    async trainVoice(filePath) {
      const sid = (this.vcSpeaker || '').trim()
      if (!sid.startsWith('S_')) {
        uni.showToast({ title: '先填 S_ 开头的音色槽位 ID', icon: 'none' })
        return
      }
      this.vcUploading = true
      this.vcStatus = '提交训练…'
      try {
        const lang = this.langPick || this.recLang || 'zh'
        const r = await cloneTrainVoice(sid, filePath, lang)
        this.vcStatus = `已提交（${r.status_text || '训练中'}）· ${r.seconds || '?'} 秒素材`
        // 训练提交后直接选用它：用户不用再去音色列表里找（目录里本来也没有）
        this.voiceId = sid
        if (r.warning) {
          uni.showModal({ title: '素材提示', content: r.warning, showCancel: false })
        }
        this.pollVoice(sid)
      } catch (e) {
        this.vcStatus = ''
        uni.showModal({ title: '训练失败', content: e.message, showCancel: false })
      } finally {
        this.vcUploading = false
      }
    },
    pollVoice(sid) {
      let n = 0
      const timer = setInterval(async () => {
        n += 1
        try {
          const s = await cloneVoiceStatus(sid)
          const left = s.available_training_times != null
            ? ` · 剩 ${s.available_training_times} 次` : ''
          this.vcStatus = `${s.status_text}${left}`
          if (s.demo_audio) this.vcDemo = s.demo_audio
          if (s.ready || s.status === 3 || n >= 40) clearInterval(timer)
        } catch (e) {
          if (n >= 5) clearInterval(timer)
        }
      }, 6000)
    },
    async render(maxSegments = 0) {
      const s = (this.script || '').trim()
      if (!s && this.edit.audio !== 'original') {
        uni.showToast({ title: '请先写新文案', icon: 'none' })
        return
      }
      const wantRegen = this.wantRegen
      // 多版本方向也算「换什么」：只写方向、不勾槽位时不该拦
      const dirs = this.multiOn
        ? this.variantDirs.map((x) => (x || '').trim()).filter(Boolean)
        : []
      if (wantRegen && !this.hasAnyChange && !dirs.length) {
        uni.showToast({ title: '先选「换什么」或写补充说明', icon: 'none' })
        return
      }
      // 🩸 2026-10-27：勾了「服装造型」却既没传图也没写描述时，后端原先会兜底
      // 拼一句「将其中的服装修改为另一套服装」—— 那不是官方 `guide:39`
      // 「修改为<新特征>」里的"新特征"，等于让模型随便换一套（结果随机、不可复现）。
      // 后端已经把这类空指令去掉了，这里再拦一道。
      // 🩸 2026-10-27 二次修正：以前**只要有一个人有图就整体放行**，多人换装里
      // 没素材的那个会被后端静默跳过（图白传、用户看不出来）。改成**逐个查**：
      // 每个人手里要么有图，要么有一句「换成什么」。
      if (wantRegen && this.edit.wardrobe) {
        const rows = this.wardrobeRows.length
          ? this.wardrobeRows
          : [{ slot: 'wardrobe', id: '' }]
        const missing = rows.filter((w) => {
          if (this.hasRefImg(w.slot)) return false
          const d = w.id
            ? (this.edit.wardrobe_desc_by_id || {})[w.id] || ''
            : this.edit.wardrobe_desc || ''
          return !String(d).trim()
        })
        if (missing.length) {
          uni.showToast({ title: '换装要传图，或写一句换成什么', icon: 'none' })
          return
        }
      }
      // 排除法：空数组 = 全部参与；有排除就换算成"要处理的镜头号"
      const allIds = (this.d.shots || []).map((s) => s.i)
      // 换开头 = 由前 N 秒决定要处理哪几镜，不看用户手动排除
      const pickedShots = this.openingOn
        ? this.openingShots
        : (this.excludedShots.length
          ? allIds.filter((i) => this.excludedShots.indexOf(i) < 0)
          : null)
      if (pickedShots && !pickedShots.length) {
        uni.showToast({ title: '至少留一个镜头要换', icon: 'none' })
        return
      }
      // 勾了人物但既没图也没 asset：后端会拒，前端先说清楚。
      // 🩸 不能再拿 person_desc 兜底 —— 诊断页选人时填进去的是原片那个人的
      // 描述，编译出来等于「换成他自己」，实测那条 12s 片连人都没换。
      if (wantRegen && this.edit.person
          && !this.subjectAsset.trim() && !this.hasRefImg('person')) {
        uni.showToast({ title: '要换人物：传张图或填资产 ID', icon: 'none' })
        return
      }
      // 产品/场景/服装：勾了但既没图也没写描述 → 出了也不会变
      // （火山会自己编一个换上去，H3 干脆一个字都不写）。口径与后端 `missing_material` 一致
      if (wantRegen) {
        const lack = []
        if (this.edit.product && !this.hasRefImg('product')
            && !(this.edit.product_desc || '').trim()) lack.push('产品')
        if (this.edit.scene && !this.hasRefImg('scene')
            && !(this.edit.scene_desc || '').trim()) lack.push('场景')
        // 服装造型不在这里查：上面已经**逐个人**查过（多人换装时只看 `wardrobe`
        // 一个槽位会漏掉第 2、3 个人）。两处都查 = 报错文案各说各的。
        if (lack.length) {
          uni.showToast({
            title: `${lack.join('、')}：传张图，或写一句换成什么`,
            icon: 'none',
          })
          return
        }
      }
      // 人数超过型号上限：后端也会拒，但别让人等到点了"开始"才看见
      if (wantRegen && this.edit.person && this.pickedIds.length > this.subjectLimit.max) {
        const t = this.subjectSwitch
        uni.showToast({
          title: `${this.subjectLimit.label}最多换 ${this.subjectLimit.max} 个人`
            + (t ? `，请切到 ${t.label}` : ''),
          icon: 'none',
        })
        return
      }
      // 选了多个人：每个人都要有自己的图 —— 没图就不知道换成谁，别让后端静默跳过
      // 🩸 只查**已绑到具体的人**的格子：`extraPeople` 现在还会多留一格"先传图后选人"的
      //    空位，拿它当必填会把只换一个人的任务拦下来。
      if (wantRegen && this.edit.person && this.extraPeople.length) {
        const miss = this.extraPeople.find((pp) => pp.bound && !this.hasRefImg(pp.slot))
        if (miss) {
          uni.showToast({ title: `${miss.label} 还没传图`, icon: 'none' })
          return
        }
      }
      // 🩸 2026-10-27（主人：「其实还是 B 更加好」）：多人同框又没指定换谁 → 默认换主角。
      // 🩸 这次**真的把主角写进 `person_ids`**。以前的 B 只有弹窗文案：用户点
      // 「换主角」继续走，`person_ids` 仍是空的，后端编译出来的还是
      // 「将其中的人物替换为@图片1中的人物」—— 弹窗说了、提示词没做，
      // 用户以为换的是主角，模型其实在画面里自己猜（2026-10-25 那次整片一帧没换）。
      // 主角有依据，不是取列表第一个：盘点 `main` = 出现时长最长 / 占据画面最大
      // （`vision_plan.py:116` 的模型提示词；`:440` 还有"没人标就按时长补"的兜底）。
      // 🩸 2026-10-27：按**可点列表**判（群体项已在上面的 `invPickable` 滤掉）。
      // 只剩一个人时不必弹窗问「换谁」—— 画面里就他一个能换。
      if (wantRegen && this.edit.person && this.inv.ready
          && this.invPickable.length > 1 && !this.pickedIds.length) {
        const main = this.invPickable.find((p) => p.main) || this.invPickable[0]
        const go = await new Promise((resolve) => {
          uni.showModal({
            title: `画面里有 ${this.invPickable.length} 个人`,
            content: `没指定换谁，就换主角：${main.desc_zh}`
              + '（画面里出现时间最长 / 占画面最大的那位）。要换别人点「去选人」。',
            confirmText: '就换主角',
            cancelText: '去选人',
            success: (r) => resolve(!!r.confirm),
            fail: () => resolve(false),
          })
        })
        if (!go) return
        // 落线：主角写进名单，后端才知道换的是谁（老字段同步，老接口还认它）
        this.edit.person_ids = [main.id]
        this.edit.person_id = main.id
      }
      if (this.submitting) return
      const opts = this.buildRenderOpts(pickedShots, s)
      // 🩸 只出前 N 段（预览）：0/不传 = 全部。继续出全部时**不传**，
      //   后端按同样的参数重跑，前面的段命中缓存不重复扣费。
      if (maxSegments > 0) opts.maxSegments = maxSegments
      // 付费前先让后端把"这一下要生成多少"算出来（全本地、不花钱）：
      // 会动几段、调几次模型、成片多少帧。算不出来就退回旧的文字确认，不阻塞。
      // 报价按第一版的开头方向算：方向本身就是这次画面改动的来源
      const planOpts = JSON.parse(JSON.stringify(opts))
      if (dirs.length) {
        planOpts.edit.extra = [this.edit.extra, dirs[0]].filter(Boolean).join('；')
      }
      let plan = null
      try {
        plan = await clonePlan(this.cid, s || (this.d.speech_text || ''), planOpts)
      } catch (e) {
        plan = null
      }
      const go = await this.confirmScope(pickedShots, plan)
      if (!go) return
      // 多版本：每个方向各出一版。任务同一时间只跑一条，所以必须等上一条结束。
      // 方向是用户写的内容，我们只负责排队和把方向拼进补充说明。
      if (this.multiOn) {
        if (dirs.length < 2) {
          uni.showToast({ title: '多版本至少写 2 个方向', icon: 'none' })
          return
        }
        const goMulti = await new Promise((resolve) => {
          uni.showModal({
            title: `连续出 ${dirs.length} 版`,
            content: `每一版都会重新配音、重新生成开头，费用约为单版的 ${dirs.length} 倍。中途失败会停下，已完成的版本留在历史里。`,
            confirmText: `出 ${dirs.length} 版`,
            cancelText: '再想想',
            success: (r) => resolve(!!r.confirm),
            fail: () => resolve(false),
          })
        })
        if (!goMulti) return
      }
      this.submitting = true
      try {
        if (dirs.length) {
          for (let i = 0; i < dirs.length; i += 1) {
            uni.showLoading({ title: `第 ${i + 1}/${dirs.length} 版`, mask: true })
            const vOpts = JSON.parse(JSON.stringify(opts))
            // 每一版只改「开头方向」，其它换什么/保什么/音色完全一致 ——
            // 不然比的就不是开头，而是两条不同的片子
            vOpts.edit.extra = [this.edit.extra, dirs[i]].filter(Boolean).join('；')
            const r = await cloneRender(this.cid, s || (this.d.speech_text || ''), vOpts)
            await this.waitRender(r.render_id)
          }
          uni.hideLoading()
          uni.showToast({ title: `已出 ${dirs.length} 版`, icon: 'success' })
          uni.navigateTo({ url: '/pages/history/history' })
          return
        }
        const r = await cloneRender(this.cid, s || (this.d.speech_text || ''), opts)
        uni.navigateTo({ url: `/pages/clone/progress?cid=${r.id}&rid=${r.render_id}` })
      } catch (e) {
        uni.hideLoading()
        uni.showModal({ title: '提交失败', content: e.message, showCancel: false })
      } finally {
        this.submitting = false
      }
    },
    // 等一条出片跑完（done/failed 都算结束）。任务一次只跑一条，
    // 不等就提交下一条会被后端以「正在跑」拒掉。
    waitRender(rid) {
      return new Promise((resolve, reject) => {
        let misses = 0
        const timer = setInterval(async () => {
          try {
            const d = await cloneRenderDetail(this.cid, rid)
            misses = 0
            if (d.state === 'done') {
              clearInterval(timer)
              resolve(d)
            } else if (d.state === 'failed') {
              clearInterval(timer)
              reject(new Error(d.error || '这一版出片失败'))
            }
          } catch (e) {
            // 轮询偶发失败不打断，连续 20 次（约 1 分钟）才放弃
            misses += 1
            if (misses >= 20) {
              clearInterval(timer)
              reject(new Error(e.message || '查不到出片进度'))
            }
          }
        }, 3000)
      })
    },
    restart() {
      uni.redirectTo({ url: '/pages/clone/index' })
    },
  },
}
</script>

<style lang="scss" scoped>
.page {
  min-height: 100vh;
  padding: 28rpx 28rpx 60rpx;
}
.block {
  padding: 80rpx 40rpx;
  text-align: center;
}
.pulse {
  font-size: 32rpx;
  font-weight: 600;
  margin-bottom: 40rpx;
}
.bar {
  height: 14rpx;
  border-radius: 999rpx;
  background: #ececf3;
  overflow: hidden;
}
.bar-in {
  height: 100%;
  border-radius: 999rpx;
  background: linear-gradient(90deg, #ff6b4a, #ff3d7f);
  transition: width 0.4s ease;
}
.stage {
  margin-top: 24rpx;
  font-size: 26rpx;
  color: #ff5a3c;
}
.hint {
  margin-top: 12rpx;
  font-size: 24rpx;
  color: #9aa0a6;
}
.bad {
  font-size: 32rpx;
  font-weight: 600;
  color: #e5484d;
  margin-bottom: 20rpx;
}
.err {
  font-size: 26rpx;
  color: #6b7280;
  line-height: 1.7;
  margin-bottom: 48rpx;
  /* 报错正文现在带错误码 / request id / 证据文件路径（2026-10-23），
     长串不折行会横向撑破页面 —— 保留换行、允许在任意字符处断。 */
  white-space: pre-wrap;
  word-break: break-all;
}
.hero-card {
  display: flex;
  align-items: center;
  padding: 24rpx;
  background: #fff;
  border-radius: 24rpx;
  box-shadow: 0 8rpx 30rpx rgba(31, 45, 90, 0.08);
}
.cover {
  width: 132rpx;
  height: 176rpx;
  border-radius: 14rpx;
  background: #eef1fb;
  flex-shrink: 0;
}
.hero-info {
  margin-left: 24rpx;
  flex: 1;
  min-width: 0;
}
.title {
  font-size: 30rpx;
  font-weight: 600;
  line-height: 1.4;
}
.author {
  margin-top: 10rpx;
  font-size: 24rpx;
  color: #9aa0a6;
}
.badge {
  display: inline-block;
  margin-top: 12rpx;
  padding: 4rpx 14rpx;
  font-size: 20rpx;
  color: #ff5a3c;
  background: #ffefec;
  border-radius: 999rpx;
}
.grid {
  display: flex;
  margin-top: 24rpx;
  background: #fff;
  border-radius: 24rpx;
  padding: 28rpx 0;
  box-shadow: 0 8rpx 30rpx rgba(31, 45, 90, 0.08);
}
.cell {
  flex: 1;
  text-align: center;
}
.cell-v {
  font-size: 34rpx;
  font-weight: 700;
  color: #ff5a3c;
}
.cell-k {
  margin-top: 8rpx;
  font-size: 22rpx;
  color: #9aa0a6;
}
.card {
  margin-top: 24rpx;
  padding: 28rpx;
  background: #fff;
  border-radius: 24rpx;
  box-shadow: 0 8rpx 30rpx rgba(31, 45, 90, 0.08);
}
.card-title {
  font-size: 28rpx;
  font-weight: 600;
  margin-bottom: 18rpx;
}
.line {
  font-size: 26rpx;
  line-height: 1.9;
  color: #4b5563;
}
.em {
  color: #ff5a3c;
  font-weight: 600;
}
.dim {
  color: #9aa0a6;
}
.strip {
  white-space: nowrap;
}
.kf {
  display: inline-block;
  width: 150rpx;
  height: 200rpx;
  margin-right: 14rpx;
  border-radius: 12rpx;
  background: #eef1fb;
}
.sheet {
  width: 100%;
  margin-top: 16rpx;
  border-radius: 14rpx;
  background: #eef1fb;
}
.sheet-btn {
  margin-top: 16rpx;
}
/* 「只改这一段」：和普通卡片分开，让人一眼看出这次只动一小截 */
.only {
  border-left: 8rpx solid #ff5a3c;
}
.variant-row {
  display: flex;
  align-items: center;
  gap: 12rpx;
  margin-top: 14rpx;
  flex-wrap: wrap;
}
.orig {
  padding: 20rpx;
  margin-bottom: 20rpx;
  background: #f6f7fb;
  border-radius: 14rpx;
}
.orig-k {
  font-size: 22rpx;
  color: #9aa0a6;
  margin-bottom: 8rpx;
}
.orig-v {
  font-size: 25rpx;
  line-height: 1.7;
  color: #4b5563;
}
.input {
  width: 100%;
  min-height: 240rpx;
  padding: 24rpx;
  font-size: 28rpx;
  line-height: 1.7;
  background: #f6f7fb;
  border-radius: 16rpx;
}
.counter {
  text-align: right;
  font-size: 22rpx;
  color: #c0c4cc;
  margin: 8rpx 4rpx 0;
}
/* 只重配其中几个人 */
.dub-box {
  padding: 18rpx;
  margin-bottom: 18rpx;
  background: #f6f7fb;
  border-radius: 14rpx;
}
.dub-title {
  font-size: 24rpx;
  color: #4b5563;
  margin-bottom: 12rpx;
}
.dub-note {
  margin-top: 10rpx;
  font-size: 22rpx;
  line-height: 1.6;
  color: #8a6d3b;
}
/* 每个人各用哪个音色 */
.dv-row {
  margin-top: 14rpx;
  padding-top: 12rpx;
  border-top: 1px solid #eceef3;
}
.dv-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8rpx 0;
}
.dv-k {
  font-size: 23rpx;
  color: #6b7280;
}
.dv-v {
  font-size: 23rpx;
  color: #ff5a3c;
}
/* 逐句台词：一行一句，左边是说话人标签 */
.spk-list {
  margin-top: 6rpx;
}
.spk-note {
  padding: 14rpx 18rpx;
  margin-bottom: 14rpx;
  font-size: 22rpx;
  line-height: 1.6;
  color: #8a6d3b;
  background: #fff8e6;
  border-radius: 12rpx;
}
.spk-row {
  display: flex;
  align-items: flex-start;
  margin-bottom: 14rpx;
}
.spk-tag {
  flex: 0 0 auto;
  width: 108rpx;
  padding: 10rpx 0;
  margin-right: 12rpx;
  font-size: 20rpx;
  line-height: 1.4;
  text-align: center;
  color: #fff;
  border-radius: 10rpx;
  word-break: break-all;
}
.spk-c0 { background: #5b8ff9; }
.spk-c1 { background: #f6903d; }
.spk-c2 { background: #5ad8a6; }
.spk-c3 { background: #9270ca; }
.spk-input {
  flex: 1 1 auto;
  min-height: 96rpx;
  padding: 16rpx 18rpx;
  font-size: 26rpx;
  line-height: 1.6;
}
.switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 20rpx 0 28rpx;
}
.switch-label {
  font-size: 26rpx;
  color: #4b5563;
}
.regen {
  margin: 8rpx 0 28rpx;
  padding: 24rpx;
  background: #fbfbfe;
  border: 1rpx solid #ececf3;
  border-radius: 18rpx;
}
.regen-head {
  display: flex;
  align-items: baseline;
  margin-bottom: 16rpx;
}
.regen-title {
  font-size: 28rpx;
  font-weight: 600;
  color: #1b1f27;
  margin-right: 12rpx;
}
.regen-note {
  font-size: 22rpx;
  color: #9aa0a6;
}
.pick-line {
  margin: 8rpx 0 18rpx;
  text-align: center;
  font-size: 23rpx;
  color: #6b7280;
}
/* 出片前预览：逐段提示词 */
.peek {
  margin: 6rpx 0 18rpx;
  border: 1rpx solid #e5e7eb;
  border-radius: 12rpx;
  overflow: hidden;
}
.peek-head {
  display: flex;
  align-items: baseline;
  padding: 18rpx 20rpx;
  background: #f9fafb;
}
.peek-title {
  font-size: 25rpx;
  color: #374151;
}
.peek-sub {
  margin-left: 8rpx;
  font-size: 21rpx;
  color: #9ca3af;
}
.peek-body {
  padding: 10rpx 20rpx 18rpx;
}
.peek-tip {
  padding: 10rpx 0;
  font-size: 23rpx;
  color: #9ca3af;
}
.peek-item {
  margin-top: 16rpx;
}
.peek-tag {
  margin-bottom: 8rpx;
  font-size: 22rpx;
  color: #6b7280;
}
.peek-text {
  display: block;
  font-size: 22rpx;
  line-height: 1.6;
  color: #111827;
  word-break: break-all;
  white-space: pre-wrap;
  /* 全局 `html,body{user-select:none}` 会让提示词划不中（uni-app H5 默认） */
  -webkit-user-select: text;
  user-select: text;
}
.peek-copy {
  display: inline-block;
  margin-top: 8rpx;
  padding: 4rpx 14rpx;
  font-size: 21rpx;
  color: #4b5563;
  border: 1rpx solid #d1d5db;
  border-radius: 8rpx;
}
/* 官方 skill 逐段重写（会调一次模型，所以按钮上把花费写出来） */
.peek-ai {
  margin-top: 20rpx;
  padding-top: 16rpx;
  border-top: 1rpx dashed #e5e7eb;
}
.peek-ai-btn {
  margin: 0;
  font-size: 23rpx;
  line-height: 2.4;
  color: #ffffff;
  background: #4b5563;
  border-radius: 10rpx;
}
.peek-ai-btn[disabled] {
  opacity: 0.6;
}
.peek-ai-tip {
  display: block;
  margin-top: 8rpx;
  font-size: 21rpx;
  color: #6b7280;
}
.mode-row {
  display: flex;
  margin-bottom: 18rpx;
}
/* 没有要换的东西时：按钮变灰，表示"现在选它没意义" */
.mode-row.muted .mode {
  color: #b6bac2;
  background: #fafbfc;
  border-color: #eff0f4;
}
.mode {
  flex: 1;
  text-align: center;
  padding: 16rpx 0;
  margin-right: 12rpx;
  font-size: 25rpx;
  color: #6b7280;
  background: #fff;
  border: 1rpx solid #e6e8ef;
  border-radius: 12rpx;
}
.mode:last-child {
  margin-right: 0;
}
.mode.on {
  color: #fff;
  background: linear-gradient(135deg, #ff6b4a 0%, #ff3d7f 100%);
  border-color: transparent;
  font-weight: 600;
}
.add-row {
  margin-top: 16rpx;
  padding: 18rpx;
  text-align: center;
  font-size: 26rpx;
  color: #ff5a3c;
  background: #fff6f3;
  border: 1rpx dashed #ffb9a8;
  border-radius: 14rpx;
}
.sub-row {
  display: flex;
  align-items: center;
  margin-top: 18rpx;
  padding: 16rpx;
  background: #fff;
  border: 1rpx solid #ececf3;
  border-radius: 14rpx;
}
.sub-img {
  width: 88rpx;
  height: 88rpx;
  border-radius: 10rpx;
  background: #eef1fb;
  flex-shrink: 0;
  margin-right: 16rpx;
}
.sub-txt {
  flex: 1;
  min-width: 0;
}
.sub-k {
  font-size: 25rpx;
  color: #1b1f27;
}
.sub-v {
  margin-top: 6rpx;
  font-size: 21rpx;
  color: #9aa0a6;
}
/* 传了图却没有对应的人 —— 静默忽略最坑，得说清"这张不会用" */
.sub-v.warn {
  color: #d93025;
}
.sub-btn {
  flex-shrink: 0;
  margin-left: 12rpx;
  background: #ffefec;
  color: #ff5a3c;
  border-radius: 999rpx;
  font-size: 23rpx;
}
/* 语速滑块：和上面的 sub-row 同一条视觉线 */
.rate-row {
  display: flex;
  align-items: center;
  margin-top: 12rpx;
  padding: 8rpx 16rpx;
  background: #fff;
  border: 1rpx solid #ececf3;
  border-radius: 14rpx;
}
.rate-label {
  flex-shrink: 0;
  font-size: 25rpx;
  color: #1b1f27;
  margin-right: 12rpx;
}
.rate-slider {
  flex: 1;
  min-width: 0;
  margin: 0 12rpx;
}
.chan-row {
  display: flex;
  margin-top: 16rpx;
}
.chan {
  padding: 10rpx 26rpx;
  margin-right: 12rpx;
  font-size: 23rpx;
  color: #6b7280;
  background: #fff;
  border: 1rpx solid #e6e8ef;
  border-radius: 999rpx;
}
.chan.on {
  color: #ff5a3c;
  border-color: #ff5a3c;
  background: #fff5f2;
  font-weight: 600;
}
.chan-hint {
  margin-top: 12rpx;
  font-size: 21rpx;
  line-height: 1.6;
  color: #9aa0a6;
}
/* 🩸 必须给显式高度：uni 基础样式是 uni-input{height:1.4em}，
   若只写上下 padding 又不给 height，border-box 下内容高度会被压成 0
   → 内层 <input> 高 0，看着有框却点不动、打不进字。 */
.asset-input {
  width: 100%;
  margin-top: 16rpx;
  box-sizing: border-box;
  height: 70rpx;
  min-height: 70rpx;
  padding: 0 20rpx;
  font-size: 24rpx;
  background: #fff;
  border: 1rpx solid #ececf3;
  border-radius: 14rpx;
}
.asset-hint {
  margin-top: 10rpx;
  font-size: 21rpx;
  line-height: 1.6;
  color: #9aa0a6;
}
.asset-hint.warn {
  color: #d97706;
}
.regen-input {
  width: 100%;
  min-height: 130rpx;
  padding: 20rpx;
  font-size: 26rpx;
  line-height: 1.6;
  background: #fff;
  border-radius: 14rpx;
}
.ratio-row {
  display: flex;
  margin-top: 18rpx;
}
.ratio {
  flex: 1;
  text-align: center;
  padding: 14rpx 0;
  margin-right: 12rpx;
  font-size: 24rpx;
  color: #6b7280;
  background: #fff;
  border: 1rpx solid #e6e8ef;
  border-radius: 999rpx;
}
.ratio:last-child {
  margin-right: 0;
}
.ratio.on {
  color: #ff5a3c;
  border-color: #ff5a3c;
  background: #fff5f2;
  font-weight: 600;
}
.regen-hint {
  margin-top: 14rpx;
  font-size: 22rpx;
  line-height: 1.6;
  color: #8b90a0;
}
.scope-line {
  margin-top: 12rpx;
  font-size: 22rpx;
  line-height: 1.6;
  color: #ff5a3c;
}
/* 花钱前的单子：复用几段 / 要重画几段 */
.reuse {
  margin-top: 18rpx;
  padding: 20rpx 22rpx;
  border-radius: 16rpx;
  background: rgba(56, 189, 248, 0.08);
  border: 1rpx solid rgba(56, 189, 248, 0.25);
}
.reuse-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.reuse-title {
  font-size: 26rpx;
  font-weight: 600;
  color: #e8f4ff;
}
.reuse-note {
  font-size: 22rpx;
  color: #7f8b99;
}
.reuse-line {
  margin-top: 10rpx;
  font-size: 24rpx;
  color: #b9c6d4;
}
.reuse-num {
  font-size: 34rpx;
  font-weight: 700;
  color: #38bdf8;
  margin: 0 6rpx 0 14rpx;
}
.reuse-num.warn {
  color: #ffb01f;
}
.reuse-sep {
  margin: 0 12rpx;
  color: #55616e;
}
.reuse-why {
  margin-top: 10rpx;
  font-size: 22rpx;
  color: #93a4b5;
  line-height: 1.5;
}
.reuse-shot {
  color: #d7e3ef;
  margin-right: 10rpx;
}
.reuse-foot {
  margin-top: 12rpx;
  font-size: 20rpx;
  color: #6b7a88;
}
/* 强制重跑：默认关，打开才会跳过逐段缓存（会重新扣费） */
.force-row {
  display: flex;
  justify-content: center;
  margin: 20rpx 0 4rpx;
}
.force-lab {
  display: flex;
  align-items: center;
}
.force-text {
  font-size: 24rpx;
  color: #8a8fa3;
  margin-left: 8rpx;
}

.btn-primary {
  width: 100%;
  height: 92rpx;
  line-height: 92rpx;
  border-radius: 999rpx;
  background: linear-gradient(135deg, #ff6b4a 0%, #ff3d7f 100%);
  color: #fff;
  font-size: 32rpx;
  font-weight: 600;
}

/* ---- 结构化规格：换什么 / 保什么 / 声音 ---- */
.sec {
  margin-top: 24rpx;
  padding-top: 20rpx;
  border-top: 1rpx solid #f0f1f6;
}
/* ---- 配音时长条：目标点在正中，条子越长说明文案超出越多 ---- */
.est-bar {
  position: relative;
  height: 12rpx;
  margin: 8rpx 0 12rpx;
  border-radius: 6rpx;
  background: #eef0f5;
  overflow: hidden;
}
.est-fill {
  height: 100%;
  border-radius: 6rpx;
  background: #22b573;
  transition: width 0.2s;
}
.est-fill.long { background: #ff5a3c; }
.est-fill.short { background: #f0a020; }
.est-mark {
  position: absolute;
  top: 0;
  left: 50%;
  width: 2rpx;
  height: 100%;
  background: #c9ccd8;
}
/* ---- 读音校正 ---- */
.pron-row {
  display: flex;
  align-items: center;
  margin-bottom: 12rpx;
}
.pron-k {
  width: 190rpx;
  font-size: 26rpx;
  color: #1a1d26;
  font-weight: 600;
}
.pron-v {
  flex: 1;
  height: 68rpx;
  padding: 0 18rpx;
  font-size: 26rpx;
  background: #f6f7fa;
  border-radius: 12rpx;
}
.sec-head {
  display: flex;
  align-items: baseline;
  margin-bottom: 14rpx;
}
.sec-title {
  font-size: 26rpx;
  font-weight: 600;
  color: #1b1f27;
  margin-right: 12rpx;
}
.sec-note {
  font-size: 21rpx;
  color: #9aa0a6;
  line-height: 1.5;
}
.slot {
  margin-bottom: 12rpx;
}
.slot-head {
  display: flex;
  align-items: center;
  padding: 16rpx 18rpx;
  background: #fff;
  border: 1rpx solid #ececf3;
  border-radius: 14rpx;
}
.chk {
  width: 32rpx;
  height: 32rpx;
  margin-right: 14rpx;
  border: 2rpx solid #d6d9e3;
  border-radius: 8rpx;
  flex-shrink: 0;
}
.chk.on {
  background: linear-gradient(135deg, #ff6b4a 0%, #ff3d7f 100%);
  border-color: transparent;
}
.slot-name {
  font-size: 26rpx;
  color: #1b1f27;
  font-weight: 500;
}
.slot-sub {
  margin-left: 12rpx;
  font-size: 21rpx;
  color: #9aa0a6;
}
.slot-body {
  margin-top: 10rpx;
  padding: 0 2rpx;
}
/* 同上：不给 height 就会被 uni 的 1.4em 压成 0 高，框能看见但打不进字 */
.field {
  width: 100%;
  margin-top: 12rpx;
  box-sizing: border-box;
  height: 70rpx;
  min-height: 70rpx;
  padding: 0 20rpx;
  font-size: 24rpx;
  background: #fff;
  border: 1rpx solid #ececf3;
  border-radius: 14rpx;
}
.chip-row {
  display: flex;
  flex-wrap: wrap;
}
/* 视觉盘点：画面里有谁 */
.inv-box {
  margin-top: 16rpx;
  padding: 16rpx 18rpx;
  background: #f8f9fc;
  border-radius: 14rpx;
}
.inv-head {
  display: flex;
  align-items: center;
  margin-bottom: 12rpx;
}
.inv-title {
  font-size: 24rpx;
  font-weight: 600;
  color: #1f2333;
}
.inv-note {
  flex: 1;
  margin-left: 12rpx;
  font-size: 22rpx;
  color: #9aa0ad;
}
.inv-refresh {
  font-size: 22rpx;
  color: #ff5a3c;
}
.inv-empty {
  font-size: 22rpx;
  line-height: 1.5;
  color: #9aa0ad;
}
.person-chip {
  min-width: 200rpx;
  margin: 0 12rpx 12rpx 0;
  padding: 12rpx 18rpx;
  background: #fff;
  border: 1rpx solid #e6e8ef;
  border-radius: 14rpx;
}
.person-chip.on {
  border-color: #ff5a3c;
  background: #fff5f2;
}
.pc-name {
  font-size: 24rpx;
  color: #1f2333;
}
.person-chip.on .pc-name {
  color: #ff5a3c;
  font-weight: 600;
}
.pc-time {
  margin-top: 4rpx;
  font-size: 20rpx;
  color: #9aa0ad;
}
.style-row {
  margin-top: 8rpx;
}
.chip {
  padding: 12rpx 24rpx;
  margin: 0 12rpx 12rpx 0;
  font-size: 23rpx;
  color: #6b7280;
  background: #fff;
  border: 1rpx solid #e6e8ef;
  border-radius: 999rpx;
}
.chip.on {
  color: #ff5a3c;
  border-color: #ff5a3c;
  background: #fff5f2;
  font-weight: 600;
}
.spec-line {
  margin-top: 18rpx;
  padding: 14rpx 18rpx;
  font-size: 21rpx;
  line-height: 1.6;
  color: #8b90a0;
  background: #f5f6fa;
  border-radius: 12rpx;
}
.adv-toggle {
  margin-top: 18rpx;
  text-align: center;
  font-size: 23rpx;
  color: #ff5a3c;
}
.adv {
  margin-top: 14rpx;
  padding: 18rpx;
  background: #fff;
  border: 1rpx solid #ececf3;
  border-radius: 14rpx;
}
.adv-label {
  margin: 6rpx 0 10rpx;
  font-size: 22rpx;
  color: #6b7280;
}
.switch-row.tight {
  margin: 10rpx 0 0;
}
.recipe-link {
  margin: 20rpx 0 8rpx;
  text-align: center;
  font-size: 24rpx;
  color: #8b909a;
  text-decoration: underline;
}
/* ---- 配音音色：一行「标签 + 当前音色」，点开是原生选择器 ---- */
.pick-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 12rpx;
  padding: 22rpx 24rpx;
  background: #fff;
  border: 1rpx solid #e6e8ef;
  border-radius: 20rpx;
}
.pick-label {
  font-size: 26rpx;
  color: #4b5563;
}
.pick-value {
  flex: 1;
  text-align: right;
  font-size: 26rpx;
  color: #ff5a3c;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.pick-strip {
  white-space: nowrap;
  padding: 4rpx 0;
}
.pick {
  display: inline-block;
  position: relative;
  width: 128rpx;
  margin-right: 12rpx;
  vertical-align: top;
  opacity: 0.45;
}
.pick.on,
.pick:not(.off) {
  opacity: 1;
}
.pick.off .pick-img {
  filter: grayscale(1);
}
.pick-img {
  width: 128rpx;
  height: 170rpx;
  border-radius: 12rpx;
  background: #eef1fb;
}
.pick-noimg {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28rpx;
  color: #9aa0a6;
}
.pick-tag {
  position: absolute;
  left: 6rpx;
  bottom: 6rpx;
  padding: 2rpx 10rpx;
  font-size: 18rpx;
  color: #6b7280;
  background: rgba(255, 255, 255, 0.9);
  border-radius: 999rpx;
}
.pick-tag.act {
  color: #fff;
  background: rgba(255, 90, 60, 0.9);
}
</style>
