/**
 * 密钥派生：主密码 → masterKey → (encKey, authKey)。
 *
 * 设计（见 docs/ARCHITECTURE.md 第 4 节）：
 *   Argon2id(主密码, salt)            → 64B masterKey
 *   HKDF(masterKey, "bypw:enc")       → 32B encKey（包裹 DEK）
 *   HKDF(masterKey, "bypw:auth")      → 32B authKey（登录认证）
 *
 * 主密码与派生结果**永不离开浏览器**；服务端只拿到 authKey 的再哈希。
 */

import { argon2id } from 'hash-wasm'
import { validateKdfParams } from '../security/policy'

import { fromBase64, randomBytes, toBase64, utf8Encode } from './base64'

export const KDF_DEFAULTS = {
  algo: 'argon2id',
  memoryKib: 65536, // 64 MiB
  time: 3,
  parallel: 1,
  hashLength: 64
}

export function generateSalt(length = 16) {
  return randomBytes(length)
}

export function createKdfParams(overrides = {}) {
  return {
    ...KDF_DEFAULTS,
    ...overrides,
    salt: toBase64(generateSalt())
  }
}

/**
 * 用主密码派生 64 字节 masterKey。
 * @param {string} password 主密码
 * @param {{salt:string, memoryKib?:number, time?:number, parallel?:number}} params
 * @returns {Promise<Uint8Array>}
 */
export async function deriveMasterKey(password, params) {
  if (!password) throw new Error('主密码不能为空')
  validateKdfParams(params)
  const salt = typeof params.salt === 'string' ? fromBase64(params.salt) : params.salt
  if (!salt || salt.length < 8) throw new Error('KDF salt 无效')

  const hash = await argon2id({
    password,
    salt,
    parallelism: params.parallel ?? KDF_DEFAULTS.parallel,
    iterations: params.time ?? KDF_DEFAULTS.time,
    memorySize: params.memoryKib ?? KDF_DEFAULTS.memoryKib,
    hashLength: params.hashLength ?? KDF_DEFAULTS.hashLength,
    outputType: 'binary'
  })
  return new Uint8Array(hash)
}

/** HKDF-SHA256 派生 32 字节子密钥。 */
async function hkdf(masterKey, info, length = 32) {
  const baseKey = await crypto.subtle.importKey('raw', masterKey, 'HKDF', false, ['deriveBits'])
  const bits = await crypto.subtle.deriveBits(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      salt: new Uint8Array(0),
      info: utf8Encode(info)
    },
    baseKey,
    length * 8
  )
  return new Uint8Array(bits)
}

/** 把 masterKey 拆成加密密钥与认证密钥。 */
export async function splitKeys(masterKey) {
  const [encKey, authKey] = await Promise.all([
    hkdf(masterKey, 'bypw:enc'),
    hkdf(masterKey, 'bypw:auth')
  ])
  return { encKey, authKey }
}

/** 登录时提交给服务端的认证值（服务端还会再做一次 Argon2 哈希）。 */
export function authHashFromAuthKey(authKey) {
  return toBase64(authKey)
}

const RECOVERY_SALT = 'bypw:recovery:v1'
const RECOVERY_ITERATIONS = 310000

/**
 * 恢复码 → 32 字节恢复密钥（PBKDF2-SHA256）。
 * 恢复码只用于包裹 DEK 副本，不参与日常登录。
 */
export async function deriveRecoveryKey(recoveryCode) {
  const normalized = String(recoveryCode).trim().toUpperCase().replace(/\s+/g, '')
  if (normalized.length < 8) throw new Error('恢复码格式不正确')

  const baseKey = await crypto.subtle.importKey('raw', utf8Encode(normalized), 'PBKDF2', false, [
    'deriveBits'
  ])
  const bits = await crypto.subtle.deriveBits(
    {
      name: 'PBKDF2',
      salt: utf8Encode(RECOVERY_SALT),
      iterations: RECOVERY_ITERATIONS,
      hash: 'SHA-256'
    },
    baseKey,
    256
  )
  return new Uint8Array(bits)
}

/** Recovery authentication is domain-separated from the key wrapping the DEK. */
export async function deriveRecoveryAuthHash(recoveryCode) {
  const recoveryKey = await deriveRecoveryKey(recoveryCode)
  try { return toBase64(await hkdf(recoveryKey, 'bypw:recovery-auth:v1')) }
  finally { recoveryKey.fill(0) }
}
