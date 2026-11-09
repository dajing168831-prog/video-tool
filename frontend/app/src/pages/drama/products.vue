<template>
  <DramaAppShell>
    <view class="ds">
      <view class="page-wrap">
        <view class="pl-head">
          <view class="pl-head-main">
            <text class="pl-title">商品库</text>
            <text class="pl-sub">跨项目复用：新建 / 编辑商品卡，批量作业和项目里直接选。</text>
          </view>
          <view class="pl-add" @click="openAdd">＋ 添加商品</view>
        </view>

        <!-- 添加商品（照竞品 /products 的「添加商品」表单） -->
        <view v-if="add.open" class="card">
          <view class="card-head">
            <view class="card-title"><text class="card-no">新</text>添加商品</view>
            <text class="pl-cancel" @click="closeAdd">取消</text>
          </view>
          <view class="fld">
            <text class="pl-lbl">商品名称</text>
            <input v-model="add.name" class="input line" placeholder="例：小米手环8 NFC版" />
          </view>
          <view class="fld">
            <text class="pl-lbl">商品品类</text>
            <input v-model="add.category" class="input line" placeholder="美妆护肤 / 食品零食 / 家居日用…" />
          </view>
          <view class="fld">
            <text class="pl-lbl">价格</text>
            <input v-model="add.price" class="input line" placeholder="例：¥199" />
          </view>
          <view class="fld">
            <text class="pl-lbl">目标人群</text>
            <input v-model="add.audience" class="input line" placeholder="例：18-35岁女性" />
          </view>
          <view class="fld">
            <text class="pl-lbl">卖点（每行一条）</text>
            <textarea v-model="add.points" class="input area" auto-height placeholder="三层加厚，湿水不破" />
          </view>
          <view class="fld">
            <text class="pl-lbl">商品图（{{ add.files.length }}/5）</text>
            <view class="pl-pics">
              <view v-for="(f, i) in add.files" :key="'af' + i" class="pl-pic">
                <image class="pl-pic-img" :src="f.path" mode="aspectFill" />
                <text class="pl-pic-del" @click.stop="dropAddPic(i)">×</text>
              </view>
              <view v-if="add.files.length < 5" class="pl-pic pl-pic-add" @click="pickAddPics">＋</view>
            </view>
          </view>
          <view class="fld">
            <text class="pl-lbl">原始资料（可选）</text>
            <textarea v-model="add.facts" class="input area" auto-height placeholder="参数 / 认证 / 评价，没有就留空" />
          </view>
          <view class="pl-ops">
            <view class="pl-save" @click="saveAdd">{{ addBusy ? '保存中…' : '加进商品库' }}</view>
          </view>
        </view>

        <!-- 编辑卡：点一行进来改 -->
        <view v-if="edit.id" class="card">
          <view class="card-head">
            <view class="card-title"><text class="card-no">改</text>编辑商品</view>
            <text class="pl-cancel" @click="closeEdit">取消</text>
          </view>
          <view class="fld">
            <text class="pl-lbl">商品名称</text>
            <input v-model="edit.name" class="input line" placeholder="例：小米手环8 NFC版" />
          </view>
          <view class="fld">
            <text class="pl-lbl">品类</text>
            <input v-model="edit.category" class="input line" placeholder="美妆护肤 / 食品零食 / 家居日用…" />
          </view>
          <view class="fld">
            <text class="pl-lbl">价格</text>
            <input v-model="edit.price" class="input line" placeholder="例：¥199" />
          </view>
          <view class="fld">
            <text class="pl-lbl">目标人群</text>
            <input v-model="edit.audience" class="input line" placeholder="例：18-35岁女性" />
          </view>
          <view class="fld">
            <text class="pl-lbl">卖点（每行一条）</text>
            <textarea v-model="edit.points" class="input area" auto-height placeholder="三层加厚，湿水不破" />
          </view>
          <view class="fld">
            <text class="pl-lbl">商品图（{{ edit.images.length }}/5）</text>
            <view class="pl-pics">
              <view v-for="(n, i) in edit.images" :key="'ei' + n" class="pl-pic">
                <image class="pl-pic-img" :src="imgUrl2(edit.id, n)" mode="aspectFill" />
                <text class="pl-pic-del" @click.stop="dropEditPic(n)">×</text>
              </view>
              <view v-if="edit.images.length < 5" class="pl-pic pl-pic-add" @click="pickEditPic">
                {{ editImgBusy ? '…' : '＋' }}
              </view>
            </view>
          </view>
          <view class="fld">
            <text class="pl-lbl">原始资料</text>
            <textarea v-model="edit.facts" class="input area" auto-height placeholder="参数 / 认证 / 评价，没有就留空" />
          </view>
          <view class="pl-ops">
            <view class="pl-save" @click="saveEdit">{{ editBusy ? '保存中…' : '保存' }}</view>
          </view>
        </view>

        <view v-if="loading" class="pl-state">正在加载…</view>
        <view v-else-if="!items.length" class="pl-state">
          还没有商品卡 —— 点右上「＋ 添加商品」，或进任意项目把商品存进来。
        </view>

        <view v-for="it in items" :key="it.id" class="pl-card" @click="openEdit(it)">
          <image
            v-if="it.images && it.images.length"
            class="pl-thumb"
            :src="imgUrl(it)"
            mode="aspectFill"
          />
          <view v-else class="pl-thumb pl-thumb-none">无图</view>
          <view class="pl-card-main">
            <text class="pl-card-name">{{ it.name }}</text>
            <text class="pl-card-meta">
              {{ it.category || '未分类' }}<text v-if="it.price"> · {{ it.price }}</text>
            </text>
            <text v-if="it.audience" class="pl-card-meta">{{ it.audience }}</text>
            <text v-if="it.points && it.points.length" class="pl-card-meta">
              {{ it.points.length }} 条卖点
            </text>
            <text class="pl-card-time">{{ it.updated || '' }}</text>
          </view>
          <view class="pl-card-side">
            <text class="pl-edit" @click.stop="openEdit(it)">编辑</text>
            <text class="pl-card-del" @click.stop="remove(it)">删除</text>
          </view>
        </view>
      </view>
    </view>
  </DramaAppShell>
