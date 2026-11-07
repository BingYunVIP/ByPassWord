<script setup>
import AppIcon from '../common/AppIcon.vue'
import { computed } from 'vue'
import { safeWebUrl } from '../../security/policy'
import { useVault } from '../../stores/vault'
import ItemIcon from '../common/ItemIcon.vue'
import FolderIcon from '../common/FolderIcon.vue'

const { selectedItem, getFolderById, toggleFavorite, openEditModal, deleteItem } = useVault()

const folder = computed(() => getFolderById(selectedItem.value.folderId))
</script>

<template>
  <!-- 【第一行】图标 | 主行：名称（网站为超链接文本） | 收藏图标 | 图标+编辑按钮 | 图标+删除按钮 -->
  <div
    class="theme-card p-5 flex items-center justify-between gap-4"
  >
    <div class="flex items-center gap-4 min-w-0">
      <!-- 大图标 -->
      <div
        
        class="bg-white border-[var(--border-color)] w-12 h-12 p-2 rounded-2xl border flex items-center justify-center shrink-0 shadow-sm"
      >
        <ItemIcon
          :item="selectedItem"
          img-class="w-7 h-7 object-contain"
          icon-class="text-2xl"
          :selected="false"
        />
      </div>

      <!-- 主行：标题（网站为可点击超链接）+ 所属文件夹徽章 -->
      <div class="min-w-0">
        <div class="flex items-center gap-2 flex-wrap">
          <a
            v-if="selectedItem.type === 'website' && safeWebUrl(selectedItem.url)"
            :href="safeWebUrl(selectedItem.url)"
            target="_blank"
            rel="noopener noreferrer"
            class="text-base font-bold text-accent hover:underline inline-flex items-center gap-1 truncate max-w-full"
            title="点击在新标签页打开该网站"
          >
            <span class="truncate">{{ selectedItem.title }}</span>
            <AppIcon name="open_in_new" size="16" class="text-accent" />
          </a>
          <span v-else class="text-base font-bold truncate">{{ selectedItem.title }}</span>

          <!-- 所属文件夹彩色标签 -->
          <span
            
            class="theme-subtle text-zinc-700 text-[0.65rem] px-2 py-0.5 rounded-lg font-semibold inline-flex items-center gap-1"
          >
            <FolderIcon
              :folder="folder"
              img-class="w-3.5 h-3.5"
              chatgpt-class="w-3.5 h-3.5"
              icon-class="text-xs"
            />
            <span>{{ folder.name }}</span>
          </span>
        </div>

        <div
          
          class="theme-text-muted text-[0.68rem] truncate mt-0.5"
        >
          <template v-if="selectedItem.type === 'website' && safeWebUrl(selectedItem.url)">{{ selectedItem.url }}</template>
          <template v-else-if="selectedItem.type === 'vps'"
            >{{ selectedItem.ipAddress }}:{{ selectedItem.sshPort }} · {{ selectedItem.vpsOs }}</template
          >
          <template v-else-if="selectedItem.type === 'bank'"
            >{{ selectedItem.cardType }} · 持卡人：{{ selectedItem.cardHolder }}</template
          >
          <template v-else-if="selectedItem.type === 'note'">端到端 AES-256 加密笔记</template>
        </div>
      </div>
    </div>

    <!-- 右侧：收藏图标 | 图标+编辑按钮 | 图标+删除按钮 -->
    <div class="flex items-center gap-2 shrink-0">
      <button
        @click="toggleFavorite(selectedItem)"
        :class="
          selectedItem.favorite
            ? 'bg-amber-400/20 text-amber-500 border-amber-400/40'
            : 'theme-subtle theme-text-muted border-[var(--border-color)] hover:text-zinc-800'
        "
        class="w-9 h-9 rounded-xl border flex items-center justify-center spring-btn"
        title="收藏/取消收藏"
      >
        <AppIcon name="star" size="18" :class="selectedItem.favorite ? 'text-amber-400' : ''" />
      </button>

      <button
        @click="openEditModal(selectedItem)"
        
        class="bg-white hover:bg-zinc-100 text-zinc-800 border-[var(--border-color)] px-3 py-2 rounded-xl border text-xs font-semibold flex items-center gap-1.5 shadow-sm spring-btn"
      >
        <AppIcon name="edit_square" size="16" class="text-accent" />
        <span>编辑</span>
      </button>

      <button
        @click="deleteItem(selectedItem.id)"
        
        class="bg-rose-50 hover:bg-rose-100 text-rose-600 border-rose-200 px-3 py-2 rounded-xl border text-xs font-semibold flex items-center gap-1.5 shadow-sm spring-btn"
      >
        <AppIcon name="delete" size="16" class="text-rose-500" />
        <span>删除</span>
      </button>
    </div>
  </div>
</template>
