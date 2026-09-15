import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // The AgentPrism UI under `src/components/agent-prism` is vendored from
      // the same revision as its data/types packages, so the published-name
      // imports resolve to the vendored sources (see agent-prism/LOCAL.md).
      "@evilmartians/agent-prism-data": fileURLToPath(
        new URL("./src/components/agent-prism/data/index.ts", import.meta.url)
      ),
      "@evilmartians/agent-prism-types": fileURLToPath(
        new URL("./src/components/agent-prism/types/index.ts", import.meta.url)
      ),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ["react", "react-dom", "react-router-dom", "@tanstack/react-query"],
          charts: ["recharts"],
        },
      },
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
