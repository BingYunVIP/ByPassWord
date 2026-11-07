<script setup>
import AppIcon from './common/AppIcon.vue'
import { computed } from 'vue'

import { useAuth } from '../stores/auth'
import { useVault } from '../stores/vault'

const { user } = useAuth()
const {
  isLocked,
  lockReason,
  unlockInput,
  unlockStep,
  unlockTotpCode,
  unlockBusy,
  handleUnlockVault,
  handleUnlockTotp,
  backToPasswordStep
} = useVault()

const email = computed(() => user.value?.email || '')
const twoFactorEnabled = computed(() => Boolean(user.value?.twoFactorEnabled))
</script>

<template>
  <div
    v-if="isLocked"
    class="bg-white/80 absolute inset-0 z-50 backdrop-blur-2xl flex items-center justify-center p-6"
  >
    <div class="theme-card w-full max-w-sm p-8 space-y-5 text-center">
      <div
        class="w-16 h-16 mx-auto rounded-3xl bg-gradient-to-tr from-accent to-accent-brandEnd flex items-center justify-center text-white shadow-xl"
      >
        <AppIcon :name="unlockStep === '2fa' ? 'verified_user' : 'lock'" size="30" class="text-white" />
      </div>

      <div>
        <h2 class="text-base font-bold">
          {{ unlockStep === '2fa' ? '两步验证' : '密码库已锁定' }}
        </h2>
        <p class="theme-text-muted text-xs mt-1 truncate" :title="email">
          {{ email || '—' }} · {{ lockReason }}
        </p>
      </div>

      <!-- 第一步：主密码 -->
      <form v-if="unlockStep === 'password'" class="space-y-3" @submit.prevent="handleUnlockVault">
        <input
          v-model="unlockInput" data-testid="unlock-password"
          type="password"
          autocomplete="current-password"
          placeholder="输入主密码"
          class="ios-input w-full px-3.5 py-2.5 rounded-xl text-sm text-center"
        />
        <button
          type="submit"
          :disabled="unlockBusy"
          class="w-full py-2.5 rounded-xl theme-accent-btn text-sm font-bold disabled:opacity-60"
        >
          {{ unlockBusy ? '解锁中…' : '解锁密码库' }}
        </button>
        <p v-if="twoFactorEnabled" class="text-[0.65rem] theme-text-muted">
          该账号已开启两步验证，密码通过后还需输入动态码
        </p>
      </form>

      <!-- 第二步：两步验证 -->
      <form v-else class="space-y-3" @submit.prevent="handleUnlockTotp">
        <p class="text-[0.68rem] theme-text-muted">主密码已验证，请输入验证器中的 6 位动态码</p>
        <input
          v-model="unlockTotpCode" data-testid="unlock-totp"
          type="text"
          inputmode="numeric"
          autocomplete="one-time-code"
          maxlength="6"
          placeholder="000000"
          class="ios-input w-full px-3.5 py-2.5 rounded-xl text-center text-lg font-bold tracking-[0.4em]"
        />
        <button
          type="submit"
          :disabled="unlockBusy || unlockTotpCode.trim().length !== 6"
          class="w-full py-2.5 rounded-xl theme-accent-btn text-sm font-bold disabled:opacity-60"
        >
          {{ unlockBusy ? '验证中…' : '验证并解锁' }}
        </button>
        <button
          type="button"
          class="text-[0.65rem] theme-text-muted hover:underline"
          @click="backToPasswordStep"
        >
          返回输入主密码
        </button>
      </form>
    </div>
  </div>
</template>
