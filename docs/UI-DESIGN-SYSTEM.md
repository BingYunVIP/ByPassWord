# 密码库 UI 设计系统

> 本文档从 `Third/ByPW.html`（原始单文件版本）与当前 Vue 3 工程中**实测提取**，是后续任何 UI 改动的唯一风格基准。
> 修改 UI 前请先读第 10 节「验收清单」，提交前逐条对照。
> 最后更新：2026-11-01

---

## 0. 适用范围（强制）

1. 本项目的视觉语言是 **Apple HIG（macOS Sonoma）毛玻璃风格 + Maple Mono 等宽字体**，不是通用后台模板。
2. 新增任何界面元素，必须复用本文档中的色板、字号阶梯、圆角、阴影、动效曲线。
3. **禁止**引入新的主色、新字体、新圆角体系、新阴影体系；如需新增，必须先改本文档并说明理由。
4. 现有 90% 以上的视觉由 Tailwind 原子类表达（`bg-[#007AFF]/15`、`text-[0.68rem]` 等），请沿用同一写法，不要另起一套 CSS 类名。

---

## 1. 设计基调

| 维度 | 取值 | 说明 |
| --- | --- | --- |
| 风格 | Apple HIG / macOS Sonoma | 大圆角、强毛玻璃、克制的阴影、系统蓝主色 |
| 质感 | 半透明层叠 | 壁纸 → 主窗口（玻璃）→ 卡片（近实心）→ 控件 |
| 字体 | Maple Mono（全站唯一字体） | 等宽、开发者气质，`!important` 全局强制 |
| 密度 | 紧凑 | 主体字号 `text-xs`（0.75rem），辅助信息 0.62–0.70rem |
| 主色 | `#007AFF`（系统蓝） | 唯一强调色，全站 130+ 处使用 |
| 主题 | 明 / 暗双主题 | 由 `.dark` class 驱动，所有颜色成对书写 |

---

## 2. 色彩系统

### 2.1 品牌色

| 名称 | 色值 | 用途 |
| --- | --- | --- |
| Apple Blue | `#007AFF` | 主按钮、选中态、链接、强调数字、图标主色 |
| Apple Blue Hover | `#0062CC` | 主按钮 hover |
| Apple Indigo | `#5856D6` | 仅用于 Logo / 锁定图标的 `bg-gradient-to-br / to-tr` 渐变终点 |
| ChatGPT Green | `#10A37F` | 中转站文件夹图标的兜底色（实际用本地 WebP） |

### 2.2 语义色（Tailwind 调色板，只允许这些）

| 语义 | 类名 | 典型场景 |
| --- | --- | --- |
| 成功 / 已解锁 / 2FA | `emerald-500` `emerald-600` | 状态点、2FA 标签、健康度、安全码图标 |
| 危险 / 删除 / 锁定 | `rose-500` `rose-600` `rose-400` | 删除按钮、锁定按钮、CVV、失败状态 |
| 提醒 / 时间 / 密钥 | `amber-500` `amber-400` `amber-300` | 倒计时图标、恢复密钥、收藏星标、显示密码按钮 |
| VPS / 网络 | `purple-500` | VPS 类型标签、SSH 相关图标 |
| 账号 / 密码 | `indigo-500` | 密码字段图标、程序员文件夹 |
| 系统 / 资源 | `cyan-500` `teal-500` `sky-500` | 操作系统、终端、云同步 |
| 笔记 / 备注 | `amber-500` `orange-500` | 安全笔记类型 |

> 颜色只表达**语义**，不表达"好看"：蓝色=可操作/主信息，绿色=安全/成功，红色=破坏性，琥珀=需注意/时间。

### 2.3 中性色

正文与背景统一使用 Tailwind `zinc` 色阶（不使用 gray / slate）：

- 亮色主题：正文 `text-zinc-900`，次级 `text-zinc-500`，三级 `text-zinc-400`
- 暗色主题：正文 `text-zinc-100`，次级 `text-zinc-400`，三级 `text-zinc-500`

### 2.4 玻璃层（核心质感，定义在 `src/styles/main.css`）

