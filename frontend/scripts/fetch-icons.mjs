/**
 * 品牌图标抓取脚本（仅开发期运行）
 *
 * 策略（严格一一对应，绝不混用）：
 *   1. 抓取品牌官网首页，解析 <link rel="icon|apple-touch-icon|mask-icon"> 中尺寸最大的图标
 *   2. 官网解析失败时，退化为官网 /favicon.ico 或 /apple-touch-icon.png
 *   3. 仍失败时，退化为 Google favicon 服务（其数据同样来自该品牌官网）
 *   4. 统一转为 128×128 透明背景 WebP，输出到 src/assets/icons/
 *
 * 运行：npm run icons
 */
import fs from 'node:fs'
import path from 'node:path'
import sharp from 'sharp'

const OUT_DIR = path.resolve('src/assets/icons')

// key 与业务代码一一对应：操作系统 / 银行 / 卡组织 / 站点
const TARGETS = [
  // ===== VPS 操作系统 =====
  { key: 'os-debian', home: 'https://www.debian.org/' },
  { key: 'os-ubuntu', home: 'https://ubuntu.com/' },
  { key: 'os-windows', home: 'https://www.microsoft.com/' },
  { key: 'os-rockylinux', home: 'https://rockylinux.org/' },
  { key: 'os-alpinelinux', home: 'https://alpinelinux.org/' },

  // ===== 银行 =====
  { key: 'bank-cmb', home: 'https://www.cmbchina.com/' },
  { key: 'bank-boc', home: 'https://www.boc.cn/' },
  { key: 'bank-icbc', home: 'https://www.icbc.com.cn/' },
  { key: 'bank-ccb', home: 'https://www.ccb.com/' },
  { key: 'bank-abc', home: 'https://www.abchina.com/' },
  { key: 'bank-bocom', home: 'https://www.bankcomm.com/' },
  { key: 'bank-unionpay', home: 'https://www.unionpayintl.com/' },

  // ===== 卡组织 =====
  { key: 'card-visa', home: 'https://www.visa.com/' },
  { key: 'card-mastercard', home: 'https://www.mastercard.com/' },
  { key: 'card-amex', home: 'https://www.americanexpress.com/' },
  { key: 'card-jcb', home: 'https://www.jcb.com/' },

  // ===== 站点 / 文件夹 =====
  { key: 'site-chatgpt', home: 'https://chatgpt.com/' },
  { key: 'site-github', home: 'https://github.com/' }
]

const UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'

const timeoutSignal = (ms) => AbortSignal.timeout(ms)

async function fetchBuffer(url, ms = 15000) {
  const res = await fetch(url, {
    redirect: 'follow',
    signal: timeoutSignal(ms),
    headers: { 'user-agent': UA, accept: '*/*' }
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const buf = Buffer.from(await res.arrayBuffer())
  if (buf.length < 100) throw new Error('empty body')
  return buf
}

async function fetchHtml(url) {
  const res = await fetch(url, {
    redirect: 'follow',
    signal: timeoutSignal(15000),
    headers: { 'user-agent': UA, accept: 'text/html' }
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return await res.text()
}

/** 从首页 HTML 里挑出尺寸最大的图标链接 */
function pickBestIcon(html, baseUrl) {
  const links = [...html.matchAll(/<link\b[^>]*>/gi)].map((m) => m[0])
  const candidates = []

  for (const tag of links) {
    const rel = (tag.match(/\brel\s*=\s*["']([^"']+)["']/i) || [])[1] || ''
    const href = (tag.match(/\bhref\s*=\s*["']([^"']+)["']/i) || [])[1] || ''
    if (!href || !/icon/i.test(rel)) continue
    if (/\.ico($|\?)/i.test(href)) continue // sharp 无法解析 ico，交给兜底策略

    const sizes = (tag.match(/\bsizes\s*=\s*["']([^"']+)["']/i) || [])[1] || ''
    let score = 0
    if (/apple-touch-icon/i.test(rel)) score += 300
    const sizeMatches = [...sizes.matchAll(/(\d+)x(\d+)/gi)].map((m) => Math.max(+m[1], +m[2]))
    if (sizeMatches.length) score += Math.max(...sizeMatches)
    if (/svg/i.test(href)) score += 120 // 矢量图标任意尺寸都清晰
    candidates.push({ href, score })
  }

  candidates.sort((a, b) => b.score - a.score)
  if (!candidates.length) return null
  try {
    return new URL(candidates[0].href, baseUrl).href
  } catch {
    return null
  }
}

async function tryOfficial(target) {
  const origin = new URL(target.home).origin
  const found = []

  // 1) 解析官网首页声明的图标
  try {
    const html = await fetchHtml(target.home)
    const iconUrl = pickBestIcon(html, target.home)
    if (iconUrl) {
      found.push({ buffer: await fetchBuffer(iconUrl), source: iconUrl })
    }
  } catch (e) {
    /* 继续兜底 */
  }

  // 2) 官网约定路径
  const guesses = [`${origin}/apple-touch-icon.png`, `${origin}/apple-touch-icon-precomposed.png`]
  for (const url of guesses) {
    try {
      found.push({ buffer: await fetchBuffer(url, 8000), source: url })
    } catch (e) {
      /* 继续兜底 */
    }
  }

  return found
}

async function tryGoogleFavicon(target) {
  const host = new URL(target.home).hostname
  const url = `https://www.google.com/s2/favicons?domain=${host}&sz=128`
  return { buffer: await fetchBuffer(url), source: url + '（官网兜底）' }
}

/** 校验并转码；非图片（例如返回 HTML 错误页）会抛错，交给下一个候选 */
async function toWebp(buffer, outFile) {
  const meta = await sharp(buffer, { density: 384 }).metadata()
  if (!meta.width || !meta.height) throw new Error('not an image')
  await sharp(buffer, { density: 384 })
    .resize(128, 128, { fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } })
    .webp({ quality: 92, alphaQuality: 100 })
    .toFile(outFile)
}

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true })
  const report = []

  for (const target of TARGETS) {
    const outFile = path.join(OUT_DIR, `${target.key}.webp`)

    // 候选顺序：官网解析出的图标 → 官网约定路径 → Google 图标服务
    let candidates = []
    try {
      candidates = await tryOfficial(target)
    } catch (e) {
      candidates = []
    }
    try {
      candidates.push(await tryGoogleFavicon(target))
    } catch (e) {
      /* 忽略 */
    }

    let done = false
    for (const candidate of candidates) {
      try {
        await toWebp(candidate.buffer, outFile)
        const size = fs.statSync(outFile).size
        report.push(`OK    ${target.key.padEnd(16)} ${String(size).padStart(6)}B  <- ${candidate.source}`)
        done = true
        break
      } catch (e) {
        /* 换下一个候选 */
      }
    }

    if (!done) report.push(`FAIL  ${target.key}`)
  }

  console.log(report.join('\n'))
}

main()
