import { ref, computed } from 'vue'
import { dramaGet } from '@/api/request'

/**
 * 项目页共用：按 id 拉一份项目 doc。
 *
 * 竞品是每页自己 `fetch('/api/project/[id]/production')` 拉快照（见 production/route.ts:1-20）；
 * 我们是把它拆成「一次 dramaGet + 本地分组」，因为后端返回的就是整份项目 JSON。
 * 🩸 不要在页面之间传整份 doc：四步页面各自按 id 重拉，刷新/深链都不会白屏。
 */
export function useDramaProject() {
  const id = ref('')
  const doc = ref(null)
  const loading = ref(false)
  const error = ref('')

  async function load(pid) {
    if (pid) id.value = pid
    if (!id.value) {
      error.value = '缺少项目号'
      return null
    }
    loading.value = true
    error.value = ''
    try {
      doc.value = await dramaGet(id.value)
      return doc.value
    } catch (e) {
      error.value = (e && e.message) || '打开失败'
      return null
    } finally {
      loading.value = false
    }
  }

  const product = computed(() => (doc.value && doc.value.product) || {})
  const projectName = computed(() => product.value.name || '未命名')
  const script = computed(() => (doc.value && (doc.value.script_json || doc.value.script)) || null)
  const storyboard = computed(() => (doc.value && doc.value.storyboard_json) || null)
  const film = computed(() => (doc.value && doc.value.film) || {})

  return { id, doc, loading, error, load, product, projectName, script, storyboard, film }
}
