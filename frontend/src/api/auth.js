/** 认证接口封装（全部返回后端原始 JSON）。 */

import { apiFetch } from './client'

export function prelogin(email) {
  return apiFetch('/auth/prelogin', { method: 'POST', body: { email }, auth: false })
}

export function register(payload) {
  return apiFetch('/auth/register', { method: 'POST', body: payload, auth: false })
}

export function login(email, authHash) {
  return apiFetch('/auth/login', { method: 'POST', body: { email, authHash }, auth: false })
}

export function verifyTwoFactor(challenge, code) {
  return apiFetch('/auth/2fa/verify', { method: 'POST', body: { challenge, code }, auth: false })
}

export function verifyRecovery(challenge, recoveryCode) {
  return apiFetch('/auth/2fa/verify-recovery', {
    method: 'POST',
    body: { challenge, recoveryCode },
    auth: false
  })
}

export function refresh() {
  return apiFetch('/auth/refresh', { method: 'POST', auth: false })
}

export function logout() {
  return apiFetch('/auth/logout', { method: 'POST', auth: false })
}

export function me() {
  return apiFetch('/auth/me')
}

export function changePassword(payload) {
  return apiFetch('/auth/change-password', { method: 'POST', body: payload })
}

export function forgot(email) {
  return apiFetch('/auth/forgot', { method: 'POST', body: { email }, auth: false })
}

export function forgotVerify(email, code) {
  return apiFetch('/auth/forgot/verify', {
    method: 'POST',
    body: { email, code },
    auth: false
  })
}

export function reset(payload) {
  return apiFetch('/auth/reset', { method: 'POST', body: payload, auth: false })
}

// 账号 2FA
export function setupTwoFactor() {
  return apiFetch('/auth/2fa/setup', { method: 'POST' })
}

export function enableTwoFactor(code) {
  return apiFetch('/auth/2fa/enable', { method: 'POST', body: { code } })
}

export function verifyUnlockTotp(code) {
  return apiFetch('/auth/unlock/verify-totp', { method: 'POST', body: { code } })
}

export function disableTwoFactor(authHash, code) {
  return apiFetch('/auth/2fa/disable', { method: 'POST', body: { authHash, code } })
}

export function recoveryCodeCount() {
  return apiFetch('/auth/2fa/recovery-codes')
}

export function updateRecovery(payload) {
  return apiFetch('/auth/recovery', { method: 'PUT', body: payload })
}

export function registrationStatus() {
  return apiFetch('/auth/registration-status', { auth: false })
}
