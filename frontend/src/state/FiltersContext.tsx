import { createContext, useContext, useState, type ReactNode } from "react";
import type { Filters } from "../api/types";

const FiltersContext = createContext<{
  filters: Filters;
  setFilters: (f: Filters) => void;
}>({ filters: { days: 30 }, setFilters: () => {} });

export function FiltersProvider({ children }: { children: ReactNode }) {
  const [filters, setFilters] = useState<Filters>({ days: 30 });
  return (
    <FiltersContext.Provider value={{ filters, setFilters }}>
      {children}
    </FiltersContext.Provider>
  );
}

export function useFilters() {
  return useContext(FiltersContext);
}
