<script setup>
import AppIcon from '../common/AppIcon.vue'
import { useVault } from '../../stores/vault'

const {
  selectedItem,
  showPassword,
  showCardCvv,
  getBankMeta,
  maskCardNumber,
  formatCardNumber,
  toggleSecretReveal,
  copyText,
  renderMarkdown
} = useVault()
</script>

<template>
  <!-- 详情模板 3：【银行卡】严格对齐 5 行结构 -->
  <!-- 第2行：姓名 | 类型（图标+名称） -->
  <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
    <div
      class="theme-card p-4 flex items-center justify-between"
    >
      <div class="space-y-1">
        <div  class="theme-text-muted text-xs flex items-center gap-1.5">
          <AppIcon name="badge" size="16" class="text-accent" />
          <span>姓名</span>
        </div>
        <div class="text-sm font-bold select-all">{{ selectedItem.cardHolder }}</div>
      </div>
      <button
        @click="copyText(selectedItem.cardHolder, '姓名')"
        class="px-3 py-1.5 rounded-xl bg-accent/15 text-accent hover:bg-accent hover:text-white text-xs font-semibold"
      >
        复制
      </button>
    </div>

    <div
      class="theme-card p-4 flex items-center justify-between"
    >
      <div class="space-y-1">
        <div  class="theme-text-muted text-xs flex items-center gap-1.5">
          <AppIcon name="account_balance" size="16" class="text-rose-500" />
          <span>类型</span>
        </div>
        <div class="text-sm font-bold flex items-center gap-2">
          <img
            v-if="getBankMeta(selectedItem.cardType).logo"
            :src="getBankMeta(selectedItem.cardType).logo"
            class="w-4 h-4 object-contain rounded-sm"
          />
          <span>{{ selectedItem.cardType }}</span>
        </div>
      </div>
    </div>
  </div>

  <!-- 第3行：银行卡卡号 -->
  <div
    class="theme-card p-5 flex items-center justify-between gap-4"
  >
    <div class="space-y-1">
      <div  class="theme-text-muted text-xs flex items-center gap-1.5">
        <AppIcon name="credit_card" size="16" class="text-indigo-500" />
        <span>银行卡卡号</span>
      </div>
      <div class="text-base font-bold tracking-wider select-all">
        {{
          showPassword
            ? formatCardNumber(selectedItem.cardNumber)
            : maskCardNumber(selectedItem.cardNumber)
        }}
      </div>
    </div>
    <div class="flex items-center gap-2">
      <button
        @click="toggleSecretReveal()"
        
        class="theme-subtle px-3 py-2 rounded-xl text-xs font-semibold flex items-center gap-1"
      >
        <AppIcon :name="showPassword ? 'visibility_off' : 'visibility'" size="14" class="text-amber-500" />
        {{ showPassword ? '隐藏' : '显示' }}
      </button>
      <button
        @click="copyText((selectedItem.cardNumber || '').replace(/\s+/g, ''), '银行卡卡号')"
        class="px-3.5 py-2 rounded-xl theme-accent-btn text-xs font-semibold flex items-center gap-1"
      >
        <AppIcon name="content_copy" size="14" /> 复制卡号
      </button>
    </div>
  </div>

  <!-- 第4行：有效期 (YYYY-MM-DD) | 安全码 | 交易密码 -->
  <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
    <div
      class="theme-card p-4 flex items-center justify-between"
    >
      <div>
        <div  class="theme-text-muted text-xs flex items-center gap-1">
          <AppIcon name="calendar_month" size="16" class="text-emerald-500" />
          <span>有效期</span>
        </div>
        <div class="text-sm font-bold mt-1 select-all">{{ selectedItem.cardExpiry || '--' }}</div>
      </div>
      <button
        @click="copyText(selectedItem.cardExpiry, '有效期')"
        class="p-2 rounded-xl bg-accent/15 text-accent hover:bg-accent hover:text-white"
      >
        <AppIcon name="content_copy" size="14" />
      </button>
    </div>

    <div
      class="theme-card p-4 flex items-center justify-between"
    >
      <div>
        <div  class="theme-text-muted text-xs flex items-center gap-1">
          <AppIcon name="security" size="16" class="text-rose-500" />
          <span>安全码</span>
        </div>
        <div class="text-sm font-bold mt-1 text-rose-500 select-all">
          {{ showCardCvv ? selectedItem.cardCvv : '•••' }}
        </div>
      </div>
      <div class="flex items-center gap-1">
        <button
          @click="showCardCvv = !showCardCvv"
          class="p-2 rounded-xl bg-black/5"
        >
          <AppIcon :name="showCardCvv ? 'visibility_off' : 'visibility'" size="14" class="text-amber-500" />
        </button>
        <button
          @click="copyText(selectedItem.cardCvv, '安全码')"
          class="p-2 rounded-xl bg-accent/15 text-accent hover:bg-accent hover:text-white"
        >
          <AppIcon name="content_copy" size="14" />
        </button>
      </div>
    </div>

    <div
      class="theme-card p-4 flex items-center justify-between"
    >
      <div>
        <div  class="theme-text-muted text-xs flex items-center gap-1">
          <AppIcon name="pin" size="16" class="text-amber-500" />
          <span>交易密码</span>
        </div>
        <div class="text-sm font-bold mt-1 text-accent select-all">
          {{ showPassword ? selectedItem.password : '••••••' }}
        </div>
      </div>
      <button
        @click="copyText(selectedItem.password, '交易密码')"
        class="p-2 rounded-xl bg-accent/15 text-accent hover:bg-accent hover:text-white"
      >
        <AppIcon name="content_copy" size="14" />
      </button>
    </div>
  </div>

  <!-- 第5行：备注（支持 Markdown 渲染） -->
  <div class="theme-card p-5 space-y-2.5">
    <div class="flex items-center justify-between">
      <div
        
        class="theme-text-muted text-xs flex items-center gap-1.5 font-semibold"
      >
        <AppIcon name="description" size="16" class="text-amber-500" />
        <span>备注</span>
      </div>
      <button
        v-if="selectedItem.markdownContent"
        @click="copyText(selectedItem.markdownContent, '备注')"
        class="text-xs text-accent hover:underline font-semibold flex items-center gap-1"
      >
        <AppIcon name="content_copy" size="14" />
        <span>复制备注</span>
      </button>
    </div>
    <div
      
      class="bg-black/[0.03] border-[var(--border-color)] text-zinc-800 p-4 rounded-xl border markdown-body"
      v-html="renderMarkdown(selectedItem.markdownContent || '暂无备注')"
    ></div>
  </div>
</template>
