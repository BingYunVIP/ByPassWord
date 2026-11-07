<script setup>
import { useVault } from '../stores/vault'
import DetailHeader from './detail/DetailHeader.vue'
import WebsiteDetail from './detail/WebsiteDetail.vue'
import VpsDetail from './detail/VpsDetail.vue'
import BankDetail from './detail/BankDetail.vue'
import NoteDetail from './detail/NoteDetail.vue'

const { selectedItem } = useVault()
</script>

<template>
  <!-- ==================== 右栏：多态详情区 ==================== -->
  <main class="flex-1 h-full overflow-y-auto p-6 lg:p-8">
    <div v-if="selectedItem" class="max-w-3xl mx-auto space-y-4">
      <!-- 公共第一行：图标 | 标题 | 收藏 | 编辑 | 删除 -->
      <DetailHeader />

      <!-- 详情模板 1：网站 -->
      <WebsiteDetail v-if="selectedItem.type === 'website'" />

      <!-- 详情模板 2：VPS -->
      <VpsDetail v-else-if="selectedItem.type === 'vps'" />

      <!-- 详情模板 3：银行卡 -->
      <BankDetail v-else-if="selectedItem.type === 'bank'" />

      <!-- 详情模板 4：安全笔记 -->
      <NoteDetail v-else-if="selectedItem.type === 'note'" />
    </div>
  </main>
</template>
