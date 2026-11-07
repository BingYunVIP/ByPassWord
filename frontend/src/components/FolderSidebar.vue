<script setup>
import AppIcon from './common/AppIcon.vue'
import { useVault } from '../stores/vault'
import FolderIcon from './common/FolderIcon.vue'

const {
  folders,
  items,
  auditLogs,
  selectedFolderId,
  securityHealthScore,
  openFolderModal,
  getFolderCount,
  moveFolder,
  openRenameFolderModal,
  deleteFolder,
  openSettings,
  exportVaultBackup
} = useVault()
</script>

<template>
  <!-- ==================== 左栏：导航与文件夹区 (w-[16.5rem]) ==================== -->
  <aside
    
    class="border-[var(--border-color)] bg-white/40 w-[16.5rem] shrink-0 h-full border-r flex flex-col justify-between p-3 overflow-y-auto"
  >
    <!-- 上半部分：新建文件夹按钮 + 文件夹列表 -->
    <div class="space-y-1.5">
      <!-- 图标+"新建文件夹"的按钮 -->
      <button
        @click="openFolderModal()"
        
        class="bg-white/90 hover:bg-white text-zinc-800 border-[var(--border-color)] w-full py-2 px-3 rounded-xl border text-xs font-semibold flex items-center justify-center gap-2 shadow-sm spring-btn"
      >
        <AppIcon name="create_new_folder" size="16" class="text-accent" />
        <span>新建文件夹</span>
      </button>

      <!-- 全部条目总览 -->
      <button
        @click="selectedFolderId = 'ALL'"
        :class="
          selectedFolderId === 'ALL'
            ? 'theme-accent-btn shadow-sm'
            : 'text-zinc-700 hover:bg-black/[0.04]'
        "
        class="w-full px-3 py-2 rounded-xl text-xs font-medium flex items-center justify-between spring-btn"
      >
        <div class="flex items-center gap-2.5 truncate">
          <AppIcon name="grid_view" size="16" :class="selectedFolderId === 'ALL' ? 'text-white' : 'text-accent'" />
          <span>所有密码条目</span>
        </div>
        <span
          :class="
            selectedFolderId === 'ALL'
              ? 'bg-white/20 text-white'
              : 'theme-subtle theme-text-muted'
          "
          class="text-[0.65rem] px-1.5 py-0.2 rounded-md"
        >
          {{ items.length }}
        </span>
      </button>

      <div  class="border-[var(--border-color)] border-t my-1"></div>

      <!-- 文件夹列表（支持自定义图片、中转站 ChatGPT 图标、Google Material 彩色图标、排序/重命名/删除） -->
      <div class="space-y-1">
        <div
          v-for="(folder, index) in folders"
          :key="folder.id"
          @click="selectedFolderId = folder.id"
          :class="[
            selectedFolderId === folder.id
              ? 'theme-accent-btn shadow-sm'
              : 'text-zinc-700 hover:bg-black/[0.04]'
          ]"
          class="group w-full px-2.5 py-2 rounded-xl text-xs font-medium flex items-center justify-between cursor-pointer spring-btn"
        >
          <div class="flex items-center gap-2.5 min-w-0 flex-1">
            <FolderIcon :folder="folder" :selected="selectedFolderId === folder.id" />

            <span class="truncate" :title="folder.desc || folder.name">{{ folder.name }}</span>
          </div>

          <!-- 右侧：排序/重命名/删除按钮与数量统计 -->
          <div class="flex items-center gap-0.5 shrink-0">
            <div class="hidden group-hover:flex items-center gap-0.5 mr-1">
              <button
                @click.stop="moveFolder(index, -1)"
                :disabled="index === 0"
                title="上移"
                class="p-0.5 rounded hover:bg-black/20 disabled:opacity-30"
              >
                <AppIcon name="keyboard_arrow_up" size="12" />
              </button>
              <button
                @click.stop="moveFolder(index, 1)"
                :disabled="index === folders.length - 1"
                title="下移"
                class="p-0.5 rounded hover:bg-black/20 disabled:opacity-30"
              >
                <AppIcon name="keyboard_arrow_down" size="12" />
              </button>
              <button
                @click.stop="openRenameFolderModal(folder)"
                title="重命名与更换图标"
                class="p-0.5 rounded hover:bg-black/20"
              >
                <AppIcon name="edit" size="12" />
              </button>
              <button
                @click.stop="deleteFolder(folder.id)"
                title="删除文件夹"
                class="p-0.5 rounded hover:bg-rose-500/40"
              >
                <AppIcon name="delete" size="12" />
              </button>
            </div>
            <span
              :class="
                selectedFolderId === folder.id
                  ? 'bg-white/20 text-white'
                  : 'theme-subtle theme-text-muted'
              "
              class="text-[0.65rem] px-1.5 py-0.2 rounded-md"
            >
              {{ getFolderCount(folder.id) }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- 下半部分：设置 + 安全健康度 -->
    <div
      class="border-[var(--border-color)] space-y-2.5 pt-3 border-t"
      
    >
      <!-- 图标+设置 -->
      <button
        @click="openSettings('account')" data-testid="open-settings"
        
        class="text-zinc-800 hover:bg-black/[0.04] bg-white/60 border-black/5 w-full px-3 py-2 rounded-xl border text-xs font-semibold flex items-center justify-between spring-btn"
      >
        <div class="flex items-center gap-2">
          <AppIcon name="settings" size="16" class="text-accent" />
          <span>安全与设置</span>
        </div>
        <span
          class="text-[0.62rem] px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-500 font-bold"
        >
          审计 {{ auditLogs.length }}
        </span>
      </button>

      <!-- 安全健康度模块 -->
      <div
        
        class="bg-white border-[var(--border-color)] p-3 rounded-xl border space-y-2"
      >
        <!-- 第一行：图标+安全健康度 xxx -->
        <div class="flex items-center justify-between text-xs">
          <div class="flex items-center gap-1.5 font-semibold">
            <AppIcon name="health_and_safety" size="16" class="text-emerald-500" />
            <span>安全健康度</span>
          </div>
          <span class="font-bold text-emerald-500">{{ securityHealthScore }}%</span>
        </div>

        <!-- 第二行：进度条 -->
        <div
          
          class="theme-subtle w-full h-1.5 rounded-full overflow-hidden"
        >
          <div
            class="bg-gradient-to-r from-accent to-emerald-500 h-full rounded-full transition-all duration-500"
            :style="{ width: securityHealthScore + '%' }"
          ></div>
        </div>

        <!-- 第三行：共 xx 项数据 | 导出按钮 -->
        <div class="flex items-center justify-between text-[0.68rem] pt-0.5">
          <span class="theme-text-muted">共 {{ items.length }} 项数据</span
          >
          <button
            @click="exportVaultBackup()"
            class="px-2 py-0.5 rounded-md bg-accent/15 text-accent hover:bg-accent hover:text-white font-semibold spring-btn"
          >
            导出
          </button>
        </div>
      </div>
    </div>
  </aside>
</template>
