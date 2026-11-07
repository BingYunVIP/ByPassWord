<script setup>
import AppIcon from './common/AppIcon.vue'
import { useVault } from '../stores/vault'

const {
  securityConfig,
  shortCipherName,
  idleRemainingSeconds,
  formatIdleTime,
  searchQuery,
  openSettings,
  openCreateModal,
  openGeneratorModal,
  lockVault
} = useVault()
</script>

<template>
  <!-- =========================================================
       第一行：顶栏
       左栏：Logo + 主行：密码库 + 副行：● AES-256 已解锁
       右栏：搜索框 | 图标+"新建条目" | 图标+"密码生成器" | 图标+"黑白切换" | 锁定
  ========================================================== -->
  <header
    
    class="border-[var(--border-color)] bg-white h-16 border-b flex items-center shrink-0 z-20"
  >
    <!-- 第一行左区（与左侧文件夹栏严格同宽 w-[16.5rem]） -->
    <div
      
      class="border-[var(--border-color)] w-[16.5rem] shrink-0 h-full px-4 border-r flex items-center gap-3"
    >
      <img
        src="/brand/logo.png"
        alt=""
        decoding="async"
        class="w-10 h-10 rounded-xl object-cover shadow-md shrink-0"
      />
      <div class="min-w-0 flex-1">
        <div class="flex items-center justify-between">
          <span class="text-sm font-bold tracking-tight truncate">密码库</span>
          <span
            
            class="theme-text-muted text-[0.62rem] ml-auto shrink-0 flex items-center gap-0.5"
          >
            <AppIcon name="schedule" size="13" class="text-amber-500" />
            {{ formatIdleTime(idleRemainingSeconds) }}
          </span>
        </div>
        <div
          class="text-[0.68rem] text-emerald-500 font-medium flex items-center gap-1.5 mt-0.5 truncate"
        >
          <span
            class="inline-block w-2 h-2 rounded-full bg-emerald-500 animate-pulse shrink-0"
          ></span>
          <span class="truncate">{{ shortCipherName }} 已解锁</span>
          <span
            @click="openSettings('crypto')"
            class="text-[0.65rem] px-1.5 py-0.5 rounded bg-accent/15 text-accent font-semibold cursor-pointer hover:bg-accent hover:text-white spring-btn ml-auto shrink-0"
            title="点击配置加密标准与KDF"
          >
            {{ securityConfig.kdfType }}
          </span>
        </div>
      </div>
    </div>

    <!-- 第一行右区：搜索框 + 功能按钮组 -->
    <div class="flex-1 h-full px-4 flex items-center justify-between gap-3 overflow-x-auto">
      <!-- 搜索框 -->
      <div class="relative flex-1 max-w-md min-w-[12rem]">
        <AppIcon name="search" size="16" class="absolute left-3 top-1/2 -translate-y-1/2 text-accent" />
        <input
          v-model="searchQuery"
          type="text"
          placeholder="搜索网站、账号、IP、卡号、恢复密钥或备注..."
          class="ios-input w-full pl-9 pr-7 py-2 rounded-xl text-xs spring-btn"
        />
        <button
          v-if="searchQuery"
          @click="searchQuery = ''"
          class="absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-rose-500"
        >
          <AppIcon name="cancel" size="14" />
        </button>
      </div>

      <!-- 右侧按钮组 -->
      <div class="flex items-center gap-2 shrink-0">
        <!-- 图标+"新建条目"的按钮 -->
        <button
          @click="openCreateModal()" data-testid="new-item"
          class="px-3.5 py-2 rounded-xl text-xs font-semibold theme-accent-btn shadow-sm flex items-center gap-1.5 spring-btn"
        >
          <AppIcon name="add_circle" size="16" class="text-white" />
          <span>新建条目</span>
        </button>

        <!-- 图标+"密码生成器"的按钮 -->
        <button
          @click="openGeneratorModal(false)"
          
          class="theme-subtle hover:bg-black/[0.04] text-zinc-800 px-3 py-2 rounded-xl text-xs font-medium border flex items-center gap-1.5 shadow-sm spring-btn"
        >
          <AppIcon name="vpn_key" size="16" class="text-emerald-500" />
          <span>密码生成器</span>
        </button>

        <!-- 锁定按钮 -->
        <button
          @click="lockVault('手动点击顶栏锁定按钮')" data-testid="lock-vault"
          
          class="bg-rose-50 hover:bg-rose-100 text-rose-600 border-rose-200 px-3 py-2 rounded-xl text-xs font-medium border flex items-center gap-1.5 shadow-sm spring-btn"
        >
          <AppIcon name="lock" size="16" class="text-rose-500" />
          <span>锁定</span>
        </button>
      </div>
    </div>
  </header>
</template>
