# 14 — Frontend: test infrastructure + coverage gate

Type: task
Status: resolved
Blocked by: —
Area: audit item 12 (coverage)
Estimate: M

## Goal

Enable component/page testing (jsdom + React Testing Library) and coverage
measurement in the frontend, with a CI gate that starts at the measured
baseline and is ratcheted to the 80% target by ticket 16.

## Changes

1. **Dev dependencies** (`frontend/package.json`, `npm install`):
   `@testing-library/react@^16`, `@testing-library/user-event@^14`,
   `@testing-library/jest-dom@^6`, `jsdom@^25`,
   `@vitest/coverage-v8@3.2.7` (matching the installed vitest).
2. **Vitest config** (`vite.config.ts` test block):
   - `include: ["src/**/*.test.{ts,tsx}"]`;
   - keep `environment: "node"` for data/`lib` tests, switch `**/*.test.tsx` to
     jsdom (`environmentMatchGlobs` or a dedicated project);
   - `setupFiles: ["src/test/setup.ts"]` registering jest-dom + a
     `matchMedia`/`ResizeObserver` polyfill (Recharts needs them) and
     silencing known noise;
   - coverage: provider `v8`, `reporter: ["text", "lcov"]`,
     `include: ["src/**"]`, exclude `src/components/agent-prism/**`
     (vendored), `src/main.tsx`, `src/vite-env.d.ts`, `src/test/**`.
3. **Test harness** (`src/test/harness.tsx`):
   - `renderWithProviders(ui, {route, profile})` wrapping `MemoryRouter` +
     `QueryClientProvider` (fresh client per test, retries off) + optional
     mocked `AuthContext`; helper to build profiles/roles.
   - `mockApi()` helper: `vi.mock("../api/client")` factory with per-test
     overrides (keep in the test files, not a global mock).
4. **Scripts + CI**
   - `package.json`: `"test": "vitest run"`, `"test:coverage": "vitest run --coverage"`.
   - `.github/workflows/frontend.yml`: run `npm run test:coverage`; enforce the
     baseline thresholds via config or CLI
     (`--coverage.thresholds.lines=<baseline>`), with a comment marking the
     ratchet plan to 80 (ticket 16).
5. **Documentation**: a short "Testing" section in `frontend/README.md`
   (how to run, the harness, what is excluded and why).

## Acceptance

- `npm run test` still runs all existing node tests; new `.tsx` tests run in
  jsdom with RTL.
- `npm run test:coverage` prints a coverage table for non-vendor `src/**` and
  fails CI below the configured baseline.
- A trivial smoke test (e.g. `Table` renders) proves the harness end-to-end and
  is included as the seed test.
- CI frontend job completes green with the same gates as before plus coverage.

## Tests

- The seed smoke test + harness self-check (build a component with providers).

## Comments

Implemented. Dev deps added (`@testing-library/react@16`, `user-event`,
`jest-dom`, `jsdom@25`, `@vitest/coverage-v8@3.2.7`); Vitest runs in jsdom with
`src/test/setup.ts` (jest-dom matchers + ResizeObserver/matchMedia/
scrollIntoView polyfills) and includes `*.test.{ts,tsx}`. Coverage: v8 over
`src/**` excluding vendored `agent-prism/**`, `main.tsx`, `test/**`; baseline
thresholds set from the measured run (**6.85% lines/statements, 41.79%
functions, 67.01% branches** — ratchet to 80 is ticket 16). `npm run
test:coverage` added; CI frontend job now runs it. `renderWithProviders`
harness + `profile()` helper in `src/test/harness.tsx`; seed test
`components/core/Table.test.tsx`.

Evidence: `npm test` (416 passed, 25 files), `npm run test:coverage` passes the
gate, `npm run lint` + `npm run build` clean; README Testing section added.
