<script setup>
import { safeInlineImage } from '../../security/policy'
import AppIcon from '../common/AppIcon.vue'
import { useVault } from '../../stores/vault'

const {
  activeModal,
  folderForm,
  googleFolderIconPreset,
  handleFolderImageUpload,
  saveFolder
} = useVault()
</script>

<template>
  <!-- 弹窗 3：新建 / 编辑文件夹（支持上传图片作为图标 + Google 彩色图标选择） -->
  <div
    v-if="activeModal === 'folderModal'"
    class="fixed inset-0 z-50 bg-black/45 backdrop-blur-[2px] flex items-center justify-center p-4"
    @click.self="activeModal = null"
  >
    <div
      
      class="surface-glass border-[var(--border-color)] text-zinc-900 w-full max-w-md rounded-2xl border p-5 space-y-4 shadow-2xl"
    >
      <div class="flex items-center justify-between">
        <h3 class="font-bold text-sm">{{ folderForm.id ? '编辑文件夹' : '新建文件夹' }}</h3>
        <button @click="activeModal = null" class="p-1 rounded-lg opacity-60 hover:opacity-100">
          <AppIcon name="close" />
        </button>
      </div>

      <div class="space-y-3 text-xs">
        <div class="space-y-1">
          <label class="font-semibold opacity-75">文件夹名称</label>
          <input
            v-model="folderForm.name"
            type="text"
            placeholder="输入文件夹名称..."
            class="ios-input w-full px-3 py-2 rounded-xl"
          />
        </div>

        <!-- 预设 Google Material 彩色图标选择 -->
        <div class="space-y-1">
          <label class="font-semibold opacity-75">选择 Google Material 彩色图标</label>
          <div class="grid grid-cols-6 gap-1.5">
            <button
              v-for="ic in googleFolderIconPreset"
              :key="ic.gIcon"
              type="button"
              @click="
                folderForm.gIcon = ic.gIcon;
                folderForm.color = ic.color;
                folderForm.customImage = ''
              "
              :class="
                folderForm.gIcon === ic.gIcon && !folderForm.customImage
                  ? 'ring-2 ring-accent bg-accent/10'
                  : 'theme-subtle'
              "
              class="p-2 rounded-xl flex items-center justify-center"
            >
              <AppIcon :name="ic.gIcon" size="18" :class="ic.color" />
            </button>
          </div>
        </div>

        <!-- 上传自定义图片作为文件夹图标 -->
        <div class="space-y-1.5">
          <label class="font-semibold opacity-75">或上传本地图片作为文件夹图标</label>
          <div class="flex items-center gap-3">
            <div
              
              class="bg-white border-[var(--border-color)] w-11 h-11 rounded-xl border flex items-center justify-center overflow-hidden shrink-0"
            >
              <img
                v-if="folderForm.customImage"
                :src="safeInlineImage(folderForm.customImage)"
                class="w-full h-full object-cover"
                alt="preview"
              />
              <AppIcon :name="folderForm.gIcon" size="20" v-else :class="folderForm.color" />
            </div>
            <label
              class="px-3 py-2 rounded-xl bg-accent/15 text-accent hover:bg-accent hover:text-white font-semibold cursor-pointer spring-btn"
            >
              <span>选择图片上传</span>
              <input type="file" accept="image/*" @change="handleFolderImageUpload" class="hidden" />
            </label>
            <button
              v-if="folderForm.customImage"
              @click="folderForm.customImage = ''"
              class="text-rose-500 hover:underline"
            >
              清除图片
            </button>
          </div>
        </div>
      </div>

      <div class="flex justify-end gap-2 pt-2">
        <button
          @click="activeModal = null"
          
          class="theme-subtle px-4 py-2 rounded-xl text-xs font-semibold"
        >
          取消
        </button>
        <button
          @click="saveFolder()"
          class="px-4 py-2 rounded-xl theme-accent-btn text-xs font-semibold"
        >
          保存文件夹
        </button>
      </div>
    </div>
  </div>
</template>
