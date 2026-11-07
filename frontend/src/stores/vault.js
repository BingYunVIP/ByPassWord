/**
 * 金库状态（单例）：UI 状态 + 加解密后的数据 + 与服务端同步。
 *
 * 数据流：登录解锁拿到 DEK → GET /api/vault → 逐条解密进内存 → UI 直接读明文；
 * 任何写操作都先加密再调接口，成功后回写 rev，冲突（409）则整体重新拉取。
 */

import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { computed, reactive, ref, watch } from 'vue'

import * as vaultApi from '../api/vault'
import { totp } from '../crypto/totp'
import { decryptRecord, encryptRecord } from '../crypto/vault-crypto'
import {
  bankCatalog,
  createEmptyItemForm,
  defaultFolders,
  googleFolderIconPreset,
  initialAuditLogs,
  initialSecurityConfig,
  itemTypeOptions,
  osCatalog,
  settingsTabs,
  siteIconMap,
  typeFilterOptions
} from '../data/catalog'
import { useAuth, onSensitiveClear } from './auth'
import { safeWebUrl, safeInlineImage, MAX_IMAGE_BYTES, IMAGE_TYPES } from '../security/policy'

const auth = useAuth()

// ============================================================
// 一、UI 状态
// ============================================================
const unlockInput = ref('')
const windowBlurred = ref(false)
const searchQuery = ref('')
const selectedFolderId = ref('ALL')
const selectedTypeFilter = ref('ALL')
const showPassword = ref(false)
const showCardCvv = ref(false)
const activeModal = ref(null)
const showGeneratorModal = ref(false)
const generatorForForm = ref(false)
const openDropdownName = ref(null)
const activeSettingsTab = ref('account')
const toastMessage = ref('')
const faviconErrorMap = reactive({})

// ============================================================
// 二、数据状态
// ============================================================
const folders = ref([])
const items = ref([])
const selectedItemId = ref(null)
const totpRemaining = ref(30)
const totpTick = ref(1)
const vaultRev = ref(0)
const vaultLoaded = ref(false)

const cipherIndex = reactive({ folders: {}, items: {} })

const createSecurityConfig = (payload = {}) => {
  const saved = payload && typeof payload === 'object' && !Array.isArray(payload) ? payload : {}
  return { ...initialSecurityConfig, ...saved }
}
const securityConfig = reactive(createSecurityConfig())
const auditLogs = ref([...initialAuditLogs])

const isLocked = computed(() => auth.status.value === 'locked')
const lockReason = auth.lockReason

// ============================================================
// 三、工具
// ============================================================
const updateViewportScale = () => {
  const w = window.innerWidth
  const calculated = Math.max(13.5, Math.min(22, (w / 2048) * 18))
  document.documentElement.style.fontSize = `${calculated}px`
}

/** Markdown 渲染：先解析再净化，防止服务端数据里的脚本在本页执行（XSS）。 */
const renderMarkdown = (raw) => {
  if (!raw) return ''
  try {
    const html = marked.parse(String(raw))
    return DOMPurify.sanitize(html, { USE_PROFILES: { html: true } })
  } catch (e) {
    return DOMPurify.sanitize(String(raw).replace(/\n/g, '<br/>'))
  }
}

const getOsMeta = (osName) => osCatalog.find((o) => o.name === osName) || osCatalog[0]
const getBankMeta = (typeName) => bankCatalog.find((b) => b.name === typeName) || bankCatalog[0]

// Site metadata never leaves this page for favicon lookup.
const getFaviconUrl = (urlStr) => {
  const url = safeWebUrl(urlStr)
  return url ? siteIconMap[new URL(url).hostname] || '' : ''
}
const currentOperation = () => {
  const epoch = auth.sessionEpoch.value, key = auth.dek.value
  return { key, active: () => Boolean(key) && auth.status.value === 'unlocked' && auth.sessionEpoch.value === epoch && auth.dek.value === key }
}

const getItemFallbackIconName = (item) => {
  if (item.type === 'vps') return 'dns'
  if (item.type === 'bank') return 'credit_card'
  if (item.type === 'note') return 'encrypted'
  return 'language'
}

