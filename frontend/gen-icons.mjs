/**
 * 从 @heroicons/vue 提取 24/outline 的 SVG 内容，生成运行时零依赖的 icons.js。
 * 用法：cd frontend && node gen-icons.mjs
 */
import fs from 'node:fs'
import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import * as All from '@heroicons/vue/24/outline/index.js'

// 读取现有 icons.js 里的「Material 名 -> Heroicons 组件名」映射
const current = fs.readFileSync('src/data/icons.js', 'utf8')
const pairs = [...current.matchAll(/^\s{2}([a-z_0-9]+):\s*(\w+Icon),?$/gm)].map((m) => [m[1], m[2]])
const fallbackMatch = current.match(/export const FALLBACK_ICON = (\w+Icon)/)

console.log('解析到映射:', pairs.length, '个 | 兜底:', fallbackMatch?.[1])

async function svgInner(componentName) {
  const comp = All[componentName]
  if (!comp) throw new Error('组件不存在: ' + componentName)
  const app = createSSRApp({ render: () => h(comp) })
  const html = await renderToString(app)
  const inner = html.replace(/^<svg[^>]*>/, '').replace(/<\/svg>$/, '')
  if (!inner.trim()) throw new Error('渲染为空: ' + componentName)
  return inner
}

const entries = []
const seen = new Set()
for (const [materialName, compName] of pairs) {
  if (seen.has(materialName)) continue
  seen.add(materialName)
  const inner = await svgInner(compName)
  // 统一成单行、双引号，去掉无意义空白
  const oneLine = inner.replace(/\s+/g, ' ').replace(/ >/g, '>').trim()
  entries.push([materialName, oneLine, compName])
}

const fallbackInner = await svgInner(fallbackMatch[1])

const lines = []
lines.push('/**')
lines.push(' * 图标注册表：Material Symbols 名称 -> Heroicons 24/outline 的 SVG 内容。')
lines.push(' *')
lines.push(' * 由 gen-icons.mjs 从 @heroicons/vue 2.2.0 提取（MIT），运行时零依赖。')
lines.push(' * 为什么不用 <component :is="HeroiconsComponent">：该包导出的是渲染函数（函数式组件），')
lines.push(' * Vue 不会把 class/style/data-* 等 attrs 透传给根 svg，导致尺寸与颜色控制失效。')
lines.push(' */')
lines.push('')
lines.push('export const ICONS = {')
for (const [name, inner, comp] of entries) {
  lines.push(`  // ${comp}`)
  lines.push(`  ${JSON.stringify(name)}:`)
  lines.push(`    ${JSON.stringify(inner)},`)
}
lines.push('}')
lines.push('')
lines.push('/** 未知名称时的兜底图标 */')
lines.push(`export const FALLBACK_ICON = ${JSON.stringify(fallbackInner.replace(/\s+/g, ' ').trim())}`)
lines.push('')
lines.push('export const hasIcon = (name) => Boolean(name && ICONS[name])')
lines.push('')

fs.writeFileSync('src/data/icons.js', lines.join('\n'), 'utf8')
console.log('已生成 src/data/icons.js：', entries.length, '个图标')
