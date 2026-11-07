import { describe, expect, it } from 'vitest'

import { aesGcmDecrypt, aesGcmEncrypt, unwrapDek, wrapDek } from './aes'
import { fromBase64, randomBytes, toBase64 } from './base64'
import { authHashFromAuthKey, deriveMasterKey, deriveRecoveryAuthHash, deriveRecoveryKey, splitKeys } from './kdf'
import {
  createVaultKeys,
  createRecoveryConfiguration,
  decryptRecord,
  encryptRecord,
  generateDek,
  recoverDekWithRecoveryCode,
  rewrapDekForNewPassword,
  unlockVault
} from './vault-crypto'

// 测试用小参数（8MiB / 1 轮），保证单测在百毫秒级完成
const FAST_KDF = { memoryKib: 8192, time: 1, parallel: 1 }
const PASSWORD = 'Maple-Vault#2026!'
const RECOVERY = 'ABCD-EFGH-IJKL-MNOP'

describe('base64', () => {
  it('往返一致', () => {
    const bytes = randomBytes(64)
    expect(Array.from(fromBase64(toBase64(bytes)))).toEqual(Array.from(bytes))
  })
})

describe('KDF', () => {
  it('同一密码 + 同一 salt 派生结果稳定', async () => {
    const kdf = { salt: toBase64(randomBytes(16)), ...FAST_KDF }
    const a = await deriveMasterKey(PASSWORD, kdf)
    const b = await deriveMasterKey(PASSWORD, kdf)
    expect(a.length).toBe(64)
    expect(Array.from(a)).toEqual(Array.from(b))
  })

  it('不同 salt 得到不同密钥', async () => {
    const kdf1 = { salt: toBase64(randomBytes(16)), ...FAST_KDF }
    const kdf2 = { salt: toBase64(randomBytes(16)), ...FAST_KDF }
    const a = await deriveMasterKey(PASSWORD, kdf1)
    const b = await deriveMasterKey(PASSWORD, kdf2)
    expect(Array.from(a)).not.toEqual(Array.from(b))
  })

  it('空密码直接拒绝', async () => {
    await expect(deriveMasterKey('', { salt: toBase64(randomBytes(16)), ...FAST_KDF })).rejects.toThrow()
  })

  it('拆出两个不同的 32 字节子密钥', async () => {
    const master = await deriveMasterKey(PASSWORD, { salt: toBase64(randomBytes(16)), ...FAST_KDF })
    const { encKey, authKey } = await splitKeys(master)
    expect(encKey.length).toBe(32)
    expect(authKey.length).toBe(32)
    expect(Array.from(encKey)).not.toEqual(Array.from(authKey))
  })

  it('authHash 由 authKey 稳定生成', async () => {
    const authKey = randomBytes(32)
    expect(authHashFromAuthKey(authKey)).toBe(authHashFromAuthKey(authKey))
    expect(authHashFromAuthKey(authKey)).not.toBe(authHashFromAuthKey(randomBytes(32)))
  })
})

describe('AES-GCM', () => {
  it('加解密往返一致', async () => {
    const key = randomBytes(32)
    const plain = new TextEncoder().encode('hello 密码库 🎉')
    const { ciphertext, nonce } = await aesGcmEncrypt(key, plain)
    const decrypted = await aesGcmDecrypt(key, ciphertext, nonce)
    expect(new TextDecoder().decode(decrypted)).toBe('hello 密码库 🎉')
  })

  it('错误密钥解密失败', async () => {
    const { ciphertext, nonce } = await aesGcmEncrypt(randomBytes(32), new TextEncoder().encode('x'))
    await expect(aesGcmDecrypt(randomBytes(32), ciphertext, nonce)).rejects.toThrow()
  })

  it('密文被篡改时校验失败', async () => {
    const key = randomBytes(32)
    const { ciphertext, nonce } = await aesGcmEncrypt(key, new TextEncoder().encode('payload'))
    ciphertext[0] ^= 0xff
    await expect(aesGcmDecrypt(key, ciphertext, nonce)).rejects.toThrow()
  })
})

describe('DEK 包裹', () => {
  it('包裹后可解出同一个 DEK', async () => {
    const encKey = randomBytes(32)
    const dek = randomBytes(32)
    const { wrappedDek, dekNonce } = await wrapDek(encKey, dek)
    const restored = await unwrapDek(encKey, wrappedDek, dekNonce)
    expect(Array.from(restored)).toEqual(Array.from(dek))
  })

  it('错误的 encKey 无法解出 DEK', async () => {
    const { wrappedDek, dekNonce } = await wrapDek(randomBytes(32), randomBytes(32))
    await expect(unwrapDek(randomBytes(32), wrappedDek, dekNonce)).rejects.toThrow()
  })
})

describe('记录加解密', () => {
  it('对象往返一致（含中文与嵌套）', async () => {
    const dek = randomBytes(32)
    const payload = {
      title: '招商银行全币种国际卡',
      account: 'me@example.com',
      tags: ['银行卡', '外币'],
      meta: { expire: '2028-09-28', nested: { a: 1 } }
    }
    const { ciphertext, nonce } = await encryptRecord(dek, payload)
    expect(ciphertext).not.toContain('招商银行')
    expect(await decryptRecord(dek, ciphertext, nonce)).toEqual(payload)
  })
})

