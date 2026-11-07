/** base64 与字节数组互转（WebCrypto / 接口传输统一用它）。 */

export function toBase64(bytes) {
  let binary = ''
  const chunk = 0x8000
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk))
  }
  return btoa(binary)
}

export function fromBase64(text) {
  const binary = atob(text)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  return bytes
}

export function concatBytes(...arrays) {
  const total = arrays.reduce((sum, arr) => sum + arr.length, 0)
  const out = new Uint8Array(total)
  let offset = 0
  for (const arr of arrays) {
    out.set(arr, offset)
    offset += arr.length
  }
  return out
}

export function randomBytes(length) {
  return crypto.getRandomValues(new Uint8Array(length))
}

export function utf8Encode(text) {
  return new TextEncoder().encode(text)
}

export function utf8Decode(bytes) {
  return new TextDecoder().decode(bytes)
}
