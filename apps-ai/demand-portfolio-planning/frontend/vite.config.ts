import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5248,
    strictPort: true,
    proxy: {
      "/runs": {
        target: "http://localhost:8138",
        changeOrigin: true,
      },
      "/api": {
        target: "http://localhost:8138",
        changeOrigin: true,
      },
    },
  },
});
