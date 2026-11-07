<script setup>
import AppIcon from '../common/AppIcon.vue'
import { useVault } from '../../stores/vault'

const { selectedItem, copyText, renderMarkdown } = useVault()
</script>

<template>
  <!-- 详情模板 4：【安全笔记】（备注支持 Markdown 渲染） -->
  <div class="theme-card p-5 space-y-3">
    <div
      class="border-[var(--border-color)] flex items-center justify-between pb-2 border-b"
      
    >
      <div
        
        class="theme-text-muted text-xs flex items-center gap-1.5 font-semibold"
      >
        <AppIcon name="notes" size="16" class="text-amber-500" />
        <span>备注</span>
      </div>
      <button
        @click="copyText(selectedItem.markdownContent, '备注')"
        class="px-3 py-1.5 rounded-xl theme-accent-btn text-xs font-semibold flex items-center gap-1"
      >
        <AppIcon name="content_copy" size="14" />
        <span>复制全文</span>
      </button>
    </div>
    <div
      
      class="bg-black/[0.03] border-[var(--border-color)] text-zinc-800 p-4 rounded-xl border markdown-body min-h-[12rem]"
      v-html="renderMarkdown(selectedItem.markdownContent || '暂无备注')"
    ></div>
  </div>
</template>
