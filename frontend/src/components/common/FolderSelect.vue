<script setup>
import AppIcon from './AppIcon.vue'
import { computed } from 'vue'
import { useVault } from '../../stores/vault'
import FolderIcon from './FolderIcon.vue'

const props = defineProps({
  modelValue: { type: String, default: '' }
})
const emit = defineEmits(['update:modelValue'])

const { folders, getFolderById, openDropdownName, toggleDropdown } = useVault()

const currentFolder = computed(() => getFolderById(props.modelValue))

const pickFolder = (folder) => {
  emit('update:modelValue', folder.id)
  openDropdownName.value = null
}
</script>

<template>
  <!-- 所属文件夹自定义下拉选择器（加载图标+名称） -->
  <div class="space-y-1 relative" @click.stop>
    <label class="font-semibold opacity-75">所属文件夹</label>
    <button
      type="button"
      @click="toggleDropdown('folder')"
      
      class="bg-white border-[var(--border-color)] text-zinc-900 w-full px-3 py-2 rounded-xl border flex items-center justify-between"
    >
      <div class="flex items-center gap-2 truncate">
        <FolderIcon :folder="currentFolder" />
        <span class="truncate">{{ currentFolder.name }}</span>
      </div>
      <AppIcon name="expand_more" size="14" class="opacity-60" />
    </button>
    <div
      v-if="openDropdownName === 'folder'"
      
      class="bg-white border-[var(--border-color)] absolute left-0 right-0 top-full mt-1 z-50 rounded-xl border shadow-xl max-h-48 overflow-y-auto p-1"
    >
      <button
        v-for="f in folders"
        :key="f.id"
        type="button"
        @click="pickFolder(f)"
        :class="
          modelValue === f.id
            ? 'theme-accent-btn'
            : 'hover:bg-black/[0.04]'
        "
        class="w-full px-2.5 py-2 rounded-lg flex items-center gap-2 text-left"
      >
        <FolderIcon :folder="f" :selected="modelValue === f.id" />
        <span class="truncate">{{ f.name }}</span>
      </button>
    </div>
  </div>
</template>
