"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Brand } from "@/components/brand";
import {
  ArrowIcon,
  BookIcon,
  BotIcon,
  GridIcon,
  MessageIcon,
  SparkIcon,
  TrashIcon,
  UserIcon,
} from "@/components/icons";
import { useAuth } from "@/lib/auth-context";

const primaryNav = [{ href: "/dashboard", label: "Overview", icon: GridIcon }];

const buildNav = [
  { href: "/dashboard/bots", label: "Bots", icon: BotIcon, available: true },
  { href: "/dashboard/knowledge", label: "Knowledge", icon: BookIcon, available: true },
  { href: "/dashboard/playground", label: "Playground", icon: MessageIcon, available: true },
  { href: "/dashboard/widget", label: "Widget", icon: SparkIcon, available: true },
  { href: "/dashboard/providers", label: "Providers", icon: UserIcon, available: true },
  { href: "/dashboard/channels", label: "Channels", icon: MessageIcon, available: true },
  { href: "/dashboard/voice", label: "Voice", icon: MessageIcon, available: true },
  { href: "/dashboard/docs", label: "Docs", icon: BookIcon, available: true },
];

function routeLabel(pathname: string): string {
  if (pathname.startsWith("/dashboard/knowledge")) return "Knowledge";
  if (pathname.startsWith("/dashboard/bots")) return "Bots";
  if (pathname.startsWith("/dashboard/playground")) return "Playground";
  if (pathname.startsWith("/dashboard/widget")) return "Widget";
  if (pathname.startsWith("/dashboard/providers")) return "Providers";
  if (pathname.startsWith("/dashboard/channels")) return "Channels";
  if (pathname.startsWith("/dashboard/voice")) return "Voice";
  if (pathname.startsWith("/dashboard/docs")) return "Docs";
  if (pathname.startsWith("/dashboard/account")) return "Account settings";
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
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const accountMenuRef = useRef<HTMLDivElement>(null);
  const sidebarAccountButtonRef = useRef<HTMLButtonElement>(null);
  const firstAccountActionRef = useRef<HTMLAnchorElement>(null);

  useEffect(() => {
    if (status === "anonymous") {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [pathname, router, status]);

  useEffect(() => {
    setAccountOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!accountOpen) return;

    const focusFrame = window.requestAnimationFrame(() => firstAccountActionRef.current?.focus());
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setAccountOpen(false);
      window.requestAnimationFrame(() => sidebarAccountButtonRef.current?.focus());
    };
    const closeOnOutsideClick = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Node) || accountMenuRef.current?.contains(target)) return;
      setAccountOpen(false);
    };

    window.addEventListener("keydown", closeOnEscape);
    document.addEventListener("pointerdown", closeOnOutsideClick);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      window.removeEventListener("keydown", closeOnEscape);
      document.removeEventListener("pointerdown", closeOnOutsideClick);
    };
  }, [accountOpen]);

  if (status === "loading") return <LoadingShell />;
  if (status === "anonymous" || user === null) return <LoadingShell />;

  const displayName = user.display_name?.trim() || user.email.split("@")[0] || "Builder";
  const organizationLabel = `${user.tenant.name}, ${user.role} workspace`;

  function closeMobileNavigation() {
    setMobileNavOpen(false);
    setAccountOpen(false);
  }

  function toggleSidebar() {
    setAccountOpen(false);
    setSidebarCollapsed((current) => !current);
  }

  async function signOut() {
    setLoggingOut(true);
    await logout();
    router.replace("/login");
  }

  return (
    <div className="dashboard-app">
      <aside
        className={`sidebar ${sidebarCollapsed ? "sidebar-collapsed" : ""} ${
          mobileNavOpen ? "sidebar-open" : ""
        }`}
      >
        <div className="sidebar-top">
          <Brand href="/dashboard" />
          <button
            className="sidebar-collapse"
            type="button"
            aria-label={sidebarCollapsed ? "Expand navigation" : "Collapse navigation"}
            aria-expanded={!sidebarCollapsed}
            title={sidebarCollapsed ? "Expand navigation" : "Collapse navigation"}
            onClick={toggleSidebar}
          >
            <ArrowIcon width={15} height={15} />
          </button>
          <button
            className="mobile-close"
            type="button"
            aria-label="Close navigation"
            onClick={closeMobileNavigation}
          >
            ×
          </button>
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
                onClick={closeMobileNavigation}
                title={sidebarCollapsed ? item.label : undefined}
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
                  onClick={closeMobileNavigation}
                  title={sidebarCollapsed ? item.label : undefined}
                >
                  <Icon width={18} height={18} />
                  <span>{item.label}</span>
                </Link>
              );
            }
            return (
              <span
                className="nav-item nav-item-disabled"
                aria-disabled="true"
                key={item.href}
                title={sidebarCollapsed ? `${item.label} (coming soon)` : undefined}
              >
                <Icon width={18} height={18} />
                <span>{item.label}</span>
                <small>Soon</small>
              </span>
            );
          })}
        </nav>
        <div className="sidebar-bottom">
          <div className="account-menu-wrap sidebar-account-wrap" ref={accountMenuRef}>
            <button
              ref={sidebarAccountButtonRef}
              className="sidebar-user"
              type="button"
              onClick={() => setAccountOpen((current) => !current)}
              aria-label={accountOpen ? "Close account menu" : "Open account menu"}
              aria-controls="sidebar-account-menu"
              aria-expanded={accountOpen}
              aria-haspopup="menu"
              disabled={loggingOut}
              title={sidebarCollapsed ? "Account" : undefined}
            >
              <span className="user-avatar">{initials(displayName)}</span>
              <span className="sidebar-user-copy">
                <strong>{displayName}</strong>
                <small>{user.email}</small>
              </span>
              <ArrowIcon className="sidebar-account-arrow" width={15} height={15} />
            </button>
            {accountOpen ? (
              <div
                className="account-menu sidebar-account-menu"
                id="sidebar-account-menu"
                role="menu"
                aria-label="Account actions"
              >
                <div className="account-menu-summary">
                  <strong>{displayName}</strong>
                  <span>{user.email}</span>
                  <span>{user.tenant.name} · {user.role}</span>
                </div>
                <div className="account-menu-actions">
                  <Link
                    ref={firstAccountActionRef}
                    className="account-menu-item"
                    href="/dashboard/account"
                    role="menuitem"
                    onClick={closeMobileNavigation}
                  >
                    <UserIcon width={16} height={16} />
                    <span>Account settings</span>
                  </Link>
                  <Link
                    className="account-menu-item account-menu-item-danger"
                    href="/dashboard/account#delete-account"
                    role="menuitem"
                    onClick={closeMobileNavigation}
                  >
                    <TrashIcon width={16} height={16} />
                    <span>Delete account</span>
                  </Link>
                  <button
                    type="button"
                    role="menuitem"
                    className="account-menu-item account-menu-signout"
                    onClick={() => void signOut()}
                    disabled={loggingOut}
                  >
                    <ArrowIcon width={16} height={16} />
                    <span>{loggingOut ? "Signing out…" : "Sign out"}</span>
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </aside>
      {mobileNavOpen ? (
        <button
          className="sidebar-backdrop"
          type="button"
          aria-label="Close navigation"
          onClick={closeMobileNavigation}
        />
      ) : null}
      <section className={`dashboard-main ${sidebarCollapsed ? "dashboard-main-collapsed" : ""}`}>
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
            <span className="status-pill">
              <span className="status-dot" />Systems operational
            </span>
            <div
              className="header-organization"
              aria-label={`Current organization: ${organizationLabel}`}
              title={organizationLabel}
            >
              <span className="workspace-avatar workspace-avatar-small">
                {initials(user.tenant.name)}
              </span>
              <span className="header-organization-copy">
                <strong>{user.tenant.name}</strong>
                <small>{user.role} workspace</small>
              </span>
            </div>
          </div>
        </header>
        <main className="dashboard-content">{children}</main>
      </section>
    </div>
  );
}
