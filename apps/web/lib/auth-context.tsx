"use client";

import type {
  LoginInput,
  MeResponse,
  RegisterInput,
} from "@support-agent/api-client";
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

type AuthStatus = "loading" | "authenticated" | "anonymous";

interface AuthContextValue {
  status: AuthStatus;
  user: MeResponse | null;
  login: (payload: LoginInput) => Promise<void>;
  register: (payload: RegisterInput) => Promise<void>;
  socialRegister: (payload: {
    continuation_token: string;
    organization_name: string;
    organization_slug?: string;
  }) => Promise<void>;
  socialSelect: (payload: { continuation_token: string; organization_slug: string }) => Promise<void>;
  linkSocial: (continuation_token: string) => Promise<void>;
  logout: () => Promise<void>;
  reload: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

class BrowserAuthError extends Error {}

async function responseDetail(response: Response): Promise<string> {
  const payload = (await response.json().catch(() => null)) as {
    detail?: unknown;
  } | null;
  return typeof payload?.detail === "string"
    ? payload.detail
    : "We could not complete that request. Please try again.";
}

export function AuthProvider({ children }: Readonly<{ children: ReactNode }>) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<MeResponse | null>(null);

  const reload = useCallback(async () => {
    setStatus("loading");
    try {
      const response = await fetch("/api/auth/session", {
        cache: "no-store",
        credentials: "same-origin",
      });
      if (response.status === 204) {
        setUser(null);
        setStatus("anonymous");
        return;
      }
      if (!response.ok) {
        throw new BrowserAuthError(await responseDetail(response));
      }
      setUser((await response.json()) as MeResponse);
      setStatus("authenticated");
    } catch {
      setUser(null);
      setStatus("anonymous");
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const authenticate = useCallback(
    async (endpoint: "login" | "register", payload: LoginInput | RegisterInput) => {
      const response = await fetch(`/api/auth/${endpoint}`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        throw new BrowserAuthError(await responseDetail(response));
      }
      await reload();
    },
    [reload],
  );

  const login = useCallback(
    (payload: LoginInput) => authenticate("login", payload),
    [authenticate],
  );
  const register = useCallback(
    (payload: RegisterInput) => authenticate("register", payload),
    [authenticate],
  );
  const socialComplete = useCallback(
    async (endpoint: "register" | "select", payload: Record<string, string>) => {
      const response = await fetch(`/api/auth/social/${endpoint}`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new BrowserAuthError(await responseDetail(response));
      await reload();
    },
    [reload],
  );
  const socialRegister = useCallback(
    (payload: { continuation_token: string; organization_name: string; organization_slug?: string }) =>
      socialComplete("register", payload),
    [socialComplete],
  );
  const socialSelect = useCallback(
    (payload: { continuation_token: string; organization_slug: string }) =>
      socialComplete("select", payload),
    [socialComplete],
  );
  const linkSocial = useCallback(
    async (continuation_token: string) => {
      const response = await fetch("/api/auth/social/link", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ continuation_token }),
      });
      if (!response.ok) throw new BrowserAuthError(await responseDetail(response));
    },
    [],
  );
  const logout = useCallback(async () => {
    await fetch("/api/auth/logout", {
      method: "POST",
      credentials: "same-origin",
    });
    setUser(null);
    setStatus("anonymous");
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ status, user, login, register, socialRegister, socialSelect, linkSocial, logout, reload }),
    [status, user, login, register, socialRegister, socialSelect, linkSocial, logout, reload],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error("useAuth must be rendered inside AuthProvider");
  }
  return context;
}

