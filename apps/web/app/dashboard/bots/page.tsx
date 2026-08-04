import type { Metadata } from "next";

import { BotManagement } from "@/components/bot-management";

export const metadata: Metadata = { title: "Bots" };

export default function BotsPage() {
  return <BotManagement />;
}
