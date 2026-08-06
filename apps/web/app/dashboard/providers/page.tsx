import type { Metadata } from "next";

import { ProviderSettings } from "@/components/provider-settings";

export const metadata: Metadata = { title: "Providers" };

export default function ProvidersPage() {
  return <ProviderSettings />;
}