| 层 | 亮色 | 暗色 |
| --- | --- | --- |
| 主窗口 `.hig-window-light/dark` | `rgba(246,247,249,0.82)` + `blur(40px) saturate(190%)` + 外阴影 `0 24px 60px -12px rgba(0,0,0,.18)` + 内描边 `inset 0 0 0 1px rgba(255,255,255,.75)` | `rgba(24,24,28,0.84)` + 同模糊 + `0 24px 60px -12px rgba(0,0,0,.75)` + `inset 0 0 0 1px rgba(255,255,255,.1)` |
| 详情卡片 `.hig-card-light/dark` | `rgba(255,255,255,0.88)` + 描边 `rgba(0,0,0,.07)` + `0 2px 10px rgba(0,0,0,.03)` | `rgba(38,38,43,0.80)` + 描边 `rgba(255,255,255,.08)` + `0 4px 14px rgba(0,0,0,.28)` |
| 弹窗遮罩 | `bg-black/50` + `backdrop-blur-sm` | 同左 |
| 锁定遮罩 | `bg-white/75` + `backdrop-blur-2xl` | `bg-black/75` + `backdrop-blur-2xl` |

### 2.5 壁纸背景

```css
/* 亮色：三处柔光 + 冷灰底 */
.macos-bg-light {
  background:
    radial-gradient(at 10% 12%, rgba(0,122,255,.16) 0, transparent 50%),
    radial-gradient(at 88% 15%, rgba(88,86,214,.14) 0, transparent 50%),
    radial-gradient(at 75% 88%, rgba(16,185,129,.13) 0, transparent 50%),
    #E6EBF2;
}
/* 暗色：#090A0F 底 + 更高透明度的三处柔光 */
```

### 2.6 透明度阶梯（必须遵守，否则层次会糊）

| 用途 | 亮色 | 暗色 |
| --- | --- | --- |
| 大面积面板 | `bg-white/30` ~ `bg-white/55` | `bg-white/[0.01]` ~ `bg-white/[0.02]` |
| 次级面板（左栏） | `bg-white/40` | `bg-black/20` |
| 控件底 | `bg-white/85` `bg-black/5` | `bg-white/10` `bg-white/[0.05]` |
| 主色浅底 | `bg-[#007AFF]/15` | 同左（主色浅底不区分主题） |
| 分隔线 | `border-black/[0.08]` `border-black/[0.06]` | `border-white/10` |

---

## 3. 排版

### 3.1 字体

```css
/* 全局强制，含 !important，不允许局部覆盖 */
*, body, input, button, select, textarea, code, pre {
  font-family: 'Maple Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace !important;
}
/* 图标字体是唯一豁免（同样本地自托管，见 7.1） */
.material-symbols-rounded { font-family: 'Material Symbols Rounded Variable' !important; }
```

两套字体均**本地打包**，不依赖任何外部字体 CDN：

- Maple Mono：`@fontsource/maple-mono`（400/500/600/700）
- Material Symbols Rounded：`@fontsource-variable/material-symbols-rounded/fill.css`（可变轴 FILL + wght）

### 3.2 动态根字号（关键）

```js
// 以 2048px 视口对应 18px 为基准线性缩放，并限制在 13.5–22px
document.documentElement.style.fontSize =
  Math.max(13.5, Math.min(22, (window.innerWidth / 2048) * 18)) + 'px'
```

**所有尺寸都用 rem**，因此整个界面会随窗口等比缩放。新增 UI 时不要写死 `px`。

### 3.3 字号阶梯（rem，实际像素随根字号变化）

| 层级 | 类名 | 用途 |
| --- | --- | --- |
| 微标 | `text-[0.62rem]` | 列表右侧标签（2FA/未设2FA）、审计计数、顶栏倒计时 |
| 小标 | `text-[0.65rem]` | KDF 徽章、文件夹计数、到期周期标签 |
| 辅助 | `text-[0.68rem]` | 副行说明、弹窗副标题、卡片数量 |
| 小正文 | `text-[0.7rem]` | 审计日志行、分段按钮 |
| 正文（默认） | `text-xs`（0.75rem） | 按钮、输入框、标签、列表主行 |
| 数值 | `text-sm`（0.875rem） | 详情卡片数值、文件夹名、弹窗标题 |
| 区块标题 | `text-base`（1rem） | 详情标题、锁定标题 |
| 强调数字 | `text-lg`（1.125rem） | TOTP 验证码 |
| 图标 | `text-xs` ~ `text-3xl` | Material 图标尺寸 |

### 3.4 字重与字距

- 标题：`font-bold`
- 强调：`font-semibold`
- 常规：`font-medium`
- 大标题加 `tracking-tight`；验证码 / 卡号加 `tracking-wider` 或 `tracking-widest`
- 副标题常用 `opacity-60` / `opacity-75` 代替换色

---

## 4. 布局与栅格

