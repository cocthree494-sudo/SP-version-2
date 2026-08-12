import type { Metadata } from "next";

import { ChannelSettings } from "@/components/channel-settings";

export const metadata: Metadata = { title: "Channels" };

export default function ChannelsPage() {
  return <ChannelSettings />;
}