const getItemFallbackIconColor = (item, isSelected) => {
  if (isSelected) return 'text-accent'
  if (item.type === 'vps') return 'text-purple-500'
  if (item.type === 'bank') return 'text-rose-500'
  if (item.type === 'note') return 'text-amber-500'
  return 'text-accent'
}

const maskCardNumber = (num) => {
  if (!num) return '•••• •••• •••• ••••'
  const clean = String(num).replace(/\s+/g, '')
  return `•••• •••• •••• ${clean.slice(-4)}`
}

const formatCardNumber = (num) => {
  if (!num) return ''
  return String(num)
    .replace(/\s+/g, '')
    .replace(/(\d{4})(?=\d)/g, '$1 ')
}

const getFolderById = (id) => {
  return (
    folders.value.find((f) => f.id === id) ||
    folders.value[0] || { name: '未分类', gIcon: 'folder', color: 'text-accent' }
  )
}

const formatIdleTime = (sec) => {
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

const appendAuditLog = (action) => {
  const t = new Date().toTimeString().split(' ')[0]
  auditLogs.value.unshift({ id: crypto.randomUUID(), time: t, action, ip: '127.0.0.1' })
}

let toastTimer = null
const showToast = (msg) => {
  toastMessage.value = msg
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => {
    if (toastMessage.value === msg) toastMessage.value = ''
  }, 2300)
}

let clipboardTimer = null
const copyText = (text, label = '内容') => {
  if (!text) return
  const el = document.createElement('textarea')
  el.value = text
  el.style.position = 'fixed'
  el.style.opacity = '0'
  document.body.appendChild(el)
  el.select()
  try {
    document.execCommand('copy')
    appendAuditLog(`复制 ${label}`)
    showToast(`${label} 已复制`)
  } catch (e) {
    showToast('复制失败')
  }
  document.body.removeChild(el)

  const seconds = Number(securityConfig.clipboardClearSeconds) || 0
  if (seconds > 0) {
    if (clipboardTimer) clearTimeout(clipboardTimer)
    clipboardTimer = setTimeout(async () => {
      try {
        if (navigator.clipboard?.writeText) await navigator.clipboard.writeText('')
        showToast('剪贴板已自动清空')
      } catch {
        /* 浏览器拒绝时静默忽略 */
      }
    }, seconds * 1000)
  }
}

// ============================================================
// 四、计算属性
// ============================================================
const shortCipherName = computed(() =>
  securityConfig.cipher.startsWith('AES-256') ? 'AES-256' : 'ChaCha20'
)

/** 收藏夹是「虚拟视图」：靠 isFavorites 标记识别，而不是固定 id（id 是全局主键）。 */
const favoritesFolderId = computed(() => folders.value.find((f) => f.isFavorites)?.id || null)
const normalizedSearchQuery = computed(() => searchQuery.value.trim().toLowerCase())

const filteredItems = computed(() => {
  const q = normalizedSearchQuery.value
  return items.value.filter((item) => {
    if (favoritesFolderId.value && selectedFolderId.value === favoritesFolderId.value) {
      if (!item.favorite) return false
    } else if (selectedFolderId.value !== 'ALL') {
      if (item.folderId !== selectedFolderId.value) return false
    }
    if (selectedTypeFilter.value !== 'ALL' && item.type !== selectedTypeFilter.value) return false
    if (q) {
      return (
        (item.title && item.title.toLowerCase().includes(q)) ||
        (item.account && item.account.toLowerCase().includes(q)) ||
        (item.ipAddress && item.ipAddress.toLowerCase().includes(q)) ||
        (item.cardNumber && item.cardNumber.toLowerCase().includes(q)) ||
        (item.url && item.url.toLowerCase().includes(q)) ||
        (item.markdownContent && item.markdownContent.toLowerCase().includes(q))
      )
    }
    return true
  })
})

const selectedItem = computed(
  () => items.value.find((i) => i.id === selectedItemId.value) || filteredItems.value[0] || null
)

const currentFolderName = computed(() => {
  if (selectedFolderId.value === 'ALL') return '所有密码条目'
  const f = folders.value.find((x) => x.id === selectedFolderId.value)
  return f ? f.name : '密码列表'
})

