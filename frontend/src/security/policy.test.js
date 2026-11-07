import { describe, it, expect } from 'vitest'
import { safeWebUrl, safeInlineImage, validateKdfParams, validateBackup } from './policy'
const b64 = n => btoa('a'.repeat(n))
const kdf = () => ({ algo: 'argon2id', salt: b64(16), memoryKib: 8192, time: 1, parallel: 1 })
describe('untrusted URLs and files', () => {
  it('opens only http(s) URLs without credentials or control characters', () => {
    expect(safeWebUrl('example.com/path')).toBe('https://example.com/path')
    expect(safeWebUrl('https://example.com')).toBe('https://example.com/')
    for (const input of ['javascript:alert(1)', 'data:text/html,test', 'file:///etc/passwd', '//example.com', 'https://user:pass@example.com', 'java\nscript:alert(1)']) expect(safeWebUrl(input)).toBe('')
  })
  it('accepts bounded raster data images and blocks SVG / remote images', () => {
    expect(safeInlineImage('data:image/png;base64,YQ==')).toBe('data:image/png;base64,YQ==')
    expect(safeInlineImage('https://third-party.invalid/icon.png')).toBe('')
    expect(safeInlineImage('data:image/svg+xml;base64,YQ==')).toBe('')
    expect(safeInlineImage('data:image/png;base64,' + 'A'.repeat(400000))).toBe('')
  })
  it('rejects hostile KDF values before allocating WASM memory', () => {
    expect(validateKdfParams(kdf())).toBeTruthy()
    for (const patch of [{memoryKib: 1e12}, {time: 10000000}, {parallel: -1}, {hashLength: 1e6}, {algo:'pbkdf2'}, {salt:'not base64'}]) expect(() => validateKdfParams({...kdf(), ...patch})).toThrow()
  })
  it('validates backup structure, duplicates and cryptographic lengths before import', () => {
    const backup = { format: 'bypw-backup', version: 1, kdf: kdf(), wrappedDek: b64(48), dekNonce: b64(12), folders: [], items: [{id:'synthetic-id', ciphertext:b64(32), nonce:b64(12)}] }
    expect(validateBackup(backup)).toBe(backup)
    expect(() => validateBackup({...backup, items:[...backup.items, ...backup.items]})).toThrow()
    expect(() => validateBackup({...backup, wrappedDek:b64(32)})).toThrow()
    expect(() => validateBackup({...backup, items:new Array(5001).fill(backup.items[0])})).toThrow()
  })
})
