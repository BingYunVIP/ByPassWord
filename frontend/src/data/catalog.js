// ============================================================
// 静态目录与默认数据（与原始单文件应用保持完全一致）
// 品牌图标均为本地 WebP 资源（源自各品牌官网，见 scripts/fetch-icons.mjs）
// ============================================================

import osDebian from '../assets/icons/os-debian.webp'
import osUbuntu from '../assets/icons/os-ubuntu.webp'
import osWindows from '../assets/icons/os-windows.webp'
import osRocky from '../assets/icons/os-rockylinux.webp'
import osAlpine from '../assets/icons/os-alpinelinux.webp'

import bankCmb from '../assets/icons/bank-cmb.webp'
import bankBoc from '../assets/icons/bank-boc.webp'
import bankIcbc from '../assets/icons/bank-icbc.webp'
import bankCcb from '../assets/icons/bank-ccb.webp'
import bankAbc from '../assets/icons/bank-abc.webp'
import bankBocom from '../assets/icons/bank-bocom.webp'
import bankUnionpay from '../assets/icons/bank-unionpay.webp'

import cardVisa from '../assets/icons/card-visa.webp'
import cardMastercard from '../assets/icons/card-mastercard.webp'
import cardAmex from '../assets/icons/card-amex.webp'
import cardJcb from '../assets/icons/card-jcb.webp'

import siteChatgpt from '../assets/icons/site-chatgpt.webp'
import siteGithub from '../assets/icons/site-github.webp'

// VPS 操作系统彩色图标目录（Debian 12+、Ubuntu 22+、Windows 10+ 等）
export const osCatalog = [
  { name: 'Debian 12 (Bookworm)', logo: osDebian },
  { name: 'Debian 13 (Trixie)', logo: osDebian },
  { name: 'Ubuntu 22.04 LTS', logo: osUbuntu },
  { name: 'Ubuntu 24.04 LTS', logo: osUbuntu },
  { name: 'Windows 10 Pro', logo: osWindows },
  { name: 'Windows 11 Pro', logo: osWindows },
  { name: 'Windows Server 2025', logo: osWindows },
  { name: 'Rocky Linux 9', logo: osRocky },
  { name: 'Alpine Linux 3.20', logo: osAlpine }
]

// 银行卡与国际卡组织彩色图标目录（中国银行、招商银行、Visa、Mastercard 等）
export const bankCatalog = [
  { name: '招商银行 (CMB)', logo: bankCmb },
  { name: '中国银行 (BOC)', logo: bankBoc },
  { name: '中国工商银行 (ICBC)', logo: bankIcbc },
  { name: '中国建设银行 (CCB)', logo: bankCcb },
  { name: '中国农业银行 (ABC)', logo: bankAbc },
  { name: '交通银行 (BOCOM)', logo: bankBocom },
  { name: '中国银联 (UnionPay)', logo: bankUnionpay },
  { name: 'Visa', logo: cardVisa },
  { name: 'Mastercard', logo: cardMastercard },
  { name: 'American Express', logo: cardAmex },
  { name: 'JCB', logo: cardJcb }
]

// 已知站点图标（本地 WebP）：未收录的站点在运行时按域名取 PNG 图标
export const siteIconMap = {
  'chatgpt.com': siteChatgpt,
  'www.chatgpt.com': siteChatgpt,
  'openai.com': siteChatgpt,
  'www.openai.com': siteChatgpt,
  'github.com': siteGithub,
  'www.github.com': siteGithub
}

// 中转站文件夹使用的 ChatGPT 图标
export const chatgptFolderIcon = siteChatgpt

// Google Material 彩色文件夹图标预设
export const googleFolderIconPreset = [
  { gIcon: 'folder', color: 'text-accent' },
  { gIcon: 'star', color: 'text-amber-500' },
  { gIcon: 'code', color: 'text-indigo-500' },
  { gIcon: 'memory', color: 'text-emerald-500' },
  { gIcon: 'dns', color: 'text-purple-500' },
  { gIcon: 'public', color: 'text-cyan-500' },
  { gIcon: 'credit_card', color: 'text-rose-500' },
  { gIcon: 'description', color: 'text-orange-500' },
  { gIcon: 'terminal', color: 'text-teal-500' },
  { gIcon: 'cloud', color: 'text-sky-500' },
  { gIcon: 'Passkey', color: 'text-pink-500' },
  { gIcon: 'shield_lock', color: 'text-emerald-600' }
]

