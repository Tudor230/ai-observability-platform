# 01 — Stack & scaffold

Type: task
Status: resolved

## Question

Which frontend stack and project layout?

## Answer

React 18 + Vite 5 + TypeScript (strict), TanStack Query for server state,
React Router 6, Recharts for charts. Dark theme CSS tokens in 	heme.css.
Pages under src/pages/, API under src/api/, shared components under
src/components/. 
pm run build runs 	sc -b + vite build (CI gate).
