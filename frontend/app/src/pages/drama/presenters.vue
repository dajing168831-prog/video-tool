<template>
  <DramaAppShell>
    <view class="ds">
      <view class="page-wrap">
        <view class="pv-head">
          <view class="pv-title">出镜人物</view>
          <view class="pv-sub">
            跨项目复用的人物库。有图就传图，没图就在这里生成四视图；挑好的人再从素材页绑到某一部片子的角色上。
          </view>
        </view>

        <!-- 1 人物库 -->
        <view class="card">
          <view class="card-head">
            <view class="card-title"><text class="card-no">人</text>库里的人物</view>
            <view class="btn-mini" @click="load">{{ loading ? '读取中…' : '刷新' }}</view>
          </view>

          <view v-if="loading && !rows.length" class="empty">正在读取…</view>
          <view v-else-if="!rows.length" class="empty">还没有人物。下面加一个：写清外观，或者直接传一张照片。</view>

          <view v-for="p in rows" :key="p.id" class="pv-row">
            <image v-if="p.hasImg" class="pv-thumb" :src="p.imgUrl" mode="aspectFill"
                   @click="previewBig(p)" />
            <view v-else class="pv-thumb pv-thumb-empty" @click="genSheet(p)">＋</view>

            <view class="pv-main">
              <view class="pv-name-line">
                <text class="pv-name">{{ p.name }}</text>
                <text v-if="p.sourceLabel" class="pv-badge">{{ p.sourceLabel }}</text>
              </view>
              <text class="pv-app">{{ p.appearanceBrief || '（还没写外观）' }}</text>
              <text v-if="p.note" class="pv-note">{{ p.note }}</text>
            </view>

            <view class="pv-ops">
              <view class="btn-mini" @click="pickPhoto(p)">传照片</view>
              <view class="btn-mini" @click="genSheet(p)">
                {{ sheetBusy === p.id ? '生成中…' : (p.hasImg ? '重生成' : '生成四视图') }}
              </view>
              <view class="btn-mini" @click="editOne(p)">改</view>
              <view class="btn-mini pv-del" @click="delOne(p)">删</view>
            </view>
          </view>
        </view>

        <!-- 2 新建 / 修改 -->
        <view class="card">
          <view class="card-head">
            <view class="card-title">
              <text class="card-no">{{ editingId ? '改' : '新' }}</text>{{ editingId ? '修改人物' : '加一个人物' }}
            </view>
            <view v-if="editingId" class="btn-mini" @click="resetForm">取消修改</view>
          </view>

          <view class="pv-field">
            <text class="pv-label">名字</text>
            <input v-model="form.name" class="pv-input" placeholder="例：小张" maxlength="24" />
          </view>
          <view class="pv-field">
            <text class="pv-label">外观</text>
            <textarea v-model="form.appearance" class="pv-area" maxlength="400"
                      placeholder="发型 / 服装 / 年龄段 + 一个随身细节（例：短寸头，灰夹克袖口磨白，30 岁）" />
          </view>
          <view class="pv-field">
            <text class="pv-label">备注</text>
            <input v-model="form.note" class="pv-input" placeholder="可选：这个人用在哪类片子里" maxlength="400" />
          </view>

          <view class="pv-tip">
            外观写清楚，生成定妆照才有依据；不想生成就加完之后「传照片」。
          </view>
          <view class="pv-actions">
            <view class="btn-main" @click="save">{{ editingId ? '保存修改' : '加进人物库' }}</view>
          </view>
          <view v-if="msg" class="pv-msg">{{ msg }}</view>
        </view>
      </view>
    </view>
  </DramaAppShell>
</template>

<script>
import DramaAppShell from '@/components/drama/AppShell.vue'
import {
  dramaPresenters,
  dramaPresenterCreate,
  dramaPresenterPatch,
  dramaPresenterDelete,
  dramaPresenterPhoto,
  dramaPresenterSheet,
  dramaPresenterUrl,
} from '@/api/request'

const SOURCE_LABEL = { upload: '上传', sheet: '定妆' }

