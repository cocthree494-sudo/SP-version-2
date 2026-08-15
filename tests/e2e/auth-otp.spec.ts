import { expect, test } from "@playwright/test";

import { uniqueAccount } from "./helpers";

test("OTP challenge stays HttpOnly and cancel removes the pending challenge", async ({ page }) => {
  const otpCode = process.env.E2E_OTP_CODE ?? process.env.AUTH_OTP_TEST_CODE;
  test.skip(!otpCode, "Set E2E_OTP_CODE for deterministic OTP browser acceptance");

  const account = uniqueAccount("otp");
  await page.goto("/register");
  await page.getByLabel("Work email").fill(account.email);
  await page.getByLabel("Password").fill(account.password);
  await page.getByLabel("Organization name").fill(account.organization);
  await page.getByLabel("Workspace URL").fill(account.slug);

  const registerResponsePromise = page.waitForResponse("**/api/auth/register");
  await page.getByRole("button", { name: "Create workspace" }).click();
  const registerResponse = await registerResponsePromise;
  expect(registerResponse.status()).toBe(202);
  const registerBody = await registerResponse.json();
  expect(registerBody.challenge_id).toBeUndefined();
  await expect(page.getByLabel("Verification code")).toBeVisible();

  const cookies = await page.context().cookies();
  const pendingCookie = cookies.find((cookie) => cookie.name === "sa_pending_auth");
  expect(pendingCookie?.httpOnly).toBe(true);
  expect(await page.evaluate(() => document.cookie)).not.toContain("sa_pending_auth");

  const crossSite = await page.request.post("/api/auth/otp/resend", {
    headers: { Origin: "https://attacker.example" },
  });
  expect(crossSite.status()).toBe(403);

  const challengeId = pendingCookie?.value;
  expect(challengeId).toBeTruthy();
  await page.getByRole("button", { name: "Start over" }).click();
  await expect(page.getByLabel("Work email")).toBeVisible();
  expect((await page.context().cookies()).some((cookie) => cookie.name === "sa_pending_auth")).toBe(false);

  const apiBase = (process.env.E2E_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
  const cancelledChallenge = await page.request.post(
    `${apiBase}/v1/auth/otp/verify`,
    { data: { challenge_id: challengeId, code: otpCode } },
  );
  expect(cancelledChallenge.status()).toBe(410);
});

test("login and social registration keep their intended mode and redirect", async ({ page }) => {
  await page.goto("/login?next=%2Fdashboard%2Fproviders");
  await expect(page.getByRole("heading", { name: "Welcome back." })).toBeVisible();
  await page.getByRole("link", { name: "Create your workspace" }).click();
  await expect(page).toHaveURL(/\/register\?next=%2Fdashboard%2Fproviders$/);
  await expect(page.getByRole("heading", { name: "Build a better support loop." })).toBeVisible();

  const googleStart = page.waitForRequest("**/api/auth/oauth/google/start?*");
  await page.getByRole("button", { name: "Continue with Google" }).click();
  const googleUrl = (await googleStart).url();
  expect(googleUrl).toContain("mode=register");
  expect(googleUrl).toContain("next=%2Fdashboard%2Fproviders");

  await page.goto("/register?social=register&next=%2Fdashboard%2Fproviders");
  await expect(page.getByRole("heading", { name: "Finish your Relay setup." })).toBeVisible();
  await expect(page.getByText(/Welcome back/i)).toHaveCount(0);

  await page.goto("/register?oauth_error=account_exists&provider=google");
  await expect(page.getByRole("alert")).toContainText(
    "already belongs to a Relay account",
  );
  await expect(page.getByRole("heading", { name: "Build a better support loop." })).toBeVisible();
});
