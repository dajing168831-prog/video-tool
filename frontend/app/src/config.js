/**
 * 全局配置
 *
 * API_BASE 说明：
 * - H5：按**当前页面的主机名**拼后端地址 —— 局域网里别的电脑打开
 *   http://192.168.1.10:8920 ，它就会去连 http://192.168.1.10:8911 。
 *   写死 127.0.0.1 的话，别人那台机器会去连它自己的本机，整个前端全是"网络异常"。
 * - 小程序开发：必须用局域网 IP，手机才连得到（开发者工具里关掉「校验合法域名」）
 * - 上线：换成备案域名（微信/抖音小程序都要求 HTTPS 且域名已加入白名单）
 */
const isH5 = process.env.UNI_PLATFORM === 'h5'

// 构建时可用 VITE_API_BASE 覆盖（预发环境、联调端口都靠它，免得改代码再打包）
const ENV_BASE = (import.meta.env && import.meta.env.VITE_API_BASE) || ''

const API_PORT = 8911

function h5Base() {
  // 小程序/App 侧没有 window，这段只在浏览器里走
  if (typeof window !== 'undefined' && window.location && window.location.hostname) {
    const proto = window.location.protocol === 'https:' ? 'https:' : 'http:'
    return `${proto}//${window.location.hostname}:${API_PORT}`
  }
  return `http://127.0.0.1:${API_PORT}`
}

export const API_BASE = ENV_BASE || (isH5 ? h5Base() : 'http://192.168.1.10:8911')

export const APP_NAME = '视频工具'

/**
 * 当前开放的平台。
 * 必须与后端 VT_ENABLED_PLATFORMS 一致：前端控制界面上显示哪些平台，
 * 后端控制实际放不放行，两边漏改一边就会出现「显示但解析报暂不支持」。
 * 2026-10-23 加 tiktok（内部测试）；2026-10-29 加 twitter（X）。
 * 🩸 X 走 yt-dlp 直连，没配代理时解析会失败 —— 见后端 config.py 的注释。
 */
export const ENABLED_PLATFORMS = [
  'douyin', 'kuaishou', 'xiaohongshu', 'bilibili', 'tiktok', 'twitter',
]

/** 平台展示名（含未开放平台，供历史记录展示） */
export const PLATFORM_LABEL = {
  douyin: '抖音',
  kuaishou: '快手',
  xiaohongshu: '小红书',
  bilibili: 'B站',
  tiktok: 'TikTok',
  instagram: 'Instagram',
  twitter: 'X',
}
