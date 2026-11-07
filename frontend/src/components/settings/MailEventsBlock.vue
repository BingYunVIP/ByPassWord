<script setup>
import AppIcon from '../common/AppIcon.vue'
import { onMounted, ref } from 'vue'

import * as vaultApi from '../../api/vault'
import { useVault } from '../../stores/vault'

const { showToast } = useVault()

const events = ref([])
const loading = ref(true)
const saving = ref(false)

async function load() {
  loading.value = true
  try {
    const data = await vaultApi.getMailEvents()
    events.value = data.events || []
  } catch (e) {
    showToast(e.message || '读取安全事件失败')
  } finally {
    loading.value = false
  }
}

async function toggle(item) {
  item.enabled = !item.enabled
  saving.value = true
  try {
    const payload = {}
    for (const e of events.value) payload[e.key] = e.enabled
    await vaultApi.saveMailEvents(payload)
    showToast(`已${item.enabled ? '开启' : '关闭'}「${item.label}」通知`)
  } catch (e) {
    item.enabled = !item.enabled
    showToast(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="space-y-4">
    <h4 class="text-sm font-bold flex items-center gap-2">
      <AppIcon name="notifications_active" class="text-amber-500" />
      <span>安全事件通知</span>
    </h4>

    <section class="theme-card p-4 space-y-3">
      <p class="text-[0.68rem] theme-text-muted">
        勾选后，对应安全事件发生时向发件人邮箱发送提醒（使用下方「邮件模板」）。
      </p>
      <p v-if="loading" class="text-[0.68rem] theme-text-muted">读取中…</p>
      <div v-else class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-x-4 gap-y-1">
        <label
          v-for="item in events"
          :key="item.key"
          class="flex min-h-11 items-center gap-2.5 cursor-pointer"
        >
          <input
            type="checkbox"
            class="h-4 w-4 shrink-0 accent-[var(--accent)]"
            :checked="item.enabled"
            :disabled="saving"
            @change="toggle(item)"
          />
          <span class="min-w-0">
            <span class="font-bold">{{ item.label }}</span>
            <span class="block text-[0.65rem] theme-text-muted truncate">{{ item.desc }}</span>
          </span>
        </label>
      </div>
    </section>
  </div>
</template>
