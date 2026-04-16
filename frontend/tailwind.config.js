/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        navy: { DEFAULT: '#16213e', dark: '#0f3460' },
        accent: { DEFAULT: '#e94560', light: '#ff6b6b' },
      },
    },
  },
  plugins: [],
}