const securityHealthScore = computed(() => {
  if (!items.value.length) return 100
  const strong = items.value.filter(
    (i) => i.type === 'note' || (i.password && i.password.length >= 8)
  ).length
  return Math.round((strong / items.value.length) * 100)
})

const currentTotpCode = ref('------')
watch([() => selectedItem.value?.totpSecret, totpTick, auth.status, auth.sessionEpoch], async ([secret], _, onCleanup) => {
  let cancelled = false
  onCleanup(() => { cancelled = true })
  currentTotpCode.value = '------'
  if (!secret || !auth.isUnlocked.value) return
  const epoch = auth.sessionEpoch.value
  try {
    const value = await totp(secret)
    if (!cancelled && auth.isUnlocked.value && epoch === auth.sessionEpoch.value) currentTotpCode.value = value
  } catch { /* An invalid stored secret must never display a fabricated code. */ }
}, { flush: 'sync' })

const folderCounts = computed(() => {
  const counts = new Map()
  let favorites = 0
  for (const item of items.value) {
    counts.set(item.folderId, (counts.get(item.folderId) || 0) + 1)
    if (item.favorite) favorites++
  }
  return { counts, favorites }
})

const getFolderCount = (folderId) => {
  if (favoritesFolderId.value && folderId === favoritesFolderId.value) return folderCounts.value.favorites
  return folderCounts.value.counts.get(folderId) || 0
}

// ============================================================
// 五、与服务端同步
// ============================================================
const handleSyncError = async (error, fallback) => {
  if (error?.code === 'rev_conflict') {
    showToast('数据已在别处更新，正在重新同步…')
    await loadVault()
    return
  }
  showToast(error?.message || fallback || '操作失败')
}

const folderPayload = (folder) => ({
  name: folder.name,
  gIcon: folder.gIcon,
  color: folder.color,
  desc: folder.desc || '',
  customImage: folder.customImage || '',
  iconType: folder.iconType || '',
  isFavorites: Boolean(folder.isFavorites)
})

const itemPayload = (item) => {
  const { id, rev, sortOrder, ...rest } = item
  return rest
}

/** 首次进入空金库时，自动创建 8 个默认文件夹（否则左栏是空的）。 */
async function ensureDefaultFolders() {
  const op = currentOperation()
  if (!op.active() || folders.value.length) return
  const seeded = []
  for (let i = 0; i < defaultFolders.length; i++) {
    if (!op.active()) return
    const preset = defaultFolders[i], id = crypto.randomUUID()
    const payload = { name: preset.name, gIcon: preset.gIcon, color: preset.color, desc: preset.desc || '', customImage: '', iconType: preset.iconType || '', isFavorites: Boolean(preset.isFavorites) }
    try {
      const enc = await encryptRecord(op.key, payload)
      if (!op.active()) return
      const res = await vaultApi.createFolder({ id, ...enc, sortOrder: i })
      if (!op.active()) return
      cipherIndex.folders[id] = enc
      seeded.push({ ...payload, id, sortOrder: i, rev: res.rev })
    } catch { if (op.active()) showToast('默认文件夹创建失败，请重试') }
  }
  if (op.active()) folders.value = seeded
}

/** Build a private result, then publish only if the session is still unlocked. */
async function performLoadVault() {
  const op = currentOperation()
  if (!op.active()) return
  const data = await vaultApi.getVault()
  if (!op.active()) return
  const nextFolders = [], nextItems = [], nextIndex = { folders: {}, items: {} }
  for (const [kind, rows, destination] of [['folders', data.folders, nextFolders], ['items', data.items, nextItems]]) {
    for (const row of rows) {
      if (!op.active()) return
      try {
        const payload = await decryptRecord(op.key, row.ciphertext, row.nonce)
        if (!op.active()) return
        nextIndex[kind][row.id] = { ciphertext: row.ciphertext, nonce: row.nonce }
        destination.push({ ...payload, ...(kind === 'folders' ? { customImage: safeInlineImage(payload.customImage), sortOrder: row.sortOrder } : {}), id: row.id, rev: row.rev })
      } catch { if (op.active()) showToast('有记录无法解密，请检查备份或重新同步') }
    }
  }
  if (!op.active()) return
  folders.value = nextFolders.sort((a, b) => a.sortOrder - b.sortOrder)
  items.value = nextItems
  cipherIndex.folders = nextIndex.folders; cipherIndex.items = nextIndex.items
  vaultRev.value = data.rev; vaultLoaded.value = true
  if (!selectedItemId.value && nextItems.length) selectedItemId.value = nextItems[0].id
  await ensureDefaultFolders()
  if (op.active()) await loadSettings()
}

