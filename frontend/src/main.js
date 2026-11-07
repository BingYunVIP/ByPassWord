import { createApp } from 'vue'

// Maple Mono 全局等宽字体（https://github.com/subframe7536/maple-font）
import '@fontsource/maple-mono/400.css'
import '@fontsource/maple-mono/500.css'
import '@fontsource/maple-mono/600.css'
import '@fontsource/maple-mono/700.css'

import './styles/main.css'
import App from './App.vue'
import router from './router'

const app = createApp(App)
app.use(router)

// 等首次路由（含会话恢复）解析完再挂载，避免已登录用户看到登录页闪一下
router.isReady().then(() => app.mount('#app'))
