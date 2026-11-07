<script setup>
import AppIcon from './common/AppIcon.vue'
import { useVault } from '../stores/vault'
import ItemIcon from './common/ItemIcon.vue'

const {
  filteredItems,
  typeFilterOptions,
  selectedTypeFilter,
  selectedItemId,
  openCreateModal,
  selectItem,
  maskCardNumber
} = useVault()
</script>

<template>
  <!-- ==================== 中栏：列表区 (w-[22rem]) ==================== -->
  <section
    
    class="border-[var(--border-color)] bg-white/30 w-[22rem] shrink-0 h-full border-r flex flex-col"
  >
    <!-- 列表顶部：条目类型筛选 -->
    <div  class="border-[var(--border-color)] p-3 border-b space-y-2">
      <div class="grid grid-cols-5 gap-1">
        <button
          v-for="t in typeFilterOptions"
          :key="t.value"
          @click="selectedTypeFilter = t.value"
          :class="
            selectedTypeFilter === t.value
              ? 'theme-accent-btn font-bold shadow-sm'
              : 'theme-subtle text-zinc-600 hover:bg-black/10'
          "
          class="py-1 rounded-lg text-[0.65rem] text-center spring-btn truncate"
        >
          {{ t.label }}
        </button>
      </div>
    </div>

    <!-- 列表滚动容器 -->
    <div class="flex-1 overflow-y-auto p-2.5 space-y-1.5">
      <div
        v-if="filteredItems.length === 0"
        class="h-60 flex flex-col items-center justify-center text-center px-4"
      >
        <AppIcon name="folder_open" class="text-4xl text-zinc-400/50 mb-2" />
        <p class="text-xs font-medium opacity-70">当前分类暂无条目</p>
        <button
          @click="openCreateModal()"
          class="mt-2 text-xs text-accent hover:underline font-semibold"
        >
          + 点击新建条目
        </button>
      </div>

      <!-- 列表项：图标 | 主行：名称 | 副行：邮箱/手机号/用户名 | 是否填写的2FA标签 -->
      <div
        v-for="item in filteredItems"
        :key="item.id"
        @click="selectItem(item.id)"
        :class="[
          selectedItemId === item.id
            ? 'theme-accent-btn shadow-sm'
            : 'hover:bg-white/75 text-zinc-900'
        ]"
        class="p-3 rounded-xl flex items-center justify-between gap-3 cursor-pointer spring-btn"
      >
        <!-- 左侧：自动从网站获取的真实图标（或对应 VPS 系统/银行卡/安全笔记彩色图标） -->
        <div
          :class="
            selectedItemId === item.id
              ? 'bg-white border-white/40'
              : 'bg-white border-[var(--border-color)]'
          "
          class="w-10 h-10 rounded-xl border flex items-center justify-center shrink-0 overflow-hidden shadow-sm"
        >
          <ItemIcon :item="item" :selected="selectedItemId === item.id" />
        </div>

        <!-- 中间：主行 + 副行 -->
        <div class="min-w-0 flex-1">
          <div class="text-xs font-bold truncate flex items-center gap-1.5">
            <span class="truncate">{{ item.title }}</span>
            <AppIcon name="star" size="14" v-if="item.favorite" class="text-amber-400 shrink-0" />
          </div>
          <div
            :class="
              selectedItemId === item.id
                ? 'text-white/85'
                : 'theme-text-muted'
            "
            class="text-[0.68rem] truncate mt-0.5"
          >
            <template v-if="item.type === 'website'">{{ item.account }}</template>
            <template v-else-if="item.type === 'vps'"
              >{{ item.sshUser || 'root' }}@{{ item.ipAddress }}:{{ item.sshPort || '22' }}</template
            >
            <template v-else-if="item.type === 'bank'"
              >{{ item.cardHolder }} · {{ maskCardNumber(item.cardNumber) }}</template
            >
            <template v-else-if="item.type === 'note'">Markdown 加密笔记</template>
          </div>
        </div>

        <!-- 右侧：是否填写的 2FA 标签（或对应类型标签） -->
        <div class="shrink-0">
          <template v-if="item.type === 'website'">
            <span
              v-if="item.totpSecret"
              :class="
                selectedItemId === item.id
                  ? 'bg-white/25 text-white border-white/30'
                  : 'bg-emerald-500/15 text-emerald-500 border-emerald-500/30'
              "
              class="text-[0.62rem] px-2 py-0.5 rounded-md border font-bold inline-flex items-center gap-0.5"
            >
              <AppIcon name="verified_user" size="12" /> 2FA
            </span>
            <span
              v-else
              :class="
                selectedItemId === item.id
                  ? 'bg-black/20 text-white/75'
                  : 'theme-subtle theme-text-muted'
              "
              class="text-[0.62rem] px-2 py-0.5 rounded-md font-medium inline-block"
            >
              未设2FA
            </span>
          </template>
          <span
            v-else-if="item.type === 'vps'"
            :class="
              selectedItemId === item.id ? 'bg-white/25 text-white' : 'bg-purple-500/15 text-purple-500'
            "
            class="text-[0.62rem] px-2 py-0.5 rounded-md font-bold inline-block"
          >
            {{ item.vpsCores }}C/{{ item.vpsRam }}G
          </span>
          <span
            v-else-if="item.type === 'bank'"
            :class="
              selectedItemId === item.id ? 'bg-white/25 text-white' : 'bg-rose-500/15 text-rose-500'
            "
            class="text-[0.62rem] px-2 py-0.5 rounded-md font-bold inline-block"
          >
            {{ item.cardType }}
          </span>
          <span
            v-else-if="item.type === 'note'"
            :class="
              selectedItemId === item.id ? 'bg-white/25 text-white' : 'bg-amber-500/15 text-amber-500'
            "
            class="text-[0.62rem] px-2 py-0.5 rounded-md font-bold inline-block"
          >
            笔记
          </span>
        </div>
      </div>
    </div>
  </section>
</template>
