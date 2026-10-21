import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

export default defineConfig({
  plugins: [react()],
  base: "/static/ui/",
  build: {
    outDir: resolve(__dirname, "../backend/static/ui"),
    emptyOutDir: true,
    sourcemap: false,
    rollupOptions: {
      input: resolve(__dirname, "src/main.jsx"),
      output: {
        entryFileNames: "app.js",
        chunkFileNames: "chunk-[hash].js",
        assetFileNames: (assetInfo) =>
          assetInfo.name && assetInfo.name.endsWith(".css") ? "app.css" : "asset-[name]-[hash][extname]",
      },
    },
  },
});