</template>

<script>
import DramaAppShell from '@/components/drama/AppShell.vue'
import {
  dramaProducts, dramaProductDelete, dramaProductPatch, dramaProductCreate,
  dramaProductImageUpload, dramaProductImageDelete, dramaProductImageUrl,
} from '@/api/request'

const EMPTY_EDIT = {
  id: '', name: '', category: '', price: '', audience: '', points: '', facts: '', images: [],
}
const EMPTY_ADD = {
  open: false, name: '', category: '', price: '', audience: '', points: '', facts: '', files: [],
}

/**
 * 商品库（照竞品 /products）：添加 → 编辑（含图片）→ 删除。
 *
 * 「添加商品」是 2026-11-07 补的：后端加了 `POST /products/create` 与
 * `POST /products/{id}/images`，所以不再只能「从项目存进库」。
 * 旧链路（项目里存进库）保留，两种入口并存。
 */
export default {
  components: { DramaAppShell },
  data() {
    return {
      items: [],
      loading: false,
      // 🩸 data() 里不能调 methods（methods 还没挂），用模块级常量
      edit: { ...EMPTY_EDIT },
      editBusy: false,
      editImgBusy: false,
      add: { ...EMPTY_ADD },
      addBusy: false,
    }
  },
  onShow() {
    this.load()
  },
  methods: {
    async load() {
      this.loading = true
      try {
        const r = await dramaProducts()
        this.items = (r && r.products) || r || []
      } catch (e) {
        this.items = []
      } finally {
        this.loading = false
      }
    },
    imgUrl(it) {
      return dramaProductImageUrl(it.id, it.images[0])
    },
    imgUrl2(id, name) {
      return dramaProductImageUrl(id, name)
    },
    rowOf(id) {
      for (let i = 0; i < this.items.length; i++) {
        if (this.items[i].id === id) return this.items[i]
      }
      return null
    },

    /* ---------- 添加 ---------- */
    openAdd() {
      this.edit = { ...EMPTY_EDIT }
      this.add = { ...EMPTY_ADD, open: true }
    },
    closeAdd() {
      this.add = { ...EMPTY_ADD }
    },
    pickAddPics() {
      const left = 5 - this.add.files.length
      if (left <= 0) return
      uni.chooseImage({
        count: left,
        sizeType: ['compressed'],
        success: (res) => {
          const paths = (res && res.tempFilePaths) || []
          this.add.files = this.add.files.concat(paths.slice(0, left).map((p) => ({ path: p })))
        },
      })
    },
    dropAddPic(i) {
      const files = this.add.files.slice()
      files.splice(i, 1)
      this.add.files = files
    },
    async saveAdd() {
      if (this.addBusy) return
      if (!(this.add.name || '').trim()) {
        uni.showToast({ title: '名称不能空', icon: 'none' })
        return
      }
      this.addBusy = true
      try {
        const row = await dramaProductCreate({
          name: this.add.name.trim(),
          category: this.add.category,
          price: this.add.price,
          audience: this.add.audience,
          facts: this.add.facts,
          points: this.add.points.split('\n').map((s) => s.trim()).filter(Boolean),
        })
        // 卡片建好再补图（图要跟着卡目录走，所以必须卡先存在）
        for (let i = 0; i < this.add.files.length; i++) {
          // eslint-disable-next-line no-await-in-loop
          await dramaProductImageUpload(row.id, this.add.files[i].path)
        }
        uni.showToast({ title: '已加进商品库', icon: 'success' })
        this.closeAdd()
        await this.load()
      } catch (e) {
        uni.showToast({ title: e.message || '保存失败', icon: 'none' })
      } finally {
        this.addBusy = false
      }
    },

    /* ---------- 编辑 ---------- */
    openEdit(it) {
      this.add = { ...EMPTY_ADD }
      this.edit = {
        id: it.id,
        name: it.name || '',
        category: it.category || '',
        price: it.price || '',
        audience: it.audience || '',
        points: (it.points || []).join('\n'),
        facts: it.facts || '',
        images: (it.images || []).slice(),
      }
    },
    closeEdit() {
      this.edit = { ...EMPTY_EDIT }
    },
    syncEditImages() {
      const row = this.rowOf(this.edit.id)
      if (row) this.edit = { ...this.edit, images: (row.images || []).slice() }
    },
    pickEditPic() {
      if (this.editImgBusy || !this.edit.id) return
      uni.chooseImage({
        count: 1,
        sizeType: ['compressed'],
        success: async (res) => {
          const path = ((res && res.tempFilePaths) || [])[0]
          if (!path) return
          this.editImgBusy = true
          try {
            await dramaProductImageUpload(this.edit.id, path)
            await this.load()
            this.syncEditImages()
          } catch (e) {
            uni.showToast({ title: e.message || '上传失败', icon: 'none' })
          } finally {
            this.editImgBusy = false
          }
        },
      })
    },
    async dropEditPic(name) {
      if (this.editImgBusy || !this.edit.id) return
      this.editImgBusy = true
      try {
        await dramaProductImageDelete(this.edit.id, name)
        await this.load()
        this.syncEditImages()
      } catch (e) {
        uni.showToast({ title: e.message || '删除失败', icon: 'none' })
      } finally {
        this.editImgBusy = false
      }
    },
    async saveEdit() {
      const e = this.edit
      if (!e.id || this.editBusy) return
      if (!e.name.trim()) {
        uni.showToast({ title: '名称不能空', icon: 'none' })
        return
      }
      this.editBusy = true
      try {
        await dramaProductPatch(e.id, {
          name: e.name.trim(),
          category: e.category,
          price: e.price,
          audience: e.audience,
          facts: e.facts,
          points: e.points.split('\n').map((s) => s.trim()).filter(Boolean),
        })
        uni.showToast({ title: '已保存', icon: 'success' })
        this.closeEdit()
        await this.load()
      } catch (err) {
        uni.showToast({ title: err.message || '保存失败', icon: 'none' })
      } finally {
        this.editBusy = false
      }
    },
    remove(it) {
      uni.showModal({
        title: '删除商品卡',
        content: `确定删除「${it.name}」？已建的项目不受影响。`,
        success: async (r) => {
          if (!r.confirm) return
          try {
            await dramaProductDelete(it.id)
            if (this.edit.id === it.id) this.closeEdit()
            this.load()
          } catch (e) {
            uni.showToast({ title: e.message || '删除失败', icon: 'none' })
          }
        },
      })
    },
  },
}
</script>

