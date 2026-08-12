"use client";

import type { FormEvent } from "react";
import { useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { ArrowIcon, GitHubIcon, GoogleIcon, MicrosoftIcon, SparkIcon } from "@/components/icons";
import { useAuth } from "@/lib/auth-context";

type AuthMode = "login" | "register";

function Field({
  id,
  label,
  type = "text",
  value,
  onChange,
  placeholder,
  hint,
  required = true,
  autoComplete,
}: Readonly<{
  id: string;
  label: string;
  type?: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  hint?: string;
  required?: boolean;
  autoComplete?: string;
}>) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        name={id}
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        required={required}
        autoComplete={autoComplete}
        aria-describedby={hint ? `${id}-hint` : undefined}
      />
      {hint ? (
        <span className="field-hint" id={`${id}-hint`}>
          {hint}
        </span>
      ) : null}
    </div>
  );
}

function AuthAside({ mode }: Readonly<{ mode: AuthMode }>) {
  return (
    <aside className="auth-aside">
      <div className="auth-aside-orbit orbit-one" />
      <div className="auth-aside-orbit orbit-two" />
      <div className="auth-aside-content">
        <span className="eyebrow eyebrow-light">
          <SparkIcon width={15} height={15} />
          Support, in sync
        </span>
        <h2>Make every answer feel like your best teammate wrote it.</h2>
        <p>
          Relay brings your team&apos;s knowledge, tone, and customer conversations into one
          calm workspace.
        </p>
        <div className="signal-card">
          <div className="signal-card-top">
            <span className="signal-dot" />
            <span>Agent signal</span>
            <span className="signal-time">live</span>
          </div>
          <div className="signal-bars" aria-hidden="true">
            <span />
            <span />
            <span />
            <span />
            <span />
            <span />
            <span />
          </div>
          <p className="signal-caption">Grounded answers, routed with care.</p>
        </div>
      </div>
      <p className="auth-aside-foot">{mode === "login" ? "Welcome back, builder." : "A clearer support loop starts here."}</p>
    </aside>
  );
}

