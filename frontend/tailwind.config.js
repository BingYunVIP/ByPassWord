/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{vue,js}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Maple Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
        mono: ['"Maple Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace']
      },
      colors: {
        // 品牌色走 CSS 变量 + RGB 分量，保证 bg-accent/15 这类透明度修饰符可用。
        // 用扁平键而非嵌套对象：嵌套的 hover 会与 Tailwind 的 hover 变体解析冲突。
        accent: 'rgb(var(--accent-rgb) / <alpha-value>)',
        'accent-hover': 'rgb(var(--accent-hover-rgb) / <alpha-value>)',
        'accent-brandEnd': 'rgb(var(--accent-brand-end-rgb) / <alpha-value>)',
        // 旧色阶保留为同值别名，避免历史 class 失效；P5 完成后可删
        apple: {
          blue: '#0071E3',
          blueHover: '#0077ED'
        }
      }
    }
  },
  plugins: []
}
