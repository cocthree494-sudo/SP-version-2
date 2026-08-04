import type { Metadata } from "next";

import { KnowledgeManagement } from "@/components/knowledge-management";

export const metadata: Metadata = { title: "Knowledge" };

export default function KnowledgePage() {
  return <KnowledgeManagement />;
}
