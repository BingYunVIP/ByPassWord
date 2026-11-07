<script setup>
import AppIcon from '../common/AppIcon.vue'
import AuditTab from '../settings/AuditTab.vue'
import BackupTab from '../settings/BackupTab.vue'
import MailSettingsTab from '../settings/MailSettingsTab.vue'
import RecoveryBlock from '../settings/RecoveryBlock.vue'
import TwoFactorBlock from '../settings/TwoFactorBlock.vue'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

import * as vaultApi from '../../api/vault'
import { KDF_DEFAULTS } from '../../crypto/kdf'
import { useAuth, onSensitiveClear } from '../../stores/auth'
import { useVault } from '../../stores/vault'

const {
  activeModal,
  settingsTabs,
  activeSettingsTab,
  securityConfig,
  passwordChangeForm,
  updateMasterPassword,
  saveSecurityConfig,
  resetIdleTimer,
  showToast
} = useVault()

const auth = useAuth()
const { user: authUser } = auth

// 账户指纹：由真实用户 ID 派生，替代原来的硬编码假值
const accountFingerprint = computed(() => {
  const id = authUser.value?.id || ''
  return id ? id.replace(/-/g, '').slice(0, 16) : '—'
})

const confirmPass = ref('')
const unsubscribeSensitive = onSensitiveClear(() => { confirmPass.value = ''; ipRecords.value = [] })
onUnmounted(unsubscribeSensitive)
watch(activeModal, value => { if (value !== 'settings') confirmPass.value = '' })
const canChangePassword = computed(
  () =>
    Boolean(passwordChangeForm.current) &&
    passwordChangeForm.newPass.length >= 12 &&
    confirmPass.value === passwordChangeForm.newPass
)

function submitPasswordChange() {
  if (passwordChangeForm.newPass !== confirmPass.value) {
    showToast('两次输入的新主密码不一致')
    return
  }
  updateMasterPassword()
  confirmPass.value = ''
}

// IP 登录记录：取真实审计日志里的登录事件（原为前端假数据）
const LOGIN_ACTIONS = [
  'register',
  'login_success',
  'login_success_recovery',
  'login_failed',
  'account_locked'
]
const ipRecords = ref([])
const ipLoading = ref(false)

async function loadIpRecords() {
  const epoch = auth.sessionEpoch.value
  if (!auth.isUnlocked.value) return
  ipLoading.value = true
  try {
    const res = await vaultApi.listAudit(100)
    if (epoch !== auth.sessionEpoch.value || !auth.isUnlocked.value) return
    ipRecords.value = (res.items || [])
      .filter((r) => LOGIN_ACTIONS.includes(r.action))
      .map((r) => ({
        id: r.id,
        time: new Date(r.time).toLocaleString('zh-CN', { hour12: false }),
        ip: r.ip || '—',
        device: r.ua || '—',
        ok: r.action !== 'login_failed' && r.action !== 'account_locked',
        label:
          r.action === 'register'
            ? '注册'
            : r.action === 'login_success_recovery'
              ? '恢复码登录'
              : r.action === 'account_locked'
                ? '已锁定'
                : r.action === 'login_success'
                  ? '成功'
                  : '失败'
      }))
  } catch (e) {
    ipRecords.value = []
  } finally {
    ipLoading.value = false
  }
}

onMounted(loadIpRecords)
watch(activeSettingsTab, (tab) => {
  if (tab === 'iplogs' && !ipRecords.value.length) loadIpRecords()
})
watch(activeModal, modal => {
  if (modal === 'settings' && activeSettingsTab.value === 'iplogs' && !ipRecords.value.length) loadIpRecords()
})
</script>

