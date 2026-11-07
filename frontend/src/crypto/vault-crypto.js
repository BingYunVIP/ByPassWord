/**
 * 金库加解密编排：注册 / 解锁 / 记录加解密 / 恢复码副本。
 *
 * 这是前端唯一需要「懂密码学」的地方，UI 层只调用这里的函数。
 */

import { aesGcmDecrypt, aesGcmEncrypt, unwrapDek, wrapDek } from './aes'
import { fromBase64, randomBytes, toBase64, utf8Decode, utf8Encode } from './base64'
import {
  authHashFromAuthKey,
  createKdfParams,
  deriveMasterKey,
  deriveRecoveryKey,
  deriveRecoveryAuthHash,
  splitKeys
} from './kdf'

export function generateDek() {
  return randomBytes(32)
}

/** 加密一条记录（folder / item / settings 的明文对象）。 */
export async function encryptRecord(dek, payload) {
  const { ciphertext, nonce } = await aesGcmEncrypt(dek, utf8Encode(JSON.stringify(payload)))
  return { ciphertext: toBase64(ciphertext), nonce: toBase64(nonce) }
}

/** 解密一条记录；密文被篡改会抛异常。 */
export async function decryptRecord(dek, ciphertext, nonce) {
  const plaintext = await aesGcmDecrypt(dek, fromBase64(ciphertext), fromBase64(nonce))
  return JSON.parse(utf8Decode(plaintext))
}

/**
 * 注册：一次生成全部密钥材料。
 * 返回的对象里，只有 authHash / wrappedDek / dekNonce / kdf / recoveryWrapped* 会发给服务端。
 */
export async function createVaultKeys(password, { kdfOverrides, recoveryCode } = {}) {
  const kdf = createKdfParams(kdfOverrides)
  const masterKey = await deriveMasterKey(password, kdf)
  let encKey, authKey
  try { ({ encKey, authKey } = await splitKeys(masterKey)) }
  finally { masterKey.fill(0) }

  const dek = generateDek()
  try {
    const { wrappedDek, dekNonce } = await wrapDek(encKey, dek)
    const recovery = recoveryCode ? await createRecoveryConfiguration(recoveryCode, dek) : {}
    return {
      kdf: { algo: kdf.algo, salt: kdf.salt, memoryKib: kdf.memoryKib, time: kdf.time, parallel: kdf.parallel },
      authHash: authHashFromAuthKey(authKey),
      wrappedDek,
      dekNonce,
      dek,
      encKey,
      authKey,
      ...recovery
    }
  } catch (e) { dek.fill(0); encKey.fill(0); authKey.fill(0); throw e }
}

/**
 * 解锁：用主密码重新派生密钥并解出 DEK。
 * 密码错误时 unwrapDek 会抛错，调用方据此提示「主密码错误」。
 */
export async function unlockVault(password, kdf, wrappedDek, dekNonce) {
  const masterKey = await deriveMasterKey(password, kdf)
  let encKey, authKey
  try {
    ;({ encKey, authKey } = await splitKeys(masterKey))
    const dek = await unwrapDek(encKey, wrappedDek, dekNonce)
    return { dek, encKey, authKey, authHash: authHashFromAuthKey(authKey) }
  } catch (e) { encKey?.fill(0); authKey?.fill(0); throw e }
  finally { masterKey.fill(0) }
}

/** 忘记密码：用恢复码解出 DEK，再用新主密码重新包裹。 */
export async function recoverDekWithRecoveryCode(
  recoveryCode,
  recoveryWrappedDek,
  recoveryDekNonce
) {
  const recoveryKey = await deriveRecoveryKey(recoveryCode)
  try { return await unwrapDek(recoveryKey, recoveryWrappedDek, recoveryDekNonce) }
  finally { recoveryKey.fill(0) }
}

/** 改密：同一 DEK 用新密码重新包裹（数据无需重加密）。 */
export async function rewrapDekForNewPassword(newPassword, dek, { recoveryCode } = {}) {
  const kdf = createKdfParams()
  const masterKey = await deriveMasterKey(newPassword, kdf)
  let encKey, authKey
  try {
    ;({ encKey, authKey } = await splitKeys(masterKey))
    const { wrappedDek, dekNonce } = await wrapDek(encKey, dek)
    const recovery = recoveryCode ? await createRecoveryConfiguration(recoveryCode, dek) : {}
    return {
      newKdf: { algo: kdf.algo, salt: kdf.salt, memoryKib: kdf.memoryKib, time: kdf.time, parallel: kdf.parallel },
      newAuthHash: authHashFromAuthKey(authKey),
      wrappedDek,
      dekNonce,
      ...recovery
    }
  } finally { masterKey.fill(0); encKey?.fill(0); authKey?.fill(0) }
}

/** Re-wrap the existing DEK; no plaintext keys are sent to the service. */
export async function createRecoveryConfiguration(recoveryCode, dek) {
  const key = await deriveRecoveryKey(recoveryCode)
  try {
    const wrapped = await wrapDek(key, dek)
    return { recoveryWrappedDek: wrapped.wrappedDek, recoveryDekNonce: wrapped.dekNonce, recoveryAuthHash: await deriveRecoveryAuthHash(recoveryCode) }
  } finally { key.fill(0) }
}
