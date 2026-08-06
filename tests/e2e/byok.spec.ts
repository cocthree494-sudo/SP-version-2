import { expect, test, type Page, type Route } from "@playwright/test";

import { register, uniqueAccount } from "./helpers";

interface MockCredential {
  id: string;
  provider: "openai";
  label: string;
  masked_secret: string;
  low_cost_model_id: string;
  strong_model_id: string | null;
  status: "unverified" | "verified" | "revoked";
  verified_at: string | null;
  rotated_at: string | null;
  revoked_at: string | null;
  created_at: string;
  updated_at: string;
}

async function json(route: Route, status: number, body: unknown) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

async function mockProviderApi(page: Page) {
  const now = new Date().toISOString();
  let credentials: MockCredential[] = [];
  let policy = { mode: "platform_only", credential_order: [] as string[] };
  await page.route("**/api/backend/providers/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace(/^\/api\/backend/, "");
    if (path === "/providers/credentials" && request.method() === "GET") {
      await json(route, 200, credentials);
      return;
    }
    if (path === "/providers/credentials" && request.method() === "POST") {
      const input = request.postDataJSON() as Record<string, string>;
      const raw = input.api_key;
      const credential: MockCredential = {
        id: crypto.randomUUID(),
        provider: "openai",
        label: input.label,
        masked_secret: `••••${raw.slice(-4)}`,
        low_cost_model_id: input.low_cost_model_id,
        strong_model_id: input.strong_model_id || null,
        status: "unverified",
        verified_at: null,
        rotated_at: null,
        revoked_at: null,
        created_at: now,
        updated_at: now,
      };
      credentials = [...credentials, credential];
      await json(route, 201, credential);
      return;
    }
    const verify = path.match(/^\/providers\/credentials\/([^/]+)\/verify$/);
    if (verify && request.method() === "POST") {
      credentials = credentials.map((item) => item.id === verify[1]
        ? { ...item, status: "verified", verified_at: now }
        : item);
      await json(route, 200, credentials.find((item) => item.id === verify[1]));
      return;
    }
    const rotate = path.match(/^\/providers\/credentials\/([^/]+)\/secret$/);
    if (rotate && request.method() === "PUT") {
      const raw = (request.postDataJSON() as { api_key: string }).api_key;
      credentials = credentials.map((item) => item.id === rotate[1]
        ? { ...item, masked_secret: `••••${raw.slice(-4)}`, status: "unverified", verified_at: null, rotated_at: now }
        : item);
      policy.credential_order = policy.credential_order.filter((id) => id !== rotate[1]);
      await json(route, 200, credentials.find((item) => item.id === rotate[1]));
      return;
    }
    const revoke = path.match(/^\/providers\/credentials\/([^/]+)$/);
    if (revoke && request.method() === "DELETE") {
      credentials = credentials.map((item) => item.id === revoke[1]
        ? { ...item, status: "revoked", revoked_at: now }
        : item);
      policy.credential_order = policy.credential_order.filter((id) => id !== revoke[1]);
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    if (path === "/providers/policy" && request.method() === "GET") {
      await json(route, 200, policy);
      return;
    }
    if (path === "/providers/policy" && request.method() === "PATCH") {
      policy = request.postDataJSON() as typeof policy;
      await json(route, 200, policy);
      return;
    }
    await route.continue();
  });
  return () => ({ credentials, policy });
}

test("BYOK add → masking → verify → explicit fallback → rotate → revoke", async ({ page }) => {
  const state = await mockProviderApi(page);
  await register(page, uniqueAccount("byok"));
  await page.goto("/dashboard/providers");

  const originalKey = "sk-e2e-write-only-secret-1234";
  await page.getByLabel("API key").fill(originalKey);
  await page.getByRole("button", { name: "Encrypt and add" }).click();
  await expect(page.getByText("••••1234")).toBeVisible();
  await expect(page.locator("body")).not.toContainText(originalKey);
  await expect(page.getByLabel("API key")).toHaveValue("");

  await page.getByRole("button", { name: "Test key" }).click();
  await expect(page.getByText("verified", { exact: true })).toBeVisible();
  await page.getByText("Your key, then platform fallback", { exact: true }).click();
  await page.locator(".policy-credential input[type=checkbox]").check();
  await page.getByRole("button", { name: "Save routing policy" }).click();
  expect(state().policy.mode).toBe("tenant_first_with_platform_fallback");
  expect(state().policy.credential_order).toHaveLength(1);

  await page.getByRole("button", { name: "Rotate" }).click();
  const rotatedKey = "sk-e2e-rotated-write-only-5678";
  await page.getByLabel("New API key").fill(rotatedKey);
  await page.getByRole("button", { name: "Rotate key" }).click();
  await expect(page.getByText("••••5678")).toBeVisible();
  await expect(page.locator("body")).not.toContainText(rotatedKey);
  await expect(page.getByText("unverified", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Test key" }).click();
  await page.getByRole("button", { name: /Revoke Production OpenAI/ }).click();
  await page.getByRole("button", { name: "Revoke credential" }).click();
  await expect(page.getByText("revoked", { exact: true })).toBeVisible();
  expect(state().policy.mode).toBe("tenant_first_with_platform_fallback");
  expect(state().policy.credential_order).toEqual([]);
});
