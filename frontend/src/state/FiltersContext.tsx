import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  type ReactNode,
} from "react";
import { useSearchParams } from "react-router-dom";
import type { Filters } from "../api/types";

const DEFAULT_DAYS = 30;

function parseFilters(params: URLSearchParams): Filters {
  const days = Number(params.get("days"));
  return {
    days: Number.isFinite(days) && days > 0 ? days : DEFAULT_DAYS,
    project_id: params.get("project_id") || undefined,
    client_id: params.get("client_id") || undefined,
    workflow: params.get("workflow") || undefined,
  };
}

const FiltersContext = createContext<{
  filters: Filters;
  setFilters: (f: Filters) => void;
}>({ filters: { days: DEFAULT_DAYS }, setFilters: () => {} });

/**
 * Global filters are URL-backed (ticket 02) so views are shareable and the
 * Manager drill-down links (?workflow=/?client_id=) feed the same state.
 * Other query params (search/sort/page on Engineering) are preserved.
 */
export function FiltersProvider({ children }: { children: ReactNode }) {
  const [params, setParams] = useSearchParams();
  const filters = useMemo(() => parseFilters(params), [params]);

  const setFilters = useCallback(
    (next: Filters) => {
      const search = new URLSearchParams(params);
      if (next.days && next.days !== DEFAULT_DAYS) search.set("days", String(next.days));
      else search.delete("days");
      for (const key of ["project_id", "client_id", "workflow"] as const) {
        const value = next[key];
        if (value) search.set(key, value);
        else search.delete(key);
      }
      setParams(search, { replace: true });
    },
    [params, setParams]
  );

  const value = useMemo(() => ({ filters, setFilters }), [filters, setFilters]);
  return <FiltersContext.Provider value={value}>{children}</FiltersContext.Provider>;
}

export function useFilters() {
  return useContext(FiltersContext);
}
