import { watch } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'

import AdminPage from '../pages/AdminPage.vue'
import LoginPage from '../pages/LoginPage.vue'
import ResetPasswordPage from '../pages/ResetPasswordPage.vue'
import { useAuth } from '../stores/auth'

const routes = [
  { path: '/', redirect: () => (useAuth().isAuthenticated.value ? '/admin' : '/login') },
  { path: '/login', name: 'login', component: LoginPage, meta: { guestOnly: true } },
  {
    path: '/reset-password',
    name: 'reset-password',
    component: ResetPasswordPage,
    meta: { guestOnly: true }
  },
  { path: '/admin', name: 'admin', component: AdminPage, meta: { requiresAuth: true } },
  { path: '/:pathMatch(.*)*', redirect: '/' }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

let restored = false

router.beforeEach(async (to) => {
  const auth = useAuth()

  // 页面刷新后先用 refresh cookie 恢复会话（只做一次），避免闪回登录页
  if (!restored) {
    restored = true
    if (!auth.isAuthenticated.value) await auth.restore()
  }

  if (to.meta.requiresAuth && !auth.isAuthenticated.value) {
    return { path: '/login', query: to.fullPath === '/admin' ? {} : { redirect: to.fullPath } }
  }

  if (to.meta.guestOnly && auth.isAuthenticated.value) {
    return '/admin'
  }

  return true
})

watch(useAuth().status, status => {
  if (status === 'anonymous' && router.currentRoute.value.meta.requiresAuth) router.replace('/login')
})

export default router
