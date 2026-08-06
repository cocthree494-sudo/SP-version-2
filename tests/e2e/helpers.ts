import { expect, type Page } from "@playwright/test";

export interface AccountFixture {
  email: string;
  password: string;
  organization: string;
  slug: string;
}

export function uniqueAccount(prefix: string): AccountFixture {
  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
  return {
    email: `${prefix}-${suffix}@example.com`,
    password: "correct horse battery staple",
    organization: `${prefix} ${suffix}`,
    slug: `${prefix}-${suffix}`.toLowerCase(),
  };
}

export async function register(page: Page, account: AccountFixture): Promise<void> {
  await page.goto("/register");
  await page.getByLabel("Work email").fill(account.email);
  await page.getByLabel("Password").fill(account.password);
  await page.getByLabel("Organization name").fill(account.organization);
  await page.getByLabel("Workspace URL").fill(account.slug);
  await page.getByRole("button", { name: "Create workspace" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
}

export async function createBot(page: Page, name: string): Promise<string> {
  await page.goto("/dashboard/bots");
  await page.getByRole("button", { name: "New bot" }).click();
  await page.getByLabel("Bot name").fill(name);
  await page.getByRole("button", { name: "Create bot" }).click();
  const card = page.locator(".management-card").filter({ hasText: name });
  await expect(card).toBeVisible();
  const href = await card.getByRole("link", { name: "Knowledge" }).getAttribute("href");
  const botId = new URL(href ?? "", "http://e2e.local").searchParams.get("bot");
  if (!botId) throw new Error("Created bot link did not expose its bot ID");
  return botId;
}
