/** Limits apply before parsing or performing expensive cryptographic work. */
export const MAX_BACKUP_BYTES = 16 * 1024 * 1024
export const MAX_IMAGE_BYTES = 256 * 1024
export const IMAGE_TYPES = new Set(['image/png', 'image/jpeg', 'image/webp', 'image/gif'])

export function safeWebUrl(value) {
  const raw = typeof value === 'string' ? value.trim() : ''
  if (!raw || raw.startsWith('//') || /[\u0000-\u0020\u007f]/.test(raw)) return ''
  try {
    const url = new URL(/^[a-z][a-z0-9+.-]*:/i.test(raw) ? raw : `https://${raw}`)
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : ''
  } catch { return '' }
}

export function safeInlineImage(value) {
  if (typeof value !== 'string' || value.length > Math.ceil(MAX_IMAGE_BYTES / 3) * 4 + 64) return ''
  return /^data:image\/(?:png|jpeg|webp|gif);base64,[A-Za-z0-9+/]+={0,2}$/.test(value) ? value : ''
}

export function validateKdfParams(params) {
  if (!params || typeof params !== 'object' || Array.isArray(params)) throw new Error('KDF 参数无效')
  if (params.algo !== undefined && params.algo !== 'argon2id') throw new Error('不支持该 KDF 算法')
  for (const [key, min, max, fallback] of [['memoryKib', 8192, 1048576, 65536], ['time', 1, 10, 3], ['parallel', 1, 8, 1]]) {
    const value = params[key] ?? fallback
    if (!Number.isSafeInteger(value) || value < min || value > max) throw new Error(`KDF ${key} 超出支持范围`)
  }
  if (params.hashLength !== undefined && params.hashLength !== 64) throw new Error('KDF 输出长度无效')
  const salt = typeof params.salt === 'string' ? params.salt : ''
  if (!/^[A-Za-z0-9+/]+={0,2}$/.test(salt) || salt.length > 128) throw new Error('KDF salt 无效')
  let bytes
  try { bytes = atob(salt) } catch { throw new Error('KDF salt 无效') }
  if (bytes.length < 8 || bytes.length > 96) throw new Error('KDF salt 无效')
  return params
}

function base64Bytes(value, min, max) {
  if (typeof value !== 'string' || value.length > Math.ceil(max / 3) * 4 + 4 || !/^[A-Za-z0-9+/]*={0,2}$/.test(value)) throw new Error('备份密文格式无效')
  let decoded
  try { decoded = atob(value) } catch { throw new Error('备份密文格式无效') }
  if (decoded.length < min || decoded.length > max) throw new Error('备份密文长度无效')
}

export function validateBackup(data) {
  if (!data || data.format !== 'bypw-backup' || data.version !== 1) throw new Error('不是支持的密码库备份格式')
  validateKdfParams(data.kdf)
  base64Bytes(data.wrappedDek, 48, 48)
  base64Bytes(data.dekNonce, 12, 12)
  for (const key of ['folders', 'items']) {
    if (!Array.isArray(data[key]) || data[key].length > 5000) throw new Error('单次导入每类最多 5000 条记录')
    const ids = new Set()
    for (const row of data[key]) {
      if (!row || typeof row.id !== 'string' || row.id.length < 8 || row.id.length > 36 || ids.has(row.id)) throw new Error('备份记录 ID 无效或重复')
      ids.add(row.id)
      base64Bytes(row.ciphertext, 16, 750000)
      base64Bytes(row.nonce, 12, 12)
      if (key === 'folders' && row.sortOrder !== undefined && !Number.isSafeInteger(row.sortOrder)) throw new Error('文件夹排序无效')
    }
  }
  return data
}
