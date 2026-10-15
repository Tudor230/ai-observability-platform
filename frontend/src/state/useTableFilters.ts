import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

/** The card-owned subset of the read filters. */
export interface TableFilters {
  project_id?: string;
  workflow?: string;
}

export const TABLE_FILTER_FIELDS = ["project_id", "workflow"] as const;
export type TableFilterField = (typeof TABLE_FILTER_FIELDS)[number];

/**
 * Per-table filters (refinements v3): each card owns its own scope, stored in
 * namespaced URL params (`<card>_project_id`, `<card>_workflow`) so filtered
 * views stay shareable. The page-level `days` window stays in `FiltersContext`.
 */
export function useTableFilters(card: string) {
  const [params, setParams] = useSearchParams();

  const filters = useMemo<TableFilters>(() => {
    const next: TableFilters = {};
    for (const field of TABLE_FILTER_FIELDS) {
      const value = params.get(`${card}_${field}`);
      if (value) next[field] = value;
    }
    return next;
  }, [params, card]);

  const setFilter = useCallback(
    (field: TableFilterField, value?: string) => {
      const next = new URLSearchParams(params);
      const key = `${card}_${field}`;
      if (value) next.set(key, value);
      else next.delete(key);
      setParams(next, { replace: true });
    },
    [card, params, setParams]
  );

  const clear = useCallback(() => {
    const next = new URLSearchParams(params);
    for (const field of TABLE_FILTER_FIELDS) next.delete(`${card}_${field}`);
    setParams(next, { replace: true });
  }, [card, params, setParams]);

  const activeCount = TABLE_FILTER_FIELDS.filter((field) => filters[field]).length;
  return { filters, setFilter, clear, activeCount };
}
