import type { ReactNode } from "react";

import { ProtectedShell } from "@/components/dashboard-shell";

export default function DashboardLayout({ children }: Readonly<{ children: ReactNode }>) {
  return <ProtectedShell>{children}</ProtectedShell>;
}

