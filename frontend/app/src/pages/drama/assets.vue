<template>
  <DramaAppShell>
    <view class="ds">
      <DramaProjectHeader :id="pid" current="assets" :name="headerName" :chips="chips" />

      <view v-if="!cur" class="pgstate">正在加载项目…</view>

      <!-- C17 云端任务恢复：已提交未取回单独列（已发出去的钱，别重复提交） -->
      <view v-if="activeTasks.length" class="card">
        <view class="card-head">
          <view class="card-title"><text class="card-no">任</text>云端任务恢复</view>
          <button class="btn-mini" :disabled="tkBusy" @click="loadTasks">
            {{ tkBusy ? '刷新中…' : '刷新' }}
          </button>
        </view>
        <view class="merge-tip">
          {{ tkHint || '先领回或去平台确认，别重复提交（会再付一次）。' }}
        </view>
        <view v-for="t in activeTasks" :key="t.pid + ':' + t.no" class="pl-row">
          <view class="pl-info">
            <text class="pl-name">{{ t.project_name || t.product || t.pid }} · 第 {{ t.no }} 段</text>
            <text class="pl-meta">
              {{ t.status === 'submitted' ? '已提交未取回' : '任务号缺失（先别重提）' }}
              · {{ t.model || '—' }} · {{ t.at || '—' }}<text v-if="t.tid"> · {{ t.tid }}</text>
            </text>
            <text v-if="tkMsg[t.pid + ':' + t.no]" class="pl-meta">
              {{ tkMsg[t.pid + ':' + t.no] }}
            </text>
          </view>
          <text v-if="t.can_resume" class="media-more" @click.stop="resumeTask(t)">
            {{ tkBusyNo === t.pid + ':' + t.no ? '领取中…' : '领回' }}
          </text>
          <text v-else class="pl-del">去平台确认</text>
        </view>
        <view class="merge-tip">
          领回只查询已提交的任务号并下载结果，不会重新提交；任务号缺失的先去平台「任务/历史」确认。
        </view>
      </view>

      <block v-if="cur">

      <!-- ===== 动作条：标题 + 只放动词（照竞品 assets/page.tsx:992-1095） ===== -->
      <view class="ab">
        <view class="ab-head">
          <view class="ab-title">素材生成</view>
          <view class="ab-sub">{{ doneCount }}/{{ shotRows.length }} 个素材已就绪</view>
        </view>
        <view class="ab-ops">
          <view v-if="uiMode === 'simple'" class="ab-btn" @click="setUiMode('pro')">⚙ 专业模式</view>
          <view class="ab-btn" @click="goTranscript">✂ 按文字剪</view>
          <!-- 不再「自动配画面」：盲目搜免费图库必然配到空镜/无关图。画面用自己传的素材。 -->
          <view class="ab-btn" :class="{ off: !!busy || !cur.storyboard_json }" @click="planGrid">
            {{ busy === 'grid-plan' ? '规划中…' : '🎬 九宫格（先规划·免费）' }}
          </view>
          <view class="ab-btn ab-main" :class="{ off: !!busy || !cur.storyboard_json }" @click="filmPlan">
            {{ busy === 'film-plan' ? '规划中…' : '🎞 出片（先规划·免费）' }}
          </view>
        </view>
      </view>

      <!-- ===== 导演台：全局设置收进一行（照竞品 1100-1256） ===== -->
      <scroll-view class="dir" scroll-x>
        <view class="dir-label">导演台</view>
        <view class="dir-chip" @click="goProduction">生产控制台</view>
        <picker v-if="castNames.length" :range="castNames" :value="castIdx" @change="onPickCast">
          <view class="dir-chip">出镜人物 · {{ castName }}</view>
        </picker>
        <view v-if="castMissing.length" class="dir-chip dir-warn" @click="goPresenters">
          ⚠ 缺参考图 · {{ castMissing.join('、') }}
        </view>
        <view v-if="castStaleText" class="dir-chip dir-warn" @click="goPresenters">
          ⚠ 角色设定变了 · {{ castStaleText }}
        </view>
        <picker v-if="modelNames.length" :range="modelNames" :value="modelIdx" @change="onPickModel">
          <view class="dir-chip">模型 · {{ modelName }}</view>
        </picker>
        <picker v-if="resNames.length" :range="resNames" :value="resIdx" @change="onPickRes">
          <view class="dir-chip">清晰度 · {{ resName }}</view>
        </picker>
        <picker v-if="ratioNames.length" :range="ratioNames" :value="ratioIdx" @change="onPickRatio">
          <view class="dir-chip">画幅 · {{ ratioName }}</view>
        </picker>
        <view class="dir-chip" :class="{ on: chain !== 'off' }"
              @click="pickChain(chain === 'off' ? 'tail' : 'off')">
          接缝 · {{ chain === 'off' ? '关' : '续拍' }}
        </view>
        <view class="dir-chip" :class="{ on: realism === 'auto' }"
              @click="pickRealism(realism === 'auto' ? 'off' : 'auto')">
          真实感 · {{ realism === 'auto' ? '自动' : (realism === 'constraints' ? '仅约束' : '关') }}
        </view>
        <view class="dir-chip" @click="bibleOpen = !bibleOpen">视觉锚点</view>
      </scroll-view>

      <!-- ===== 就绪进度 ===== -->
      <view class="prog">
        <view class="prog-in" :style="'width:' + donePct + '%'"></view>
      </view>

      <!-- ===== 素材库（图 / 视频） ===== -->
      <view class="card">
        <view class="card-head">
          <view class="card-title"><text class="card-no">素</text>素材库</view>
          <view class="head-ops">
            <view class="btn-mini" @click="libPoolOpen = !libPoolOpen">{{ libPoolOpen ? '收起' : '展开' }}</view>
            <button class="btn-mini" :disabled="!!busy || !!poolBusy" @click="pickMaterial">
              {{ poolBusy === 'upload' ? '上传中…' : '上传素材' }}
            </button>
          </view>
        </view>
        <view class="merge-tip">图 / 视频都收，单个 ≤80MB｜配画面就从这里挑</view>
        <block v-if="libPoolOpen">
          <view v-for="m in pool" :key="m.name" class="mat-row" @click="openMaterial(m)">
            <view class="mat-main">
              <view class="mat-title">
                {{ m.original_name }}
                <text class="mat-kind">{{ m.media_type === 'video' ? '视频' : '图片' }}</text>
              </view>
              <view class="mat-meta">{{ materialMeta(m) }}</view>
              <view v-if="(m.tags || []).length" class="mat-tags">
                <text v-for="t in m.tags" :key="t" class="mat-tag">{{ t }}</text>
              </view>
            </view>
            <text class="mat-del" @click.stop="removeMaterial(m)">删</text>
          </view>
          <view v-if="!pool.length" class="empty">还没有素材——传段实拍 B-roll 或商品细节图进来</view>
        </block>
      </view>

      <!-- ===== 免版权素材检索 ===== -->
      <view class="card">
        <view class="card-head">
          <view class="card-title"><text class="card-no">搜</text>免版权素材</view>
          <view class="head-ops">
            <view class="btn-mini" @click="stockOpen = !stockOpen">{{ stockOpen ? '收起' : '展开' }}</view>
            <button class="btn-mini" :disabled="!!busy || !!stockBusy" @click="doStockSearch">
              {{ stockBusy === 'search' ? '搜索中…' : '搜索' }}
            </button>
          </view>
        </view>
        <view class="merge-tip">免 Key：Openverse / Wikimedia / NASA / Archive｜图能配画面，音乐能当 BGM</view>
        <block v-if="stockOpen">
          <input class="stock-q" v-model="stockQ" placeholder="英文检索词召回更好，如 coffee cup"
                 confirm-type="search" @confirm="doStockSearch" />
          <view class="stock-tabs">
            <text v-for="t in [['video','视频'],['image','图片'],['audio','音乐']]" :key="'st' + t[0]"
                  class="stock-tab" :class="{ on: stockType === t[0] }" @click="stockType = t[0]">
              {{ t[1] }}
            </text>
          </view>
          <view v-if="stockFillMsg" class="hint">{{ stockFillMsg }}</view>
          <view class="stock-srcs">
            <text class="stock-src" :class="{ on: stockSource === 'all' }" @click="stockSource = 'all'">全部</text>
            <text v-for="s in stockSrcs" :key="'ss' + s.id" class="stock-src"
                  :class="{ on: stockSource === s.id, off: !s.available }" @click="stockSource = s.id">
              {{ s.label }}<text v-if="!s.available" class="stock-src-key">需 Key</text>
            </text>
          </view>
          <view v-if="stockMsg" class="hint">{{ stockMsg }}</view>
          <view v-for="c in stockResults" :key="'sr' + c.source + c.id" class="stock-row">
            <image v-if="c.preview_image" :src="c.preview_image" class="stock-thumb" mode="aspectFill" />
            <view v-else class="stock-thumb stock-thumb-empty">{{ c.media_type === 'audio' ? '音' : '图' }}</view>
            <view class="stock-main">
              <view class="stock-title">{{ c.title || c.id }}</view>
              <view class="stock-meta">
                {{ stockSourceLabel(c.source) }} · {{ c.license || '许可未知' }}
                <text v-if="c.requires_attribution" class="stock-warn"> · 需署名</text>
                <text v-if="stockSize(c)"> · {{ stockSize(c) }}</text>
              </view>
              <view class="stock-meta">{{ c.author }}</view>
            </view>
            <button class="btn-mini" :disabled="!!stockBusy" @click="importStock(c)">
              {{ stockBusy === 'import' && stockImported === (c.source + ':' + c.id) ? '加入中…'
                : (c.media_type === 'audio' ? '设为 BGM' : '加进来') }}
            </button>
          </view>
          <view v-if="!stockResults.length && !stockBusy" class="empty">搜一段实拍素材：加了就能给某一镜配画面，或者当背景乐</view>
        </block>
      </view>


      <!-- ===== 每镜一张卡（照竞品 1433-1712：左编号 / 中描述 / 右画面与操作） ===== -->
      <view v-for="r in shotRows" :key="'sh' + r.id" class="shot">
        <view class="shot-side">
          <text class="shot-no">{{ r.no }}</text>
          <text class="shot-type">{{ r.typeLabel }}</text>
          <text class="shot-dur">{{ r.duration }}s</text>
          <text class="shot-real" :class="r.real ? 'real' : 'ai'">{{ r.real ? '实拍' : 'AI' }}</text>
        </view>

        <view class="shot-main">
          <view class="shot-desc">{{ r.description }}</view>
          <view class="shot-camera">🎥 {{ r.camera || '运镜未设置' }}</view>
          <view class="shot-src">{{ r.sourceLabel }}</view>
          <view v-if="r.note" class="shot-warn">⚠ {{ r.note }}</view>
        </view>

        <view class="shot-side2">
          <image v-if="r.thumb" class="shot-thumb" :src="r.thumb" mode="aspectFill" />
          <view v-else class="shot-thumb shot-thumb-empty">{{ r.hasClip ? '🎞' : '图' }}</view>
          <view class="shot-ops">
            <text class="shot-op" @click="openMatFor(r)">{{ r.hasImg ? '换画面' : '配画面' }}</text>
            <text class="shot-op" @click="openClipPick(r.id)">{{ r.hasClip ? '换视频' : '配视频' }}</text>
            <text v-if="r.segNo" class="shot-op" :class="{ off: !!busy }"
                  @click="filmRender(r.segNo)">
              {{ r.hasFilm ? '重出这段' : '出这段' }}
            </text>
            <text v-if="r.hasFilm" class="shot-op play" @click="openFilm(r.segNo)">看这段</text>
          </view>
        </view>
      </view>

      <!-- D1（2026-11-08）：结构卡重出后，这一版分镜是旧卡写的 -->
      <view v-if="storyboardCardStale" class="film-warn">⚠ 结构卡改过了，这版分镜还是旧卡写的，重新出分镜才对得上</view>
      <view v-if="!shotRows.length" class="empty">先出分镜，这里才会出现镜头卡</view>

      <!-- ===== 视觉锚点（一致性硬闸）：默认收起 ===== -->
      <view v-if="bibleOpen" class="card">
        <view class="card-head">
          <view class="card-title"><text class="card-no">锚</text>视觉锚点（一致性硬闸）</view>
          <button class="btn-mini" :disabled="!!busy" @click="saveBible">
            {{ busy === 'bible-save' ? '保存中…' : '保存锚点' }}
          </button>
        </view>
        <view v-for="i in bibleIssues" :key="'bi' + i.kind + i.anchor"
              :class="i.severity === 'fail' ? 'film-err' : 'film-warn'">
          {{ i.severity === 'fail' ? '⛔ 禁改：' : '⚠ 缺锚：' }}{{ i.anchor }}
        </view>
        <view v-for="f in bibleFields" :key="'bf' + f.key" class="bible-row">
          <text class="bible-label">{{ f.label }}</text>
          <input class="bible-input" v-model="bibleDraft[f.key]" :placeholder="f.hint" />
        </view>
      </view>

      <!-- ===== 人物定妆：分镜板之前的一步（2026-11-08 补） =====
           剧本写完就有角色了，但长相全靠文字描述 → 九宫格/整片每个人都不一样。
           这里把每个角色摆出来：有图就显示，没图当场生成或上传。 -->
      <view v-if="castList.length" class="card">
        <view class="card-head">
          <view class="card-title">
            <text class="card-no">妆</text>人物定妆
            <text class="grid-multi">{{ castDone }}/{{ castList.length }} 已定妆</text>
          </view>
          <button class="btn-mini" :disabled="!!busy" @click="goPresenters">人物库</button>
        </view>
        <view class="cast-note">
          定妆 = 这个角色长什么样。**先定妆再出分镜板**，九格和整片才会是同一个人；
          没定妆也能出，但每段长相靠文字，容易一镜一个样。
        </view>
        <view v-for="c in castList" :key="'cast-' + c.name" class="cast-row">
          <image v-if="c.image" class="cast-face" :src="castUrl(c.image)" mode="aspectFill" />
          <view v-else class="cast-face cast-face-empty"><text>无图</text></view>
          <view class="cast-col">
            <text class="cast-name">{{ c.name }}</text>
            <text class="cast-state">{{ c.image ? (c.source === 'sheet' ? '已生成定妆' : '已上传照片') : '还没定妆' }}</text>
          </view>
          <button class="btn-mini" :disabled="!!busy"
                  @click="castSheet(c.name)">
            {{ c.image ? '重新定妆（会花钱）' : '生成定妆（会花钱）' }}
          </button>
        </view>
        <view class="cast-tip">上传真人照片锁脸更稳 → 点右上「人物库」；这里只负责「照剧本外观画一张」。</view>
      </view>

      <!-- ===== 九宫格：规划结果 + 出图（花钱只在这一下） ===== -->
      <view v-if="cur.grid" class="card">
        <view class="card-head">
          <view class="card-title">
            <text class="card-no">九</text>分镜板
            <text v-if="gridBoards.length > 1" class="grid-multi">共 {{ gridBoards.length }} 块</text>
          </view>
          <button class="btn-mini" :disabled="!!busy" @click="planGrid">重新规划</button>
        </view>
        <view class="grid-note">
          九格同一组人、同一套衣服、同一个房间；整图按 9:16 出，裁开每格也是 9:16。
          <text v-if="gridBoards.length > 1">一张板只有 9 格，这部片子超过 9 镜 → 按出片段每段一块板，各出各的。</text>
        </view>

        <view v-for="b in gridBoards" :key="'b' + b.no" class="gboard">
          <view v-if="gridBoards.length > 1" class="gboard-head">
            <text class="gboard-t">第 {{ b.no }} 块 · 镜头 {{ (b.shot_ids || []).join(' / ') }}</text>
            <text class="gboard-s">{{ b.image ? '已出图' : '还没出图' }}</text>
          </view>
          <view class="grid-wrap">
            <view v-for="c in (b.cells || [])" :key="'c' + b.no + '-' + c.idx" class="gcell">
              <view class="gcell-in" :class="{ has: !!b.image }">
                <image v-if="b.image" class="gcell-img" :src="cellUrl(c.idx, b.no)" mode="aspectFill" />
                <text class="gcell-no" :class="{ lit: !!b.image }">{{ c.idx }}</text>
                <text v-if="c.product" class="gcell-prod">商品</text>
                <view v-if="!b.image" class="gcell-desc">{{ c.description }}</view>
              </view>
            </view>
          </view>
          <view v-if="b.crop_error" class="grid-warn">{{ b.crop_error }}</view>
          <button class="btn-cost" :disabled="!!busy || gridBibleFails.length" @click="renderGrid(b.no)">
            {{ busy === 'grid-render' ? '出图中…' : (b.image ? '重新出图（会花钱）' : '出九宫格图（会花钱）') }}
          </button>
        </view>

        <view v-for="(w, wi) in gridCellLints" :key="'gl' + wi" class="grid-warn">{{ w }}</view>
        <view v-for="i in gridBibleIssues" :key="'gb' + i.kind + i.anchor"
              :class="i.severity === 'fail' ? 'film-err' : 'film-warn'">
          {{ i.severity === 'fail' ? '⛔ 禁改：' : '⚠ 缺锚：' }}{{ i.anchor }}
        </view>
        <view class="grid-tip">出图消耗额度；出完自动裁成九张，直接当一键整片的参考图。</view>
      </view>

      <!-- ===== 出片计划确认（照竞品 1280-1306） ===== -->
      <view v-if="plan" class="planbar">
        <view class="planbar-title">
          {{ modelLabel(plan.model) }} · {{ plan.shot_count }} 镜 / {{ plan.total_seconds }} 秒 / {{ (plan.segments || []).length }} 段
        </view>
        <view class="planbar-price">预计花费：{{ priceText }}</view>
        <view v-if="chain !== 'off'" class="merge-tip">续拍：第 2 段起用上一段真实尾帧锁首帧，顺序出片。</view>
        <view v-for="e in (plan.errors || [])" :key="'pe' + e" class="film-err">{{ e }}</view>
        <view v-for="w in (plan.warnings || [])" :key="'pw' + w" class="film-warn">{{ w }}</view>
        <view v-for="w in (plan.dialogue_warnings || [])" :key="'pd' + w" class="film-warn">🗣 {{ w }}</view>
        <view v-for="i in bibleIssues" :key="'pb' + i.kind + i.anchor"
              :class="i.severity === 'fail' ? 'film-err' : 'film-warn'">
          {{ i.severity === 'fail' ? '⛔ 禁改：' : '⚠ 缺锚：' }}{{ i.anchor }}
        </view>
        <view class="planbar-ops">
          <view class="ab-btn ab-main" :class="{ off: !!busy || (plan.errors || []).length || bibleFails.length }"
                @click="filmRenderAll">
            {{ busy === 'film-render-all' ? '整片出片中…' : '确认，开始出片（全部段）' }}
          </view>
        </view>
      </view>

      <!-- 计划作废时**不把这一块藏起来**：分镜板/分镜/参考图一改，旧确认卡就失效，
           页面要是整块消失，人会以为「出片界面没了」（2026-11-08 主人实测）。 -->
      <view v-else-if="cur && cur.storyboard_json" class="planbar">
        <view class="planbar-title">出片计划已作废</view>
        <view class="film-warn">
          分镜板 / 分镜 / 参考图改过 —— 出片提示词和参考图编号都跟着变了，
          旧确认卡不能再拿去付这一版的钱。重新规划一版（免费），看过提示词再出片。
        </view>
        <view class="planbar-ops">
          <view class="ab-btn ab-main" :class="{ off: !!busy }" @click="filmPlan">
            {{ busy === 'film-plan' ? '规划中…' : '重新规划（免费）' }}
          </view>
        </view>
      </view>

      <!-- ===== 人物库弹层（选一张现成的脸） ===== -->
      <view v-if="libOpen" class="lib-mask" @click="closeLib">
        <view class="lib-sheet" @click.stop>
          <view class="lib-head">
            <text class="lib-title">给「{{ libRole }}」挑一个人</text>
            <text class="lib-x" @click="closeLib">✕</text>
          </view>
          <view v-if="libBusy" class="lib-state">正在读取人物库…</view>
          <view v-else-if="!libRows.length" class="lib-state">
            人物库里还没有人。去「出镜人物」页加一个（可以传照片，也可以生成四视图）。
          </view>
          <view v-for="p in libRows" :key="p.id" class="lib-row"
                :class="p.hasImg ? '' : 'lib-row-dim'" @click="pickLibPerson(p)">
            <image v-if="p.hasImg" class="lib-thumb" :src="p.imgUrl" mode="aspectFill" />
            <view v-else class="lib-thumb lib-thumb-empty">无图</view>
            <view class="lib-main">
              <view class="lib-name-line">
                <text class="lib-name">{{ p.name }}</text>
                <text v-if="p.sourceLabel" class="lib-badge">{{ p.sourceLabel }}</text>
              </view>
              <text class="lib-brief">{{ p.brief }}</text>
            </view>
            <text class="lib-go">{{ p.hasImg ? '用这个' : '没图' }}</text>
          </view>
          <view v-if="libMsg" class="lib-msg">{{ libMsg }}</view>
        </view>
      </view>

      <!-- ===== 下一步 ===== -->
      <view class="next-row">
        <view class="ab-btn ab-main" :class="{ off: !allReady }" @click="goVideo">
          {{ allReady ? '下一步：合成 →' : '全部素材就绪后可去合成' }}
        </view>
      </view>

      </block>
    <view v-if="poolEdit.open" class="sheet">
      <view class="sheet-top">
        <view>
          <view class="sheet-title">素材信息</view>
          <view class="sheet-sub">{{ (poolEdit.row || {}).original_name || (poolEdit.row || {}).name }}</view>
        </view>
        <text class="sheet-x" @click="poolEdit.open = false">×</text>
      </view>

      <view class="field">
        <view class="label">名称</view>
        <input v-model="poolEdit.name" class="input line" />
      </view>
      <view class="field">
        <view class="label">标签<text class="label-tip">逗号分隔，最多 12 个，每个 ≤32 字</text></view>
        <input v-model="poolEdit.tags" class="input line" placeholder="例：厨房, 特写" />
      </view>
      <view class="field">
        <view class="label">出处<text class="label-tip">买的素材、别人拍的，都写这儿</text></view>
        <input v-model="poolEdit.author" class="input line" placeholder="作者 / 摄影师（可空）" />
        <input v-model="poolEdit.license" class="input line" placeholder="许可，如 CC BY 4.0 / CC0 / Pexels（可空）" />
        <input v-model="poolEdit.sourceUrl" class="input line" placeholder="来源链接（可空）" />
      </view>
      <view class="hint">
        CC0 / PDM / Pexels / Pixabay 判可免署名商用；CC BY 判需署名；含 NC / ND 或写不清的判「需人工复核」。
        不填 = 自有素材。
      </view>
      <button class="btn-main" :disabled="!!poolBusy" @click="saveMaterial">
        {{ poolBusy === 'save' ? '保存中…' : '保存' }}
      </button>
    </view>

    <view v-if="matPick.open" class="sheet">
      <view class="sheet-top">
        <view>
          <view class="sheet-title">配参考画面</view>
          <view class="sheet-sub">第 {{ matPick.seg }} 段 · 一镜一张</view>
        </view>
        <text class="sheet-x" @click="matPick.open = false">×</text>
      </view>

      <view class="field">
        <view class="label">配给哪一镜</view>
        <view class="mat-shots">
          <view v-for="s in matPick.shots" :key="'ms' + s.id" class="mat-shot"
                :class="{ on: Number(matPick.shotId) === Number(s.id) }"
                @click="matPick.shotId = s.id">
            <text class="mat-shot-no">镜头 {{ s.id }}</text>
            <text class="mat-shot-txt">{{ s.text }}</text>
            <text v-if="matOfShot(s.id)" class="mat-shot-has">已配</text>
          </view>
        </view>
      </view>

      <view class="field">
        <view class="label">选一张图片<text class="label-tip">只有图片能当参考画面</text></view>
        <view v-if="!shotImages.length" class="hint">素材库里还没有图片——先去「素材库」上传。</view>
        <view v-else class="mat-picks">
          <view v-for="img in shotImages" :key="'mi' + img.name" class="mat-pick"
                :class="{ on: matPick.material === img.name }"
                @click="matPick.material = img.name">
            <text class="mat-pick-name">{{ img.original_name }}</text>
            <text v-if="(img.tags || []).length" class="mat-pick-tags">{{ (img.tags || []).join('、') }}</text>
          </view>
        </view>
      </view>
      <button class="btn-main" :disabled="!!busy" @click="saveMatPick">
        {{ busy === 'shot-mat' ? '保存中…' : '保存' }}
      </button>
    </view>

    <view v-if="clipPick.open" class="sheet">
      <view class="sheet-top">
        <view>
          <view class="sheet-title">配画面素材</view>
          <view class="sheet-sub">镜头 {{ clipPick.shotId }} · 这一镜将由这段视频代替 AI 生成</view>
        </view>
        <text class="sheet-x" @click="clipPick.open = false">×</text>
      </view>
      <view class="field">
        <view class="label">选一段视频<text class="label-tip">只有视频能当画面</text></view>
        <view v-if="!clipVideos.length" class="hint">素材库里还没有视频 —— 先去「素材库」上传。</view>
        <view v-else class="mat-picks">
          <view v-for="v in clipVideos" :key="'cv' + v.name" class="mat-pick"
                :class="{ on: clipPick.material === v.name }"
                @click="clipPick.material = v.name">
            <text class="mat-pick-name">{{ v.original_name }}</text>
            <text class="mat-pick-tags">{{ Number(v.durationSec || 0).toFixed(1) }}s</text>
          </view>
        </view>
      </view>
      <view class="hint">
        按这一镜的时长自动对齐：略长/略短会变速，差太多会定格补足；有原声的素材不变速（会裁尾）。
      </view>
      <button class="btn-main" :disabled="!!busy" @click="saveClipPick">
        {{ busy === 'shot-clip' ? '保存中…' : '保存' }}
      </button>
    </view>

    </view>
  </DramaAppShell>
