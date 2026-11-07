/** 金库接口封装。 */

import { apiFetch } from './client'

export function getVault(since) {
  const query = typeof since === 'number' ? `?since=${since}` : ''
  return apiFetch(`/vault${query}`)
}

export function createFolder(payload) {
  return apiFetch('/folders', { method: 'POST', body: payload })
}

export function patchFolder(id, payload) {
  return apiFetch(`/folders/${encodeURIComponent(id)}`, { method: 'PATCH', body: payload })
}

export function deleteFolder(id, rev) {
  const query = rev ? `?rev=${rev}` : ''
  return apiFetch(`/folders/${encodeURIComponent(id)}${query}`, { method: 'DELETE' })
}

export function createItem(payload) {
  return apiFetch('/items', { method: 'POST', body: payload })
}

export function patchItem(id, payload) {
  return apiFetch(`/items/${encodeURIComponent(id)}`, { method: 'PATCH', body: payload })
}

export function deleteItem(id, rev) {
  const query = rev ? `?rev=${rev}` : ''
  return apiFetch(`/items/${encodeURIComponent(id)}${query}`, { method: 'DELETE' })
}

export function importVault(payload) {
  return apiFetch('/vault/import', { method: 'POST', body: payload })
}

export function getSettings() {
  return apiFetch('/settings')
}

export function putSettings(ciphertext, nonce) {
  return apiFetch('/settings', { method: 'PUT', body: { ciphertext, nonce } })
}

export function testMail(to) {
  return apiFetch('/settings/mail/test', { method: 'POST', body: { to: to || null } })
}

export function getMailSettings() {
  return apiFetch('/settings/mail')
}

export function getMailEvents() {
  return apiFetch('/settings/mail/events')
}

export function saveMailEvents(events) {
  return apiFetch('/settings/mail/events', { method: 'PUT', body: { events } })
}

export function getMailTemplates() {
  return apiFetch('/settings/mail/templates')
}

export function saveMailTemplate(eventKey, subject, body) {
  return apiFetch(`/settings/mail/templates/${encodeURIComponent(eventKey)}`, {
    method: 'PUT',
    body: { subject, body }
  })
}

export function resetMailTemplate(eventKey) {
  return apiFetch(`/settings/mail/templates/${encodeURIComponent(eventKey)}/reset`, { method: 'POST' })
}

export function saveMailSettings(payload) {
  return apiFetch('/settings/mail', { method: 'PUT', body: payload })
}

export function getBackupSettings() {
  return apiFetch('/settings/backup')
}

export function saveBackupSettings(payload) {
  return apiFetch('/settings/backup', { method: 'PUT', body: payload })
}

export function listBackups() {
  return apiFetch('/backup/list')
}

export function createSnapshot() {
  return apiFetch('/backup/snapshot', { method: 'POST' })
}

export function listAudit(limit = 50) {
  return apiFetch(`/audit?limit=${limit}`)
}