// 左侧默认文件夹（首次进入时自动创建；id 由客户端生成 UUID，避免跨用户主键冲突）
export const defaultFolders = [
  { name: '收藏夹', gIcon: 'star', color: 'text-amber-500', desc: '星标常用条目', isFavorites: true },
  { name: '中转站', iconType: 'chatgpt', gIcon: 'smart_toy', color: 'text-[#10A37F]', desc: '记录AI中转站的网站、账号、密码等' },
  { name: '程序员', gIcon: 'code_blocks', color: 'text-indigo-500', desc: '代码仓库与开发者平台' },
  { name: '嵌入式', gIcon: 'memory', color: 'text-emerald-500', desc: 'EDA、芯片文档与固件平台' },
  { name: 'VPS', gIcon: 'dns', color: 'text-purple-500', desc: 'VPS服务器实例' },
  { name: '资源网站', gIcon: 'public', color: 'text-cyan-500', desc: '镜像站与资源站点' },
  { name: '银行卡', gIcon: 'credit_card', color: 'text-rose-500', desc: '境内外银行卡' },
  { name: '安全笔记', gIcon: 'encrypted', color: 'text-orange-500', desc: '加密文档与备注' }
]

// 条目类型筛选
export const typeFilterOptions = [
  { label: '全部', value: 'ALL' },
  { label: '网站', value: 'website' },
  { label: 'VPS', value: 'vps' },
  { label: '银行卡', value: 'bank' },
  { label: '笔记', value: 'note' }
]

// 新建 / 编辑条目的 4 种类型
export const itemTypeOptions = [
  { label: '网站', value: 'website', gIcon: 'language', color: 'text-accent' },
  { label: 'VPS', value: 'vps', gIcon: 'dns', color: 'text-purple-500' },
  { label: '银行卡', value: 'bank', gIcon: 'credit_card', color: 'text-rose-500' },
  { label: '安全笔记', value: 'note', gIcon: 'encrypted', color: 'text-amber-500' }
]

// Bitwarden 级安全设置参数（登录邮箱与账户指纹来自真实会话，不放这里）
export const initialSecurityConfig = {
  cipher: 'AES-256-GCM',
  kdfType: 'Argon2id',
  idleTimeoutMinutes: 15,
  clipboardClearSeconds: 20,
  blurOnBlur: false,
  smtpHost: 'smtp.fastmail.com',
  smtpPort: 465,
  backupSchedule: '每周日 02:00'
}

// 设置中心导航
export const settingsTabs = [
  { id: 'account', label: '登录邮箱与密码', gIcon: 'manage_accounts', color: 'text-accent' },
  { id: 'crypto', label: '加密标准', gIcon: 'enhanced_encryption', color: 'text-purple-500' },
  { id: 'lock', label: '未操作锁定时间', gIcon: 'timer', color: 'text-amber-500' },
  { id: 'smtp', label: '邮箱配置', gIcon: 'forward_to_inbox', color: 'text-emerald-500' },
  { id: 'backup', label: '备份时间', gIcon: 'cloud_sync', color: 'text-cyan-500' },
  { id: 'iplogs', label: 'IP 登录记录', gIcon: 'travel_explore', color: 'text-indigo-500' },
  { id: 'audit', label: '日志记录', gIcon: 'receipt_long', color: 'text-rose-500' }
]

export const initialAuditLogs = [
  { id: 1, time: '22:08:15', action: '密码库通过 Argon2id + AES-256-GCM 解锁', ip: '127.0.0.1' }
]

// 新建条目表单的初始字段（严格遵循原始字段集）
export const createEmptyItemForm = () => ({
  id: null,
  type: 'website',
  folderId: 'relay',
  title: '',
  url: 'https://',
  account: '',
  password: '',
  totpSecret: '',
  ipAddress: '',
  sshPort: '22',
  vpsOs: 'Debian 12 (Bookworm)',
  vpsExpiryDate: '2027-12-31',
  vpsExpiryCycle: '每次',
  vpsCores: 2,
  vpsRam: 4,
  vpsDisk: 80,
  sshUser: 'root',
  cardHolder: '',
  cardType: '招商银行 (CMB)',
  cardNumber: '',
  cardExpiry: '2028-09-28',
  cardCvv: '',
  markdownContent: ''
})
