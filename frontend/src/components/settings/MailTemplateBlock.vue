<script setup>
import AppIcon from '../common/AppIcon.vue'
import { computed, onMounted, ref } from 'vue'

import * as vaultApi from '../../api/vault'
import { useVault } from '../../stores/vault'

const { showToast } = useVault()

const templates = ref([])
const activeKey = ref('')
const subject = ref('')
const body = ref('')
const loading = ref(true)
const saving = ref(false)

const active = computed(() => templates.value.find((t) => t.key === activeKey.value) || null)

function pick(key) {
  activeKey.value = key
  const tpl = templates.value.find((t) => t.key === key)
  subject.value = tpl ? tpl.subject : ''
  body.value = tpl ? tpl.body : ''
}

async function load() {
  loading.value = true
  try {
    const data = await vaultApi.getMailTemplates()
    templates.value = data.templates || []
    if (templates.value.length) pick(templates.value[0].key)
  } catch (e) {
    showToast(e.message || '读取邮件模板失败')
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!activeKey.value) return
  saving.value = true
  try {
    await vaultApi.saveMailTemplate(activeKey.value, subject.value, body.value)
    const tpl = templates.value.find((t) => t.key === activeKey.value)
    if (tpl) {
      tpl.subject = subject.value
      tpl.body = body.value
    }
    showToast('模板已保存')
  } catch (e) {
    showToast(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function reset() {
  if (!activeKey.value) return
  saving.value = true
  try {
    const res = await vaultApi.resetMailTemplate(activeKey.value)
    subject.value = res.template.subject
    body.value = res.template.body
    const tpl = templates.value.find((t) => t.key === activeKey.value)
    if (tpl) {
      tpl.subject = res.template.subject
      tpl.body = res.template.body
    }
    showToast('已恢复默认模板')
  } catch (e) {
    showToast(e.message || '恢复失败')
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="space-y-4">
    <h4 class="text-sm font-bold flex items-center gap-2">
      <AppIcon name="description" class="text-indigo-500" />
      <span>邮件模板</span>
    </h4>

    <section class="theme-card p-4 space-y-3">
      <p v-if="loading" class="text-[0.68rem] theme-text-muted">读取中…</p>
      <template v-else>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label for="tpl-event" class="block font-bold mb-1">选择事件</label>
            <select
              id="tpl-event"
              :value="activeKey"
              class="ios-input w-full rounded-xl px-3.5 py-2.5"
              @change="pick($event.target.value)"
            >
              <option v-for="tpl in templates" :key="tpl.key" :value="tpl.key">
                {{ tpl.label }}
              </option>
            </select>
          </div>
          <div>
            <label for="tpl-subject" class="block font-bold mb-1">邮件主题</label>
            <input
              id="tpl-subject"
              v-model="subject"
              type="text"
              class="ios-input w-full rounded-xl px-3.5 py-2.5"
            />
          </div>
        </div>

        <div>
          <label for="tpl-body" class="block font-bold mb-1">正文</label>
          <textarea
            id="tpl-body"
            v-model="body"
            rows="10"
            class="ios-input w-full rounded-xl px-3.5 py-2.5 leading-6 resize-y"
          ></textarea>
          <p class="text-[0.68rem] theme-text-muted mt-1">
            可用占位符：<code class="font-bold">{time}</code> 时间、<code class="font-bold">{ip}</code>
            IP、<code class="font-bold">{ua}</code> 设备、<code class="font-bold">{detail}</code> 详情
          </p>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <button
            type="button"
            :disabled="saving"
            class="px-4 py-2 rounded-xl font-bold theme-accent-btn disabled:opacity-60"
            @click="save"
          >
            {{ saving ? '保存中…' : '保存模板' }}
          </button>
          <button
            type="button"
            :disabled="saving"
            class="theme-subtle hover:bg-black/[0.04] px-3 py-2 rounded-xl text-xs font-bold disabled:opacity-60"
            @click="reset"
          >
            恢复默认
          </button>
          <span v-if="active" class="text-[0.65rem] theme-text-muted ml-auto">
            默认主题：{{ active.defaultSubject }}
          </span>
        </div>
      </template>
    </section>
  </div>
</template>
