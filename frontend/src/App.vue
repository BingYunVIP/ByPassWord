<script setup>
import { onMounted, onUnmounted } from 'vue'

import ToastMessage from './components/ToastMessage.vue'
import { useVault } from './stores/vault'

const { initVault, disposeVault, closeAllDropdowns } = useVault()

onMounted(initVault)
onUnmounted(disposeVault)
</script>

<template>
  <div
    class="bg-[var(--bg-page)] text-[var(--text-main)] h-full w-full overflow-hidden"
    @click="closeAllDropdowns"
  >
    <router-view />
    <ToastMessage />
  </div>
</template>
