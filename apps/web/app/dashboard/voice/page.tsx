import type { Metadata } from "next";

import { VoiceSettings } from "@/components/voice-settings";

export const metadata: Metadata = { title: "Voice" };

export default function VoicePage() {
  return <VoiceSettings />;
}
