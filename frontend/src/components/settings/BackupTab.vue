<script setup>
import AppIcon from '../common/AppIcon.vue'
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'

import * as vaultApi from '../../api/vault'
import { validateBackup, MAX_BACKUP_BYTES } from '../../security/policy'
import { unwrapDek } from '../../crypto/aes'
import { deriveMasterKey, splitKeys } from '../../crypto/kdf'
import { decryptRecord, encryptRecord } from '../../crypto/vault-crypto'
import { useAuth, onSensitiveClear } from '../../stores/auth'
import { useVault } from '../../stores/vault'

const auth = useAuth()
const { showToast, exportVaultBackup, loadVault } = useVault()

const settings = reactive({ schedule: 'weekly-02:00', retentionDays: 30 })
const snapshots = ref([])
const canManage = computed(() => Boolean(auth.user.value?.isOwner))
const capacity = ref(2)
const snapshotCount = ref(0)
const canCreate = ref(false)
const loading = ref(true)
const saving = ref(false)
const snapshotting = ref(false)

const importFile = ref(null)
const importPassword = ref('')
const importStrategy = ref('skip')
const importPreview = ref(null)
const importing = ref(false)
const importError = ref('')

async function load() {
  loading.value = true
  if (!canManage.value) { loading.value = false; return }
  try {
    const [cfg, list] = await Promise.all([vaultApi.getBackupSettings(), vaultApi.listBackups()])
    if (disposed || !auth.isUnlocked.value) return
    Object.assign(settings, cfg)
    snapshots.value = list.items || []
    capacity.value = list.capacity ?? 2
    snapshotCount.value = list.count ?? snapshots.value.length
    canCreate.value = Boolean(list.canCreate)
  } catch (e) {
    showToast(e.message || '读取备份配置失败')
  } finally {
    loading.value = false
  }
}

