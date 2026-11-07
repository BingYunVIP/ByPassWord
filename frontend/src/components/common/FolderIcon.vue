<script setup>
import AppIcon from './AppIcon.vue'
import { safeInlineImage } from '../../security/policy'
import { chatgptFolderIcon } from '../../data/catalog'

defineProps({
  folder: { type: Object, required: true },
  // 自定义图片图标类名
  imgClass: { type: String, default: 'w-4 h-4' },
  // ChatGPT 图标类名
  chatgptClass: { type: String, default: 'w-4 h-4 rounded-sm' },
  // Material 图标尺寸类
  iconClass: { type: String, default: 'text-base' },
  // 选中态时图标强制白色
  selected: { type: Boolean, default: false }
})
</script>

<template>
  <!-- 1. 用户上传的自定义图片图标 -->
  <img
    v-if="safeInlineImage(folder.customImage)"
    :src="safeInlineImage(folder.customImage)"
    :class="[imgClass, 'rounded object-cover shrink-0']"
    alt="folder"
  />
  <!-- 2. 中转站使用 ChatGPT 图标（本地 WebP） -->
  <img
    v-else-if="folder.iconType === 'chatgpt' || folder.id === 'relay'"
    :src="chatgptFolderIcon"
    :class="[chatgptClass, 'object-contain shrink-0']"
    alt="ChatGPT"
  />
  <!-- 3. Heroicons 线性图标（颜色由 folder.color / 选中态决定） -->
  <AppIcon
    :name="folder.gIcon"
    v-else
    :size="iconClass"
    class="shrink-0"
    :class="selected ? 'text-white' : folder.color"
  />
</template>