```
┌──────────────────────────────────────────────────────────┐
│ Header  h-[4.2rem]                                        │
│  ├ 左区 w-[16.5rem]（Logo + 标题 + 状态/时间/KDF 徽章）    │
│  └ 右区 flex-1（搜索框 max-w-md | 按钮组 gap-2）           │
├──────────┬──────────────┬────────────────────────────────┤
│ 左栏      │ 中栏          │ 右栏                            │
│ w-[16.5rem]│ w-[22rem]    │ flex-1，内容 max-w-3xl mx-auto  │
│ 文件夹    │ 类型筛选+列表 │ 详情卡片，p-6 lg:p-8            │
└──────────┴──────────────┴────────────────────────────────┘
```

- 三栏均为 `shrink-0`（右栏除外），总高度 `h-full`，各栏独立滚动。
- 间距节奏：`p-3`（栏内边距）/ `p-4`（小卡片）/ `p-5`（标准卡片）/ `gap-2`（按钮组）/ `gap-4`（卡片内图文）/ `space-y-4`（卡片之间）。
- 响应式只在窗口极窄时生效（`sm:` 断点），主体按桌面优先设计。

---

## 5. 形状

| 元素 | 圆角 | 示例 |
| --- | --- | --- |
| 小按钮 / 图标按钮 / 下拉项 | `rounded-lg` | 类型筛选、下拉选项 |
| 标准控件（按钮、输入框、小卡片） | `rounded-xl` ← **最常用（106 处）** | 顶栏按钮、输入框、列表项 |
| 卡片 / 弹窗 / 主窗口 | `rounded-2xl`（36 处） | 详情卡片、模态框、主窗口 |
| 大图标底板 | `rounded-3xl` | 锁定遮罩的锁图标 |
| 胶囊 | `rounded-full` | Toast、状态点、进度条 |
| 品牌图标 | `rounded-sm` ~ `rounded` | favicon、文件夹自定义图片 |

描边：统一 `border` + 主题化颜色（亮 `border-black/10`、暗 `border-white/10`），不使用粗边框。
阴影：卡片用 `.hig-card-*`；交互控件用 `shadow-sm`；弹窗用 `shadow-2xl`；主窗口用 `.hig-window-*`。

---

## 6. 动效

| 场景 | 参数 |
| --- | --- |
| 通用交互（**所有可点元素**） | `.spring-btn { transition: all .18s cubic-bezier(.25,1,.5,1) }` |
| 主题切换 / 窗口状态 | `transition-colors duration-300` / `transition-all duration-300` |
| 进度条 / TOTP 圆环 | `transition-all duration-500` |
| 状态点 | `animate-pulse` |
| 缩放反馈（窗口失焦） | `blur-xl scale-[0.99]` |

> 曲线固定为 `cubic-bezier(.25, 1, .5, 1)`（苹果式快速起步、柔和收尾），不要用 `ease-in-out` 或弹跳动画。

---

## 7. 图标系统

### 7.1 界面图标 = Material Symbols Rounded（本地自托管）

字体文件：`node_modules/@fontsource-variable/material-symbols-rounded/files/material-symbols-rounded-latin-fill-normal.woff2`（约 1.4MB，可变轴 `FILL` + `wght`）。

```css
.material-symbols-rounded {
  font-family: 'Material Symbols Rounded Variable' !important;
  font-size: 1.2rem;                                        /* 基准，靠 text-* 类覆盖 */
  font-variation-settings: 'FILL' 1, 'wght' 500, 'GRAD' 0, 'opsz' 24;
}
```

> 这组轴值与原先 Google Fonts 的请求参数 `opsz,wght,FILL,GRAD@24,500,1,0` 完全一致，因此替换为本地字体后渲染逐像素相同；`opsz`/`GRAD` 取字体默认值即可。

- 统一使用**填充（FILL=1）**风格，不混用描边风格。
- 尺寸：`text-xs`（标签内）→ `text-sm`/`text-base`（常规）→ `text-lg`/`text-xl`（卡片图标）→ `text-2xl`/`text-3xl`（大图标）。
- 颜色跟随语义色（见 2.2），**不要给图标单独上品牌色以外的颜色**。
- 选中态图标强制 `text-white`。
- 新增图标只写连字名（如 `verified_user`），不要引入图片或 SVG。

### 7.2 品牌图标 = 本地 WebP

