import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/data": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://localhost:8000",
        ws: true,
      },
      "/audit": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/weather": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