</template>

<script>
import { onLoad } from '@dcloudio/uni-app'
import DramaAppShell from '@/components/drama/AppShell.vue'
import DramaProjectHeader from '@/components/drama/ProjectHeader.vue'
import dramaPageBoot from '@/mixins/dramaPageBoot'
import {
  dramaPresenters,
  dramaPresenterUrl,
  dramaCastFromLibrary,
  dramaMaterialUrl,
  dramaFilmRender,
} from '@/api/request'

const LIB_SOURCE = { upload: '上传', sheet: '定妆' }

/**
 * 商品短剧 · 素材 步（照竞品 app/project/[id]/assets/page.tsx 的分工）
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
      // 入门 / 专业两档（照竞品 assets/page.tsx 的 uiMode）：和剧本页共用一个值
      uiMode: uni.getStorageSync('dramaUiMode') || 'simple',
      // 人物库弹层（数组必须是 data 顶层：绑 computed / 对象路径在 mp 会让整页 setData 停更）
      libOpen: false,
      libRole: '',
      libBusy: false,
      libRows: [],
      libMsg: '',
      libBusyId: '',
      // 每镜一张卡（照竞品 assets/page.tsx 的镜头列表）：模板里 v-for 的数组必须是 data 顶层
      shotRows: [],
      doneCount: 0,
      donePct: 0,
      // 导演台 select 的候选与当前项（mp 的 picker 只吃 data 数组）
      castNames: [],
      castIdx: 0,
      castName: '不指定',
      modelNames: [],
      modelIdx: 0,
      modelName: '—',
      resNames: [],
      resIdx: 0,
      resName: '—',
      ratioNames: [],
      ratioIdx: 0,
      ratioName: '—',
      // 底部三块的折叠态（默认收起，主界面只留镜头卡）
      libPoolOpen: false,
      stockOpen: false,
      mediaOpen2: false,
    }
  },
  async onLoad(q) {
    await this.boot((q && q.id) || '')
    this.rebuildAssets()
    // C17 云端任务恢复卡的数据（旧单页是 onShow 里 loadTasks 带出来的）
    this.safe(this.loadTasks)
  },
  methods: {
    /**
     * 把分镜 + 已配画面 + 九宫格 + 出片计划拼成「每镜一张卡」的数据。
     * 照竞品 assets/page.tsx:1433-1712 的一行结构：左编号 / 中描述 / 右画面与操作。
     */
    rebuildAssets() {
      const doc = this.cur || {}
      const shots = ((doc.storyboard_json || {}).shots) || []
      const mats = this.shotMats || []
      const clips = this.clipItems || []
      const cells = ((doc.grid || {}).cells) || []
      const hasCells = !!this.hasCells
      const segs = (this.plan && this.plan.segments) || []
      const rows = []
      for (let k = 0; k < shots.length; k++) {
        const s = shots[k] || {}
        const id = Number(s.id)
        const mat = mats.find((m) => Number(m.shot_id) === id) || null
        const clip = clips.find((c) => Number(c.shot_id) === id) || null
        const cell = cells.find((c) => Number(c.idx) === id) || null
        let segNo = 0
        for (let i = 0; i < segs.length; i++) {
          if ((segs[i].shot_ids || []).map(Number).indexOf(id) >= 0) { segNo = segs[i].no; break }
        }
        let thumb = ''
        if (mat) thumb = dramaMaterialUrl(doc.id, mat.material)
        else if (hasCells && cell) thumb = this.cellUrl(cell.idx)
        const type = String(s.purpose || '').trim()
        rows.push({
          id,
          no: String(id).padStart(2, '0'),
          duration: s.duration || 0,
          typeLabel: type ? type.slice(0, 4) : (s.product ? '商品' : '镜头'),
          description: s.description || '（没写画面描述）',
          camera: s.camera || s.framing || '',
          hasImg: !!mat,
          hasClip: !!clip,
          real: !!clip,
          thumb,
          segNo,
          hasFilm: segNo ? !!this.filmFile(segNo) : false,
          sourceLabel: clip
            ? '🎞 实拍素材'
            : (mat ? '🖼 参考画面' : (hasCells ? '✨ AI 九宫格' : (s.product ? '📷 商品原图' : '还没画面'))),
          note: (!mat && !clip && !hasCells) ? '还没配画面，点右边「配画面」从你上传的素材里挑' : '',
        })
      }
      this.shotRows = rows
      const done = rows.filter((r) => r.hasImg || r.hasClip || (hasCells && r.thumb)).length
      this.doneCount = done
      this.donePct = rows.length ? Math.round((done / rows.length) * 100) : 0
      this.rebuildDirector()
    },
    /** 导演台下拉：候选与当前项都算成 data 数组/下标（picker 只吃这些） */
    rebuildDirector() {
      const models = this.opt.film_models || []
      this.modelNames = models.map((m) => m.label)
      this.modelIdx = Math.max(0, models.findIndex((m) => m.id === this.filmModel))
      this.modelName = (models[this.modelIdx] || {}).label || this.filmModel || '—'

      const rs = this.resRows || []
      this.resNames = rs.map((r) => r.label)
      this.resIdx = Math.max(0, rs.findIndex((r) => r.id === this.filmResolution))
      this.resName = (rs[this.resIdx] || {}).label || this.filmResolution || '—'

      const rt = this.ratioRows || []
      this.ratioNames = rt.map((r) => r.label)
      this.ratioIdx = Math.max(0, rt.findIndex((r) => r.id === this.filmRatio))
      this.ratioName = (rt[this.ratioIdx] || {}).label || this.filmRatio || '—'

      const cs = this.castList || []
      this.castNames = ['不指定'].concat(cs.map((c) => c.name))
      this.castIdx = 0
      this.castName = cs.length ? ('已绑 ' + cs.length + ' 人') : '不指定'
    },
    onPickCast(e) {
      const i = Number(e.detail.value)
      this.castIdx = i
      if (!i) { this.castName = '不指定'; return }
      const c = (this.castList || [])[i - 1]
      if (c) this.pickCast(c.name)
    },
    onPickModel(e) {
      const i = Number(e.detail.value)
      const m = (this.opt.film_models || [])[i]
      if (m) this.pickModel(m)
      this.rebuildDirector()
    },
    onPickRes(e) {
      const i = Number(e.detail.value)
      const r = (this.resRows || [])[i]
      if (r) this.pickResolution(r.id)
      this.rebuildDirector()
    },
    onPickRatio(e) {
      const i = Number(e.detail.value)
      const r = (this.ratioRows || [])[i]
      if (r) this.pickRatio(r.id)
      this.rebuildDirector()
    },
    /** 入门 / 专业切换：和剧本页共用一个本地值 */
    setUiMode(m) {
      this.uiMode = m === 'pro' ? 'pro' : 'simple'
      try { uni.setStorageSync('dramaUiMode', this.uiMode) } catch (e) { /* 忽略 */ }
    },
    /** 某一镜「配画面」：把单镜包成一段交给原有的选择器 */
    openMatFor(r) {
      this.openMatPick({ no: r.segNo || 0, shot_ids: [r.id] })
    },
    /** 一键整片：出全部段（和脚本页 AI 成片同一条后端调用，no=0） */
    async filmRenderAll() {
      if (!this.cur || this.busy) return
      const p = this.plan || {}
      if (!p.plan_hash || !(p.segments || []).length) {
        uni.showToast({ title: '先规划出片', icon: 'none' })
        return
      }
      if ((p.errors || []).length) {
        uni.showModal({ title: '这版出不了片', content: p.errors[0], showCancel: false })
        return
      }
      const go = await new Promise((res) => uni.showModal({
        title: '确认出整片',
        content: `${(p.segments || []).length} 段 / ${p.total_seconds} 秒\n花费：${this.priceText}\n确认后真扣费。`,
        confirmText: '确认出片',
        success: (x) => res(x.confirm),
      }))
      if (!go) return
      this.busy = 'film-render-all'
      try {
        this.cur = await dramaFilmRender(this.cur.id, 0, this.filmResolution, p.plan_hash)
        uni.showToast({ title: '整片出好了', icon: 'success' })
        await this.filmPlan()
        this.rebuildAssets()
      } catch (e) {
        const msg = e.message || ''
        // 计划过期（分镜板/参考图/台词改过）≠ 出片出错：自动重算一版（免费）再看
        if (msg.indexOf('计划和你看的那一版不一样了') >= 0) {
          this.busy = ''
          await this.filmStaleReplan()
          this.rebuildAssets()
          return
        }
        uni.showModal({ title: '出片没跑完', content: msg, showCancel: false })
      } finally {
        this.busy = ''
      }
    },
    goProduction() {
      if (!this.pid) return
      uni.redirectTo({ url: `/pages/drama/production?id=${this.pid}` })
    },
    goVideo() {
      if (!this.pid) return
      uni.redirectTo({ url: `/pages/drama/video?id=${this.pid}` })
    },
    /** 转写工作台是二级页（照竞品 transcript 独立页）：不堆栈，用 redirectTo */
    goPresenters() {
      if (!this.pid) return
      uni.redirectTo({ url: `/pages/drama/presenters?id=${this.pid}` })
    },
    goTranscript() {
      if (!this.pid) return
      uni.redirectTo({ url: `/pages/drama/transcript?id=${this.pid}` })
    },

    /** 覆盖 mixin 的同名方法：多给一条「从人物库选」（库是跨项目的，见 pages/drama/presenters） */
    pickCast(name) {
      if (!this.cur || this.busy) return
      uni.showActionSheet({
        itemList: ['上传一张照片', '生成四视图定妆照（会花钱）', '从人物库选'],
        success: (r) => {
          if (r.tapIndex === 0) this.uploadCast(name)
          else if (r.tapIndex === 1) this.castSheet(name)
          else if (r.tapIndex === 2) this.openCastLibrary(name)
        },
      })
    },

    async openCastLibrary(name) {
      this.libRole = name
      this.libRows = []
      this.libMsg = ''
      this.libOpen = true
      this.libBusy = true
      try {
        const d = await dramaPresenters()
        const list = (d && d.presenters) || []
        const rows = []
        for (let i = 0; i < list.length; i++) {
          const p = list[i]
          const app = String(p.appearance || '')
          rows.push({
            id: p.id,
            name: p.name || '未命名',
            hasImg: !!p.image,
            imgUrl: p.image ? dramaPresenterUrl(p.id) + '?v=' + encodeURIComponent(p.image) : '',
            sourceLabel: LIB_SOURCE[p.source] || '',
            brief: app ? (app.length > 30 ? app.slice(0, 30) + '…' : app) : '（没写外观）',
          })
        }
        this.libRows = rows
      } catch (e) {
        this.libMsg = '读取人物库失败：' + (e.message || '')
      } finally {
        this.libBusy = false
      }
    },

    async pickLibPerson(p) {
      if (!this.cur || this.libBusyId) return
      if (!p.hasImg) {
        this.libMsg = '「' + p.name + '」还没有图，去「出镜人物」页传照片或生成四视图'
        return
      }
      this.libBusyId = p.id
      try {
        this.cur = await dramaCastFromLibrary(this.cur.id, p.id, this.libRole)
        this.libOpen = false
        uni.showToast({ title: '已绑到「' + this.libRole + '」', icon: 'none' })
      } catch (e) {
        this.libMsg = e.message || '绑定失败'
      } finally {
        this.libBusyId = ''
      }
    },

    closeLib() {
      if (this.libBusyId) return
      this.libOpen = false
    },
  },
  watch: {
    // 素材/计划一变就重排镜头卡（配画面、出片、九宫格都会改这几份数据）
    shotMats: { deep: true, handler() { this.rebuildAssets() } },
    clipItems: { deep: true, handler() { this.rebuildAssets() } },
    plan: { deep: true, handler() { this.rebuildAssets() } },
    'cur.grid': { deep: true, handler() { this.rebuildAssets() } },
  },
  computed: {
    /** 还没配参考图的人物：AI 出片时会一段一张脸，这里必须提前说（2026-11-08） */
    castMissing() {
      return (this.castList || []).filter((c) => !c.image).map((c) => c.name)
    },
    allReady() {
      const rows = this.shotRows || []
      return rows.length > 0 && rows.every((r) => r.hasImg || r.hasClip || r.thumb)
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
}
</script>

<style scoped>
.pgstate {
  padding: 60rpx;
  text-align: center;
  color: #9aa0a6;
  font-size: 24rpx;
}
.head-ops { display: flex; align-items: center; gap: 10rpx; }

/* 人物库弹层 */
.lib-mask {
  position: fixed;
  left: 0; right: 0; top: 0; bottom: 0;
  background: rgba(17, 24, 39, 0.45);
  z-index: 90;
  display: flex;
  align-items: flex-end;
}
.lib-sheet {
  width: 100%;
  max-height: 78vh;
  background: #fff;
  border-radius: 20rpx 20rpx 0 0;
  padding: 20rpx 24rpx 40rpx;
  box-sizing: border-box;
  overflow-y: auto;
}
.lib-head { display: flex; align-items: center; justify-content: space-between; padding-bottom: 12rpx; }
.lib-title { font-size: 26rpx; font-weight: 600; color: #1b1f27; }
.lib-x { font-size: 26rpx; color: #9aa0a6; padding: 6rpx 12rpx; }
.lib-state { padding: 40rpx 10rpx; font-size: 22rpx; color: #9aa0a6; line-height: 1.7; }
.lib-row {
  display: flex;
  align-items: center;
  gap: 16rpx;
  padding: 16rpx 0;
  border-bottom: 1rpx solid #f2f4f7;
}
.lib-row-dim { opacity: 0.5; }
.lib-thumb { width: 96rpx; height: 96rpx; border-radius: 10rpx; background: #f2f4f7; flex: none; }
.lib-thumb-empty {
  display: flex; align-items: center; justify-content: center;
  font-size: 20rpx; color: #b0b6bd; border: 1rpx dashed #dfe3e8;
}
.lib-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4rpx; }
.lib-name-line { display: flex; align-items: center; gap: 10rpx; }
.lib-name { font-size: 24rpx; font-weight: 600; color: #1b1f27; }
.lib-badge { padding: 2rpx 10rpx; border-radius: 999rpx; background: #e8f8f2; font-size: 18rpx; color: #0b8f6b; }
.lib-brief { font-size: 20rpx; color: #9aa0a6; }
.lib-go { flex: none; font-size: 21rpx; color: #0b8f6b; }
.lib-msg { padding-top: 14rpx; font-size: 21rpx; color: #c62828; line-height: 1.6; }

/* ===== 动作条（竞品 assets 页的标题 + 动词行） ===== */
.ab { padding: 6rpx 0 14rpx; }
.ab-head { display: flex; align-items: baseline; justify-content: space-between; }
.ab-title { font-size: 34rpx; font-weight: 700; color: #1b1f27; }
.ab-sub { font-size: 21rpx; color: #9aa0a6; }
.ab-ops { display: flex; flex-wrap: wrap; gap: 12rpx; margin-top: 14rpx; }
.ab-btn {
  padding: 12rpx 22rpx;
  border-radius: 999rpx;
  border: 1rpx solid #dfe3e8;
  background: #fff;
  font-size: 22rpx;
  color: #4b5563;
}
.ab-btn.off { opacity: 0.45; }
.ab-main { background: #0b8f6b; border-color: #0b8f6b; color: #fff; font-weight: 600; }

/* ===== 导演台（一行横滑） ===== */
.dir { white-space: nowrap; padding: 4rpx 0 16rpx; }
.dir-label {
  display: inline-block;
  margin-right: 12rpx;
  font-size: 21rpx;
  color: #9aa0a6;
  letter-spacing: 1rpx;
}
.dir-chip {
  display: inline-block;
  margin-right: 10rpx;
  padding: 9rpx 18rpx;
  border-radius: 999rpx;
  background: #f5f6f8;
  font-size: 21rpx;
  color: #4b5563;
}
.dir-chip.on { background: #e8f8f2; color: #0b8f6b; }
.dir-chip.dir-warn { background: #fff4e5; color: #b26a00; border-color: #f0a13c; }

/* ===== 就绪进度 ===== */
.prog { height: 8rpx; border-radius: 999rpx; background: #eef0f3; overflow: hidden; margin-bottom: 18rpx; }
.prog-in { height: 100%; background: #0b8f6b; transition: width 0.4s; }

/* ===== 出片计划条 ===== */
.planbar {
  margin: 6rpx 0 18rpx;
  padding: 18rpx 20rpx;
  border: 1rpx solid #c9ecdf;
  background: #f2fbf7;
  border-radius: 14rpx;
}
.planbar-title { font-size: 24rpx; font-weight: 600; color: #1b1f27; }
.planbar-price { margin-top: 6rpx; font-size: 22rpx; color: #0b8f6b; }
.planbar-ops { margin-top: 12rpx; }

/* ===== 每镜一张卡 ===== */
.shot {
  display: flex;
  gap: 16rpx;
  padding: 20rpx 0;
  border-bottom: 1rpx solid #f2f4f7;
}
.shot-side {
  flex: none;
  width: 92rpx;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6rpx;
}
.shot-no { font-size: 30rpx; font-weight: 700; color: #c3c8cf; }
.shot-type { font-size: 19rpx; color: #4b5563; background: #f5f6f8; border-radius: 6rpx; padding: 2rpx 8rpx; }
.shot-dur { font-size: 19rpx; color: #9aa0a6; }
.shot-real { font-size: 18rpx; border-radius: 6rpx; padding: 2rpx 8rpx; }
.shot-real.real { background: #e8f8f2; color: #0b8f6b; }
.shot-real.ai { background: #f3eefc; color: #7c4dff; }
.shot-main { flex: 1; min-width: 0; }
.shot-desc { font-size: 24rpx; color: #1b1f27; line-height: 1.55; }
.shot-camera { margin-top: 6rpx; font-size: 21rpx; color: #9aa0a6; }
.shot-src { margin-top: 4rpx; font-size: 20rpx; color: #9aa0a6; }
.shot-warn { margin-top: 6rpx; font-size: 20rpx; color: #a06400; }
.shot-side2 { flex: none; width: 150rpx; display: flex; flex-direction: column; align-items: flex-end; gap: 8rpx; }
.shot-thumb {
  width: 140rpx; height: 92rpx; border-radius: 10rpx; background: #f2f4f7;
}
.shot-thumb-empty {
  display: flex; align-items: center; justify-content: center;
  font-size: 22rpx; color: #c3c8cf; border: 1rpx dashed #dfe3e8;
}
.shot-ops { display: flex; flex-direction: column; align-items: flex-end; gap: 4rpx; }
.shot-op { font-size: 20rpx; color: #0b8f6b; padding: 2rpx 0; }
.shot-op.off { opacity: 0.4; }
.shot-op.play { color: #4b5563; }

.next-row { display: flex; justify-content: flex-end; padding: 30rpx 0 10rpx; }
</style>
