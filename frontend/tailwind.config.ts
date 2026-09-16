import type { Config } from "tailwindcss";

import { agentPrismTailwindColors } from "./src/components/agent-prism/theme";

/**
 * Tailwind is scoped to the vendored AgentPrism components. The dashboard's own
 * design system lives in `src/theme/` (plain CSS) — the two meet at the
 * `agentprism-*` color tokens, which are remapped to the Phoenix palette in
 * `src/theme/agent-prism.css`.
 */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: agentPrismTailwindColors,
    },
  },
  plugins: [],
} satisfies Config;