export function AuthForm({ mode }: Readonly<{ mode: AuthMode }>) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login, register, socialRegister, socialSelect, linkSocial } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [organizationName, setOrganizationName] = useState("");
  const [organizationSlug, setOrganizationSlug] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const isRegister = mode === "register";
  const socialToken = searchParams.get("social_token");
  const socialSelectToken = searchParams.get("social_select");
  const socialLinkToken = searchParams.get("social_link");
  const socialRegistration = isRegister && Boolean(socialToken);
  const socialOrganizationSelection = !isRegister && Boolean(socialSelectToken);

  function beginSocial(provider: "google" | "microsoft" | "github") {
    const params = new URLSearchParams({ mode: isRegister ? "register" : "login" });
    if (organizationSlug) params.set("organization_slug", organizationSlug);
    window.location.assign(`/api/auth/oauth/${provider}/start?${params.toString()}`);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (socialRegistration && socialToken) {
        await socialRegister({
          continuation_token: socialToken,
          organization_name: organizationName,
          ...(organizationSlug ? { organization_slug: organizationSlug } : {}),
        });
      } else if (socialOrganizationSelection && socialSelectToken) {
        await socialSelect({
          continuation_token: socialSelectToken,
          organization_slug: organizationSlug,
        });
      } else if (isRegister) {
        await register({
          email,
          password,
          ...(displayName ? { display_name: displayName } : {}),
          organization_name: organizationName,
          ...(organizationSlug ? { organization_slug: organizationSlug } : {}),
        });
      } else {
        await login({
          email,
          password,
          ...(organizationSlug ? { organization_slug: organizationSlug } : {}),
        });
        if (socialLinkToken) await linkSocial(socialLinkToken);
      }
      const requestedPath = new URLSearchParams(window.location.search).get("next");
      const safeNext =
        requestedPath?.startsWith("/") && !requestedPath.startsWith("//")
          ? requestedPath
          : "/dashboard";
      router.replace(safeNext);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Something went wrong. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <AuthAside mode={mode} />
      <section className="auth-panel" aria-labelledby="auth-title">
        <div className="auth-panel-inner">
          <div className="auth-mobile-brand">
            <Link className="brand" href="/">
              <span className="brand-mark" aria-hidden="true">
                <span />
                <span />
              </span>
              <span className="brand-word">Relay</span>
            </Link>
          </div>
          <div className="auth-heading">
            <span className="eyebrow">{isRegister ? "Start your workspace" : "Your workspace awaits"}</span>
            <h1 id="auth-title">{isRegister ? "Build a better support loop." : "Welcome back."}</h1>
            <p>
              {isRegister
                ? "Create your organization and meet your new support command center."
                : "Sign in to see what your agent learned while you were away."}
            </p>
          </div>

          <form className="auth-form" onSubmit={submit}>
            {isRegister && !socialRegistration ? (
              <Field
                id="display-name"
                label="Your name"
                value={displayName}
                onChange={setDisplayName}
                placeholder="Aisha Rahman"
                required={false}
                autoComplete="name"
              />
            ) : null}
            {!socialRegistration && !socialOrganizationSelection ? (
              <>
                <Field
                  id="email"
                  label="Work email"
                  type="email"
                  value={email}
                  onChange={setEmail}
                  placeholder="you@company.com"
                  autoComplete="email"
                />
                <Field
                  id="password"
                  label="Password"
                  type="password"
                  value={password}
                  onChange={setPassword}
                  placeholder={isRegister ? "At least 8 characters" : "Your password"}
                  hint={isRegister ? "Use 8 or more characters." : undefined}
                  autoComplete={isRegister ? "new-password" : "current-password"}
                />
              </>
            ) : null}
            {socialRegistration ? (
              <div className="social-continuation-note">
                Your verified social account is ready. Choose a workspace name to finish setup.
              </div>
            ) : null}
            {socialOrganizationSelection ? (
              <div className="social-continuation-note">
                Choose the organization where you want to continue.
              </div>
            ) : null}
            {isRegister ? (
              <Field
                id="organization-name"
                label="Organization name"
                value={organizationName}
                onChange={setOrganizationName}
                placeholder="Northstar Labs"
                autoComplete="organization"
              />
            ) : null}
            <Field
              id="organization-slug"
              label={isRegister ? "Workspace URL" : "Organization slug"}
              value={organizationSlug}
              onChange={setOrganizationSlug}
              placeholder={isRegister ? "northstar-labs (optional)" : "northstar-labs (optional)"}
              hint={isRegister ? "You can use the suggested name if left blank." : "Only needed if your email belongs to more than one organization."}
              required={false}
              autoComplete="organization"
            />

            {error ? (
              <div className="form-alert" role="alert">
                <span className="form-alert-mark">!</span>
                <span>{error}</span>
              </div>
            ) : null}

            <button className="button button-primary button-wide" type="submit" disabled={submitting}>
              <span>
                {submitting
                  ? "Connecting…"
                  : socialRegistration
                    ? "Create workspace"
                    : socialOrganizationSelection
                      ? "Continue"
                      : isRegister
                        ? "Create workspace"
                        : "Sign in"}
              </span>
              {!submitting ? <ArrowIcon width={18} height={18} /> : <span className="button-spinner" aria-hidden="true" />}
            </button>
          </form>

          {!socialRegistration && !socialOrganizationSelection ? (
            <>
              <div className="auth-divider"><span>or continue with</span></div>
              <div className="social-buttons" aria-label="Social sign-in providers">
                <button className="social-button" type="button" aria-label="Continue with Google" title="Continue with Google" onClick={() => beginSocial("google")}>
                  <GoogleIcon className="social-glyph" width={22} height={22} />
                </button>
                <button className="social-button" type="button" aria-label="Continue with Microsoft" title="Continue with Microsoft" onClick={() => beginSocial("microsoft")}>
                  <MicrosoftIcon className="social-glyph" width={22} height={22} />
                </button>
                <button className="social-button" type="button" aria-label="Continue with GitHub" title="Continue with GitHub" onClick={() => beginSocial("github")}>
                  <GitHubIcon className="social-glyph" width={22} height={22} />
                </button>
              </div>
            </>
          ) : null}

          <p className="auth-switch">
            {isRegister ? "Already have an account?" : "New to Relay?"}{" "}
            <Link href={isRegister ? "/login" : "/register"}>
              {isRegister ? "Sign in" : "Create your workspace"}
            </Link>
          </p>
          <p className="auth-legal">By continuing, you agree to keep customer data private and your workspace secure.</p>
        </div>
      </section>
    </main>
  );
}
