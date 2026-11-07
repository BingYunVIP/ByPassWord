<script setup>
import AppIcon from '../common/AppIcon.vue'
import MailEventsBlock from './MailEventsBlock.vue'
import MailTemplateBlock from './MailTemplateBlock.vue'
import { onMounted, onUnmounted, reactive, ref } from 'vue'

import { onSensitiveClear, useAuth } from '../../stores/auth'
import * as vaultApi from '../../api/vault'
import { useVault } from '../../stores/vault'

const { showToast } = useVault()
const auth = useAuth()
let disposed = false
const isCurrent = epoch => !disposed && auth.isUnlocked.value && epoch === auth.sessionEpoch.value

const form = reactive({
  host: 'smtp.qq.com',
  port: 465,
  user: '',
  password: '',
  sender: '',
  testTarget: ''
})
const hasPassword = ref(false)
const loading = ref(true)
const saving = ref(false)
const testing = ref(false)

async function load() {
  const epoch = auth.sessionEpoch.value
  loading.value = true
  try {
    const data = await vaultApi.getMailSettings()
    if (!isCurrent(epoch)) return
    Object.assign(form, {
      host: data.host,
      port: data.port,
      user: data.user,
      sender: data.from || data.user,
      password: '',
      testTarget: data.from || data.user
    })
    hasPassword.value = data.hasPassword
  } catch (e) {
    showToast(e.message || '读取邮箱配置失败')
  } finally {
    loading.value = false
  }
}

async function save() {
  const epoch = auth.sessionEpoch.value
  saving.value = true
  try {
    const payload = {
      host: form.host.trim(),
      port: Number(form.port) || 465,
      user: form.user.trim(),
      from: (form.sender || form.user).trim()
    }
    if (form.password) payload.password = form.password

    const res = await vaultApi.saveMailSettings(payload)
    if (!isCurrent(epoch)) return
    hasPassword.value = res.hasPassword
    form.password = ''
    showToast('邮箱配置已保存')
  } catch (e) {
    showToast(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function sendTest() {
  const epoch = auth.sessionEpoch.value
  testing.value = true
  try {
    const res = await vaultApi.testMail(form.testTarget.trim())
    if (!isCurrent(epoch)) return
    showToast(`测试邮件已发送至 ${res.to}`)
  } catch (e) {
    showToast(e.message || '发送失败，请检查授权码与端口')
  } finally {
    testing.value = false
  }
}

function clearSensitive() { Object.assign(form, {host: '', port: 465, user: '', password: '', sender: '', testTarget: ''}); hasPassword.value = false }
const unsubscribeSensitive = onSensitiveClear(clearSensitive)
onUnmounted(() => { disposed = true; unsubscribeSensitive(); clearSensitive() })
onMounted(load)
</script>

<template>
  <div class="space-y-4">
    <h4 class="text-sm font-bold flex items-center gap-2">
      <AppIcon name="forward_to_inbox" class="text-emerald-500" />
      <span>邮箱配置</span>
    </h4>

    <div class="theme-card p-4 space-y-4">
      <!-- 第一行：服务器地址 + SSL 端口 -->
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label for="mail-host" class="block font-bold mb-1.5">SMTP 服务器地址</label>
          <input
            id="mail-host"
            v-model="form.host"
            type="text"
            placeholder="smtp.qq.com"
            class="ios-input w-full px-3.5 py-2.5 rounded-xl"
          />
        </div>
        <div>
          <label for="mail-port" class="block font-bold mb-1.5">SSL 端口</label>
          <input
            id="mail-port"
            v-model.number="form.port"
            type="number"
            placeholder="465"
            class="ios-input w-full px-3.5 py-2.5 rounded-xl"
          />
        </div>
      </div>

      <!-- 第二行：发件人账号 + 授权码 -->
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label for="mail-sender" class="block font-bold mb-1.5">发件人邮箱账号</label>
          <input
            id="mail-sender"
            v-model="form.sender"
            type="email"
            autocomplete="email"
            placeholder="me@qq.com"
            class="ios-input w-full px-3.5 py-2.5 rounded-xl"
          />
        </div>
        <div>
          <label for="mail-auth" class="block font-bold mb-1.5">SMTP 授权码</label>
          <input
            id="mail-auth"
            v-model="form.password"
            type="password"
            autocomplete="new-password"
            :placeholder="hasPassword ? '••••••••（留空不修改）' : 'QQ 邮箱生成的 16 位授权码'"
            class="ios-input w-full px-3.5 py-2.5 rounded-xl"
          />
        </div>
      </div>

      <!-- 第三行：测试邮箱 + 两个操作 -->
      <div
        class="grid grid-cols-1 sm:grid-cols-12 gap-3 items-end pt-2 border-t"
        style="border-color: var(--border-color)"
      >
        <div class="sm:col-span-6">
          <label for="mail-test-target" class="block font-bold mb-1.5">测试邮箱账号</label>
          <input
            id="mail-test-target"
            v-model="form.testTarget"
            type="email"
            autocomplete="email"
            placeholder="接收测试邮件的邮箱"
            class="ios-input w-full px-3.5 py-2.5 rounded-xl"
          />
        </div>
        <div class="sm:col-span-3">
          <button
            type="button"
            :disabled="testing || loading"
            class="w-full py-2.5 px-4 rounded-xl text-xs font-bold theme-subtle border hover:border-[var(--accent)] transition disabled:opacity-60"
            @click="sendTest"
          >
            {{ testing ? '发送中…' : '发送测试邮件' }}
          </button>
        </div>
        <div class="sm:col-span-3">
          <button
            type="button"
            :disabled="saving || loading"
            class="w-full py-2.5 px-5 rounded-xl text-xs font-bold theme-accent-btn disabled:opacity-60"
            @click="save"
          >
            {{ saving ? '保存中…' : '保存邮箱配置' }}
          </button>
        </div>
      </div>
    </div>

    <MailEventsBlock />
    <MailTemplateBlock />
  </div>
</template>
