"use client";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { dashboardApi } from "@/lib/dashboard-api";
import { useAuth } from "@/lib/auth-context";
export default function AccountPage() {
  const { user, logout } = useAuth(); const router = useRouter();
  const [password, setPassword] = useState(""); const [confirmation, setConfirmation] = useState(""); const [error, setError] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) { event.preventDefault(); if (confirmation !== "DELETE MY ACCOUNT") { setError("Type DELETE MY ACCOUNT exactly to continue."); return; } setBusy(true); setError(null); try { await dashboardApi.deleteAccount(password); await logout(); router.replace("/login"); } catch (caught) { setError(caught instanceof Error ? caught.message : "Account deletion failed."); setBusy(false); } }
  return <div className="workspace-screen"><header className="screen-heading"><div><span className="eyebrow">Account settings</span><h1>Delete your account.</h1><p>This permanently removes your personal login and, if you are the sole owner, your workspace data.</p></div></header><section className="config-card"><h2>Final confirmation</h2><p>Recent password authentication is required. This cannot be undone.</p>{error ? <div className="workspace-alert workspace-alert-error" role="alert">{error}</div> : null}<form className="workspace-form" onSubmit={submit}><label>Password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required autoComplete="current-password" /></label><label>Type DELETE MY ACCOUNT<input value={confirmation} onChange={(event) => setConfirmation(event.target.value)} required /></label><button className="button button-danger" type="submit" disabled={busy || !user}>{busy ? "Deleting…" : "Delete account permanently"}</button></form></section></div>;
}
