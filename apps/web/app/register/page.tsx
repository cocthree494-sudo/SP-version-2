import type { Metadata } from "next";

import { AuthForm } from "@/components/auth-form";

export const metadata: Metadata = {
  title: "Create workspace",
  description: "Create a Relay support workspace.",
};

export default function RegisterPage() {
  return <AuthForm mode="register" />;
}
