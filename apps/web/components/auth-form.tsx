"use client";

import type { PendingAuthResponse } from "@support-agent/api-client";
import type { FormEvent } from "react";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { Brand } from "@/components/brand";
import { ArrowIcon, GitHubIcon, GoogleIcon, MicrosoftIcon, SparkIcon } from "@/components/icons";
import { useAuth } from "@/lib/auth-context";

type AuthMode = "login" | "register";

interface PendingChallenge {
  emailHint: string;
  expiresAt: number;
  resendAt: number;
}

function pendingChallenge(response: PendingAuthResponse): PendingChallenge {
  const now = Date.now();
  return {
    emailHint: response.email_hint,
    expiresAt: now + response.expires_in * 1000,
    resendAt: now + response.resend_after * 1000,
  };
}

function formatCountdown(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes}:${remainder.toString().padStart(2, "0")}`;
}

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
      <Brand />
      <div className="auth-aside-orbit orbit-one" />
      <div className="auth-aside-orbit orbit-two" />
      <div className="auth-aside-content">
        <span className="eyebrow eyebrow-light">
          <SparkIcon width={15} height={15} />
          Support, in sync
        </span>
        <p className="auth-aside-title">Make every answer feel like your best teammate wrote it.</p>
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
  const {
    login,
    register,
    socialRegister,
    socialSelect,
    otpStatus,
    resendOtp,
    verifyOtp,
    cancelOtp,
  } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [organizationName, setOrganizationName] = useState("");
  const [organizationSlug, setOrganizationSlug] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [checkingOtp, setCheckingOtp] = useState(true);
  const [challenge, setChallenge] = useState<PendingChallenge | null>(null);
  const [otpCode, setOtpCode] = useState("");
  const [resending, setResending] = useState(false);
  const [verificationBlocked, setVerificationBlocked] = useState(false);
  const [clock, setClock] = useState(() => Date.now());

  const isRegister = mode === "register";
  const socialStep = searchParams.get("social");
  const oauthError = searchParams.get("oauth_error");
  const oauthProvider = searchParams.get("provider");
  const oauthErrorMessage =
    oauthError === "provider_unavailable"
      ? `${oauthProvider === "microsoft" ? "Microsoft" : oauthProvider === "github" ? "GitHub" : "Google"} sign-in is not configured yet. Ask the workspace administrator to enable it.`
      : null;
  const socialRegistration = isRegister && socialStep === "register";
  const socialOrganizationSelection = !isRegister && socialStep === "select";
  const socialLink = !isRegister && socialStep === "link";

  useEffect(() => {
    let active = true;
    void otpStatus()
      .then((status) => {
        if (active && status) setChallenge(pendingChallenge(status));
      })
      .catch((caught) => {
        if (active && searchParams.get("otp") === "1") {
          setError(caught instanceof Error ? caught.message : "The verification request expired.");
        }
      })
      .finally(() => {
        if (active) setCheckingOtp(false);
      });
    return () => {
      active = false;
    };
  }, [otpStatus, searchParams]);

  useEffect(() => {
    if (!challenge) return;
    setClock(Date.now());
    const timer = window.setInterval(() => setClock(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [challenge]);

  const expiresIn = useMemo(
    () => (challenge ? Math.max(0, Math.ceil((challenge.expiresAt - clock) / 1000)) : 0),
    [challenge, clock],
  );
  const resendIn = useMemo(
    () => (challenge ? Math.max(0, Math.ceil((challenge.resendAt - clock) / 1000)) : 0),
    [challenge, clock],
  );
  const otpExpired = Boolean(challenge) && expiresIn === 0;

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
      let result: PendingAuthResponse;
      if (socialRegistration) {
        result = await socialRegister({
          organization_name: organizationName,
          ...(organizationSlug ? { organization_slug: organizationSlug } : {}),
        });
      } else if (socialOrganizationSelection) {
        result = await socialSelect({
          organization_slug: organizationSlug,
        });
      } else if (isRegister) {
        result = await register({
          email,
          password,
          ...(displayName ? { display_name: displayName } : {}),
          organization_name: organizationName,
          ...(organizationSlug ? { organization_slug: organizationSlug } : {}),
        });
      } else {
        result = await login(
          {
            email,
            password,
            ...(organizationSlug ? { organization_slug: organizationSlug } : {}),
          },
          socialLink,
        );
      }
      setPassword("");
      setOtpCode("");
      setVerificationBlocked(false);
      setChallenge(pendingChallenge(result));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Something went wrong. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  async function submitOtp(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (otpCode.length !== 6) {
      setError("Enter the complete six-digit code.");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await verifyOtp(otpCode);
      const requestedPath = new URLSearchParams(window.location.search).get("next");
      const safeNext =
        requestedPath?.startsWith("/") && !requestedPath.startsWith("//")
          ? requestedPath
          : "/dashboard";
      router.replace(safeNext);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "The code could not be verified.";
      setError(message);
      const errorStatus =
        typeof caught === "object" && caught !== null && "status" in caught
          ? Number((caught as { status: unknown }).status)
          : 0;
      if (errorStatus === 410 || errorStatus === 429) {
        setVerificationBlocked(true);
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function resendCode() {
    setError(null);
    setResending(true);
    try {
      const result = await resendOtp();
      setOtpCode("");
      setVerificationBlocked(false);
      setChallenge(pendingChallenge(result));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "A new code could not be sent.");
      const errorStatus =
        typeof caught === "object" && caught !== null && "status" in caught
          ? Number((caught as { status: unknown }).status)
          : 0;
      if (errorStatus === 410) setVerificationBlocked(true);
    } finally {
      setResending(false);
    }
  }

  async function startOver() {
    setError(null);
    setSubmitting(true);
    try {
      await cancelOtp();
      setChallenge(null);
      setOtpCode("");
      setVerificationBlocked(false);
      const next = searchParams.get("next");
      router.replace(`${isRegister ? "/register" : "/login"}${next ? `?next=${encodeURIComponent(next)}` : ""}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The verification flow could not be reset.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <AuthAside mode={mode} />
      <section
        className="auth-panel"
        aria-labelledby={checkingOtp ? undefined : "auth-title"}
        aria-label={checkingOtp ? "Authentication" : undefined}
      >
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
          {checkingOtp ? (
            <div className="otp-checking" role="status">
              <span className="button-spinner" aria-hidden="true" />
              <span>Checking verification status</span>
            </div>
          ) : challenge ? (
            <>
              <div className="auth-heading">
                <span className="eyebrow">Email verification</span>
                <h1 id="auth-title">Check your inbox.</h1>
                <p>
                  Enter the six-digit code sent to <strong>{challenge.emailHint}</strong>. The
                  code expires in <span aria-live="polite">{formatCountdown(expiresIn)}</span>.
                </p>
              </div>

              <form className="auth-form" onSubmit={submitOtp}>
                <div className="field otp-field">
                  <label htmlFor="verification-code">Verification code</label>
                  <input
                    id="verification-code"
                    name="verification-code"
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    pattern="[0-9]{6}"
                    maxLength={6}
                    value={otpCode}
                    onChange={(event) =>
                      setOtpCode(event.target.value.replace(/\D/g, "").slice(0, 6))
                    }
                    placeholder="000000"
                    autoFocus
                    disabled={otpExpired || verificationBlocked || submitting}
                    aria-describedby="verification-code-hint"
                  />
                  <span className="field-hint" id="verification-code-hint">
                    Each code works once. A newly sent code replaces the previous one.
                  </span>
                </div>

                {error ? (
                  <div className="form-alert" role="alert">
                    <span className="form-alert-mark">!</span>
                    <span>{error}</span>
                  </div>
                ) : null}

                {otpExpired || verificationBlocked ? (
                  <button
                    className="button button-primary button-wide"
                    type="button"
                    onClick={() => void startOver()}
                    disabled={submitting}
                  >
                    <span>{submitting ? "Resetting…" : "Start again"}</span>
                    {!submitting ? (
                      <ArrowIcon width={18} height={18} />
                    ) : (
                      <span className="button-spinner" aria-hidden="true" />
                    )}
                  </button>
                ) : (
                  <>
                    <button
                      className="button button-primary button-wide"
                      type="submit"
                      disabled={submitting || otpCode.length !== 6}
                    >
                      <span>{submitting ? "Verifying…" : "Verify and continue"}</span>
                      {!submitting ? (
                        <ArrowIcon width={18} height={18} />
                      ) : (
                        <span className="button-spinner" aria-hidden="true" />
                      )}
                    </button>
                    <button
                      className="otp-resend"
                      type="button"
                      onClick={() => void resendCode()}
                      disabled={resending || resendIn > 0}
                    >
                      {resending
                        ? "Sending a new code…"
                        : resendIn > 0
                          ? `Send another code in ${formatCountdown(resendIn)}`
                          : "Send another code"}
                    </button>
                  </>
                )}
              </form>

              {!otpExpired && !verificationBlocked ? (
                <p className="auth-switch">
                  Wrong email or account?{" "}
                  <button className="auth-text-button" type="button" onClick={() => void startOver()}>
                    Start over
                  </button>
                </p>
              ) : null}
            </>
          ) : (
            <>
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
                {!isRegister ? (
                  <p className="auth-recovery">
                    <Link href="/docs#account-security">Can&apos;t access your account?</Link>
                    <span> Review sign-in and account guidance.</span>
                  </p>
                ) : null}
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
            {socialLink ? (
              <div className="social-continuation-note">
                Sign in with your password to confirm this social account belongs to you.
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
              required={socialOrganizationSelection}
              autoComplete="organization"
            />

            {error || oauthErrorMessage ? (
              <div className="form-alert" role="alert">
                <span className="form-alert-mark">!</span>
                <span>{error ?? oauthErrorMessage}</span>
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

              {!socialRegistration && !socialOrganizationSelection && !socialLink ? (
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
            </>
          )}
          <p className="auth-legal">
            Customer data stays private to your workspace. Review the{" "}
            <Link href="/docs#account-security">account and security guide</Link>.
          </p>
        </div>
      </section>
    </main>
  );
}