export default {
  components: { DramaAppShell },
  data() {
    return {
      rows: [],
      loading: false,
      saving: false,
      sheetBusy: '',
      editingId: '',
      form: { name: '', appearance: '', note: '' },
      msg: '',
    }
  },
  onShow() {
    this.load()
  },
  methods: {
    async load() {
      this.loading = true
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
            appearanceBrief: app.length > 40 ? app.slice(0, 40) + '…' : app,
            appearance: app,
            note: p.note || '',
            source: p.source || '',
            sourceLabel: SOURCE_LABEL[p.source] || '',
            hasImg: !!p.image,
            // 提前拼好：模板里不调函数
            imgUrl: p.image ? dramaPresenterUrl(p.id) + '?v=' + encodeURIComponent(p.image) : '',
          })
        }
        this.rows = rows
      } catch (e) {
        this.rows = []
        this.msg = '读取失败：' + (e.message || '')
      } finally {
        this.loading = false
      }
    },

    resetForm() {
      this.editingId = ''
      this.form = { name: '', appearance: '', note: '' }
    },

    editOne(p) {
      this.editingId = p.id
      this.form = { name: p.name, appearance: p.appearance, note: p.note }
      this.msg = ''
    },

    async save() {
      const name = String(this.form.name || '').trim()
      if (!name) {
        this.msg = '先写个名字'
        return
      }
      if (this.saving) return
      this.saving = true
      this.msg = ''
      try {
        if (this.editingId) {
          await dramaPresenterPatch(this.editingId, {
            name,
            appearance: this.form.appearance,
            note: this.form.note,
          })
          this.msg = '已保存'
        } else {
          await dramaPresenterCreate(name, this.form.appearance, this.form.note)
          this.msg = '已加进人物库'
        }
        this.resetForm()
        await this.load()
      } catch (e) {
        this.msg = e.message || '保存失败'
      } finally {
        this.saving = false
      }
    },

    /** 有图就传图：选一张本地照片当这个人的脸 */
    pickPhoto(p) {
      uni.chooseImage({
        count: 1,
        sizeType: ['compressed'],
        sourceType: ['album', 'camera'],
        success: async (res) => {
          const path = res.tempFilePaths && res.tempFilePaths[0]
          if (!path) return
          uni.showLoading({ title: '上传中…', mask: true })
          try {
            await dramaPresenterPhoto(p.id, path)
            await this.load()
            uni.showToast({ title: '已换图', icon: 'none' })
          } catch (e) {
            uni.showModal({ title: '上传失败', content: e.message || '', showCancel: false })
          } finally {
            uni.hideLoading()
          }
        },
      })
    },

    /** 没图就在这里生成 2×2 四视图定妆照（花钱 —— 必须用户点并二次确认） */
    genSheet(p) {
      if (this.sheetBusy) return
      if (!p.appearance) {
        uni.showModal({
          title: '先写外观',
          content: '定妆照要照外观画：发型 / 服装 / 年龄段。点「改」补一下再来。',
          showCancel: false,
        })
        return
      }
      uni.showModal({
        title: '生成四视图定妆照？',
        content: '按「' + p.appearanceBrief + '」画正面/侧面/背面/半身四格。会调用一次图片模型（花钱），生成约需 1 分钟。',
        confirmText: '生成',
        success: async (r) => {
          if (!r.confirm) return
          this.sheetBusy = p.id
          try {
            await dramaPresenterSheet(p.id)
            await this.load()
            uni.showToast({ title: '定妆照已生成', icon: 'none' })
          } catch (e) {
            uni.showModal({ title: '生成失败', content: e.message || '', showCancel: false })
          } finally {
            this.sheetBusy = ''
          }
        },
      })
    },

    previewBig(p) {
      if (!p.hasImg) return
      uni.previewImage({ urls: [p.imgUrl] })
    },

    delOne(p) {
      uni.showModal({
        title: '从人物库删掉？',
        content: '「' + p.name + '」会从库里摘掉；已经绑进片子的照样能用，不受影响。',
        success: async (r) => {
          if (!r.confirm) return
          try {
            await dramaPresenterDelete(p.id)
            if (this.editingId === p.id) this.resetForm()
            await this.load()
            uni.showToast({ title: '已删除', icon: 'none' })
          } catch (e) {
            uni.showModal({ title: '删除失败', content: e.message || '', showCancel: false })
          }
        },
      })
    },
  },
}
</script>

<style scoped>
.pv-head { padding: 4rpx 0 18rpx; }
.pv-title { font-size: 34rpx; font-weight: 700; color: #1b1f27; }
.pv-sub { margin-top: 8rpx; font-size: 21rpx; color: #9aa0a6; line-height: 1.6; }

.pv-row {
  display: flex;
  align-items: flex-start;
  gap: 16rpx;
  padding: 16rpx 0;
  border-bottom: 1rpx solid #f2f4f7;
}
.pv-thumb { width: 112rpx; height: 112rpx; border-radius: 12rpx; background: #f2f4f7; flex: none; }
.pv-thumb-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 40rpx;
  color: #b0b6bd;
  border: 1rpx dashed #dfe3e8;
}
.pv-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4rpx; }
.pv-name-line { display: flex; align-items: center; gap: 10rpx; }
.pv-name { font-size: 25rpx; font-weight: 600; color: #1b1f27; }
.pv-badge {
  padding: 2rpx 10rpx;
  border-radius: 999rpx;
  background: #e8f8f2;
  font-size: 18rpx;
  color: #0b8f6b;
}
.pv-app { font-size: 21rpx; color: #4b5563; line-height: 1.6; }
.pv-note { font-size: 20rpx; color: #9aa0a6; line-height: 1.6; }
.pv-ops { flex: none; display: flex; flex-wrap: wrap; gap: 8rpx; width: 210rpx; justify-content: flex-end; }
.pv-del { color: #c62828; }

.pv-field { display: flex; align-items: flex-start; gap: 12rpx; padding: 12rpx 0; }
.pv-label { flex: none; width: 72rpx; font-size: 22rpx; color: #9aa0a6; padding-top: 8rpx; }
.pv-input {
  flex: 1;
  padding: 12rpx 16rpx;
  border-radius: 10rpx;
  background: #f7f8fa;
  font-size: 23rpx;
  color: #1b1f27;
}
.pv-area {
  flex: 1;
  height: 140rpx;
  padding: 12rpx 16rpx;
  border-radius: 10rpx;
  background: #f7f8fa;
  font-size: 23rpx;
  color: #1b1f27;
  line-height: 1.6;
  box-sizing: border-box;
}
.pv-tip { padding: 10rpx 0; font-size: 20rpx; color: #9aa0a6; line-height: 1.6; }
.pv-actions { display: flex; gap: 12rpx; padding-top: 6rpx; }
.pv-msg { padding-top: 10rpx; font-size: 21rpx; color: #0b8f6b; }
</style>
