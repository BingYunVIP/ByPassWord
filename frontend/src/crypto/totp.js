/** RFC 6238, 30-second TOTP with HMAC-SHA-1. No secret leaves WebCrypto. */
const ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
export function decodeBase32(secret) {
  const raw = String(secret ?? '').replace(/\s/g, '').toUpperCase()
  if (!/^[A-Z2-7]+={0,6}$/.test(raw) || raw.length > 160) throw new Error('动态码密钥必须是有效的 Base32')
  const text = raw.replace(/=+$/, '')
  if ([1, 3, 6].includes(text.length % 8)) throw new Error('动态码密钥长度无效')
  let bits = 0, buffer = 0
  const bytes = []
  for (const ch of text) {
    buffer = (buffer << 5) | ALPHABET.indexOf(ch)
    bits += 5
    if (bits >= 8) { bits -= 8; bytes.push((buffer >>> bits) & 255); buffer &= (1 << bits) - 1 }
  }
  if (buffer !== 0 || bytes.length < 10) throw new Error('动态码密钥无效或过短')
  if (raw.includes('=') && raw.length % 8 !== 0) throw new Error('动态码密钥补位无效')
  return new Uint8Array(bytes)
}
export async function totp(secret, timestampMs = Date.now(), digits = 6) {
  if (!Number.isSafeInteger(timestampMs) || timestampMs < 0 || ![6, 8].includes(digits)) throw new Error('动态码时间或位数无效')
  const bytes = decodeBase32(secret), message = new Uint8Array(8)
  let counter = BigInt(Math.floor(timestampMs / 30000))
  for (let i = 7; i >= 0; i--) { message[i] = Number(counter & 255n); counter >>= 8n }
  try {
    const key = await crypto.subtle.importKey('raw', bytes, { name: 'HMAC', hash: 'SHA-1' }, false, ['sign'])
    const mac = new Uint8Array(await crypto.subtle.sign('HMAC', key, message))
    const offset = mac[mac.length - 1] & 15
    const number = ((mac[offset] & 127) << 24) | (mac[offset + 1] << 16) | (mac[offset + 2] << 8) | mac[offset + 3]
    return String(number % (10 ** digits)).padStart(digits, '0')
  } finally { bytes.fill(0) }
}