let loadingVault = null, loadingEpoch = -1
function loadVault() {
  const epoch = auth.sessionEpoch.value
  if (loadingVault && loadingEpoch === epoch) return loadingVault
  loadingEpoch = epoch
  const work = performLoadVault()
  loadingVault = work
  work.finally(() => { if (loadingVault === work) loadingVault = null }).catch(() => {})
  return work
}

function clearVault() {
  activeModal.value = null; showGeneratorModal.value = false; generatorForForm.value = false
  currentTotpCode.value = '------'
  showPassword.value = false; showCardCvv.value = false; openDropdownName.value = null
  generatedPassword.value = ''; editingForm.value = createEmptyItemForm()
  folderForm.value = { id: null, name: '', gIcon: 'folder', color: 'text-accent', customImage: '' }
  passwordChangeForm.current = ''; passwordChangeForm.newPass = ''
  unlockInput.value = ''; unlockStep.value = 'password'; unlockTotpCode.value = ''
  searchQuery.value = ''; auditLogs.value = []
  Object.assign(securityConfig, createSecurityConfig())
  if (clipboardTimer) {
    clearTimeout(clipboardTimer); clipboardTimer = null
    navigator.clipboard?.writeText('')?.catch(() => {})
  }
  folders.value = []
  items.value = []
  selectedItemId.value = null
  vaultLoaded.value = false
  vaultRev.value = 0
  Object.keys(cipherIndex.folders).forEach((k) => delete cipherIndex.folders[k])
  Object.keys(cipherIndex.items).forEach((k) => delete cipherIndex.items[k])
}

async function loadSettings() {
  const op = currentOperation()
  if (!op.active()) return
  try {
    const row = await vaultApi.getSettings()
    if (!op.active() || !row?.ciphertext) return
    const payload = await decryptRecord(op.key, row.ciphertext, row.nonce)
    if (op.active()) Object.assign(securityConfig, createSecurityConfig(payload))
  } catch { if (op.active()) showToast('设置读取失败') }
}
async function persistSettings() {
  const op = currentOperation()
  if (!op.active()) return
  try {
    const enc = await encryptRecord(op.key, { ...securityConfig })
    if (op.active()) await vaultApi.putSettings(enc.ciphertext, enc.nonce)
  } catch { if (op.active()) showToast('设置保存失败') }
}

// ============================================================
// 六、空闲计时 / 锁定
// ============================================================
const idleRemainingSeconds = ref(securityConfig.idleTimeoutMinutes * 60)
const resetIdleTimer = () => {
  idleRemainingSeconds.value = securityConfig.idleTimeoutMinutes * 60
}

const lockVault = (reason = '手动锁定') => {
  auth.lock(reason)
  clearVault()
  showPassword.value = false
  unlockStep.value = 'password'
  unlockTotpCode.value = ''
  appendAuditLog(`密码库已锁定 (${reason})`)
}

const unlockStep = ref('password') // password | 2fa
const unlockTotpCode = ref('')
const unlockBusy = ref(false)

async function finishUnlock() {
  unlockStep.value = 'password'
  unlockTotpCode.value = ''
  resetIdleTimer()
  await loadVault()
  if (!auth.isUnlocked.value) return
  appendAuditLog('密码库成功解锁')
  showToast('密码库已解锁')
}

const handleUnlockVault = async () => {
  if (unlockBusy.value) return
  unlockBusy.value = true
  try {
    const res = await auth.unlock(unlockInput.value)
    unlockInput.value = ''
    if (res?.requires2fa) {
      unlockStep.value = '2fa'
      return
    }
    await finishUnlock()
  } catch (e) {
    showToast('主密码错误')
  } finally {
    unlockBusy.value = false
  }
}

