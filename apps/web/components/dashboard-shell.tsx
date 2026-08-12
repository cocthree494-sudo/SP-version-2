"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Brand } from "@/components/brand";
import {
  BookIcon,
  BotIcon,
  GridIcon,
  MessageIcon,
  SparkIcon,
  UserIcon,
} from "@/components/icons";
import { useAuth } from "@/lib/auth-context";

const primaryNav = [
  { href: "/dashboard", label: "Overview", icon: GridIcon },
];

const buildNav = [
  { href: "/dashboard/bots", label: "Bots", icon: BotIcon, available: true },
  { href: "/dashboard/knowledge", label: "Knowledge", icon: BookIcon, available: true },
  { href: "/dashboard/playground", label: "Playground", icon: MessageIcon, available: true },
  { href: "/dashboard/widget", label: "Widget", icon: SparkIcon, available: true },
  { href: "/dashboard/providers", label: "Providers", icon: UserIcon, available: true },
];

function routeLabel(pathname: string): string {
  if (pathname.startsWith("/dashboard/knowledge")) return "Knowledge";
  if (pathname.startsWith("/dashboard/bots")) return "Bots";
  if (pathname.startsWith("/dashboard/playground")) return "Playground";
  if (pathname.startsWith("/dashboard/widget")) return "Widget";
  if (pathname.startsWith("/dashboard/providers")) return "Providers";
  return "Overview";
}

function initials(name: string): string {
  const pieces = name.trim().split(/\s+/).filter(Boolean);
  if (pieces.length === 0) return "R";
  return pieces
    .slice(0, 2)
    .map((piece) => piece[0]?.toUpperCase() ?? "")
    .join("");
}

function LoadingShell() {
  return (
    <div className="dashboard-loading" aria-live="polite" aria-busy="true">
      <div className="skeleton skeleton-nav" />
      <div className="skeleton skeleton-heading" />
      <div className="skeleton-grid">
        <div className="skeleton skeleton-card" />
        <div className="skeleton skeleton-card" />
        <div className="skeleton skeleton-card" />
      </div>
      <span className="sr-only">Loading your workspace</span>
    </div>
  );
}

export function ProtectedShell({ children }: Readonly<{ children: React.ReactNode }>) {
  const { status, user, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);

  useEffect(() => {
    if (status === "anonymous") {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [pathname, router, status]);

  useEffect(() => {
    if (!accountOpen) return;
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") setAccountOpen(false); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [accountOpen]);

  if (status === "loading") return <LoadingShell />;
  if (status === "anonymous" || user === null) return <LoadingShell />;

  const displayName = user.display_name?.trim() || user.email.split("@")[0] || "Builder";

  async function signOut() {
    setLoggingOut(true);
    await logout();
    router.replace("/login");
  }

  return (
    <div className="dashboard-app">
      <aside className={`sidebar ${mobileNavOpen ? "sidebar-open" : ""}`}>
        <div className="sidebar-top">
          <Brand href="/dashboard" />
          <button
            className="mobile-close"
            type="button"
            aria-label="Close navigation"
            onClick={() => setMobileNavOpen(false)}
          >
            ×
          </button>
        </div>
        <div className="workspace-switcher" aria-label="Current organization">
          <span className="workspace-avatar">{initials(user.tenant.name)}</span>
          <span className="workspace-copy">
            <strong>{user.tenant.name}</strong>
            <small>{user.role} workspace</small>
          </span>
          <span className="workspace-chevron" aria-hidden="true">⌄</span>
        </div>
        <nav className="sidebar-nav" aria-label="Workspace navigation">
          <span className="nav-label">Workspace</span>
          {primaryNav.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href;
            return (
              <Link
                className={`nav-item ${active ? "nav-item-active" : ""}`}
                href={item.href}
                aria-current={active ? "page" : undefined}
                key={item.href}
                onClick={() => setMobileNavOpen(false)}
              >
                <Icon width={18} height={18} />
                <span>{item.label}</span>
              </Link>
            );
          })}
          <span className="nav-label nav-label-spaced">Build</span>
          {buildNav.map((item) => {
            const Icon = item.icon;
            const active = pathname.startsWith(item.href);
            if (item.available) {
              return (
                <Link
                  className={`nav-item ${active ? "nav-item-active" : ""}`}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  key={item.href}
                  onClick={() => setMobileNavOpen(false)}
                >
                  <Icon width={18} height={18} />
                  <span>{item.label}</span>
                </Link>
              );
            }
            return (
              <span className="nav-item nav-item-disabled" aria-disabled="true" key={item.href}>
                <Icon width={18} height={18} />
                <span>{item.label}</span>
                <small>Soon</small>
              </span>
            );
          })}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-tip">
            <span className="tip-icon"><SparkIcon width={16} height={16} /></span>
            <div>
              <strong>Small steps, sharp answers.</strong>
              <span>Shape each answer from trusted knowledge.</span>
            </div>
          </div>
          <div className="sidebar-user">
            <span className="user-avatar">{initials(displayName)}</span>
            <span className="sidebar-user-copy">
              <strong>{displayName}</strong>
              <small>{user.email}</small>
            </span>
            <button
              className="icon-button icon-button-muted"
              type="button"
              onClick={() => setAccountOpen((current) => !current)}
              aria-label="Open account menu"
              disabled={loggingOut}
              title="Account"
            >
              <UserIcon width={17} height={17} />
            </button>
          </div>
        </div>
      </aside>
      {mobileNavOpen ? (
        <button
          className="sidebar-backdrop"
          type="button"
          aria-label="Close navigation"
          onClick={() => setMobileNavOpen(false)}
        />
      ) : null}
      <section className="dashboard-main">
        <header className="dashboard-header">
          <div className="dashboard-header-left">
            <button
              className="mobile-menu"
              type="button"
              onClick={() => setMobileNavOpen(true)}
              aria-label="Open navigation"
              aria-expanded={mobileNavOpen}
            >
              <span />
              <span />
              <span />
            </button>
            <div className="breadcrumb">
              <span>Workspace</span>
              <span aria-hidden="true">/</span>
              <strong>{routeLabel(pathname)}</strong>
            </div>
          </div>
          <div className="dashboard-header-actions">
            <span className="status-pill"><span className="status-dot" />Systems operational</span>
            <div className="account-menu-wrap"><button className="header-user" type="button" onClick={() => setAccountOpen((current) => !current)} aria-expanded={accountOpen} aria-haspopup="menu">
              <span className="user-avatar user-avatar-small">{initials(displayName)}</span>
              <span>{displayName}</span>
              <span className="header-user-chevron" aria-hidden="true">⌄</span>
            </button>{accountOpen ? <div className="account-menu" role="menu"><div className="account-menu-summary"><strong>{displayName}</strong><span>{user.email}</span><span>{user.tenant.name} · {user.role}</span></div><button type="button" role="menuitem" className="account-menu-signout" onClick={() => void signOut()} disabled={loggingOut}>{loggingOut ? "Signing out…" : "Sign out"}</button></div> : null}</div>
          </div>
        </header>
        <main className="dashboard-content">{children}</main>
      </section>
    </div>
  );
}
