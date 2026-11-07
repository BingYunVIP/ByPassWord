<script setup>
import AppIcon from '../components/common/AppIcon.vue'
import { computed, ref, onMounted, onUnmounted } from 'vue'
import * as authApi from '../api/auth'
import { useRoute, useRouter } from 'vue-router'

import { useAuth, onSensitiveClear } from '../stores/auth'

const auth = useAuth()
const router = useRouter()
const route = useRoute()

const registrationAllowed = ref(false)
const mode = ref('login') // login | register
const step = ref('password') // password | 2fa | recovery-login | recovery-codes
const email = ref('')
const password = ref('')
const confirmPassword = ref('')
const code = ref('')
const recoveryInput = ref('')
const showPassword = ref(false)
const error = ref('')
const busy = ref(false)
const issuedRecoveryCode = ref('')

const title = computed(() => (mode.value === 'register' ? '创建密码库' : '密码库'))
const canSubmit = computed(() => email.value.trim() && password.value.length >= 8 && !busy.value)

function goNext() {
  const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/admin'
  router.replace(redirect.startsWith('/') && !redirect.startsWith('//') ? redirect : '/admin')
}

async function submitPassword() {
  error.value = ''
  if (mode.value === 'register') return submitRegister()

  busy.value = true
  try {
    const result = await auth.login(email.value.trim(), password.value)
    if (result.requires2fa) {
      password.value = ''
      step.value = '2fa'
      code.value = ''
    } else {
      goNext()
    }
  } catch (e) {
    error.value = e.message || '登录失败'
  } finally {
    busy.value = false
  }
}

async function submitRegister() {
  error.value = ''
  if (password.value.length < 12) {
    error.value = '主密码至少 12 位'
    return
  }
  if (password.value !== confirmPassword.value) {
    error.value = '两次输入的主密码不一致'
    return
  }

  busy.value = true
  try {
    const { recoveryCode } = await auth.register(email.value.trim(), password.value)
    password.value = ''; confirmPassword.value = ''
    issuedRecoveryCode.value = recoveryCode
    step.value = 'recovery-codes'
  } catch (e) {
    error.value = e.message || '注册失败'
  } finally {
    busy.value = false
  }
}

async function submit2fa() {
  error.value = ''
  if (!/^\d{6}$/.test(code.value)) {
    error.value = '请输入 6 位验证码'
    return
  }
  busy.value = true
  try {
    await auth.verifyTwoFactor(code.value)
    goNext()
  } catch (e) {
    error.value = e.message || '验证码错误'
  } finally {
    busy.value = false
  }
}

async function submitRecoveryLogin() {
  error.value = ''
  if (recoveryInput.value.trim().length < 8) {
    error.value = '请输入完整的恢复码'
    return
  }
  busy.value = true
  try {
    await auth.verifyRecoveryCode(recoveryInput.value.trim())
    goNext()
  } catch (e) {
    error.value = e.message || '恢复码无效'
  } finally {
    busy.value = false
  }
}

function switchMode() {
  if (!registrationAllowed.value) return
  mode.value = mode.value === 'login' ? 'register' : 'login'
  step.value = 'password'
  error.value = ''
  password.value = ''
  confirmPassword.value = ''
}

function copyRecoveryCode() {
  navigator.clipboard?.writeText(issuedRecoveryCode.value).catch(() => {})
}
onMounted(async () => {
  try {
    const registration = await authApi.registrationStatus()
    registrationAllowed.value = registration.allowed
    if (!registration.initialized && registration.allowed) mode.value = 'register'
  } catch { registrationAllowed.value = false }
})
const unsubscribeSensitive = onSensitiveClear(() => { password.value = ''; confirmPassword.value = ''; code.value = ''; recoveryInput.value = ''; issuedRecoveryCode.value = '' })
onUnmounted(() => {
  unsubscribeSensitive()
  password.value = ''; confirmPassword.value = ''; code.value = ''; recoveryInput.value = ''; issuedRecoveryCode.value = ''
  if (!auth.isAuthenticated.value && auth.pending.value) auth.clearSession()
})
</script>