- 位置：`src/assets/icons/*.webp`，128×128 透明背景，由 `npm run icons` 从官网抓取。
- 命名：`os-*`（操作系统）、`bank-*`（银行）、`card-*`（卡组织）、`site-*`（站点）。
- 展示尺寸：`w-4 h-4`（行内）/ `w-5 h-5` / `w-6 h-6`（列表）/ `w-7 h-7`（详情大图标）。
- 通过 `getOsMeta()` / `getBankMeta()` / `getFaviconUrl()` 取用，不要在组件里硬编码路径。
- 新增品牌：在 `scripts/fetch-icons.mjs` 的 `TARGETS` 中加官网地址 → `npm run icons` → 在 `catalog.js` 中登记。

### 7.3 禁止

- ❌ 用 emoji 当图标
- ❌ 引入第三方图标库（Font Awesome、Heroicons 等）
- ❌ 引用外部图标 / 字体 CDN（Google Fonts、simpleicons 等；favicon 服务仅作为任意站点的运行时兜底）

---

## 8. 组件范式

### 8.1 详情卡片行（最核心）

```html
<div :class="isDark ? 'hig-card-dark' : 'hig-card-light'" class="p-5 rounded-2xl flex items-center justify-between gap-4">
  <div class="min-w-0 flex-1 space-y-1">
    <!-- 副行：小图标 + 说明（0.68–0.75rem，次级色） -->
    <div :class="isDark ? 'text-zinc-400' : 'text-zinc-500'" class="text-xs flex items-center gap-1.5">
      <span class="material-symbols-rounded text-base text-[#007AFF]">account_circle</span>
      <span>字段名</span>
    </div>
    <!-- 主行：数值（text-sm font-bold，可 select-all） -->
    <div class="text-sm font-bold break-all select-all">值</div>
  </div>
  <!-- 右侧：主色浅底按钮（15% 透明 → hover 实心白字） -->
  <button class="px-3.5 py-2 rounded-xl bg-[#007AFF]/15 text-[#007AFF] hover:bg-[#007AFF] hover:text-white text-xs font-semibold flex items-center gap-1.5 spring-btn">
    <span class="material-symbols-rounded text-base">content_copy</span><span>复制</span>
  </button>
</div>
```

### 8.2 按钮

| 类型 | 类名组合 |
| --- | --- |
| 主按钮 | `bg-[#007AFF] hover:bg-[#0062CC] text-white rounded-xl shadow-sm` |
| 次按钮 | 亮 `bg-white/85 hover:bg-white text-zinc-800 border-black/10`；暗 `bg-white/10 hover:bg-white/15 text-zinc-100 border-white/10` |
| 浅色主按钮 | `bg-[#007AFF]/15 text-[#007AFF] hover:bg-[#007AFF] hover:text-white` |
| 危险按钮 | 亮 `bg-rose-50 hover:bg-rose-100 text-rose-600 border-rose-200`；暗 `bg-rose-500/15 hover:bg-rose-500/25 text-rose-400 border-rose-500/25` |
| 图标按钮 | `w-9 h-9 rounded-xl border flex items-center justify-center` |

所有按钮必须带 `spring-btn`；文字 `text-xs font-semibold`（次要可 `font-medium`）。

### 8.3 徽章 / 标签

```html
<!-- 类型/状态徽章：0.62–0.65rem + 15% 语义色底 + 同色文字 -->
<span class="text-[0.62rem] px-2 py-0.5 rounded-md bg-emerald-500/15 text-emerald-500 font-bold">2FA</span>
<!-- 可点击徽章（如 KDF）：hover 变实心 -->
<span class="text-[0.65rem] px-1.5 py-0.5 rounded bg-[#007AFF]/15 text-[#007AFF] font-semibold cursor-pointer hover:bg-[#007AFF] hover:text-white spring-btn">Argon2id</span>
```

### 8.4 输入框 / 下拉框

```html
<input class="w-full px-3 py-2 rounded-xl text-xs border outline-none focus:border-[#007AFF] focus:ring-2 focus:ring-[#007AFF]/20"
       :class="isDark ? 'bg-white/10 text-white border-white/10' : 'bg-black/[0.05] text-zinc-900 border-black/5'" />
```

- 聚焦态统一：`focus:border-[#007AFF]` + 可选 `focus:ring-2 focus:ring-[#007AFF]/20`
- 日期类字段统一用原生 `<input type="date">`（YYYY-MM-DD），保持与 VPS 到期日一致。

### 8.5 列表项

