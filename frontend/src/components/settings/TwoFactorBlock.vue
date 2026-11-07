<script setup>
import AppIcon from '../common/AppIcon.vue'
import { onMounted, onUnmounted, ref } from 'vue'

import * as authApi from '../../api/auth'
import { useAuth, onSensitiveClear } from '../../stores/auth'
import { useVault } from '../../stores/vault'

const auth = useAuth()
const { showToast } = useVault()

const enabled = ref(false)
const remaining = ref(0)
const loading = ref(true)
const busy = ref(false)

const setupSecret = ref('')
const otpauthUrl = ref('')
const code = ref('')
const password = ref('')
const recoveryCodes = ref([])
const error = ref('')

let disposed = false
onUnmounted(() => { disposed = true })

const inputClass = () =>
  'bg-white border-[var(--border-color)] text-zinc-900'

async function load() {
  loading.value = true
  try {
    const me = await authApi.me()
    if (disposed || !auth.isUnlocked.value) return
    enabled.value = me.twoFactorEnabled
    auth.user.value = me
    if (enabled.value) {
      const res = await authApi.recoveryCodeCount()
      remaining.value = res.remaining
    }
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function startSetup() {
  error.value = ''
  busy.value = true
  try {
    const res = await authApi.setupTwoFactor()
    if (disposed || !auth.isUnlocked.value) return
    setupSecret.value = res.secret
    otpauthUrl.value = res.otpauthUrl
  } catch (e) {
    error.value = e.message || '生成密钥失败'
  } finally {
    busy.value = false
  }
}

async function confirmEnable() {
  error.value = ''
  if (!/^\d{6}$/.test(code.value)) {
    error.value = '请输入验证器上的 6 位验证码'
    return
  }
  busy.value = true
  try {
    const res = await authApi.enableTwoFactor(code.value)
    if (disposed || !auth.isUnlocked.value) return
    recoveryCodes.value = res.recoveryCodes
    enabled.value = true
    auth.user.value = { ...auth.user.value, twoFactorEnabled: true }
    remaining.value = res.recoveryCodes.length
    setupSecret.value = ''
    otpauthUrl.value = ''
    code.value = ''
    showToast('两步验证已开启')
  } catch (e) {
    error.value = e.message || '验证码错误'
  } finally {
    busy.value = false
  }
}

async function disable() {
  error.value = ''
  if (!password.value || !/^\d{6}$/.test(code.value)) {
    error.value = '需要主密码 + 当前验证码'
    return
  }
  busy.value = true
  try {
    const authHash = await auth.authHashFor(password.value)
    await authApi.disableTwoFactor(authHash, code.value)
    if (disposed || !auth.isUnlocked.value) return
    enabled.value = false
    auth.user.value = { ...auth.user.value, twoFactorEnabled: false }
    remaining.value = 0
    password.value = ''
    code.value = ''
    showToast('两步验证已关闭')
  } catch (e) {
    error.value = e.message || '关闭失败'
  } finally {
    busy.value = false
  }
}

function copyCodes() {
  navigator.clipboard?.writeText(recoveryCodes.value.join('\n')).catch(() => {})
  showToast('恢复码已复制')
}

function clearSensitive() { setupSecret.value = ''; otpauthUrl.value = ''; code.value = ''; password.value = ''; recoveryCodes.value = []; error.value = '' }
const unsubscribe = onSensitiveClear(clearSensitive)
onUnmounted(() => { unsubscribe(); clearSensitive() })
onMounted(load)
</script>

<template>
  <div class="theme-card p-4 space-y-3">
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-1.5 font-semibold">
        <AppIcon name="verified_user" size="16" class="text-emerald-500" />
        <span>账号 2FA（TOTP）</span>
      </div>
      <span
        :class="enabled ? 'bg-emerald-500/15 text-emerald-500' : 'bg-black/5 opacity-70'"
        class="text-[0.62rem] px-2 py-0.5 rounded font-bold"
      >
        {{ enabled ? '已开启' : '未开启' }}
      </span>
    </div>

    <p v-if="loading" class="text-[0.68rem] opacity-60">读取中…</p>

    <template v-else-if="!enabled">
      <p class="text-[0.68rem] opacity-70 leading-relaxed">
        开启后登录需要额外输入验证器（Google Authenticator / 1Password / 微软验证器）的 6 位验证码。
      </p>

      <button
        v-if="!setupSecret"
        :disabled="busy"
        class="px-4 py-2 rounded-xl theme-accent-btn text-xs font-semibold disabled:opacity-40 spring-btn"
        @click="startSetup"
      >
        {{ busy ? '生成中…' : '开始绑定' }}
      </button>

      <div v-else class="space-y-2">
        <p class="text-[0.68rem] opacity-75">在验证器中手动添加以下密钥（时间基准 TOTP）：</p>
        <code
          
          data-testid="two-factor-setup-secret" class="theme-subtle border-[var(--border-color)] text-emerald-600 block px-3 py-2 rounded-xl border text-[0.72rem] font-bold tracking-wider break-all select-all"
        >
          {{ setupSecret }}
        </code>
        <p class="text-[0.6rem] opacity-50 break-all">{{ otpauthUrl }}</p>
        <div class="flex gap-2">
          <input
            v-model="code" data-testid="two-factor-code"
            inputmode="numeric"
            maxlength="6"
            placeholder="000000"
            :class="inputClass()"
            class="flex-1 px-3 py-2 rounded-xl border text-center tracking-[0.3em]"
          />
          <button
            :disabled="busy"
            class="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-600 text-white text-xs font-semibold disabled:opacity-40 spring-btn"
            @click="confirmEnable"
          >
            确认开启
          </button>
        </div>
      </div>
    </template>

    <template v-else>
      <p class="text-[0.68rem] opacity-70">
        剩余可用恢复码：<strong class="text-emerald-500">{{ remaining }}</strong> 个
      </p>
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-2">
        <input v-model="password" data-testid="two-factor-password" type="password" placeholder="主密码" :class="inputClass()" class="px-3 py-2 rounded-xl border" />
        <input
          v-model="code" data-testid="two-factor-code"
          inputmode="numeric"
          maxlength="6"
          placeholder="当前验证码"
          :class="inputClass()"
          class="px-3 py-2 rounded-xl border"
        />
        <button
          :disabled="busy"
          class="px-3 py-2 rounded-xl bg-rose-500/15 text-rose-500 hover:bg-rose-500 hover:text-white text-xs font-semibold disabled:opacity-40 spring-btn"
          @click="disable"
        >
          关闭 2FA
        </button>
      </div>
    </template>

    <div v-if="recoveryCodes.length" class="space-y-2 pt-1">
      <div
        
        class="bg-rose-50 border-rose-200 text-rose-600 p-2.5 rounded-xl border text-[0.65rem] font-semibold"
      >
        恢复码仅显示这一次，请立即保存（丢失验证器时用它登录）。
      </div>
      <div class="grid grid-cols-2 gap-1 text-[0.68rem] font-mono">
        <span v-for="item in recoveryCodes" :key="item" class="opacity-80">{{ item }}</span>
      </div>
      <button
        
        class="theme-subtle hover:bg-black/[0.04] px-3 py-1.5 rounded-xl text-[0.68rem] font-semibold spring-btn"
        @click="copyCodes"
      >
        复制全部恢复码
      </button>
    </div>

    <p v-if="error" class="text-[0.68rem] text-rose-500">{{ error }}</p>
  </div>
</template>
