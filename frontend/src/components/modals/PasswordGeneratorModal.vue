<script setup>
import AppIcon from '../common/AppIcon.vue'
import { useVault } from '../../stores/vault'

const {
  showGeneratorModal,
  generatedPassword,
  genLength,
  genOptions,
  generatorForForm,
  generateNewPassword,
  applyGeneratedPasswordToForm,
  copyText
} = useVault()
</script>

<template>
  <!-- 弹窗 2：密码生成器（支持顶栏独立打开，也支持从"随机生成强密码"唤起并一键回填表单） -->
  <div
    v-if="showGeneratorModal"
    class="fixed inset-0 z-50 bg-black/45 backdrop-blur-[2px] flex items-center justify-center p-4"
    @click.self="showGeneratorModal = false"
  >
    <div
      
      class="surface-glass border-[var(--border-color)] text-zinc-900 w-full max-w-md rounded-2xl border p-5 space-y-4 shadow-2xl"
    >
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <AppIcon name="vpn_key" size="20" class="text-emerald-500" />
          <h3 class="font-bold text-sm">密码生成器 (CSPRNG 加密随机)</h3>
        </div>
        <button @click="showGeneratorModal = false" class="p-1 rounded-lg opacity-60 hover:opacity-100">
          <AppIcon name="close" />
        </button>
      </div>

      <div
        
        class="bg-white border-[var(--border-color)] p-4 rounded-xl border text-center space-y-1.5"
      >
        <div class="text-base font-bold tracking-wider break-all select-all text-accent">
          {{ generatedPassword }}
        </div>
      </div>

      <div class="space-y-1.5">
        <div class="flex justify-between text-xs font-semibold">
          <span>密码长度</span>
          <span class="text-accent">{{ genLength }} 位</span>
        </div>
        <input
          type="range"
          min="8"
          max="64"
          v-model.number="genLength"
          @input="generateNewPassword"
          class="w-full accent-[var(--accent)] cursor-pointer"
        />
      </div>

      <div class="grid grid-cols-2 gap-2 text-xs">
        <label
          
          class="bg-white border-[var(--border-color)] p-2.5 rounded-xl border flex items-center justify-between cursor-pointer"
        >
          <span>大写 (A-Z)</span>
          <input
            type="checkbox"
            v-model="genOptions.upper"
            @change="generateNewPassword"
            class="accent-[var(--accent)]"
          />
        </label>
        <label
          
          class="bg-white border-[var(--border-color)] p-2.5 rounded-xl border flex items-center justify-between cursor-pointer"
        >
          <span>小写 (a-z)</span>
          <input
            type="checkbox"
            v-model="genOptions.lower"
            @change="generateNewPassword"
            class="accent-[var(--accent)]"
          />
        </label>
        <label
          
          class="bg-white border-[var(--border-color)] p-2.5 rounded-xl border flex items-center justify-between cursor-pointer"
        >
          <span>数字 (0-9)</span>
          <input
            type="checkbox"
            v-model="genOptions.numbers"
            @change="generateNewPassword"
            class="accent-[var(--accent)]"
          />
        </label>
        <label
          
          class="bg-white border-[var(--border-color)] p-2.5 rounded-xl border flex items-center justify-between cursor-pointer"
        >
          <span>符号 (!@#$)</span>
          <input
            type="checkbox"
            v-model="genOptions.symbols"
            @change="generateNewPassword"
            class="accent-[var(--accent)]"
          />
        </label>
      </div>

      <div class="flex items-center gap-2 pt-1">
        <button
          @click="generateNewPassword()"
          
          class="theme-subtle hover:bg-black/[0.04] px-3.5 py-2 rounded-xl text-xs font-semibold flex items-center gap-1"
        >
          <AppIcon name="refresh" size="16" class="text-accent" /> 刷新
        </button>
        <button
          v-if="generatorForForm"
          @click="applyGeneratedPasswordToForm()"
          class="flex-1 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-600 text-white text-xs font-semibold shadow-sm flex items-center justify-center gap-1"
        >
          <AppIcon name="check_circle" size="16" />
          <span>填入当前密码框并复制</span>
        </button>
        <button
          v-else
          @click="copyText(generatedPassword, '生成的密码'); showGeneratorModal = false"
          class="flex-1 py-2 rounded-xl theme-accent-btn text-xs font-semibold shadow-sm"
        >
          复制密码
        </button>
      </div>
    </div>
  </div>
</template>
