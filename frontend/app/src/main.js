import { createSSRApp } from 'vue'
import App from './App.vue'
// 商品短剧四步页共用的样式（从旧单页原样搬出，选择器统一加 .ds 前缀，不会污染别的页）
import './styles/drama.css'

export function createApp() {
  const app = createSSRApp(App)
  return { app }
}
