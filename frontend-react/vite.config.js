import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins:[react()],
  base:'/cryptosniper/static/react/',
  build:{
    outDir:'../backend/static/react',
    emptyOutDir:true,
    rollupOptions:{output:{entryFileNames:'app.js',chunkFileNames:'chunk-[name].js',assetFileNames:(asset)=>asset.name?.endsWith('.css')?'app.css':'[name][extname]'}}
  }
})
