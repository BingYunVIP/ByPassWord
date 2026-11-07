<script setup>
import AppIcon from '../components/common/AppIcon.vue'
import { computed, ref, onUnmounted } from 'vue'

import * as authApi from '../api/auth'
import { deriveRecoveryAuthHash } from '../crypto/kdf'
import { recoverDekWithRecoveryCode, rewrapDekForNewPassword } from '../crypto/vault-crypto'
import { useVault } from '../stores/vault'

const { showToast } = useVault()

const step = ref(1)
const email = ref('')
const code = ref('')
const recoveryCode = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const error = ref('')
const busy = ref(false)
const done = ref(false)
const resetInfo = ref(null)
let disposed = false

const hasRecovery = computed(() => Boolean(resetInfo.value?.recoveryWrappedDek))

async function sendCode() {
  error.value = ''
  if (!email.value.trim()) {
    error.value = '请输入注册邮箱'
    return
  }
  busy.value = true
  try {
    await authApi.forgot(email.value.trim())
    if (disposed) return
    step.value = 2
  } catch (e) {
    error.value = e.message || '发送失败'
  } finally {
    busy.value = false
  }
}

async function verifyCode() {
  error.value = ''
  if (!/^\d{6}$/.test(code.value)) {
    error.value = '请输入 6 位验证码'
    return
  }
  busy.value = true
  try {
    const response = await authApi.forgotVerify(email.value.trim(), code.value)
    if (disposed) return
    resetInfo.value = response
    step.value = 3
  } catch (e) {
    error.value = e.message || '验证码错误或已过期'
  } finally {
    busy.value = false
  }
}

async function submitReset() {
  error.value = ''
  if (newPassword.value.length < 12) {
    error.value = '新主密码至少 12 位'
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    error.value = '两次输入的新主密码不一致'
    return
  }
  if (!hasRecovery.value) {
    error.value = '该账号没有恢复码副本，无法解密历史数据'
    return
  }

  busy.value = true
  let dek
  try {
    dek = await recoverDekWithRecoveryCode(
      recoveryCode.value.trim(),
      resetInfo.value.recoveryWrappedDek,
      resetInfo.value.recoveryDekNonce
    )
    if (disposed) return
    const rewrapped = await rewrapDekForNewPassword(newPassword.value, dek)
    const recoveryAuthHash = await deriveRecoveryAuthHash(recoveryCode.value)

    if (disposed) return
    await authApi.reset({
      resetToken: resetInfo.value.resetToken,
      recoveryAuthHash,
      newKdf: rewrapped.newKdf,
      newAuthHash: rewrapped.newAuthHash,
      wrappedDek: rewrapped.wrappedDek,
      dekNonce: rewrapped.dekNonce
    })

    if (disposed) return
    recoveryCode.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
    resetInfo.value = null
    done.value = true
    showToast('主密码已重置，请重新登录')
  } catch (e) {
    error.value = e.message?.includes('operation') || e.name === 'OperationError'
      ? '恢复码不正确，或数据已被篡改'
      : e.message || '重置失败'
  } finally {
    dek?.fill(0)
    busy.value = false
  }
}
onUnmounted(() => { disposed = true; recoveryCode.value = ''; newPassword.value = ''; confirmPassword.value = ''; code.value = ''; resetInfo.value = null })
</script>

<template>
  <div class="h-full w-full flex items-center justify-center p-4">
    <div
      
      class="theme-card w-full max-w-md p-8 space-y-4"
    >
      <div class="flex items-center gap-2">
        <AppIcon name="lock_reset" size="20" class="text-accent" />
        <h1 class="text-sm font-bold">重置主密码</h1>
      </div>

      <!-- 步骤条 -->
      <div class="flex items-center gap-1.5">
        <span
          v-for="n in 3"
          :key="n"
          :class="step >= n ? 'bg-accent' : 'bg-black/10'"
          class="h-1 flex-1 rounded-full transition-colors duration-300"
        ></span>
      </div>

      <template v-if="done">
        <p class="text-[0.7rem] leading-relaxed">
          主密码已重置，历史数据仍可正常解密。请用新主密码重新登录。
        </p>
        <router-link
          to="/login"
          class="block text-center w-full py-2.5 rounded-xl theme-accent-btn text-xs font-semibold shadow-sm spring-btn"
        >
          返回登录
        </router-link>
      </template>

      <template v-else-if="step === 1">
        <p  class="theme-text-muted text-[0.68rem]">
          输入注册邮箱，我们会发送 6 位验证码。
        </p>
        <input
          v-model="email"
          type="email"
          placeholder="me@qq.com"
          class="ios-input w-full px-3 py-2 rounded-xl text-xs"
        />
        <p v-if="error" class="text-[0.68rem] text-rose-500">{{ error }}</p>
        <button
          :disabled="busy"
          class="w-full py-2.5 rounded-xl theme-accent-btn text-xs font-semibold disabled:opacity-40 spring-btn"
          @click="sendCode"
        >
          {{ busy ? '发送中…' : '发送验证码' }}
        </button>
      </template>

      <template v-else-if="step === 2">
        <p  class="theme-text-muted text-[0.68rem]">
          验证码已发送（10 分钟内有效，最多尝试 5 次）。
        </p>
        <input
          v-model="code"
          inputmode="numeric"
          maxlength="6"
          placeholder="000000"
          class="ios-input w-full px-3 py-3 rounded-xl text-2xl tracking-[0.4em] text-center"
        />
        <p v-if="error" class="text-[0.68rem] text-rose-500">{{ error }}</p>
        <button
          :disabled="busy"
          class="w-full py-2.5 rounded-xl theme-accent-btn text-xs font-semibold disabled:opacity-40 spring-btn"
          @click="verifyCode"
        >
          {{ busy ? '校验中…' : '下一步' }}
        </button>
      </template>

      <template v-else-if="step === 3">
        <div
          v-if="!hasRecovery"
          class="p-3 rounded-xl border text-[0.68rem] font-semibold text-rose-500 bg-rose-500/10 border-rose-500/30"
        >
          该账号没有恢复码副本，无法解密历史数据。
        </div>
        <p v-else  class="theme-text-muted text-[0.68rem] leading-relaxed">
          输入恢复码（用于解出你的数据密钥），再设置新的主密码。
        </p>

        <input
          v-if="hasRecovery"
          v-model="recoveryCode"
          placeholder="XXXX-XXXX-XXXX-XXXX"
          class="ios-input w-full px-3 py-2 rounded-xl text-xs text-center tracking-widest"
        />
        <input
          v-if="hasRecovery"
          v-model="newPassword"
          type="password"
          autocomplete="new-password"
          placeholder="新主密码（至少 12 位）"
          class="ios-input w-full px-3 py-2 rounded-xl text-xs"
        />
        <input
          v-if="hasRecovery"
          v-model="confirmPassword"
          type="password"
          autocomplete="new-password"
          placeholder="再输入一次"
          class="ios-input w-full px-3 py-2 rounded-xl text-xs"
        />

        <p v-if="error" class="text-[0.68rem] text-rose-500">{{ error }}</p>

        <button
          v-if="hasRecovery"
          :disabled="busy"
          class="w-full py-2.5 rounded-xl theme-accent-btn text-xs font-semibold disabled:opacity-40 spring-btn"
          @click="submitReset"
        >
          {{ busy ? '正在重置…' : '重置主密码' }}
        </button>
      </template>

      <div class="text-center">
        <router-link to="/login" class="text-[0.65rem] opacity-70 hover:opacity-100">
          返回登录
        </router-link>
      </div>
    </div>
  </div>
</template>
