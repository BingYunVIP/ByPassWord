<script setup>
import AppIcon from './AppIcon.vue'
import { useVault } from '../../stores/vault'

defineProps({
  item: { type: Object, required: true },
  // 图片完整类名（列表：w-6 h-6 object-contain rounded-sm / 详情：w-7 h-7 object-contain）
  imgClass: { type: String, default: 'w-6 h-6 object-contain rounded-sm' },
  // Material 图标尺寸类
  iconClass: { type: String, default: 'text-xl' },
  // 列表选中态影响回退图标颜色
  selected: { type: Boolean, default: false }
})

const {
  getFaviconUrl,
  getOsMeta,
  getBankMeta,
  getItemFallbackIconName,
  getItemFallbackIconColor,
  faviconErrorMap
} = useVault()
</script>

<template>
  <!-- 网站：自动抓取网站 Favicon -->
  <img
    v-if="item.type === 'website' && getFaviconUrl(item.url) && !faviconErrorMap[item.id]"
    :src="getFaviconUrl(item.url)"
    @error="faviconErrorMap[item.id] = true"
    :class="imgClass"
    alt="icon"
  />
  <!-- VPS：显示所选操作系统的彩色品牌图标 -->
  <img
    v-else-if="item.type === 'vps' && getOsMeta(item.vpsOs).logo"
    :src="getOsMeta(item.vpsOs).logo"
    :class="imgClass.replace(' rounded-sm', '')"
    alt="os"
  />
  <!-- 银行卡：显示所选银行/卡组织的彩色图标 -->
  <img
    v-else-if="
      item.type === 'bank' &&
      getBankMeta(item.cardType).logo &&
      !faviconErrorMap['bank_' + item.id]
    "
    :src="getBankMeta(item.cardType).logo"
    @error="faviconErrorMap['bank_' + item.id] = true"
    :class="imgClass"
    alt="bank"
  />
  <AppIcon
    :name="getItemFallbackIconName(item)"
    v-else
    :size="iconClass"
    :class="getItemFallbackIconColor(item, selected)"
  />
</template>
