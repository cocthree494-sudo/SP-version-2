import type { ReactNode } from "react";

import { AdminConsole } from "@/components/admin-console";

export default function AdminLayout({ children }: Readonly<{ children: ReactNode }>) {
  return children;
}

