import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const backendPort = env.BACKEND_PORT || "8787";
  const frontendPort = Number(env.FRONTEND_PORT || "5373");
  const backendUrl = env.BACKEND_URL || `http://127.0.0.1:${backendPort}`;
  const backendWsUrl = backendUrl.replace(/^http/, "ws");

  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    server: {
      port: frontendPort,
      strictPort: false,
      proxy: {
        "/api": backendUrl,
        "/ws": { target: backendWsUrl, ws: true },
        "/health": backendUrl,
      },
    },
  };
});
