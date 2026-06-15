import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/data": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://127.0.0.1:8000",
        ws: true,
      },
      "/audit": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/weather": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/decisions": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/collaboration": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/whatif": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