const handleUnlockTotp = async () => {
  if (unlockBusy.value) return
  unlockBusy.value = true
  try {
    await auth.confirmUnlockTotp(unlockTotpCode.value.trim())
    await finishUnlock()
  } catch (e) {
    showToast(e.message || '验证码错误')
  } finally {
    unlockBusy.value = false
  }
}

const backToPasswordStep = () => {
  auth.lock(auth.lockReason.value)
  unlockStep.value = 'password'
  unlockTotpCode.value = ''
}

let clockTimer = null
const tickClock = () => {
  const s = new Date().getSeconds()
  totpRemaining.value = 30 - (s % 30)
  totpTick.value = Math.floor(Date.now() / 30000)
  if (auth.isUnlocked.value) {
    if (idleRemainingSeconds.value > 0) idleRemainingSeconds.value--
    else lockVault(`超过 ${securityConfig.idleTimeoutMinutes} 分钟未操作自动锁定`)
  }
}

const initVault = () => {
  updateViewportScale()
  window.addEventListener('resize', updateViewportScale)
  ;['mousemove', 'keydown', 'mousedown', 'touchstart'].forEach((ev) =>
    window.addEventListener(ev, resetIdleTimer)
  )
  tickClock()
  clockTimer = setInterval(tickClock, 1000)
}

const disposeVault = () => {
  window.removeEventListener('resize', updateViewportScale)
  ;['mousemove', 'keydown', 'mousedown', 'touchstart'].forEach((ev) =>
    window.removeEventListener(ev, resetIdleTimer)
  )
  if (clockTimer) clearInterval(clockTimer)
  clockTimer = null
}

// ============================================================
// 七、条目交互
// ============================================================
const selectItem = (id) => {
  selectedItemId.value = id
  showPassword.value = false
  showCardCvv.value = false
}

const toggleSecretReveal = () => {
  showPassword.value = !showPassword.value
  if (showPassword.value && selectedItem.value) {
    appendAuditLog(`查看密码明文: [${selectedItem.value.title}]`)
  }
}

async function toggleFavorite(item) {
  const op = currentOperation()
  if (!op.active()) return
  const next = !item.favorite
  try {
    const enc = await encryptRecord(auth.dek.value, itemPayload({ ...item, favorite: next }))
      if (!op.active()) return
    const res = await vaultApi.patchItem(item.id, { ...enc, rev: item.rev })
      if (!op.active()) return
    item.favorite = next
    item.rev = res.rev
    cipherIndex.items[item.id] = { ciphertext: enc.ciphertext, nonce: enc.nonce }
    showToast(next ? '已添加到收藏夹' : '已取消收藏')
  } catch (e) {
    await handleSyncError(e, '收藏失败')
  }
}

async function deleteItem(id) {
  const op = currentOperation()
  if (!op.active()) return
  const item = items.value.find((i) => i.id === id)
  if (!item) return
  try {
    await vaultApi.deleteItem(id, item.rev)
      if (!op.active()) return
    items.value = items.value.filter((i) => i.id !== id)
    delete cipherIndex.items[id]
    if (filteredItems.value.length > 0) selectedItemId.value = filteredItems.value[0].id
    showToast('条目已删除')
  } catch (e) {
    await handleSyncError(e, '删除失败')
  }
}

const toggleDropdown = (name) => {
  openDropdownName.value = openDropdownName.value === name ? null : name
}
const closeAllDropdowns = () => {
  openDropdownName.value = null
}

// ============================================================
// 八、新建 / 编辑条目
// ============================================================
const editingForm = ref(createEmptyItemForm())

const openCreateModal = () => {
  // 按「当前文件夹名」推断默认条目类型（文件夹 id 是 UUID，不能写死）
  const TYPE_BY_FOLDER_NAME = { VPS: 'vps', 银行卡: 'bank', 安全笔记: 'note' }
  const currentFolder = folders.value.find((f) => f.id === selectedFolderId.value)
  const defaultType = TYPE_BY_FOLDER_NAME[currentFolder?.name] || 'website'

  generateNewPassword()
  editingForm.value = {
    ...createEmptyItemForm(),
    type: defaultType,
    folderId:
      selectedFolderId.value === 'ALL' ||
      (favoritesFolderId.value && selectedFolderId.value === favoritesFolderId.value)
        ? folders.value.find((f) => !f.isFavorites)?.id || ''
        : selectedFolderId.value,
    password: generatedPassword.value
  }
  activeModal.value = 'editItem'
}

