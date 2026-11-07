<script setup>
import { computed, ref, onUnmounted } from 'vue'
import { onSensitiveClear, useAuth } from '../../stores/auth'
const auth = useAuth()
const password = ref(''), code = ref(''), issued = ref(''), error = ref(''), busy = ref(false)
let disposed = false
const configured = computed(() => Boolean(auth.user.value?.recoveryConfigured))
const twoFactor = computed(() => Boolean(auth.user.value?.twoFactorEnabled))
function clear() { password.value = ''; code.value = ''; issued.value = ''; error.value = '' }
const unsubscribe = onSensitiveClear(clear)
onUnmounted(() => { disposed = true; unsubscribe(); clear() })
async function submit() {
  if (busy.value) return
  error.value = ''
  if (!password.value || (twoFactor.value && !/^\d{6}$/.test(code.value))) { error.value = '请输入当前主密码；已开启两步验证时还需 6 位动态码'; return }
  const epoch = auth.sessionEpoch.value
  busy.value = true
  try {
    const result = await auth.rotateRecovery(password.value, code.value)
    if (!disposed && epoch === auth.sessionEpoch.value && auth.isUnlocked.value) issued.value = result
  } catch (e) { if (epoch === auth.sessionEpoch.value) error.value = e.message || '恢复配置更新失败' }
  finally { password.value = ''; code.value = ''; busy.value = false }
}
async function copy() {
  try { await navigator.clipboard.writeText(issued.value) }
  catch { error.value = '复制失败，请手动抄写恢复码' }
}
</script>
<template>
  <section class="theme-card p-4 space-y-3" aria-labelledby="recovery-title">
    <h3 id="recovery-title" class="font-bold">主密码恢复码</h3>
    <p class="text-xs leading-relaxed" :class="configured ? 'theme-text-muted' : 'text-amber-600'">
      {{ configured ? '邮箱验证码与恢复码共同授权主密码重置。' : '此账号需要升级恢复配置。升级前无法通过邮箱重置，请使用现有主密码登录。' }}
      更新只重新包裹现有数据密钥，不改变金库条目；更新成功后旧恢复码失效。
    </p>
    <div v-if="issued" class="space-y-3" role="status" aria-live="polite">
      <p class="text-xs font-semibold">新恢复码已生效，仅在此显示。请保存在独立的安全位置。</p>
      <code class="block theme-subtle rounded-xl p-3 text-xs break-all select-all" data-testid="vault-recovery-code">{{ issued }}</code>
      <div class="flex flex-wrap gap-2">
        <button type="button" class="theme-subtle px-3 py-2 rounded-xl" @click="copy">复制恢复码</button>
        <button type="button" class="theme-accent-btn px-3 py-2 rounded-xl" @click="clear">我已保存，隐藏恢复码</button>
      </div>
    </div>
    <form v-else class="space-y-3" @submit.prevent="submit">
      <div><label for="recovery-password" class="block font-bold mb-1">当前主密码</label><input id="recovery-password" v-model="password" type="password" autocomplete="current-password" class="ios-input w-full px-3 py-2 rounded-xl" required /></div>
      <div v-if="twoFactor"><label for="recovery-totp" class="block font-bold mb-1">当前动态码</label><input id="recovery-totp" v-model="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" pattern="[0-9]{6}" class="ios-input w-full px-3 py-2 rounded-xl" required /></div>
      <button type="submit" :disabled="busy" class="theme-accent-btn px-4 py-2 rounded-xl font-bold disabled:opacity-60">{{ busy ? '正在更新…' : configured ? '验证并生成新恢复码' : '验证并升级恢复配置' }}</button>
    </form>
    <p v-if="error" role="alert" class="text-xs text-rose-500">{{ error }}</p>
  </section>
</template>
