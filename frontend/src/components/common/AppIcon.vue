<script setup>
import { computed } from 'vue'

import { FALLBACK_ICON, ICONS } from '../../data/icons'

// 允许直接传原 Material 的字号类（如 iconClass="text-base"），保持调用方无需改语义
const SIZE_CLASS_MAP = {
  'text-xs': 12,
  'text-sm': 14,
  'text-base': 16,
  'text-lg': 18,
  'text-xl': 20,
  'text-2xl': 24,
  'text-3xl': 30,
  'text-4xl': 36
}

const props = defineProps({
  /** Material Symbols 名称，与 icons.js 的 key 一致 */
  name: { type: String, default: '' },
  /** 像素尺寸（数字）或 Tailwind 字号类（text-base 等） */
  size: { type: [Number, String], default: 20 },
  strokeWidth: { type: [Number, String], default: 2 }
})

const icon = computed(() => ICONS[props.name] || FALLBACK_ICON)
const isMissing = computed(() => !ICONS[props.name])
const dimension = computed(() => {
  if (typeof props.size === 'number') return `${props.size}px`
  if (SIZE_CLASS_MAP[props.size]) return `${SIZE_CLASS_MAP[props.size]}px`
  return props.size
})
</script>

<template>
  <!-- 内容为构建期从 Heroicons 提取的静态 path，非用户输入，故用 v-html -->
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    :stroke-width="strokeWidth"
    :width="dimension"
    :height="dimension"
    :data-icon="name"
    :data-icon-missing="isMissing ? '1' : null"
    class="shrink-0"
    aria-hidden="true"
    v-html="icon"
  />
</template>
