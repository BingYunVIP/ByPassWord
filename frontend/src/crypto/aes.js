/** AES-256-GCM 封装：加密 / 解密 / 包裹 DEK。 */

import { fromBase64, randomBytes, toBase64 } from './base64'

const NONCE_LENGTH = 12

async function importAesKey(rawKey, usage) {
  if (!rawKey || rawKey.length !== 32) throw new Error('AES 密钥必须是 32 字节')
  return crypto.subtle.importKey('raw', rawKey, { name: 'AES-GCM' }, false, [usage])
}

/** @returns {Promise<{ciphertext: Uint8Array, nonce: Uint8Array}>} */
export async function aesGcmEncrypt(keyBytes, plaintextBytes) {
  const key = await importAesKey(keyBytes, 'encrypt')
  const nonce = randomBytes(NONCE_LENGTH)
  const buffer = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv: nonce, tagLength: 128 },
    key,
    plaintextBytes
  )
  return { ciphertext: new Uint8Array(buffer), nonce }
}

export async function aesGcmDecrypt(keyBytes, ciphertext, nonce) {
  const key = await importAesKey(keyBytes, 'decrypt')
  const buffer = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: nonce, tagLength: 128 },
    key,
    ciphertext
  )
  return new Uint8Array(buffer)
}

/** 用 encKey 包裹 DEK，返回可直接入库的 base64。 */
export async function wrapDek(encKey, dek) {
  const { ciphertext, nonce } = await aesGcmEncrypt(encKey, dek)
  return { wrappedDek: toBase64(ciphertext), dekNonce: toBase64(nonce) }
}

/** 解出 DEK；密码错误会抛异常（GCM 校验失败）。 */
export async function unwrapDek(encKey, wrappedDek, dekNonce) {
  const plaintext = await aesGcmDecrypt(
    encKey,
    fromBase64(wrappedDek),
    fromBase64(dekNonce)
  )
  return new Uint8Array(plaintext)
}