<template>
  <div class="h-full w-full flex items-center justify-center p-4">
    <div
      
      class="theme-card w-full max-w-md p-8"
    >
      <!-- 品牌 -->
      <div class="flex flex-col items-center text-center space-y-2 mb-6">
        <div
          class="w-12 h-12 rounded-2xl bg-gradient-to-br from-accent to-accent-brandEnd flex items-center justify-center text-white shadow-md"
        >
          <AppIcon name="verified_user" size="24" class="text-white" />
        </div>
        <h1 class="text-base font-bold tracking-tight">{{ title }}</h1>
        <p  class="theme-text-muted text-[0.68rem]">
          零知识加密 · 服务端只存密文
        </p>
      </div>

      <!-- 第一步：账号 + 主密码 -->
      <form data-testid="credentials-form" v-if="step === 'password'" class="space-y-3" @submit.prevent="submitPassword">
        <div class="space-y-1">
          <label class="text-[0.68rem] font-semibold opacity-75">邮箱</label>
          <input
            v-model="email" data-testid="login-email"
            type="email"
            autocomplete="username"
            placeholder="me@qq.com"
            class="ios-input w-full px-3 py-2 rounded-xl text-xs"
          />
        </div>

        <div class="space-y-1">
          <label class="text-[0.68rem] font-semibold opacity-75">主密码</label>
          <div class="relative">
            <input
              v-model="password" data-testid="login-password"
              :type="showPassword ? 'text' : 'password'"
              :autocomplete="mode === 'register' ? 'new-password' : 'current-password'"
              :placeholder="mode === 'register' ? '至少 12 位，务必牢记' : '输入主密码'"
              class="ios-input w-full pl-3 pr-9 py-2 rounded-xl text-xs"
            />
            <button
              type="button"
              class="absolute right-2 top-1/2 -translate-y-1/2 text-amber-500"
              @click="showPassword = !showPassword"
            >
              <AppIcon :name="showPassword ? 'visibility_off' : 'visibility'" size="16" />
            </button>
          </div>
        </div>

        <div v-if="mode === 'register'" class="space-y-1">
          <label class="text-[0.68rem] font-semibold opacity-75">确认主密码</label>
          <input
            v-model="confirmPassword" data-testid="login-confirm-password"
            :type="showPassword ? 'text' : 'password'"
            autocomplete="new-password"
            placeholder="再输入一次"
            class="ios-input w-full px-3 py-2 rounded-xl text-xs"
          />
        </div>

        <p v-if="error" class="text-[0.68rem] text-rose-500 font-medium">{{ error }}</p>

        <button
          type="submit"
          :disabled="!canSubmit"
          class="w-full py-2.5 rounded-xl theme-accent-btn text-xs font-semibold shadow-sm disabled:opacity-40 spring-btn flex items-center justify-center gap-1.5"
        >
          <AppIcon name="progress_activity" size="16" v-if="busy" class="animate-spin" />
          <span>{{ busy ? '正在派生密钥…' : mode === 'register' ? '创建并解锁' : '解锁' }}</span>
        </button>

        <div class="flex items-center justify-between text-[0.65rem] pt-1">
          <button type="button" class="text-accent hover:underline font-semibold" v-if="registrationAllowed" @click="switchMode">
            {{ mode === 'login' ? '首次使用？创建密码库' : '已有账号，去登录' }}
          </button>
          <router-link
            v-if="mode === 'login'"
            to="/reset-password"
            class="opacity-70 hover:opacity-100"
          >
            忘记主密码？
          </router-link>
        </div>
      </form>

      <!-- 第二步：2FA -->
      <form v-else-if="step === '2fa'" class="space-y-3" @submit.prevent="submit2fa">
        <p  class="theme-text-muted text-[0.68rem] text-center">
          两步验证：请输入验证器上的 6 位验证码
        </p>
        <input
          v-model="code" data-testid="login-totp"
          inputmode="numeric"
          maxlength="6"
          autofocus
          placeholder="000000"
          class="ios-input w-full px-3 py-3 rounded-xl text-2xl tracking-[0.4em] text-center"
        />
        <p v-if="error" class="text-[0.68rem] text-rose-500 font-medium">{{ error }}</p>
        <button
          type="submit"
          :disabled="busy"
          class="w-full py-2.5 rounded-xl theme-accent-btn text-xs font-semibold shadow-sm disabled:opacity-40 spring-btn"
        >
          {{ busy ? '校验中…' : '验证并解锁' }}
        </button>
        <div class="text-center">
          <button
            type="button"
            class="text-[0.65rem] text-accent hover:underline"
            @click="step = 'recovery-login'"
          >
            使用恢复码登录
          </button>
        </div>
      </form>

      <!-- 恢复码登录 -->
      <form v-else-if="step === 'recovery-login'" class="space-y-3" @submit.prevent="submitRecoveryLogin">
        <p  class="theme-text-muted text-[0.68rem] text-center">
          输入一个尚未使用的一次性恢复码
        </p>
        <input
          v-model="recoveryInput" data-testid="login-backup-code"
          placeholder="XXXX-XXXX（两步验证备用码）"
          class="ios-input w-full px-3 py-2 rounded-xl text-xs text-center tracking-widest"
        />
        <p v-if="error" class="text-[0.68rem] text-rose-500 font-medium">{{ error }}</p>
        <button
          type="submit"
          :disabled="busy"
          class="w-full py-2.5 rounded-xl theme-accent-btn text-xs font-semibold shadow-sm disabled:opacity-40 spring-btn"
        >
          {{ busy ? '校验中…' : '用恢复码解锁' }}
        </button>
        <div class="text-center">
          <button type="button" class="text-[0.65rem] opacity-70 hover:opacity-100" @click="step = '2fa'">
            返回验证码
          </button>
        </div>
      </form>

      <!-- 注册后：一次性恢复码 -->
      <div v-else-if="step === 'recovery-codes'" class="space-y-3">
        <div
          
          class="bg-rose-50 border-rose-200 p-3 rounded-xl border text-[0.68rem] text-rose-500 font-semibold leading-relaxed"
        >
          这是你唯一的恢复码，仅显示一次。忘记主密码时只能靠它恢复数据，请立即抄写或下载保存。
        </div>
        <div
          
          data-testid="registration-recovery-code" class="bg-black/[0.03] border-[var(--border-color)] text-emerald-600 p-4 rounded-xl border text-center text-sm font-bold tracking-widest select-all"
        >
          {{ issuedRecoveryCode }}
        </div>
        <div class="flex gap-2">
          <button
            type="button"
            
            class="theme-subtle hover:bg-black/[0.04] flex-1 py-2 rounded-xl text-xs font-semibold spring-btn"
            @click="copyRecoveryCode"
          >
            复制
          </button>
          <button
            type="button"
            class="flex-1 py-2 rounded-xl theme-accent-btn text-xs font-semibold shadow-sm spring-btn"
            @click="goNext"
          >
            我已保存，进入密码库
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