const openEditModal = (item) => {
  editingForm.value = { ...item }
  activeModal.value = 'editItem'
}

async function saveItem() {
  const op = currentOperation()
  if (!op.active()) return
  const form = { ...editingForm.value }
  if (!form.title?.trim()) {
    showToast('请填写条目名称')
    return
  }

  try {
    if (form.id) {
      const payload = itemPayload(form)
      const enc = await encryptRecord(auth.dek.value, payload)
      if (!op.active()) return
      const res = await vaultApi.patchItem(form.id, { ...enc, rev: form.rev })
      if (!op.active()) return
      const idx = items.value.findIndex((i) => i.id === form.id)
      if (idx !== -1) items.value[idx] = { ...payload, id: form.id, rev: res.rev }
      cipherIndex.items[form.id] = { ciphertext: enc.ciphertext, nonce: enc.nonce }
      appendAuditLog(`修改条目: [${form.title}]`)
      showToast('条目修改已保存')
    } else {
      const newId = crypto.randomUUID()
      const payload = {
        ...itemPayload(form),
        favorite:
          favoritesFolderId.value && selectedFolderId.value === favoritesFolderId.value
            ? true
            : Boolean(form.favorite)
      }
      const enc = await encryptRecord(auth.dek.value, payload)
      if (!op.active()) return
      const res = await vaultApi.createItem({ id: newId, ...enc })
      if (!op.active()) return
      items.value.unshift({ ...payload, id: newId, rev: res.rev })
      cipherIndex.items[newId] = { ciphertext: enc.ciphertext, nonce: enc.nonce }
      selectedItemId.value = newId
      appendAuditLog(`新建条目: [${form.title}]`)
      showToast('新条目已保存')
    }
    activeModal.value = null
  } catch (e) {
    await handleSyncError(e, '保存失败')
  }
}

// ============================================================
// 九、密码生成器（CSPRNG）
// ============================================================
const genLength = ref(20)
const genOptions = ref({ upper: true, lower: true, numbers: true, symbols: true })
const generatedPassword = ref('')

/** crypto.getRandomValues + 拒绝采样，避免取模偏差。 */
function randomInt(max) {
  if (max <= 0) return 0
  const limit = Math.floor(0xffffffff / max) * max
  const buffer = new Uint32Array(1)
  let value
  do {
    crypto.getRandomValues(buffer)
    value = buffer[0]
  } while (value >= limit)
  return value % max
}

const generateNewPassword = () => {
  let chars = ''
  if (genOptions.value.upper) chars += 'ABCDEFGHJKLMNPQRSTUVWXYZ'
  if (genOptions.value.lower) chars += 'abcdefghijkmnopqrstuvwxyz'
  if (genOptions.value.numbers) chars += '0123456789'
  if (genOptions.value.symbols) chars += '!@#$%^&*_+-='
  if (!chars) chars = 'abcdefghijkmnopqrstuvwxyz0123456789'

  let res = ''
  for (let i = 0; i < genLength.value; i++) res += chars.charAt(randomInt(chars.length))
  generatedPassword.value = res
}
generateNewPassword()

const openGeneratorModal = (fromForm = false) => {
  generatorForForm.value = fromForm
  generateNewPassword()
  showGeneratorModal.value = true
}

const applyGeneratedPasswordToForm = () => {
  editingForm.value.password = generatedPassword.value
  copyText(generatedPassword.value, '生成的强密码')
  showGeneratorModal.value = false
}

// ============================================================
// 十、文件夹管理
// ============================================================
const folderForm = ref({
  id: null,
  name: '',
  gIcon: 'folder',
  color: 'text-accent',
  customImage: ''
})

const openFolderModal = () => {
  folderForm.value = { id: null, name: '', gIcon: 'folder', color: 'text-accent', customImage: '' }
  activeModal.value = 'folderModal'
}

const openRenameFolderModal = (folder) => {
  folderForm.value = {
    id: folder.id,
    name: folder.name,
    gIcon: folder.gIcon || 'folder',
    color: folder.color || 'text-accent',
    customImage: folder.customImage || ''
  }
  activeModal.value = 'folderModal'
}

