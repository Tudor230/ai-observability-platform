import {
  createContext,
  useCallback,
  useContext,
  useState,
  type ReactNode,
} from "react";

export type Role = "all" | "engineer" | "manager" | "executive";

const STORAGE_KEY = "aiobs.role";

const RoleContext = createContext<{ role: Role; setRole: (role: Role) => void }>({
  role: "all",
  setRole: () => {},
});

function initialRole(): Role {
  const stored =
    typeof localStorage !== "undefined" ? localStorage.getItem(STORAGE_KEY) : null;
  return stored === "engineer" || stored === "manager" || stored === "executive"
    ? stored
    : "all";
}

export function RoleProvider({ children }: { children: ReactNode }) {
  const [role, setRoleState] = useState<Role>(initialRole);
  const setRole = useCallback((next: Role) => {
    setRoleState(next);
    localStorage.setItem(STORAGE_KEY, next);
  }, []);
  return (
    <RoleContext.Provider value={{ role, setRole }}>{children}</RoleContext.Provider>
  );
}

export function useRole() {
  return useContext(RoleContext);
}
