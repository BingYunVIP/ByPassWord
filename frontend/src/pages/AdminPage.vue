<script setup>
import { onMounted, watch } from 'vue'

import AppHeader from '../components/AppHeader.vue'
import FolderSidebar from '../components/FolderSidebar.vue'
import ItemList from '../components/ItemList.vue'
import DetailPanel from '../components/DetailPanel.vue'
import ItemEditorModal from '../components/modals/ItemEditorModal.vue'
import PasswordGeneratorModal from '../components/modals/PasswordGeneratorModal.vue'
import FolderModal from '../components/modals/FolderModal.vue'
import SettingsModal from '../components/modals/SettingsModal.vue'
import VaultLockOverlay from '../components/VaultLockOverlay.vue'
import { useAuth } from '../stores/auth'
import { useVault } from '../stores/vault'

const auth = useAuth()
const { windowBlurred, securityConfig, vaultLoaded, loadVault, clearVault } = useVault()

async function ensureData() {
  if (auth.isUnlocked.value && !vaultLoaded.value) {
    try {
      await loadVault()
    } catch (e) {
      console.error('加载金库失败', e)
    }
  }
}

onMounted(ensureData)

watch(
  () => auth.status.value,
  (status) => {
    if (status === 'unlocked') ensureData()
    if (status !== 'unlocked') clearVault()
  }
)
</script>

<template>
  <!-- 主窗口容器 -->
  <div
    :class="[
      'surface-glass border-[var(--border-color)]',
      windowBlurred && securityConfig.blurOnBlur ? 'blur-xl scale-[0.99]' : ''
    ]"
    class="relative w-full h-full sm:rounded-2xl border flex flex-col overflow-hidden transition-all duration-300"
  >
    <!-- 第一行：顶栏 -->
    <AppHeader />

    <!-- 下方三栏主体区：左栏(文件夹与健康度) | 中栏(列表区) | 右栏(多态详情区) -->
    <div class="flex-1 flex overflow-hidden">
      <FolderSidebar />
      <ItemList />
      <DetailPanel />
    </div>

    <!-- 弹窗 1：新建 / 编辑条目 -->
    <ItemEditorModal />
    <!-- 弹窗 2：密码生成器 -->
    <PasswordGeneratorModal />
    <!-- 弹窗 3：新建 / 编辑文件夹 -->
    <FolderModal />
    <!-- 弹窗 4：安全与系统设置中心 -->
    <SettingsModal />

    <!-- 锁定金库遮罩 -->
    <VaultLockOverlay />
  </div>
</template>
