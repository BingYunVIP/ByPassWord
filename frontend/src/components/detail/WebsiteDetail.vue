<script setup>
import AppIcon from '../common/AppIcon.vue'
import { useVault } from '../../stores/vault'

const {
  selectedItem,
  showPassword,
  currentTotpCode,
  totpRemaining,
  toggleSecretReveal,
  copyText,
  renderMarkdown
} = useVault()
</script>

<template>
  <!-- 详情模板 1：【网站】五段式详情（第5行：恢复密钥 Markdown 渲染） -->
  <!-- 第二行：副行：图标 + 邮箱 / 手机号 / 用户名 | 主行：xxxxx | 上下居中位置 复制按钮 -->
  <div
    class="theme-card p-5 flex items-center justify-between gap-4"
  >
    <div class="min-w-0 flex-1 space-y-1">
      <div  class="theme-text-muted text-xs flex items-center gap-1.5">
        <AppIcon name="account_circle" size="16" class="text-accent" />
        <span>邮箱 / 手机号 / 用户名</span>
      </div>
      <div class="text-sm font-bold break-all select-all">
        {{ selectedItem.account }}
      </div>
    </div>
    <div class="self-center shrink-0">
      <button
        @click="copyText(selectedItem.account, '账号')"
        class="px-3.5 py-2 rounded-xl bg-accent/15 text-accent hover:bg-accent hover:text-white text-xs font-semibold flex items-center gap-1.5 spring-btn"
      >
        <AppIcon name="content_copy" size="16" />
        <span>复制</span>
      </button>
    </div>
  </div>

  <!-- 第三行：副行：登录密码 | 主行：xxxxx | 显示/隐藏的按钮 复制按钮 -->
  <div
    class="theme-card p-5 flex items-center justify-between gap-4"
  >
    <div class="min-w-0 flex-1 space-y-1">
      <div  class="theme-text-muted text-xs flex items-center gap-1.5">
        <AppIcon name="password" size="16" class="text-indigo-500" />
        <span>登录密码</span>
      </div>
      <div v-if="!showPassword" class="text-base font-bold tracking-widest select-none">
        ••••••••••••••
      </div>
      <div v-else class="text-sm font-bold break-all select-all text-accent">
        {{ selectedItem.password }}
      </div>
    </div>

    <div class="self-center flex items-center gap-2 shrink-0">
      <button
        @click="toggleSecretReveal()"
        
        class="theme-subtle hover:bg-black/[0.04] text-zinc-700 border-[var(--border-color)] px-3 py-2 rounded-xl border text-xs font-semibold flex items-center gap-1.5 spring-btn"
      >
        <AppIcon :name="showPassword ? 'visibility_off' : 'visibility'" size="16" class="text-amber-500" />
        <span>{{ showPassword ? '隐藏' : '显示' }}</span>
      </button>

      <button
        @click="copyText(selectedItem.password, '登录密码')"
        class="px-3.5 py-2 rounded-xl theme-accent-btn text-xs font-semibold flex items-center gap-1.5 shadow-sm spring-btn"
      >
        <AppIcon name="content_copy" size="16" class="text-white" />
        <span>复制</span>
      </button>
    </div>
  </div>

  <!-- 第四行：副行：2FA | 主行：xxxxx | 动态的圆形倒计时 复制按钮 -->
  <div
    class="theme-card p-5 flex items-center justify-between gap-4"
  >
    <div class="min-w-0 flex-1 space-y-1">
      <div  class="theme-text-muted text-xs flex items-center gap-1.5">
        <AppIcon name="encrypted" size="16" class="text-emerald-500" />
        <span>2FA</span>
      </div>
      <div
        v-if="selectedItem.totpSecret"
        data-testid="item-totp-code" class="text-lg font-bold tracking-wider text-emerald-500 select-all"
      >
        {{ currentTotpCode.slice(0, 3) }} {{ currentTotpCode.slice(3, 6) }}
      </div>
      <div v-else  class="theme-text-muted text-xs font-medium">
        未配置 2FA 动态验证码密钥
      </div>
    </div>

    <div v-if="selectedItem.totpSecret" class="self-center flex items-center gap-3 shrink-0">
      <div class="flex items-center gap-2">
        <svg class="w-8 h-8 -rotate-90" viewBox="0 0 36 36">
          <circle
            cx="18"
            cy="18"
            r="14"
            fill="none"
            :stroke="'rgba(0,0,0,0.08)'"
            stroke-width="3.5"
          ></circle>
          <circle
            cx="18"
            cy="18"
            r="14"
            fill="none"
            :stroke="totpRemaining <= 5 ? '#EF4444' : '#10B981'"
            stroke-width="3.5"
            stroke-dasharray="88"
            :stroke-dashoffset="88 - (88 * totpRemaining) / 30"
            stroke-linecap="round"
            class="transition-all duration-500"
          ></circle>
        </svg>
        <span class="text-xs font-bold w-6">{{ totpRemaining }}s</span>
      </div>

      <button
        @click="copyText(currentTotpCode, '2FA 验证码')"
        class="px-3.5 py-2 rounded-xl bg-emerald-500/15 text-emerald-500 hover:bg-emerald-500 hover:text-white text-xs font-semibold flex items-center gap-1.5 spring-btn"
      >
        <AppIcon name="content_copy" size="16" />
        <span>复制</span>
      </button>
    </div>
  </div>

  <!-- 第五行：恢复密钥（支持 Markdown 保存后渲染） -->
  <div class="theme-card p-5 space-y-2.5">
    <div class="flex items-center justify-between">
      <div
        
        class="theme-text-muted text-xs flex items-center gap-1.5 font-semibold"
      >
        <AppIcon name="key_visualizer" size="16" class="text-amber-500" />
        <span>恢复密钥</span>
      </div>
      <button
        v-if="selectedItem.markdownContent"
        @click="copyText(selectedItem.markdownContent, '恢复密钥')"
        class="text-xs text-accent hover:underline font-semibold flex items-center gap-1"
      >
        <AppIcon name="content_copy" size="14" />
        <span>复制恢复密钥</span>
      </button>
    </div>
    <div
      
      class="bg-black/[0.03] border-[var(--border-color)] text-zinc-800 p-4 rounded-xl border markdown-body"
      v-html="renderMarkdown(selectedItem.markdownContent || '暂无恢复密钥')"
    ></div>
  </div>
</template>
