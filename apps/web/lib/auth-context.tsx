"use client";

import type {
  LoginInput,
  MeResponse,
  PendingAuthResponse,
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
  login: (payload: LoginInput, completeSocialLink?: boolean, adminFlow?: boolean) => Promise<PendingAuthResponse>;
  register: (payload: RegisterInput) => Promise<PendingAuthResponse>;
  socialRegister: (payload: {
    organization_name: string;
    organization_slug?: string;
  }, adminFlow?: boolean) => Promise<PendingAuthResponse>;
  socialSelect: (payload: { organization_slug: string }, adminFlow?: boolean) => Promise<PendingAuthResponse>;
  otpStatus: () => Promise<PendingAuthResponse | null>;
  resendOtp: () => Promise<PendingAuthResponse>;
  verifyOtp: (code: string) => Promise<void>;
  cancelOtp: () => Promise<void>;
  logout: () => Promise<void>;
  reload: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

class BrowserAuthError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "BrowserAuthError";
    this.status = status;
  }
}

async function responseDetail(response: Response): Promise<string> {
  const payload = (await response.json().catch(() => null)) as {
    detail?: unknown;
  } | null;
  return typeof payload?.detail === "string"
    ? payload.detail
    : "We could not complete that request. Please try again.";
}

async function browserAuthError(response: Response): Promise<BrowserAuthError> {
  return new BrowserAuthError(response.status, await responseDetail(response));
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
        throw await browserAuthError(response);
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
    async (
      endpoint: "login" | "register",
      payload: LoginInput | RegisterInput,
      completeSocialLink = false,
      adminFlow = false,
    ): Promise<PendingAuthResponse> => {
      const response = await fetch(`/api/auth/${endpoint}`, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          ...(adminFlow ? { "X-Relay-Admin-Flow": "1" } : {}),
        },
        body: JSON.stringify(
          endpoint === "login" ? { ...payload, complete_social_link: completeSocialLink } : payload,
        ),
      });
      if (!response.ok) {
        throw await browserAuthError(response);
      }
      return (await response.json()) as PendingAuthResponse;
    },
    [],
  );

  const login = useCallback(
    (payload: LoginInput, completeSocialLink = false, adminFlow = false) =>
      authenticate("login", payload, completeSocialLink, adminFlow),
    [authenticate],
  );
  const register = useCallback(
    (payload: RegisterInput) => authenticate("register", payload),
    [authenticate],
  );
  const socialComplete = useCallback(
    async (
      endpoint: "register" | "select",
      payload: Record<string, string>,
      adminFlow = false,
    ): Promise<PendingAuthResponse> => {
      const response = await fetch(`/api/auth/social/${endpoint}`, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          ...(adminFlow ? { "X-Relay-Admin-Flow": "1" } : {}),
        },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw await browserAuthError(response);
      return (await response.json()) as PendingAuthResponse;
    },
    [],
  );
  const socialRegister = useCallback(
    (payload: { organization_name: string; organization_slug?: string }, adminFlow = false) =>
      socialComplete("register", payload, adminFlow),
    [socialComplete],
  );
  const socialSelect = useCallback(
    (payload: { organization_slug: string }, adminFlow = false) =>
      socialComplete("select", payload, adminFlow),
    [socialComplete],
  );

  const otpStatus = useCallback(async (): Promise<PendingAuthResponse | null> => {
    const response = await fetch("/api/auth/otp/status", {
      cache: "no-store",
      credentials: "same-origin",
    });
    if (response.status === 204) return null;
    if (!response.ok) throw await browserAuthError(response);
    return (await response.json()) as PendingAuthResponse;
  }, []);

  const resendOtp = useCallback(async (): Promise<PendingAuthResponse> => {
    const response = await fetch("/api/auth/otp/resend", {
      method: "POST",
      credentials: "same-origin",
    });
    if (!response.ok) throw await browserAuthError(response);
    return (await response.json()) as PendingAuthResponse;
  }, []);

  const verifyOtp = useCallback(
    async (code: string): Promise<void> => {
      const response = await fetch("/api/auth/otp/verify", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
      if (!response.ok) throw await browserAuthError(response);
      await reload();
    },
    [reload],
  );

  const cancelOtp = useCallback(async (): Promise<void> => {
    const response = await fetch("/api/auth/otp/cancel", {
      method: "POST",
      credentials: "same-origin",
    });
    if (!response.ok) throw await browserAuthError(response);
  }, []);
  const logout = useCallback(async () => {
    await fetch("/api/auth/logout", {
      method: "POST",
      credentials: "same-origin",
    });
    setUser(null);
    setStatus("anonymous");
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      login,
      register,
      socialRegister,
      socialSelect,
      otpStatus,
      resendOtp,
      verifyOtp,
      cancelOtp,
      logout,
      reload,
    }),
    [
      status,
      user,
      login,
      register,
      socialRegister,
      socialSelect,
      otpStatus,
      resendOtp,
      verifyOtp,
      cancelOtp,
      logout,
      reload,
    ],
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

