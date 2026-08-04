"use client";

import type { ReactNode } from "react";

import { AuthProvider } from "@/lib/auth-context";

export function Providers({ children }: Readonly<{ children: ReactNode }>) {
  return <AuthProvider>{children}</AuthProvider>;
}