async function saveSettings() {
  if (!canManage.value) return
  saving.value = true
  try {
    await vaultApi.saveBackupSettings({
      schedule: settings.schedule,
      retentionDays: Number(settings.retentionDays)
    })
    showToast('备份策略已保存')
  } catch (e) {
    showToast(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function takeSnapshot() {
  if (!canManage.value || !canCreate.value) return
  snapshotting.value = true
  try {
    const meta = await vaultApi.createSnapshot()
    showToast(`快照已创建（${Math.round(meta.size / 1024)} KB）`)
    await load()
  } catch (e) {
    showToast(e.message || '创建快照失败')
  } finally {
    snapshotting.value = false
  }
}

function formatSize(bytes) {
  if (!bytes) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function formatTime(iso) {
  try {
    return new Date(iso).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return iso
  }
}

async function onPickFile(event) {
  importError.value = ''
  const file = event.target.files?.[0]
  if (!file) return
  if (file.size > MAX_BACKUP_BYTES) { importError.value = '备份文件最大 16 MB'; event.target.value = ''; return }
  const epoch = auth.sessionEpoch.value
  try {
    const text = await file.text()
    if (disposed || epoch !== auth.sessionEpoch.value || !auth.isUnlocked.value) return
    const data = validateBackup(JSON.parse(text))
    if (data.format !== 'bypw-backup' || !data.wrappedDek || !data.kdf) {
      throw new Error('不是有效的密码库备份文件')
    }
    importFile.value = data
    importPreview.value = { folders: data.folders?.length || 0, items: data.items?.length || 0 }
  } catch (e) {
    importError.value = e.message || '文件解析失败'
    importFile.value = null
    importPreview.value = null
  }
}

async function runImport() {
  importError.value = ''
  if (!importFile.value) return
  if (!auth.dek.value) {
    importError.value = '请先解锁密码库再导入'
    return
  }
  if (!importPassword.value) {
    importError.value = '请输入该备份文件的主密码'
    return
  }

  const epoch = auth.sessionEpoch.value
  const key = auth.dek.value
  let backupDek
  const active = () => !disposed && epoch === auth.sessionEpoch.value && auth.isUnlocked.value && key === auth.dek.value
  importing.value = true
  try {
    const backup = importFile.value
    const masterKey = await deriveMasterKey(importPassword.value, backup.kdf)
    const { encKey, authKey } = await splitKeys(masterKey)
    try { backupDek = await unwrapDek(encKey, backup.wrappedDek, backup.dekNonce) }
    finally { masterKey.fill(0); encKey.fill(0); authKey.fill(0) }
    if (!active()) return

    const folders = []
    for (const row of backup.folders || []) {
      if (!active()) return
      const payload = await decryptRecord(backupDek, row.ciphertext, row.nonce)
      const enc = await encryptRecord(key, payload)
      folders.push({ id: row.id, ...enc, sortOrder: row.sortOrder ?? 0 })
    }

    const items = []
    for (const row of backup.items || []) {
      if (!active()) return
      const payload = await decryptRecord(backupDek, row.ciphertext, row.nonce)
      const enc = await encryptRecord(key, payload)
      items.push({ id: row.id, ...enc })
    }

    if (!active()) return
    const result = await vaultApi.importVault({
      folders,
      items,
      strategy: importStrategy.value
    })

    if (!active()) return
    await loadVault()
    if (!active()) return
    showToast(
      `导入完成：文件夹 ${result.imported.folders}、条目 ${result.imported.items}，跳过 ${result.skipped}`
    )
    importFile.value = null
    importPreview.value = null
    importPassword.value = ''
  } catch (e) {
    importError.value =
      e.name === 'OperationError' ? '备份主密码错误，或文件已损坏' : e.message || '导入失败'
  } finally {
    backupDek?.fill(0)
    importing.value = false
  }
}

let disposed = false
function clearSensitive() { importFile.value = null; importPassword.value = ''; importPreview.value = null; importError.value = ''; snapshots.value = [] }
const unsubscribe = onSensitiveClear(clearSensitive)
onUnmounted(() => { disposed = true; unsubscribe(); clearSensitive() })
onMounted(load)
</script>

<template>
  <div class="space-y-4">
    <h4 class="text-sm font-bold flex items-center gap-2">
      <AppIcon name="cloud_sync" class="text-cyan-500" />
      <span>自动备份、保留策略与快照</span>
    </h4>

    <div class="grid grid-cols-1 xl:grid-cols-2 gap-4">
      <!-- 备份策略 -->
      <section v-if="canManage" class="theme-card p-4 space-y-3">
        <h3 class="font-bold">备份策略</h3>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label for="backup-schedule" class="block font-bold mb-1">自动备份时间</label>
            <select
              id="backup-schedule"
              v-model="settings.schedule"
              class="ios-input w-full rounded-xl px-3.5 py-2.5"
            >
              <option value="daily-03:00">每日凌晨 03:00</option>
              <option value="weekly-02:00">每周日 02:00</option>
              <option value="every-change">每次修改后（暂未启用）</option>
            </select>
          </div>
          <div>
            <label for="backup-retention" class="block font-bold mb-1">备份保留</label>
            <select
              id="backup-retention"
              v-model.number="settings.retentionDays"
              class="ios-input w-full rounded-xl px-3.5 py-2.5"
            >
              <option :value="7">7 天</option>
              <option :value="14">14 天</option>
              <option :value="30">30 天</option>
              <option :value="90">90 天</option>
              <option :value="0">永久保留</option>
            </select>
          </div>
        </div>
        <p class="text-[0.68rem] theme-text-muted">手动快照保留至运维确认删除；全库快照最多保留两份。</p>
        <div class="flex flex-wrap items-center gap-2">
          <button
            :disabled="saving"
            class="px-4 py-2 rounded-xl font-bold theme-accent-btn disabled:opacity-60"
            @click="saveSettings"
          >
            {{ saving ? '保存中…' : '保存策略' }}
          </button>
          <button
            :disabled="snapshotting || !canCreate"
            class="px-3 py-2 rounded-xl font-bold bg-amber-500/10 text-amber-600 hover:bg-amber-500/20 disabled:opacity-60"
            @click="takeSnapshot"
          >
            {{ snapshotting ? '创建中…' : '立即创建快照' }}
          </button>
        </div>
      </section>

      <p v-if="!canManage" class="text-xs theme-text-muted">共享备份策略由本机密码库所有者管理；你仍可导出和导入自己的加密备份。</p>

      <!-- 备份文件 -->
      <section class="theme-card p-4 space-y-3">
        <h3 class="font-bold">备份文件</h3>
        <div class="flex flex-wrap items-center gap-2">
          <button
            class="theme-subtle hover:bg-black/[0.04] px-3 py-2 rounded-xl text-xs font-bold spring-btn"
            @click="exportVaultBackup"
          >
            导出备份
          </button>
          <label
            class="theme-subtle hover:bg-black/[0.04] inline-flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-bold cursor-pointer spring-btn"
          >
            <AppIcon name="upload_file" size="16" class="text-accent" />
            <span>选择备份文件</span>
            <input type="file" accept="application/json,.json" class="hidden" @change="onPickFile" />
          </label>
        </div>

        <div v-if="importPreview" class="space-y-2">
          <p class="text-[0.68rem] theme-text-muted">
            文件包含 <strong>{{ importPreview.folders }}</strong> 个文件夹、<strong>{{
              importPreview.items
            }}</strong>
            条目
          </p>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <input
              v-model="importPassword"
              type="password"
              placeholder="该备份的主密码"
              class="ios-input w-full rounded-xl px-3 py-2"
            />
            <select v-model="importStrategy" class="ios-input w-full rounded-xl px-3 py-2">
              <option value="skip">跳过已存在（推荐）</option>
              <option value="overwrite">覆盖同 ID</option>
              <option value="duplicate">全部作为新记录</option>
            </select>
          </div>
          <button
            :disabled="importing"
            class="px-4 py-2 rounded-xl font-bold bg-emerald-500 hover:bg-emerald-600 text-white disabled:opacity-60 spring-btn"
            @click="runImport"
          >
            {{ importing ? '导入中…' : '开始导入' }}
          </button>
        </div>
        <p v-else class="text-[0.68rem] theme-text-muted">导入需要该备份文件自己的主密码。</p>
        <p v-if="importError" class="text-[0.68rem] text-rose-500">{{ importError }}</p>
      </section>
    </div>

    <!-- 最近快照 -->
    <section v-if="canManage" class="theme-card p-4 space-y-3">
      <p class="text-xs theme-text-muted">已用 {{ snapshotCount }} / {{ capacity }} 份全库加密快照。</p>
      <p v-if="!canCreate && !loading" role="status" class="text-xs text-amber-600">快照容量已满。请先由运维验证并管理现有快照；不会自动删除旧备份或创建第三份。</p>
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h3 class="font-bold">最近快照</h3>
        <span class="text-[0.68rem] theme-text-muted">
          保留 {{ settings.retentionDays === 0 ? '永久' : settings.retentionDays + ' 天' }}
        </span>
      </div>
      <p v-if="loading" class="text-[0.68rem] theme-text-muted">读取中…</p>
      <p v-else-if="!snapshots.length" class="text-[0.68rem] theme-text-muted">还没有快照</p>
      <div v-else class="overflow-x-auto max-h-56">
        <table class="w-full text-left text-xs border-collapse">
          <thead class="sticky top-0 theme-subtle border-b" style="border-color: var(--border-color)">
            <tr>
              <th class="py-2 px-3 font-bold whitespace-nowrap">时间</th>
              <th class="py-2 px-3 font-bold whitespace-nowrap">大小</th>
              <th class="py-2 px-3 font-bold whitespace-nowrap">类型</th>
            </tr>
          </thead>
          <tbody class="divide-y" style="border-color: var(--border-color)">
            <tr v-for="item in snapshots" :key="item.id">
              <td class="py-2 px-3 whitespace-nowrap">{{ formatTime(item.createdAt) }}</td>
              <td class="py-2 px-3 theme-text-muted whitespace-nowrap">{{ formatSize(item.size) }}</td>
              <td class="py-2 px-3">
                <span
                  :class="
                    item.kind === 'manual'
                      ? 'bg-amber-500/15 text-amber-600'
                      : 'bg-cyan-500/15 text-cyan-600'
                  "
                  class="px-2 py-0.5 rounded font-bold text-[11px]"
                >
                  {{ item.kind === 'manual' ? '手动' : item.kind === 'pre-import' ? '导入前' : '自动' }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>
