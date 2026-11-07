<script setup>
import AppIcon from '../common/AppIcon.vue'
import { useVault } from '../../stores/vault'

const { selectedItem, showPassword, getOsMeta, toggleSecretReveal, copyText, renderMarkdown } =
  useVault()
</script>

<template>
  <!-- 详情模板 2：【VPS】严格对齐 6 行结构 -->
  <!-- 第2行：IP 地址 | SSH 端口 -->
  <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
    <div
      class="theme-card p-4 flex items-center justify-between"
    >
      <div class="space-y-1">
        <div  class="theme-text-muted text-xs flex items-center gap-1.5">
          <AppIcon name="dns" size="16" class="text-accent" />
          <span>IP 地址</span>
        </div>
        <div class="text-sm font-bold select-all">{{ selectedItem.ipAddress }}</div>
      </div>
      <button
        @click="copyText(selectedItem.ipAddress, 'IP 地址')"
        class="px-3 py-1.5 rounded-xl bg-accent/15 text-accent hover:bg-accent hover:text-white text-xs font-semibold flex items-center gap-1"
      >
        <AppIcon name="content_copy" size="14" /> 复制
      </button>
    </div>

    <div
      class="theme-card p-4 flex items-center justify-between"
    >
      <div class="space-y-1">
        <div  class="theme-text-muted text-xs flex items-center gap-1.5">
          <AppIcon name="terminal" size="16" class="text-purple-500" />
          <span>SSH 端口</span>
        </div>
        <div class="text-sm font-bold select-all">{{ selectedItem.sshPort || '22' }}</div>
      </div>
      <button
        @click="copyText(selectedItem.sshPort || '22', 'SSH 端口')"
        class="px-3 py-1.5 rounded-xl bg-accent/15 text-accent hover:bg-accent hover:text-white text-xs font-semibold flex items-center gap-1"
      >
        <AppIcon name="content_copy" size="14" /> 复制
      </button>
    </div>
  </div>

  <!-- 第3行：操作系统（图标+名称） | 到期日（YYYY-MM-DD + 每次/一次） -->
  <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
    <div
      class="theme-card p-4 flex items-center justify-between"
    >
      <div class="space-y-1">
        <div  class="theme-text-muted text-xs flex items-center gap-1.5">
          <AppIcon name="computer" size="16" class="text-cyan-500" />
          <span>操作系统</span>
        </div>
        <div class="text-sm font-bold flex items-center gap-2">
          <img
            v-if="getOsMeta(selectedItem.vpsOs).logo"
            :src="getOsMeta(selectedItem.vpsOs).logo"
            class="w-4 h-4 object-contain"
          />
          <span>{{ selectedItem.vpsOs }}</span>
        </div>
      </div>
    </div>

    <div
      class="theme-card p-4 flex items-center justify-between"
    >
      <div class="space-y-1">
        <div  class="theme-text-muted text-xs flex items-center gap-1.5">
          <AppIcon name="event_available" size="16" class="text-emerald-500" />
          <span>到期日</span>
        </div>
        <div class="text-sm font-bold flex items-center gap-2">
          <span>{{ selectedItem.vpsExpiryDate || '2027-12-31' }}</span>
          <span
            :class="
              selectedItem.vpsExpiryCycle === '每次'
                ? 'bg-emerald-500/15 text-emerald-500'
                : 'bg-amber-500/15 text-amber-500'
            "
            class="text-[0.65rem] px-2 py-0.5 rounded-md font-bold"
          >
            {{ selectedItem.vpsExpiryCycle || '每次' }}
          </span>
        </div>
      </div>
    </div>
  </div>

  <!-- 第4行：核心数 | 运行内存 (GB) | 磁盘内存 (GB) -->
  <div class="grid grid-cols-3 gap-4">
    <div class="theme-card p-4">
      <div  class="theme-text-muted text-xs flex items-center gap-1">
        <AppIcon name="memory" size="16" class="text-indigo-500" />
        <span>核心数</span>
      </div>
      <div class="text-sm font-bold mt-1">{{ selectedItem.vpsCores }} 核 (vCPU)</div>
    </div>

    <div class="theme-card p-4">
      <div  class="theme-text-muted text-xs flex items-center gap-1">
        <AppIcon name="developer_board" size="16" class="text-emerald-500" />
        <span>运行内存</span>
      </div>
      <div class="text-sm font-bold mt-1">{{ selectedItem.vpsRam }} GB</div>
    </div>

    <div class="theme-card p-4">
      <div  class="theme-text-muted text-xs flex items-center gap-1">
        <AppIcon name="hard_drive" size="16" class="text-amber-500" />
        <span>磁盘内存</span>
      </div>
      <div class="text-sm font-bold mt-1">{{ selectedItem.vpsDisk }} GB</div>
    </div>
  </div>

  <!-- 第5行：用户名 | 登录密码 -->
  <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
    <div
      class="theme-card p-4 flex items-center justify-between"
    >
      <div class="space-y-1 min-w-0">
        <div  class="theme-text-muted text-xs flex items-center gap-1.5">
          <AppIcon name="person" size="16" class="text-accent" />
          <span>用户名</span>
        </div>
        <div class="text-sm font-bold select-all truncate">{{ selectedItem.sshUser || 'root' }}</div>
      </div>
      <button
        @click="copyText(selectedItem.sshUser || 'root', '用户名')"
        class="px-3 py-1.5 rounded-xl bg-accent/15 text-accent hover:bg-accent hover:text-white text-xs font-semibold flex items-center gap-1 shrink-0"
      >
        <AppIcon name="content_copy" size="14" /> 复制
      </button>
    </div>

    <div
      class="theme-card p-4 flex items-center justify-between gap-2"
    >
      <div class="space-y-1 min-w-0">
        <div  class="theme-text-muted text-xs flex items-center gap-1.5">
          <AppIcon name="lock" size="16" class="text-rose-500" />
          <span>登录密码</span>
        </div>
        <div v-if="!showPassword" class="text-sm font-bold tracking-widest">••••••••••••</div>
        <div v-else class="text-sm font-bold text-accent break-all select-all">
          {{ selectedItem.password }}
        </div>
      </div>
      <div class="flex items-center gap-1.5 shrink-0">
        <button
          @click="toggleSecretReveal()"
          
          class="theme-subtle px-2.5 py-1.5 rounded-xl text-xs font-semibold"
        >
          {{ showPassword ? '隐藏' : '显示' }}
        </button>
        <button
          @click="copyText(selectedItem.password, '登录密码')"
          class="px-3 py-1.5 rounded-xl theme-accent-btn text-xs font-semibold"
        >
          复制
        </button>
      </div>
    </div>
  </div>

  <!-- 第6行：SSH 私钥（支持 Markdown 渲染） -->
  <div class="theme-card p-5 space-y-2.5">
    <div class="flex items-center justify-between">
      <div
        
        class="theme-text-muted text-xs flex items-center gap-1.5 font-semibold"
      >
        <AppIcon name="vpn_key" size="16" class="text-purple-500" />
        <span>SSH 私钥</span>
      </div>
      <button
        v-if="selectedItem.markdownContent"
        @click="copyText(selectedItem.markdownContent, 'SSH 私钥')"
        class="text-xs text-accent hover:underline font-semibold flex items-center gap-1"
      >
        <AppIcon name="content_copy" size="14" />
        <span>复制 SSH 私钥</span>
      </button>
    </div>
    <div
      
      class="bg-black/[0.03] border-[var(--border-color)] text-zinc-800 p-4 rounded-xl border markdown-body"
      v-html="renderMarkdown(selectedItem.markdownContent || '暂无 SSH 私钥')"
    ></div>
  </div>
</template>
