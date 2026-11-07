/** Session keys are memory-only. Every lock invalidates in-flight sensitive work. */
import { computed, ref } from 'vue'
import * as authApi from '../api/auth'
import { setAccessToken, setRefreshHandler, setUnauthorizedHandler } from '../api/client'
import { unwrapDek } from '../crypto/aes'
import { authHashFromAuthKey, deriveMasterKey, splitKeys } from '../crypto/kdf'
import { createVaultKeys, createRecoveryConfiguration, rewrapDekForNewPassword } from '../crypto/vault-crypto'

const RECOVERY_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
export function generateRecoveryCode() {
  const raw = Array.from(crypto.getRandomValues(new Uint8Array(24)), b => RECOVERY_ALPHABET[b % 32]).join('')
  return raw.match(/.{1,4}/g).join('-')
}
const user = ref(null)
const status = ref('anonymous')
const dek = ref(null)
const pending = ref(null)
const lockReason = ref('手动锁定')
const busy = ref(false)
const lastError = ref('')
const sessionEpoch = ref(0)
const cleanupHandlers = new Set()
export function onSensitiveClear(fn) { cleanupHandlers.add(fn); return () => cleanupHandlers.delete(fn) }
function wipe(value) { if (value instanceof Uint8Array) value.fill(0) }
function clearKeys() {
  wipe(dek.value); dek.value = null
  if (pending.value) {
    wipe(pending.value.encKey); wipe(pending.value.pendingDek)
    pending.value.encKey = null; pending.value.pendingDek = null
  }
}
function invalidate() {
  sessionEpoch.value++
  clearKeys()
  for (const fn of cleanupHandlers) fn()
}
function ensureCurrent(epoch) {
  if (epoch !== sessionEpoch.value) throw new Error('操作已取消，请重新解锁')
}
function clearSession() {
  invalidate()
  user.value = null; pending.value = null; status.value = 'anonymous'; busy.value = false
  setAccessToken(null)
}
setUnauthorizedHandler(clearSession)
setRefreshHandler(async () => {
  const epoch = sessionEpoch.value
  try {
    const res = await authApi.refresh()
    ensureCurrent(epoch)
    setAccessToken(res.accessToken)
    if (pending.value) { pending.value.wrappedDek = res.wrappedDek; pending.value.dekNonce = res.dekNonce }
    return true
  } catch {
    if (epoch === sessionEpoch.value) clearSession()
    return false
  }
})
async function syncProfile(epoch) {
  const profile = await authApi.me()
  ensureCurrent(epoch)
  user.value = profile
}
async function unlockWithEncKey(epoch) {
  const current = pending.value
  if (!current?.encKey || !current.wrappedDek) throw new Error('会话信息不完整')
  const restored = await unwrapDek(current.encKey, current.wrappedDek, current.dekNonce)
  try { ensureCurrent(epoch) } catch (e) { wipe(restored); throw e }
  dek.value = restored; status.value = 'unlocked'
}
async function unlock(password) {
  if (!pending.value) throw new Error('会话已失效，请重新登录')
  const epoch = sessionEpoch.value, current = pending.value
  const master = await deriveMasterKey(password, current.kdf)
  const { encKey, authKey } = await splitKeys(master)
  wipe(master); wipe(authKey)
  try {
    ensureCurrent(epoch)
    const restored = await unwrapDek(encKey, current.wrappedDek, current.dekNonce)
    try { ensureCurrent(epoch) } catch (e) { wipe(restored); throw e }
    current.encKey = encKey
    if (user.value?.twoFactorEnabled) { current.pendingDek = restored; return { requires2fa: true } }
    dek.value = restored; status.value = 'unlocked'
    return { ok: true }
  } catch (e) { wipe(encKey); throw e }
}
async function confirmUnlockTotp(code) {
  const epoch = sessionEpoch.value, current = pending.value
  if (!current?.pendingDek) throw new Error('请先输入主密码')
  await authApi.verifyUnlockTotp(code)
  ensureCurrent(epoch)
  if (pending.value !== current || !current.pendingDek) throw new Error('请重新输入主密码')
  dek.value = current.pendingDek; current.pendingDek = null; status.value = 'unlocked'
  return { ok: true }
}
function beginAuthentication() { clearSession(); busy.value = true; lastError.value = ''; return sessionEpoch.value }
async function login(email, password) {
  const epoch = beginAuthentication()
  let master, encKey, authKey
  try {
    const { kdf } = await authApi.prelogin(email); ensureCurrent(epoch)
    master = await deriveMasterKey(password, kdf); ensureCurrent(epoch)
    ;({ encKey, authKey } = await splitKeys(master)); ensureCurrent(epoch)
    const res = await authApi.login(email, authHashFromAuthKey(authKey)); ensureCurrent(epoch)
    if (res.requires2fa) { pending.value = { email, kdf, encKey, challenge: res.challenge }; return { requires2fa: true } }
    setAccessToken(res.accessToken)
    pending.value = { email, kdf, encKey, wrappedDek: res.wrappedDek, dekNonce: res.dekNonce }
    await syncProfile(epoch)
    await unlockWithEncKey(epoch)
    return { ok: true }
  } catch (e) {
    if (epoch === sessionEpoch.value) { lastError.value = e.message; clearSession() }
    wipe(encKey); throw e
  } finally { wipe(master); wipe(authKey); if (epoch === sessionEpoch.value) busy.value = false }
}
async function finishTwoFactor(action) {
  const epoch = sessionEpoch.value, current = pending.value
  if (!current?.challenge) throw new Error('登录挑战已失效，请重新登录')
  busy.value = true
  try {
    const res = await action(current.challenge); ensureCurrent(epoch)
    setAccessToken(res.accessToken); current.wrappedDek = res.wrappedDek; current.dekNonce = res.dekNonce
    await syncProfile(epoch)
    await unlockWithEncKey(epoch)
    return { ok: true }
  } finally { if (epoch === sessionEpoch.value) busy.value = false }
}
const verifyTwoFactor = code => finishTwoFactor(challenge => authApi.verifyTwoFactor(challenge, code))
const verifyRecoveryCode = code => finishTwoFactor(challenge => authApi.verifyRecovery(challenge, code))
async function register(email, password) {
  const epoch = beginAuthentication()
  let keys
  try {
    const recoveryCode = generateRecoveryCode()
    keys = await createVaultKeys(password, { recoveryCode }); ensureCurrent(epoch)
    const res = await authApi.register({ email, kdf: keys.kdf, authHash: keys.authHash, wrappedDek: keys.wrappedDek, dekNonce: keys.dekNonce, recoveryWrappedDek: keys.recoveryWrappedDek, recoveryDekNonce: keys.recoveryDekNonce, recoveryAuthHash: keys.recoveryAuthHash }); ensureCurrent(epoch)
    setAccessToken(res.accessToken)
    pending.value = { email, kdf: keys.kdf, encKey: keys.encKey, wrappedDek: keys.wrappedDek, dekNonce: keys.dekNonce }
    dek.value = keys.dek
    await syncProfile(epoch)
    status.value = 'unlocked'
    return { recoveryCode }
  } catch (e) {
    wipe(keys?.dek); wipe(keys?.encKey)
    if (epoch === sessionEpoch.value) { lastError.value = e.message; clearSession() }
    throw e
  } finally { wipe(keys?.authKey); if (epoch === sessionEpoch.value) busy.value = false }
}
async function restore() {
  const epoch = sessionEpoch.value
  try {
    const res = await authApi.refresh(); ensureCurrent(epoch)
    setAccessToken(res.accessToken)
    const profile = await authApi.me(); ensureCurrent(epoch)
    const pre = await authApi.prelogin(profile.email); ensureCurrent(epoch)
    pending.value = { email: profile.email, kdf: pre.kdf, wrappedDek: res.wrappedDek, dekNonce: res.dekNonce }
    user.value = profile; status.value = 'locked'; return true
  } catch { if (epoch === sessionEpoch.value) clearSession(); return false }
}
function lock(reason = '手动锁定') {
  lockReason.value = reason
  invalidate()
  status.value = pending.value ? 'locked' : 'anonymous'
}
async function logout() { clearSession(); try { await authApi.logout() } catch { /* Already cleared locally. */ } }
async function authHashFor(password) {
  if (!pending.value) throw new Error('会话已失效，请重新登录')
  const epoch = sessionEpoch.value
  const master = await deriveMasterKey(password, pending.value.kdf)
  const { encKey, authKey } = await splitKeys(master)
  try { ensureCurrent(epoch); return authHashFromAuthKey(authKey) }
  finally { wipe(master); wipe(encKey); wipe(authKey) }
}
async function changeMasterPassword(oldPassword, newPassword) {
  if (!pending.value || !dek.value) throw new Error('请先解锁')
  const epoch = sessionEpoch.value
  const oldAuthHash = await authHashFor(oldPassword); ensureCurrent(epoch)
  const rewrapped = await rewrapDekForNewPassword(newPassword, dek.value); ensureCurrent(epoch)
  await authApi.changePassword({ oldAuthHash, ...rewrapped })
  if (epoch === sessionEpoch.value) clearSession()
}
async function rotateRecovery(password, code) {
  if (!dek.value || status.value !== 'unlocked') throw new Error('请先解锁')
  const epoch = sessionEpoch.value
  const authHash = await authHashFor(password); ensureCurrent(epoch)
  const recoveryCode = generateRecoveryCode()
  const config = await createRecoveryConfiguration(recoveryCode, dek.value); ensureCurrent(epoch)
  await authApi.updateRecovery({ authHash, ...(code ? { code } : {}), ...config }); ensureCurrent(epoch)
  user.value = { ...user.value, recoveryConfigured: true }
  return recoveryCode
}
const isAuthenticated = computed(() => status.value !== 'anonymous')
const isUnlocked = computed(() => status.value === 'unlocked')
export function useAuth() {
  return { user, status, dek, pending, lockReason, busy, lastError, sessionEpoch, isAuthenticated, isUnlocked, login, verifyTwoFactor, verifyRecoveryCode, register, restore, unlock, confirmUnlockTotp, lock, logout, changeMasterPassword, rotateRecovery, authHashFor, generateRecoveryCode, clearSession }
}
