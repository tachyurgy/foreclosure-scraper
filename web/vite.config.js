import { defineConfig } from 'vite'
import preact from '@preact/preset-vite'

export default defineConfig({
  plugins: [preact()],
  base: '/foreclosure-scraper/',  // GitHub Pages base path
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
  }
})
