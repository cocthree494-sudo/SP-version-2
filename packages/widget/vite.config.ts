import preact from "@preact/preset-vite";
import { defineConfig } from "vite";
import { resolve } from "node:path";

export default defineConfig({
  plugins: [preact()],
  build: {
    rollupOptions: {
      input: {
        loader: resolve(import.meta.dirname, "src/loader.ts"),
        widget: resolve(import.meta.dirname, "src/widget.tsx"),
      },
      output: {
        entryFileNames: "[name].js",
        chunkFileNames: "chunks/[name]-[hash].js",
        assetFileNames: "assets/[name]-[hash][extname]",
      },
    },
  },
});