const handleFolderImageUpload = (e) => {
  const file = e.target.files?.[0], op = currentOperation()
  if (!file || !op.active()) return
  if (!IMAGE_TYPES.has(file.type) || file.size > MAX_IMAGE_BYTES) {
    e.target.value = ''; showToast('图片限 PNG、JPEG、WebP、GIF，最大 256 KB'); return
  }
  const reader = new FileReader()
  reader.onload = () => {
    if (!op.active()) return
    const image = safeInlineImage(reader.result)
    if (!image) { showToast('图片格式无效'); return }
    folderForm.value.customImage = image
    showToast('文件夹图片图标已载入')
  }
  reader.onerror = () => { if (op.active()) showToast('图片读取失败') }
  reader.readAsDataURL(file)
}

async function saveFolder() {
  const op = currentOperation()
  if (!op.active()) return
  const form = { ...folderForm.value, customImage: safeInlineImage(folderForm.value.customImage) }
  if (!form.name.trim()) return

  try {
    if (form.id) {
      const target = folders.value.find((f) => f.id === form.id)
      if (!target) return
      const payload = folderPayload({ ...target, ...form })
      const enc = await encryptRecord(auth.dek.value, payload)
      if (!op.active()) return
      const res = await vaultApi.patchFolder(form.id, {
        ...enc,
        sortOrder: target.sortOrder,
        rev: target.rev
      })
      if (!op.active()) return
      Object.assign(target, payload, { rev: res.rev })
      cipherIndex.folders[form.id] = { ciphertext: enc.ciphertext, nonce: enc.nonce }
      showToast('文件夹已更新')
    } else {
      const id = crypto.randomUUID()
      const payload = folderPayload(form)
      const enc = await encryptRecord(auth.dek.value, payload)
      if (!op.active()) return
      const res = await vaultApi.createFolder({ id, ...enc, sortOrder: folders.value.length })
      if (!op.active()) return
      folders.value.push({ ...payload, id, sortOrder: folders.value.length, rev: res.rev })
      cipherIndex.folders[id] = { ciphertext: enc.ciphertext, nonce: enc.nonce }
      showToast('已新建文件夹')
    }
    activeModal.value = null
  } catch (e) {
    await handleSyncError(e, '文件夹保存失败')
  }
}

async function moveFolder(index, direction) {
  const op = currentOperation()
  if (!op.active()) return
  const targetIdx = index + direction
  if (targetIdx < 0 || targetIdx >= folders.value.length) return

  const list = [...folders.value]
  const temp = list[index]
  list[index] = list[targetIdx]
  list[targetIdx] = temp

  try {
    for (let i = 0; i < list.length; i++) {
      const folder = list[i]
      if (folder.sortOrder === i) continue
      const enc = await encryptRecord(op.key, folderPayload(folder))
      if (!op.active()) return
      const res = await vaultApi.patchFolder(folder.id, { ...enc, sortOrder: i, rev: folder.rev })
      if (!op.active()) return
      folder.sortOrder = i
      folder.rev = res.rev
    }
    folders.value = list
  } catch (e) {
    await handleSyncError(e, '排序失败')
  }
}

async function deleteFolder(folderId) {
  const op = currentOperation()
  if (!op.active()) return
  if (folders.value.length <= 1) return
  const target = folders.value.find((f) => f.id === folderId)
  if (!target) return

  try {
    await vaultApi.deleteFolder(folderId, target.rev)
      if (!op.active()) return
    folders.value = folders.value.filter((f) => f.id !== folderId)
    delete cipherIndex.folders[folderId]
    if (selectedFolderId.value === folderId) selectedFolderId.value = 'ALL'
    showToast('文件夹已删除')
  } catch (e) {
    await handleSyncError(e, '删除文件夹失败')
  }
}

// ============================================================
// 十一、设置中心
// ============================================================
const passwordChangeForm = reactive({ current: '', newPass: '' })

const openSettings = (tab = 'account') => {
  activeSettingsTab.value = tab
  activeModal.value = 'settings'
}

const saveSecurityConfig = (desc) => {
  appendAuditLog(desc)
  showToast(desc)
  persistSettings()
}

