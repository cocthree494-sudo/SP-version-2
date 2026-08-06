import type { Metadata } from "next";

import { WidgetConfiguration } from "@/components/widget-configuration";

export const metadata: Metadata = { title: "Widget" };

export default function WidgetPage() {
  return <WidgetConfiguration />;
}
