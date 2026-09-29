import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, setUnauthorizedHandler } from "../api/client";
import type { Profile, Role } from "../api/types";

interface AuthValue {
  profile: Profile | null;
  loading: boolean;
  roles: Set<Role>;
  /** Client accounts never receive cost data (backend strips it). */
  costVisible: boolean;
  canApprove: boolean;
  hasRole: (...allowed: Role[]) => boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthValue>({
  profile: null,
  loading: true,
  roles: new Set(),
  costVisible: false,
  canApprove: false,
  hasRole: () => false,
  login: async () => {},
  logout: async () => {},
  refresh: async () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      setProfile(await api.auth.me());
    } catch {
      setProfile(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    api.auth
      .me()
      .then((next) => {
        if (!cancelled) setProfile(next);
      })
      .catch(() => {
        if (!cancelled) setProfile(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setProfile(null);
      queryClient.clear();
    });
    return () => setUnauthorizedHandler(null);
  }, [queryClient]);

  const login = useCallback(
    async (email: string, password: string) => {
      const next = await api.auth.login(email, password);
      queryClient.clear();
      setProfile(next);
    },
    [queryClient]
  );

  const logout = useCallback(async () => {
    try {
      await api.auth.logout();
    } finally {
      setProfile(null);
      queryClient.clear();
    }
  }, [queryClient]);

  const roles = useMemo(() => new Set(profile?.roles ?? []), [profile]);
  const costVisible = useMemo(
    () => Array.from(roles).some((role) => role !== "client"),
    [roles]
  );

  const value: AuthValue = {
    profile,
    loading,
    roles,
    costVisible,
    canApprove: Boolean(profile?.can_approve),
    // Platform admins see every view.
    hasRole: (...allowed) => roles.has("admin") || allowed.some((role) => roles.has(role)),
    login,
    logout,
    refresh: load,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
