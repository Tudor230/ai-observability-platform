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
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["src/test/setup.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      include: ["src/**"],
      exclude: [
        // Vendored AgentPrism UI/data/types (see components/agent-prism/LOCAL.md).
        "src/components/agent-prism/**",
        "src/main.tsx",
        "src/vite-env.d.ts",
        "src/test/**",
        "src/**/*.test.{ts,tsx}",
      ],
      // Gate (ticket 16): lines/statements meet the 80% goal; functions and
      // branches were raised from the ticket-14 baseline (41.79/67.01) to the
      // measured levels minus margin and remain a documented exception
      // (JSX-callback density keeps them below 80 without diminishing value).
      thresholds: {
        statements: 80,
        branches: 70,
        functions: 65,
        lines: 80,
      },
    },
  },
});