async function updateMasterPassword() {
  if (!passwordChangeForm.newPass || passwordChangeForm.newPass.length < 12) {
    showToast('新主密码长度需至少 12 位')
    return
  }
  try {
    await auth.changeMasterPassword(passwordChangeForm.current, passwordChangeForm.newPass)
    passwordChangeForm.current = ''
    passwordChangeForm.newPass = ''
    appendAuditLog('更新了管理员登录主密码')
    showToast('主密码已更新，请重新登录')
    activeModal.value = null
  } catch (e) {
    showToast(e.message || '修改失败')
  }
}

const createManualSnapshot = () => {
  appendAuditLog('创建手动加密备份快照')
  showToast('加密备份快照已创建')
}

/** 导出：只导出密文 + 包裹后的 DEK，文件里没有任何明文。 */
function exportVaultBackup() {
  const pending = auth.pending.value
  if (!auth.isUnlocked.value || !pending?.wrappedDek) {
    showToast('请先解锁后再导出')
    return
  }

  const backup = {
    format: 'bypw-backup',
    version: 1,
    createdAt: new Date().toISOString(),
    kdf: pending.kdf,
    wrappedDek: pending.wrappedDek,
    dekNonce: pending.dekNonce,
    folders: Object.entries(cipherIndex.folders).map(([id, v]) => ({
      id,
      ciphertext: v.ciphertext,
      nonce: v.nonce,
      sortOrder: folders.value.find((f) => f.id === id)?.sortOrder ?? 0
    })),
    items: Object.entries(cipherIndex.items).map(([id, v]) => ({
      id,
      ciphertext: v.ciphertext,
      nonce: v.nonce
    }))
  }

  const blob = new Blob([JSON.stringify(backup, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `vault-backup-${new Date().toISOString().slice(0, 10)}.json`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
  appendAuditLog('导出密码库备份文件（密文）')
  showToast('加密备份已导出')
}

// ============================================================
// 十二、出口
// ============================================================
onSensitiveClear(clearVault)

export function useVault() {
  return {
    isLocked,
    lockReason,
    unlockInput,
    windowBlurred,
    searchQuery,
    selectedFolderId,
    selectedTypeFilter,
    showPassword,
    showCardCvv,
    activeModal,
    showGeneratorModal,
    generatorForForm,
    openDropdownName,
    activeSettingsTab,
    toastMessage,
    faviconErrorMap,
    folders,
    items,
    selectedItemId,
    totpRemaining,
    vaultRev,
    vaultLoaded,
    securityConfig,
    auditLogs,
    idleRemainingSeconds,
    genLength,
    genOptions,
    generatedPassword,
    editingForm,
    folderForm,
    passwordChangeForm,

    osCatalog,
    bankCatalog,
    googleFolderIconPreset,
    typeFilterOptions,
    itemTypeOptions,
    settingsTabs,

    shortCipherName,
    filteredItems,
    selectedItem,
    currentFolderName,
    securityHealthScore,
    currentTotpCode,

    getOsMeta,
    getBankMeta,
    getFolderById,
    getFaviconUrl,
    getItemFallbackIconName,
    getItemFallbackIconColor,
    maskCardNumber,
    formatCardNumber,
    formatIdleTime,
    getFolderCount,
    renderMarkdown,
    copyText,
    showToast,
    resetIdleTimer,
    lockVault,
    handleUnlockVault,
    handleUnlockTotp,
    backToPasswordStep,
    unlockStep,
    unlockTotpCode,
    unlockBusy,
    initVault,
    disposeVault,
    loadVault,
    clearVault,
    selectItem,
    toggleSecretReveal,
    toggleFavorite,
    deleteItem,
    toggleDropdown,
    closeAllDropdowns,
    openCreateModal,
    openEditModal,
    saveItem,
    generateNewPassword,
    openGeneratorModal,
    applyGeneratedPasswordToForm,
    openFolderModal,
    openRenameFolderModal,
    handleFolderImageUpload,
    saveFolder,
    moveFolder,
    deleteFolder,
    openSettings,
    saveSecurityConfig,
    updateMasterPassword,
    createManualSnapshot,
    exportVaultBackup
  }
}
