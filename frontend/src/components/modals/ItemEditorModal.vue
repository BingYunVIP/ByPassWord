<script setup>
import AppIcon from '../common/AppIcon.vue'
import { useVault } from '../../stores/vault'
import FolderSelect from '../common/FolderSelect.vue'

const {
  activeModal,
  editingForm,
  itemTypeOptions,
  osCatalog,
  bankCatalog,
  getOsMeta,
  getBankMeta,
  getFaviconUrl,
  openGeneratorModal,
  openDropdownName,
  toggleDropdown,
  saveItem
} = useVault()
</script>

<template>
  <!-- 弹窗 1：新建 / 编辑条目（严格遵循表单行布局、彩色图标下拉框、联动密码生成器） -->
  <div
    v-if="activeModal === 'editItem'"
    class="fixed inset-0 z-40 bg-black/45 backdrop-blur-[2px] flex items-center justify-center p-4"
    @click.self="activeModal = null"
  >
    <div
      
      class="surface-glass border-[var(--border-color)] text-zinc-900 w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl border p-6 space-y-4 shadow-2xl"
    >
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <AppIcon name="post_add" size="20" class="text-accent" />
          <h3 class="font-bold text-sm">{{ editingForm.id ? '编辑条目' : '新建条目' }}</h3>
        </div>
        <button @click="activeModal = null" class="p-1 rounded-lg opacity-60 hover:opacity-100">
          <AppIcon name="close" />
        </button>
      </div>

      <!-- 默认选择 4 种类型：网站、VPS、银行卡、安全笔记 -->
      <div class="grid grid-cols-4 gap-2 text-xs">
        <button
          v-for="t in itemTypeOptions"
          :key="t.value"
          type="button"
          @click="editingForm.type = t.value"
          :class="
            editingForm.type === t.value
              ? 'theme-accent-btn font-bold shadow-sm'
              : 'bg-white text-zinc-700 border-[var(--border-color)]'
          "
          class="py-2 px-3 rounded-xl border flex items-center justify-center gap-1.5 spring-btn"
        >
          <AppIcon :name="t.gIcon" size="16" :class="editingForm.type === t.value ? 'text-white' : t.color" />
          <span>{{ t.label }}</span>
        </button>
      </div>

      <!-- ==================== 表单类型 A：网站 ==================== -->
      <div v-if="editingForm.type === 'website'" class="space-y-3.5 text-xs">
        <!-- 第1行：条目名称 | 所属文件夹（带彩色图标+名称的下拉框） -->
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div class="space-y-1">
            <label class="font-semibold opacity-75">网站名称 *</label>
            <input
              v-model="editingForm.title" data-testid="item-title"
              type="text"
              placeholder="如：GitHub / ChatGPT 中转站"
              class="ios-input w-full px-3 py-2 rounded-xl"
            />
          </div>

          <FolderSelect v-model="editingForm.folderId" />
        </div>

        <!-- 网址 URL（自动抓取网站图标） -->
        <div class="space-y-1">
          <label class="font-semibold opacity-75">网站网址 URL（自动抓取网站图标）</label>
          <div class="flex items-center gap-2">
            <div
              
              class="bg-white border-[var(--border-color)] w-9 h-9 rounded-xl border flex items-center justify-center shrink-0"
            >
              <img
                v-if="getFaviconUrl(editingForm.url)"
                :src="getFaviconUrl(editingForm.url)"
                class="w-5 h-5 object-contain"
              />
              <AppIcon name="language" size="16" v-else class="text-accent" />
            </div>
            <input
              v-model="editingForm.url"
              type="text"
              placeholder="https://github.com"
              class="ios-input flex-1 px-3 py-2 rounded-xl"
            />
          </div>
        </div>

        <!-- 邮箱 / 手机号 / 用户名 -->
        <div class="space-y-1">
          <label class="font-semibold opacity-75">邮箱 / 手机号 / 用户名 *</label>
          <input
            v-model="editingForm.account"
            type="text"
            placeholder="user@example.com"
            class="ios-input w-full px-3 py-2 rounded-xl"
          />
        </div>

        <!-- 登录密码（点击"随机生成强密码"直接调用"密码生成器"弹窗） -->
        <div class="space-y-1">
          <div class="flex justify-between items-center">
            <label class="font-semibold opacity-75">登录密码 *</label>
            <button
              type="button"
              @click="openGeneratorModal(true)"
              class="text-accent hover:underline font-semibold"
            >
              随机生成强密码
            </button>
          </div>
          <input
            v-model="editingForm.password" data-testid="item-password"
            type="text"
            class="ios-input w-full px-3 py-2 rounded-xl"
          />
        </div>

        <!-- 2FA 密钥 -->
        <div class="space-y-1">
          <label class="font-semibold opacity-75">2FA 密钥（TOTP Base32，选填）</label>
          <input
            v-model="editingForm.totpSecret" data-testid="item-totp-secret"
            type="text"
            placeholder="JBSWY3DPEHPK3PXP"
            class="ios-input w-full px-3 py-2 rounded-xl"
          />
        </div>

        <!-- 恢复密钥（支持 Markdown，保存后自动渲染） -->
        <div class="space-y-1">
          <label class="font-semibold opacity-75">恢复密钥（支持 Markdown 语法，保存后自动渲染）</label>
          <textarea
            v-model="editingForm.markdownContent"
            rows="4"
            placeholder="支持 Markdown 列表、代码块、加粗等，例如：\n- 恢复码 1: `8829-1029`\n- API Key: `sk-proj-...`"
            class="ios-input w-full px-3 py-2 rounded-xl"
          ></textarea>
        </div>
      </div>

      <!-- ==================== 表单类型 B：VPS（严格 6 行布局） ==================== -->
      <div v-else-if="editingForm.type === 'vps'" class="space-y-3.5 text-xs">
        <!-- 第一行：条目名称 | 所属文件夹(图标+名称) -->
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div class="space-y-1">
            <label class="font-semibold opacity-75">条目名称 *</label>
            <input
              v-model="editingForm.title" data-testid="item-title"
              type="text"
              placeholder="如：东京主力节点 VPS"
              class="ios-input w-full px-3 py-2 rounded-xl"
            />
          </div>

          <FolderSelect v-model="editingForm.folderId" />
        </div>

        <!-- 第二行：IP 地址 | SSH 端口 -->
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div class="space-y-1">
            <label class="font-semibold opacity-75">IP 地址 *</label>
            <input
              v-model="editingForm.ipAddress"
              type="text"
              placeholder="54.199.88.24"
              class="ios-input w-full px-3 py-2 rounded-xl"
            />
          </div>
          <div class="space-y-1">
            <label class="font-semibold opacity-75">SSH 端口</label>
            <input
              v-model="editingForm.sshPort"
              type="text"
              placeholder="22"
              class="ios-input w-full px-3 py-2 rounded-xl"
            />
          </div>
        </div>

        <!-- 第三行：操作系统(下拉加载图标+名称) | 到期日(YYYY-MM-DD 日历表 + 每次或一次) -->
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <!-- 操作系统自定义带图标下拉框 -->
          <div class="space-y-1 relative" @click.stop>
            <label class="font-semibold opacity-75">操作系统</label>
            <button
              type="button"
              @click="toggleDropdown('os')"
              
              class="bg-white border-[var(--border-color)] text-zinc-900 w-full px-3 py-2 rounded-xl border flex items-center justify-between"
            >
              <div class="flex items-center gap-2 truncate">
                <img :src="getOsMeta(editingForm.vpsOs).logo" class="w-4 h-4 object-contain" />
                <span class="truncate">{{ editingForm.vpsOs }}</span>
              </div>
              <AppIcon name="expand_more" size="14" class="opacity-60" />
            </button>
            <div
              v-if="openDropdownName === 'os'"
              
              class="bg-white border-[var(--border-color)] absolute left-0 right-0 top-full mt-1 z-50 rounded-xl border shadow-xl max-h-56 overflow-y-auto p-1"
            >
              <button
                v-for="os in osCatalog"
                :key="os.name"
                type="button"
                @click="editingForm.vpsOs = os.name; openDropdownName = null"
                :class="
                  editingForm.vpsOs === os.name
                    ? 'theme-accent-btn'
                    : 'hover:bg-black/[0.04]'
                "
                class="w-full px-2.5 py-2 rounded-lg flex items-center gap-2.5 text-left"
              >
                <img :src="os.logo" class="w-4 h-4 object-contain shrink-0" />
                <span class="truncate">{{ os.name }}</span>
              </button>
            </div>
          </div>

          <!-- 到期日：YYYY-MM-DD 日历表 + 每次/一次 -->
          <div class="space-y-1">
            <label class="font-semibold opacity-75">到期日 (YYYY-MM-DD &amp; 每次/一次)</label>
            <div class="flex items-center gap-1.5">
              <input
                v-model="editingForm.vpsExpiryDate"
                type="date"
                class="ios-input flex-1 px-2.5 py-2 rounded-xl"
              />
              <div
                
                class="theme-subtle border-[var(--border-color)] p-0.5 rounded-xl border flex shrink-0"
              >
                <button
                  type="button"
                  @click="editingForm.vpsExpiryCycle = '每次'"
                  :class="
                    editingForm.vpsExpiryCycle === '每次' ? 'theme-accent-btn font-bold' : 'opacity-70'
                  "
                  class="px-2.5 py-1.5 rounded-lg text-[0.7rem] spring-btn"
                >
                  每次
                </button>
                <button
                  type="button"
                  @click="editingForm.vpsExpiryCycle = '一次'"
                  :class="
                    editingForm.vpsExpiryCycle === '一次' ? 'theme-accent-btn font-bold' : 'opacity-70'
                  "
                  class="px-2.5 py-1.5 rounded-lg text-[0.7rem] spring-btn"
                >
                  一次
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- 第四行：核心数 | 运行内存(单位默认是GB) | 磁盘内存(单位默认是GB) -->
        <div class="grid grid-cols-3 gap-3">
          <div class="space-y-1">
            <label class="font-semibold opacity-75">核心数</label>
            <div class="relative">
              <input
                v-model="editingForm.vpsCores"
                type="number"
                min="1"
                placeholder="2"
                class="ios-input w-full pl-3 pr-10 py-2 rounded-xl"
              />
              <span class="absolute right-3 top-1/2 -translate-y-1/2 opacity-50 font-bold">核</span>
            </div>
          </div>
          <div class="space-y-1">
            <label class="font-semibold opacity-75">运行内存</label>
            <div class="relative">
              <input
                v-model="editingForm.vpsRam"
                type="number"
                min="1"
                placeholder="4"
                class="ios-input w-full pl-3 pr-10 py-2 rounded-xl"
              />
              <span class="absolute right-3 top-1/2 -translate-y-1/2 text-accent font-bold">GB</span>
            </div>
          </div>
          <div class="space-y-1">
            <label class="font-semibold opacity-75">磁盘内存</label>
            <div class="relative">
              <input
                v-model="editingForm.vpsDisk"
                type="number"
                min="1"
                placeholder="80"
                class="ios-input w-full pl-3 pr-10 py-2 rounded-xl"
              />
              <span class="absolute right-3 top-1/2 -translate-y-1/2 text-accent font-bold">GB</span>
            </div>
          </div>
        </div>

        <!-- 第五行：用户名 | 登录密码（支持调用密码生成器弹窗） -->
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div class="space-y-1">
            <label class="font-semibold opacity-75">用户名</label>
            <input
              v-model="editingForm.sshUser"
              type="text"
              placeholder="root"
              class="ios-input w-full px-3 py-2 rounded-xl"
            />
          </div>
          <div class="space-y-1">
            <div class="flex justify-between items-center">
              <label class="font-semibold opacity-75">登录密码</label>
              <button
                type="button"
                @click="openGeneratorModal(true)"
                class="text-accent hover:underline font-semibold"
              >
                随机生成强密码
              </button>
            </div>
            <input
              v-model="editingForm.password" data-testid="item-password"
              type="text"
              class="ios-input w-full px-3 py-2 rounded-xl"
            />
          </div>
        </div>

        <!-- 第六行：SSH 私钥（支持 Markdown 渲染） -->
        <div class="space-y-1">
          <label class="font-semibold opacity-75">SSH 私钥（支持 Markdown 语法，保存后自动渲染）</label>
          <textarea
            v-model="editingForm.markdownContent"
            rows="4"
            placeholder="```ssh\n-----BEGIN OPENSSH PRIVATE KEY-----\n...\n-----END OPENSSH PRIVATE KEY-----\n```"
            class="ios-input w-full px-3 py-2 rounded-xl"
          ></textarea>
        </div>
      </div>

      <!-- ==================== 表单类型 C：银行卡（严格 5 行布局） ==================== -->
      <div v-else-if="editingForm.type === 'bank'" class="space-y-3.5 text-xs">
        <!-- 第一行：条目名称 | 所属文件夹(图标+名称) -->
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div class="space-y-1">
            <label class="font-semibold opacity-75">条目名称 *</label>
            <input
              v-model="editingForm.title" data-testid="item-title"
              type="text"
              placeholder="如：招行全币种信用卡"
              class="ios-input w-full px-3 py-2 rounded-xl"
            />
          </div>

          <FolderSelect v-model="editingForm.folderId" />
        </div>

        <!-- 第二行：姓名 | 类型(中国银行、招商银行、Visa、Mastercard等，加载图标+名称) -->
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div class="space-y-1">
            <label class="font-semibold opacity-75">姓名</label>
            <input
              v-model="editingForm.cardHolder"
              type="text"
              placeholder="ZHANG SAN"
              class="ios-input w-full px-3 py-2 rounded-xl"
            />
          </div>

          <!-- 银行卡类型自定义带图标下拉框 -->
          <div class="space-y-1 relative" @click.stop>
            <label class="font-semibold opacity-75">类型</label>
            <button
              type="button"
              @click="toggleDropdown('bankType')"
              
              class="bg-white border-[var(--border-color)] text-zinc-900 w-full px-3 py-2 rounded-xl border flex items-center justify-between"
            >
              <div class="flex items-center gap-2 truncate">
                <img
                  :src="getBankMeta(editingForm.cardType).logo"
                  class="w-4 h-4 object-contain rounded-sm"
                />
                <span class="truncate">{{ editingForm.cardType }}</span>
              </div>
              <AppIcon name="expand_more" size="14" class="opacity-60" />
            </button>
            <div
              v-if="openDropdownName === 'bankType'"
              
              class="bg-white border-[var(--border-color)] absolute left-0 right-0 top-full mt-1 z-50 rounded-xl border shadow-xl max-h-56 overflow-y-auto p-1"
            >
              <button
                v-for="b in bankCatalog"
                :key="b.name"
                type="button"
                @click="editingForm.cardType = b.name; openDropdownName = null"
                :class="
                  editingForm.cardType === b.name
                    ? 'theme-accent-btn'
                    : 'hover:bg-black/[0.04]'
                "
                class="w-full px-2.5 py-2 rounded-lg flex items-center gap-2.5 text-left"
              >
                <img :src="b.logo" class="w-4 h-4 object-contain rounded-sm shrink-0" />
                <span class="truncate">{{ b.name }}</span>
              </button>
            </div>
          </div>
        </div>

        <!-- 第三行：银行卡卡号 -->
        <div class="space-y-1">
          <label class="font-semibold opacity-75">银行卡卡号 *</label>
          <input
            v-model="editingForm.cardNumber"
            type="text"
            placeholder="6214 8302 8800 9910"
            class="ios-input w-full px-3 py-2 rounded-xl"
          />
        </div>

        <!-- 第四行：有效期(YYYY-MM-DD 日历表，与 VPS 到期日同款) | 安全码 | 交易密码 -->
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div class="space-y-1">
            <label class="font-semibold opacity-75">有效期 (YYYY-MM-DD)</label>
            <input
              v-model="editingForm.cardExpiry"
              type="date"
              class="ios-input w-full px-2.5 py-2 rounded-xl"
            />
          </div>

          <div class="space-y-1">
            <label class="font-semibold opacity-75">安全码</label>
            <input
              v-model="editingForm.cardCvv"
              type="text"
              placeholder="886"
              class="ios-input w-full px-3 py-2 rounded-xl"
            />
          </div>

          <div class="space-y-1">
            <label class="font-semibold opacity-75">交易密码</label>
            <input
              v-model="editingForm.password" data-testid="item-password"
              type="text"
              placeholder="6位交易密码"
              class="ios-input w-full px-3 py-2 rounded-xl"
            />
          </div>
        </div>

        <!-- 第五行：备注（支持 Markdown 渲染） -->
        <div class="space-y-1">
          <label class="font-semibold opacity-75">备注（支持 Markdown 语法，保存后自动渲染）</label>
          <textarea
            v-model="editingForm.markdownContent"
            rows="4"
            placeholder="支持 Markdown 格式记录账单日、年费政策或开户支行..."
            class="ios-input w-full px-3 py-2 rounded-xl"
          ></textarea>
        </div>
      </div>

      <!-- ==================== 表单类型 D：安全笔记 ==================== -->
      <div v-else-if="editingForm.type === 'note'" class="space-y-3.5 text-xs">
        <!-- 第一行：条目名称 | 所属文件夹(图标+名称) -->
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div class="space-y-1">
            <label class="font-semibold opacity-75">条目名称 *</label>
            <input
              v-model="editingForm.title" data-testid="item-title"
              type="text"
              placeholder="如：硬件冷钱包助记词备份"
              class="ios-input w-full px-3 py-2 rounded-xl"
            />
          </div>

          <FolderSelect v-model="editingForm.folderId" />
        </div>

        <!-- 备注（支持 Markdown 语法，保存后自动渲染） -->
        <div class="space-y-1">
          <label class="font-semibold opacity-75">备注（支持 Markdown 语法，保存后自动渲染）</label>
          <textarea
            v-model="editingForm.markdownContent"
            rows="6"
            placeholder="在此输入支持 Markdown 的安全笔记内容..."
            class="ios-input w-full px-3 py-2 rounded-xl"
          ></textarea>
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
          @click="saveItem()" data-testid="save-item"
          class="px-5 py-2 rounded-xl theme-accent-btn text-xs font-semibold shadow-sm"
        >
          保存条目
        </button>
      </div>
    </div>
  </div>
</template>
