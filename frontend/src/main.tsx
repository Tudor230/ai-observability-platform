import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import App from "./App";

import "@fontsource/geist-sans/400.css";
import "@fontsource/geist-sans/500.css";
import "@fontsource/geist-sans/600.css";
import "@fontsource/geist-mono/400.css";

// Style order matters: `base.css` pulls in Tailwind's preflight and the
// dashboard's element styles, followed by the Phoenix tokens and components,
// the vendored AgentPrism theme plus its token remap, and Tailwind utilities.
import "./theme/tokens.css";
import "./theme/base.css";
import "./theme/components.css";
import "./theme/layout.css";
import "./components/agent-prism/theme/theme.css";
import "./theme/agent-prism.css";
import "./theme/tailwind-utilities.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, staleTime: 15_000 } },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