<template>
  <!-- 弹窗 4：Bitwarden 级全功能【安全与系统设置中心】 -->
  <div
    v-if="activeModal === 'settings'"
    class="fixed inset-0 z-50 bg-black/45 backdrop-blur-[2px] flex items-center justify-center p-4"
    @click.self="activeModal = null"
  >
    <div
      
      class="surface-glass border-[var(--border-color)] text-zinc-900 w-full max-w-5xl h-[84vh] rounded-2xl border flex flex-col overflow-hidden shadow-2xl"
    >
      <div
        
        class="border-[var(--border-color)] bg-white/60 px-6 py-4 border-b flex items-center justify-between shrink-0"
      >
        <div class="flex items-center gap-2.5">
          <div class="w-8 h-8 rounded-lg theme-accent-btn flex items-center justify-center">
            <AppIcon name="admin_panel_settings" size="18" class="text-white" />
          </div>
          <div>
            <h3 class="font-bold text-sm">密码库安全与系统设置 (Bitwarden Security Suite)</h3>
          </div>
        </div>
        <button @click="activeModal = null" class="p-1.5 rounded-xl hover:bg-black/10">
          <AppIcon name="close" />
        </button>
      </div>

      <div class="flex-1 flex overflow-hidden">
        <!-- 设置导航栏 -->
        <div
          
          class="border-[var(--border-color)] bg-white/40 w-56 shrink-0 border-r p-3 space-y-1 overflow-y-auto"
        >
          <button
            v-for="tab in settingsTabs"
            :key="tab.id"
            @click="activeSettingsTab = tab.id"
            :class="
              activeSettingsTab === tab.id
                ? 'theme-accent-btn font-bold shadow-sm'
                : 'text-zinc-700 hover:bg-black/[0.04]'
            "
            class="w-full px-3 py-2.5 rounded-xl text-xs flex items-center gap-2.5 text-left spring-btn"
          >
            <AppIcon :name="tab.gIcon" size="16" :class="activeSettingsTab === tab.id ? 'text-white' : tab.color" />
            <span class="truncate">{{ tab.label }}</span>
          </button>
        </div>

        <!-- 设置右侧内容 -->
        <div class="flex-1 p-6 overflow-y-auto space-y-5 text-xs">
          <!-- Tab 1: 登录邮箱与登录密码 -->
          <div v-if="activeSettingsTab === 'account'" class="space-y-4">
            <h4 class="text-sm font-bold flex items-center gap-2">
              <AppIcon name="manage_accounts" class="text-accent" />
              <span>登录邮箱与主密码</span>
            </h4>

            <!-- 账户信息（真实会话数据） -->
            <div class="theme-card p-4">
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label class="block font-bold mb-1.5">登录邮箱</label>
                  <div class="ios-input w-full rounded-xl px-3.5 py-2.5 theme-text-muted truncate">
                    {{ authUser?.email || '—' }}
                  </div>
                </div>
                <div>
                  <label class="block font-bold mb-1.5">账户指纹</label>
                  <code
                    class="theme-subtle border-[var(--border-color)] text-rose-600 block px-3.5 py-2.5 rounded-xl border font-bold truncate"
                  >
                    {{ accountFingerprint }}
                  </code>
                </div>
              </div>
            </div>

            <!-- 改密与 2FA 并排（同 ByUI SecuritySettingsView） -->
            <div class="grid grid-cols-1 xl:grid-cols-2 gap-4">
              <section class="theme-card p-4 space-y-3">
                <h3 class="font-bold">修改主密码</h3>
                <div>
                  <label for="sec-cur-pwd" class="block font-bold mb-1">当前主密码</label>
                  <input
                    id="sec-cur-pwd"
                    v-model="passwordChangeForm.current"
                    type="password"
                    autocomplete="current-password"
                    class="ios-input w-full rounded-xl px-3.5 py-2.5"
                  />
                </div>
                <div>
                  <label for="sec-new-pwd" class="block font-bold mb-1">新主密码</label>
                  <input
                    id="sec-new-pwd"
                    v-model="passwordChangeForm.newPass"
                    type="password"
                    autocomplete="new-password"
                    placeholder="至少 12 位高强度主密码"
                    class="ios-input w-full rounded-xl px-3.5 py-2.5"
                  />
                </div>
                <div>
                  <label for="sec-new-pwd2" class="block font-bold mb-1">确认新主密码</label>
                  <input
                    id="sec-new-pwd2"
                    v-model="confirmPass"
                    type="password"
                    autocomplete="new-password"
                    class="ios-input w-full rounded-xl px-3.5 py-2.5"
                  />
                </div>
                <button
                  type="button"
                  id="btn-change-password"
                  class="px-4 py-2 rounded-xl font-bold theme-accent-btn disabled:opacity-60"
                  :disabled="!canChangePassword"
                  @click="submitPasswordChange"
                >
                  修改主密码
                </button>
              </section>

              <TwoFactorBlock />
              <RecoveryBlock />
            </div>
          </div>

          <!-- Tab 2: 选择加密标准 -->
          <!-- Tab 2: 加密标准（只读） -->
          <div v-if="activeSettingsTab === 'crypto'" class="space-y-4">
            <h4 class="text-sm font-bold flex items-center gap-2">
              <AppIcon name="enhanced_encryption" class="text-purple-500" />
              <span>加密标准与密钥派生</span>
            </h4>

            <section class="theme-card p-4 space-y-3">
              <h3 class="font-bold">对称加密</h3>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label class="block font-bold mb-1">加密算法</label>
                  <div class="ios-input w-full rounded-xl px-3.5 py-2.5 theme-text-muted">
                    AES-256-GCM
                  </div>
                </div>
                <div>
                  <label class="block font-bold mb-1">密钥长度</label>
                  <div class="ios-input w-full rounded-xl px-3.5 py-2.5 theme-text-muted">256 bit</div>
                </div>
              </div>
              <p class="text-[0.68rem] theme-text-muted">
                创建密码库时确定，不可更改；更换算法会导致历史数据无法解密。
              </p>
            </section>

            <section class="theme-card p-4 space-y-3">
              <h3 class="font-bold">密钥派生（Argon2id）</h3>
              <div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
                <div>
                  <label class="block font-bold mb-1">内存</label>
                  <div class="ios-input w-full rounded-xl px-3 py-2 theme-text-muted">
                    {{ Math.round(KDF_DEFAULTS.memoryKib / 1024) }} MiB
                  </div>
                </div>
                <div>
                  <label class="block font-bold mb-1">迭代次数</label>
                  <div class="ios-input w-full rounded-xl px-3 py-2 theme-text-muted">
                    {{ KDF_DEFAULTS.time }}
                  </div>
                </div>
                <div>
                  <label class="block font-bold mb-1">并行度</label>
                  <div class="ios-input w-full rounded-xl px-3 py-2 theme-text-muted">
                    {{ KDF_DEFAULTS.parallel }}
                  </div>
                </div>
                <div>
                  <label class="block font-bold mb-1">输出长度</label>
                  <div class="ios-input w-full rounded-xl px-3 py-2 theme-text-muted">
                    {{ KDF_DEFAULTS.hashLength }} B
                  </div>
                </div>
              </div>
              <p class="text-[0.68rem] theme-text-muted">
                主密码只在浏览器内派生密钥，服务端永远拿不到明文。
              </p>
            </section>
          </div>

          <!-- Tab 3: 未操作锁定 -->
          <div v-if="activeSettingsTab === 'lock'" class="space-y-4">
            <h4 class="text-sm font-bold flex items-center gap-2">
              <AppIcon name="timer" class="text-amber-500" />
              <span>未操作锁定</span>
            </h4>

            <section class="theme-card p-4 space-y-3">
              <h3 class="font-bold">自动锁定</h3>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label for="idle-timeout" class="block font-bold mb-1">未操作自动锁定</label>
                  <select
                    id="idle-timeout"
                    v-model.number="securityConfig.idleTimeoutMinutes"
                    class="ios-input w-full rounded-xl px-3.5 py-2.5"
                    @change="
                      resetIdleTimer();
                      saveSecurityConfig(
                        '设置未操作锁定时间为 ' + securityConfig.idleTimeoutMinutes + ' 分钟'
                      )
                    "
                  >
                    <option :value="1">1 分钟</option>
                    <option :value="5">5 分钟</option>
                    <option :value="15">15 分钟</option>
                    <option :value="30">30 分钟</option>
                    <option :value="60">60 分钟</option>
                  </select>
                </div>
                <div>
                  <label for="clipboard-clear" class="block font-bold mb-1">剪贴板自动清空</label>
                  <select
                    id="clipboard-clear"
                    v-model.number="securityConfig.clipboardClearSeconds"
                    class="ios-input w-full rounded-xl px-3.5 py-2.5"
                  >
                    <option :value="10">10 秒</option>
                    <option :value="20">20 秒</option>
                    <option :value="30">30 秒</option>
                  </select>
                </div>
              </div>
              <p class="text-[0.68rem] theme-text-muted">
                超时后需重新输入主密码才能解锁，剪贴板到期自动清除复制的密码。
              </p>
            </section>
          </div>

          <!-- Tab 4: 邮箱配置 -->
          <div v-if="activeSettingsTab === 'smtp'" class="space-y-4">
            <MailSettingsTab />
          </div>

          <!-- Tab 5: 备份时间 -->
          <div v-if="activeSettingsTab === 'backup'" class="space-y-4">
            <BackupTab />
          </div>

          <!-- Tab 6: IP 登录记录 -->
          <div v-if="activeSettingsTab === 'iplogs'" class="space-y-4">
            <h4 class="text-sm font-bold flex items-center gap-2">
              <AppIcon name="travel_explore" class="text-indigo-500" />
              <span>IP 登录记录</span>
            </h4>
            <div class="theme-card overflow-hidden">
              <table class="w-full text-left border-collapse">
                <thead>
                  <tr
                    
                    class="theme-subtle border-b border-[var(--border-color)] text-[0.68rem] opacity-75"
                  >
                    <th class="p-3 whitespace-nowrap">时间</th>
                    <th class="p-3">IP</th>
                    <th class="p-3 whitespace-nowrap">账号</th>
                    <th class="p-3 whitespace-nowrap">结果</th>
                    <th class="p-3">UA</th>
                  </tr>
                </thead>
                <tbody class="divide-black/10 divide-y">
                  <tr v-if="ipLoading">
                    <td colspan="5" class="p-4 text-center opacity-60">加载中…</td>
                  </tr>
                  <tr v-else-if="!ipRecords.length">
                    <td colspan="5" class="p-4 text-center opacity-60">暂无登录记录</td>
                  </tr>
                  <tr v-for="rec in ipRecords" :key="rec.id">
                    <td class="p-3 whitespace-nowrap">{{ rec.time }}</td>
                    <td class="p-3 font-bold whitespace-nowrap">{{ rec.ip }}</td>
                    <td class="p-3 theme-text-muted truncate max-w-[14rem]">{{ authUser?.email || '—' }}</td>
                    <td class="p-3">
                      <span
                        :class="
                          rec.ok
                            ? 'bg-emerald-500/15 text-emerald-500'
                            : 'bg-rose-500/15 text-rose-500'
                        "
                        class="px-2 py-0.5 rounded font-bold text-[0.65rem] whitespace-nowrap"
                        >{{ rec.label }}</span
                      >
                    </td>
                    <td class="p-3 max-w-[16rem] truncate theme-text-muted" :title="rec.device">{{ rec.device }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Tab 7: 日志记录 -->
          <div v-if="activeSettingsTab === 'audit'" class="space-y-4">
            <AuditTab />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
