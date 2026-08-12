import type { Metadata } from "next";

import { DocumentationCenter } from "@/components/documentation-center";

export const metadata: Metadata = { title: "Documentation" };

export default function PublicDocumentationPage() {
  return <DocumentationCenter publicPage />;
}
