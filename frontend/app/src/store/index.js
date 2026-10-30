import { reactive } from 'vue'

const HISTORY_KEY = 'vt_history'
const MAX_HISTORY = 50

/** 当前解析结果（页面间传递，避免 URL 过长） */
export const store = reactive({
  current: null,
})

export function setCurrent(data) {
  store.current = data
  addHistory(data)
}

export function getHistory() {
  try {
    return uni.getStorageSync(HISTORY_KEY) || []
  } catch (e) {
    return []
  }
}

export function addHistory(data) {
  if (!data || !data.token) return
  const item = {
    token: data.token,
    platform: data.platform,
    title: data.title,
    cover: data.cover,
    is_video: data.is_video,
    time: Date.now(),
  }
  const list = getHistory().filter((x) => x.token !== item.token)
  list.unshift(item)
  try {
    uni.setStorageSync(HISTORY_KEY, list.slice(0, MAX_HISTORY))
  } catch (e) {
    /* 存储满了忽略 */
  }
}

export function removeHistory(token) {
  const list = getHistory().filter((x) => x.token !== token)
  try {
    uni.setStorageSync(HISTORY_KEY, list)
  } catch (e) {
    /* ignore */
  }
}

export function clearHistory() {
  try {
    uni.removeStorageSync(HISTORY_KEY)
  } catch (e) {
    /* ignore */
  }
}
