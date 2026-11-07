<script setup>
import AppIcon from './common/AppIcon.vue'
import { useVault } from '../stores/vault'

const { toastMessage } = useVault()
</script>

<template>
  <!-- 底部 Toast 提示 -->
  <div
    v-if="toastMessage"
    class="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 px-4 py-2 rounded-full bg-zinc-900/95 text-white text-xs font-semibold shadow-xl border border-white/15 flex items-center gap-2"
  >
    <AppIcon name="check_circle" size="16" class="text-emerald-400" />
    <span>{{ toastMessage }}</span>
  </div>
</template>