describe('注册 / 解锁 / 改密', () => {
  it('注册后可用同一主密码解锁出相同 DEK', async () => {
    const vault = await createVaultKeys(PASSWORD, { kdfOverrides: FAST_KDF })
    const unlocked = await unlockVault(PASSWORD, vault.kdf, vault.wrappedDek, vault.dekNonce)

    expect(Array.from(unlocked.dek)).toEqual(Array.from(vault.dek))
    expect(unlocked.authHash).toBe(vault.authHash)
  })

  it('错误主密码无法解锁', async () => {
    const vault = await createVaultKeys(PASSWORD, { kdfOverrides: FAST_KDF })
    await expect(
      unlockVault('wrong-password', vault.kdf, vault.wrappedDek, vault.dekNonce)
    ).rejects.toThrow()
  })

  it('改密后新密码可解出同一 DEK，旧密码失效', async () => {
    const vault = await createVaultKeys(PASSWORD, { kdfOverrides: FAST_KDF })
    const rewrapped = await rewrapDekForNewPassword('New-Password#2026', vault.dek)

    const unlocked = await unlockVault(
      'New-Password#2026',
      rewrapped.newKdf,
      rewrapped.wrappedDek,
      rewrapped.dekNonce
    )
    expect(Array.from(unlocked.dek)).toEqual(Array.from(vault.dek))

    await expect(
      unlockVault(PASSWORD, rewrapped.newKdf, rewrapped.wrappedDek, rewrapped.dekNonce)
    ).rejects.toThrow()
  })

  it('恢复码可解出 DEK，错误恢复码失败', async () => {
    const vault = await createVaultKeys(PASSWORD, {
      kdfOverrides: FAST_KDF,
      recoveryCode: RECOVERY
    })
    expect(vault.recoveryWrappedDek).toBeTruthy()

    const dek = await recoverDekWithRecoveryCode(
      RECOVERY,
      vault.recoveryWrappedDek,
      vault.recoveryDekNonce
    )
    expect(Array.from(dek)).toEqual(Array.from(vault.dek))

    await expect(
      recoverDekWithRecoveryCode('ZZZZ-ZZZZ-ZZZZ-ZZZZ', vault.recoveryWrappedDek, vault.recoveryDekNonce)
    ).rejects.toThrow()
  })

  it('备份包可用主密码解出并重新加密（导入路径）', async () => {
    const vault = await createVaultKeys(PASSWORD, { kdfOverrides: FAST_KDF })
    const record = await encryptRecord(vault.dek, { title: '备份条目', account: 'a@b.c' })

    const backup = {
      kdf: vault.kdf,
      wrappedDek: vault.wrappedDek,
      dekNonce: vault.dekNonce,
      items: [record]
    }

    // 导入：用备份的主密码解出 DEK
    const master = await deriveMasterKey(PASSWORD, backup.kdf)
    const { encKey } = await splitKeys(master)
    const backupDek = await unwrapDek(encKey, backup.wrappedDek, backup.dekNonce)

    const payload = await decryptRecord(backupDek, record.ciphertext, record.nonce)
    expect(payload.title).toBe('备份条目')

    // 用当前金库的 DEK 重新加密
    const newDek = generateDek()
    const reEncrypted = await encryptRecord(newDek, payload)
    expect(await decryptRecord(newDek, reEncrypted.ciphertext, reEncrypted.nonce)).toEqual(payload)

    // 密码错误则解不开
    const wrongMaster = await deriveMasterKey('wrong-password', backup.kdf)
    const wrongKeys = await splitKeys(wrongMaster)
    await expect(
      unwrapDek(wrongKeys.encKey, backup.wrappedDek, backup.dekNonce)
    ).rejects.toThrow()
  })
})

describe('recovery authentication separation', () => {
  it('derives a stable verifier distinct from the wrapping key and code', async () => {
    const auth = await deriveRecoveryAuthHash(RECOVERY)
    expect(auth).toBe(await deriveRecoveryAuthHash(RECOVERY.toLowerCase()))
    expect(fromBase64(auth).length).toBe(32)
    expect(auth).not.toBe(toBase64(await deriveRecoveryKey(RECOVERY)))
    expect(auth).not.toContain(RECOVERY)
    const vault = await createVaultKeys(PASSWORD, {kdfOverrides:FAST_KDF, recoveryCode:RECOVERY})
    expect(vault.recoveryAuthHash).toBe(auth)
  })
  it('rotates recovery wrapping without changing existing encrypted records', async () => {
    const vault = await createVaultKeys(PASSWORD, { kdfOverrides: FAST_KDF, recoveryCode: RECOVERY })
    const record = await encryptRecord(vault.dek, { password: 'synthetic-record-password' })
    const nextCode = 'QRST-UVWX-YZ23-4567'
    const next = await createRecoveryConfiguration(nextCode, vault.dek)
    const recovered = await recoverDekWithRecoveryCode(nextCode, next.recoveryWrappedDek, next.recoveryDekNonce)
    expect(await decryptRecord(recovered, record.ciphertext, record.nonce)).toEqual({ password: 'synthetic-record-password' })
    expect(next.recoveryAuthHash).not.toBe(vault.recoveryAuthHash)
    await expect(recoverDekWithRecoveryCode(RECOVERY, next.recoveryWrappedDek, next.recoveryDekNonce)).rejects.toThrow()
  })
})