<style scoped>
.pl-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 20rpx;
}
.pl-head-main { flex: 1; min-width: 0; }
.pl-title { display: block; font-size: 32rpx; font-weight: 700; }
.pl-sub { display: block; margin-top: 6rpx; font-size: 21rpx; color: #9aa0a6; line-height: 1.5; }
.pl-add {
  flex: none;
  margin-left: 16rpx;
  padding: 14rpx 24rpx;
  border-radius: 999rpx;
  background: #12b886;
  color: #fff;
  font-size: 23rpx;
  font-weight: 600;
}
.pl-state { padding: 60rpx; text-align: center; color: #9aa0a6; font-size: 23rpx; }
.pl-card {
  display: flex;
  align-items: center;
  gap: 18rpx;
  padding: 20rpx 22rpx;
  background: #fff;
  border-radius: 14rpx;
  margin-bottom: 12rpx;
}
.pl-thumb {
  width: 110rpx;
  height: 110rpx;
  border-radius: 12rpx;
  background: #f2f4f8;
  flex: none;
}
.pl-thumb-none {
  font-size: 20rpx;
  color: #b0b7c3;
  text-align: center;
  line-height: 110rpx;
}
.pl-card-main { flex: 1; min-width: 0; }
.pl-card-name { display: block; font-size: 26rpx; font-weight: 600; color: #1f2329; }
.pl-card-meta { display: block; margin-top: 4rpx; font-size: 21rpx; color: #6b7280; }
.pl-card-time { display: block; margin-top: 4rpx; font-size: 19rpx; color: #b0b6bd; }
.pl-card-side { flex: none; display: flex; flex-direction: column; gap: 10rpx; align-items: flex-end; }
.pl-edit { font-size: 21rpx; color: #0b8f6b; }
.pl-card-del { font-size: 21rpx; color: #f56c6c; }
.fld { margin-bottom: 18rpx; }
.pl-lbl { display: block; margin-bottom: 8rpx; font-size: 22rpx; color: #6b7280; }
.pl-ops { display: flex; justify-content: flex-end; padding-top: 6rpx; }
.pl-save {
  padding: 16rpx 48rpx;
  border-radius: 12rpx;
  background: #12b886;
  color: #fff;
  font-size: 25rpx;
  font-weight: 600;
}
.pl-cancel { font-size: 22rpx; color: #9aa3af; }
.pl-pics { display: flex; flex-wrap: wrap; }
.pl-pic {
  position: relative;
  width: 120rpx;
  height: 120rpx;
  margin: 0 14rpx 14rpx 0;
  border-radius: 12rpx;
  overflow: hidden;
  background: #f2f4f8;
}
.pl-pic-img { width: 100%; height: 100%; }
.pl-pic-del {
  position: absolute;
  top: 2rpx;
  right: 2rpx;
  width: 34rpx;
  height: 34rpx;
  line-height: 32rpx;
  text-align: center;
  border-radius: 10rpx;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  font-size: 22rpx;
}
.pl-pic-add {
  font-size: 40rpx;
  color: #9aa3af;
  text-align: center;
  line-height: 116rpx;
  border: 2rpx dashed #dfe3ea;
  box-sizing: border-box;
}
</style>
