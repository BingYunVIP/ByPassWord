<script setup>
import AppIcon from '../common/AppIcon.vue'
import { computed, onMounted, ref } from 'vue'

import * as vaultApi from '../../api/vault'
import { useAuth } from '../../stores/auth'
import { useVault } from '../../stores/vault'

const { showToast } = useVault()
const { user } = useAuth()

const items = ref([])
const loading = ref(true)

const ACTION_LABELS = {
  register: '注册账号',
  login_success: '登录成功',
  login_success_2fa: '登录成功（2FA）',
  login_success_recovery: '登录成功（恢复码）',
  login_failed: '登录失败',
  login_password_ok: '密码校验通过，等待 2FA',
  account_locked: '账号临时锁定',
  logout: '退出登录',
  password_changed: '修改主密码',
  password_reset: '通过恢复码重置主密码',
  reset_code_sent: '发送重置验证码',
  reset_code_verified: '重置验证码校验通过',
  '2fa_enabled': '开启两步验证',
  '2fa_disabled': '关闭两步验证',
  '2fa_failed': '两步验证码错误',
  recovery_code_failed: '恢复码校验失败',
  recovery_codes_regenerated: '重新生成恢复码',
  mail_test: '发送测试邮件',
  mail_settings_updated: '更新邮箱配置',
  backup_settings_updated: '更新备份策略',
  backup_snapshot: '创建备份快照',
  vault_import: '导入备份'
}

const CATEGORIES = [
  [/^(register|login_|logout|account_locked)/, '登录'],
  [/^(password_|2fa_|recovery_|reset_)/, '安全'],
  [/^mail_/, '邮件'],
  [/^backup_/, '备份'],
  [/^vault_/, '数据']
]

const LEVEL_CLASS = {
  ERROR: 'bg-rose-500/15 text-rose-600',
  WARN: 'bg-amber-500/15 text-amber-600',
  INFO: 'bg-blue-500/10 text-blue-600'
}

function label(action) {
  return ACTION_LABELS[action] || action
}

function category(action) {
  for (const [re, name] of CATEGORIES) if (re.test(action)) return name
  return '其他'
}

function level(action) {
  if (/failed$|account_locked$/.test(action)) return 'ERROR'
  if (/reset_code_sent|mail_test/.test(action)) return 'INFO'
  return 'INFO'
}

function formatTime(iso) {
  try {
    return new Date(iso).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return iso
  }
}

const actor = computed(() => user.value?.email || '—')

async function load() {
  loading.value = true
  try {
    const data = await vaultApi.listAudit(100)
    items.value = data.items || []
  } catch (e) {
    showToast(e.message || '读取审计日志失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="flex flex-col gap-3 min-h-0 h-full">
    <div class="flex items-center justify-between shrink-0">
      <h4 class="text-sm font-bold flex items-center gap-2">
        <AppIcon name="receipt_long" class="text-rose-500" />
        <span>日志记录</span>
      </h4>
      <button
        class="theme-subtle hover:bg-black/[0.04] px-3 py-1.5 rounded-xl text-[0.68rem] font-semibold spring-btn"
        @click="load"
      >
        刷新
      </button>
    </div>

    <div
      class="border rounded-2xl overflow-hidden flex-1 min-h-0 flex flex-col"
      style="border-color: var(--border-color)"
    >
      <div class="overflow-y-auto flex-1 min-h-0">
        <table class="w-full text-left text-xs border-collapse">
          <thead class="sticky top-0 z-10 theme-subtle border-b" style="border-color: var(--border-color)">
            <tr>
              <th class="py-3 px-4 font-bold whitespace-nowrap">时间</th>
              <th class="py-3 px-4 font-bold">级别</th>
              <th class="py-3 px-4 font-bold">分类</th>
              <th class="py-3 px-4 font-bold">详情</th>
              <th class="py-3 px-4 font-bold whitespace-nowrap">IP</th>
              <th class="py-3 px-4 font-bold">操作者</th>
            </tr>
          </thead>
          <tbody class="divide-y" style="border-color: var(--border-color)">
            <tr v-if="loading">
              <td colspan="6" class="py-10 text-center theme-text-muted">读取中…</td>
            </tr>
            <tr v-else-if="!items.length">
              <td colspan="6" class="py-10 text-center theme-text-muted">暂无日志</td>
            </tr>
            <tr v-for="log in items" :key="log.id" class="hover:bg-accent/10">
              <td class="py-3 px-4 theme-text-muted whitespace-nowrap">{{ formatTime(log.time) }}</td>
              <td class="py-3 px-4 whitespace-nowrap">
                <span
                  class="px-2 py-0.5 rounded font-bold text-[11px]"
                  :class="LEVEL_CLASS[level(log.action)]"
                  >{{ level(log.action) }}</span
                >
              </td>
              <td class="py-3 px-4">
                <span class="px-2 py-0.5 rounded bg-accent/10 text-accent font-bold text-[11px]">{{
                  category(log.action)
                }}</span>
              </td>
              <td class="py-3 px-4 font-bold text-[var(--text-main)] max-w-[420px]">
                <div class="truncate" :title="label(log.action)">{{ label(log.action) }}</div>
                <div class="text-[10px] font-normal theme-text-muted truncate">{{ log.action }}</div>
              </td>
              <td class="py-3 px-4 whitespace-nowrap theme-text-muted">{{ log.ip || '—' }}</td>
              <td class="py-3 px-4 theme-text-muted truncate max-w-[160px]">{{ actor }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
