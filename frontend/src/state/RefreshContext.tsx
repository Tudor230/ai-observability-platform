import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

const STORAGE_KEY = "aiobs.refresh";
const OPTIONS = [0, 30_000, 60_000, 300_000];

const RefreshContext = createContext<{
  /** Auto-refresh interval in ms; 0 = off. */
  interval: number;
  setIntervalMs: (ms: number) => void;
}>({ interval: 0, setIntervalMs: () => {} });

function readStored(): number {
  if (typeof localStorage === "undefined") return 0;
  const raw = Number(localStorage.getItem(STORAGE_KEY));
  return OPTIONS.includes(raw) ? raw : 0;
}

/** Dashboard auto-refresh cadence, persisted in localStorage (audit item 11). */
export function RefreshProvider({ children }: { children: ReactNode }) {
  const [interval, setIntervalState] = useState<number>(readStored);

  const setIntervalMs = useCallback((ms: number) => {
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(STORAGE_KEY, String(ms));
    }
    setIntervalState(OPTIONS.includes(ms) ? ms : 0);
  }, []);

  const value = useMemo(
    () => ({ interval, setIntervalMs }),
    [interval, setIntervalMs]
  );
  return <RefreshContext.Provider value={value}>{children}</RefreshContext.Provider>;
}

export function useRefresh() {
  return useContext(RefreshContext);
}

/** react-query `refetchInterval` value for dashboard queries. */
export function useRefetchInterval(): number | false {
  const { interval } = useRefresh();
  return interval > 0 ? interval : false;
}
