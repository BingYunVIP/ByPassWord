import { describe, it, expect } from 'vitest'
import { decodeBase32, totp } from './totp'
// RFC 6238 Appendix B: SHA-1 key is ASCII "12345678901234567890".
const secret = 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'
describe('RFC 6238 TOTP', () => {
  it('matches every official SHA-1 8-digit vector', async () => {
    for (const [seconds, expected] of [[59,'94287082'],[1111111109,'07081804'],[1111111111,'14050471'],[1234567890,'89005924'],[2000000000,'69279037'],[20000000000,'65353130']]) {
      expect(await totp(secret, seconds * 1000, 8)).toBe(expected)
    }
  })
  it('uses the standard 6-digit truncation and exact 30-second boundary', async () => {
    expect(await totp(secret, 59000)).toBe('287082')
    expect(await totp(secret, 29999)).toBe(await totp(secret, 0))
    expect(await totp(secret, 30000)).not.toBe(await totp(secret, 29999))
    expect(await totp(secret.toLowerCase().replace(/(.{4})/g, '$1 '), 59000)).toBe('287082')
  })
  it('rejects malformed / too short Base32 and invalid times', async () => {
    for (const invalid of ['', 'not-a-secret!', 'JBSWY3DP0HPK3PXP', 'AAA', 'JBSWY3DPEHPK3PXQ=']) expect(() => decodeBase32(invalid)).toThrow()
    await expect(totp(secret, -1)).rejects.toThrow()
  })
})