- 容器：`p-3 rounded-xl flex items-center justify-between gap-3 cursor-pointer spring-btn`
- 未选中：亮 `hover:bg-white/75 text-zinc-900`；暗 `hover:bg-white/[0.06] text-zinc-100`
- 选中：`bg-[#007AFF] text-white shadow-sm`，内部次级文字转 `text-white/85`，标签转 `bg-white/25 text-white`
- 图标容器：`w-10 h-10 rounded-xl border flex items-center justify-center shrink-0 overflow-hidden shadow-sm`

### 8.6 弹窗

```html
<div class="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4" @click.self="close">
  <div :class="isDark ? 'hig-window-dark border-white/15 text-zinc-100' : 'hig-window-light border-black/10 text-zinc-900'"
       class="w-full max-w-2xl rounded-2xl border p-6 space-y-4 shadow-2xl">
```

- 层级：普通弹窗 `z-40`（条目编辑），生成器/文件夹/设置 `z-50`。
- 头部：图标 + 标题（`text-sm font-bold`）+ 右上 `close` 图标按钮。
- 底部操作：右对齐 `取消`（次按钮）+ 主操作（主按钮）。

### 8.7 Toast

```html
<div class="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 px-4 py-2 rounded-full bg-zinc-900/95 text-white text-xs font-semibold shadow-xl border border-white/15 flex items-center gap-2">
  <span class="material-symbols-rounded text-emerald-400 text-base">check_circle</span>
```

显示 2.3 秒，同一时刻只允许一个。

---

## 9. 明暗主题规则

1. 主题开关是**内层容器的 `.dark` class**（不是 `<html>`），配合 `macos-bg-dark / macos-bg-light`。
2. 任何颜色都必须成对书写：`:class="isDark ? '暗色' : '亮色'"`，不允许只写一半。
3. 主色 `#007AFF` 及其浅底 `bg-[#007AFF]/15` **在两种主题下保持一致**，保证品牌感。
4. 阴影在暗色下更重（见 2.4 表），因为暗色需要更深的层次分离。
5. 玻璃透明度在暗色下略高（0.84 vs 0.82），以维持可读性。

---

## 10. 新增 / 修改 UI 的验收清单

提交前逐条自检：

- [ ] 用的是 `.hig-card-*` / `.hig-window-*`，而不是自造背景色？
- [ ] 主色只有 `#007AFF` / `#0062CC`，没有引入新蓝？
- [ ] 字号来自第 3.3 节阶梯，没有出现 0.71rem 这类"随手值"？
- [ ] 圆角只用 `lg / xl / 2xl / 3xl / full`？
- [ ] 所有可点元素都有 `spring-btn`？
- [ ] 亮/暗两种主题都写了？都肉眼看过？
- [ ] 图标是 Material Symbols 或本地 WebP？没有 emoji、没有新图标库？
- [ ] 尺寸用 rem（Tailwind 默认即 rem），没有 `px` 硬编码？
- [ ] 交互后有空态 / 加载态 / 失败态？（列表空态已有范式：`folder_open` + 提示 + 新建入口）
- [ ] 文案是简洁中文，与现有语气一致（"新建条目""未设2FA""已解锁"）？

---

## 11. 禁止事项（反例）

| ❌ 不要 | ✅ 应该 |
| --- | --- |
| `bg-blue-500` 当主色 | `bg-[#007AFF]` |
| `rounded-md` 做卡片 | `rounded-2xl` |
| `shadow-lg` 做卡片 | `.hig-card-light / .hig-card-dark` |
| 新增渐变按钮 | 纯色主按钮 + `spring-btn` |
| 用 `transition: 0.3s ease` | `spring-btn` 的苹果曲线 |
| 图标用 SVG 内联或图标库 | Material Symbols 字体图标 |
| 只做亮色主题 | 亮暗成对 |
| 用 `px` 定尺寸 | rem / Tailwind 尺寸类 |

---

## 12. 快速参考

```
主色        #007AFF        主色 hover  #0062CC
渐变终点    #5856D6        壁纸亮      #E6EBF2      壁纸暗  #090A0F
成功        emerald-500    危险        rose-500     提醒    amber-500
正文        亮 zinc-900 / 暗 zinc-100
次级        亮 zinc-500 / 暗 zinc-400
圆角        控件 xl / 卡片 2xl / 胶囊 full
动效        cubic-bezier(.25, 1, .5, 1) · 0.18s
布局        16.5rem | 22rem | flex(≤48rem 内容宽)
根字号      13.5–22px 随视口缩放（2048px → 18px）
```
