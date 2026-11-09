import dramaPage from './dramaPage'

/**
 * 四步页面共用的「打开一个项目」引导。
 *
 * 旧单页把所有加载都塞在 onShow 里（`drama/index.vue:3338`），
 * 拆页后每页都会重建组件，所以改成：进页 → 拉选项（缺才拉）→ 打开项目。
 * 🩸 顺序不能反：`open()` 读 `this.opt.default_film_model`，选项没到就打开会拿到空型号。
 */
export default {
  mixins: [dramaPage],
  data() {
    return { pid: '' }
  },
  methods: {
    async boot(pid) {
      this.pid = pid || ''
      if (!this.opt.categories.length) await this.safe(this.loadOptions)
      if (!this.compOpt.transitions.length) await this.safe(this.loadComposeOptions)
      if (!this.stKeys.length) await this.safe(this.initSettingsDefaults)
      if (!this.matOpt.platforms.length) await this.safe(this.loadMaterialOptions)
      if (!this.stockSources.length) await this.safe(this.loadStockSources)
      await this.safe(this.loadTemplatesMeta)
      await this.safe(this.loadScriptTpls)
      if (this.pid) await this.open(this.pid)
    },
    /** 任何一项拉不到都不该把整页打死 —— 页面里各自有兜底渲染。多余参数原样传给 fn */
    async safe(fn, ...args) {
      try {
        return await fn.call(this, ...args)
      } catch (e) {
        return null
      }
    },
  },
}
