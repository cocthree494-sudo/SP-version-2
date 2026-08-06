import { expect, test } from "@playwright/test";

import { createBot, register, uniqueAccount } from "./helpers";

const fixtureOrigin = process.env.E2E_FIXTURE_ORIGIN ?? "http://127.0.0.1:4174";
const apiOrigin = process.env.E2E_API_URL ?? "http://127.0.0.1:8000";
const websiteUrl = process.env.E2E_WEBSITE_URL;

test("register → bot → all source types → grounded playground → widget chat", async ({ page }) => {
  test.skip(!websiteUrl, "Set E2E_WEBSITE_URL to a public deterministic crawl fixture");
  const account = uniqueAccount("critical");
  await register(page, account);
  const botName = "Critical path bot";
  const botId = await createBot(page, botName);

  await page.goto(`/dashboard/knowledge?bot=${encodeURIComponent(botId)}`);
  await page.locator('input[type="file"]').setInputFiles({
    name: "refund-policy.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Refund requests are accepted within 30 days with an order number."),
  });
  await expect(page.getByText(/file queued for processing/i)).toBeVisible();

  await page.getByRole("button", { name: "website" }).click();
  await page.getByLabel("Website URL").fill(websiteUrl!);
  await page.getByLabel("Display name").fill("E2E help center");
  await page.getByRole("button", { name: "Start bounded crawl" }).click();
  await expect(page.getByText(/Website crawl queued/i)).toBeVisible();

  await page.getByRole("button", { name: "manual" }).click();
  await page.getByLabel("Entry name").fill("Refund window");
  await page.getByLabel("Customer question").fill("How long do I have to request a refund?");
  await page.getByLabel("Authoritative answer").fill("Customers have 30 days to request a refund.");
  await page.getByRole("button", { name: "Add manual answer" }).click();
  await expect(page.getByText(/Manual answer queued/i)).toBeVisible();

  for (const sourceName of ["refund-policy.txt", "E2E help center", "Refund window"]) {
    const row = page.locator(".source-row").filter({ hasText: sourceName });
    await expect(row).toBeVisible();
    await expect(row.getByText("ready", { exact: true })).toBeVisible({ timeout: 120_000 });
  }

  await page.goto("/dashboard/playground");
  await page.getByLabel("Support question").fill("How many days do I have to request a refund?");
  await page.getByRole("button", { name: "Send" }).click();
  const answer = page.locator(".chat-bubble-assistant").last();
  await expect(answer).not.toContainText("Thinking", { timeout: 60_000 });
  await expect(answer.locator(".citation-list")).toBeVisible();

  await page.goto("/dashboard/widget");
  const originInput = page.getByLabel("Exact origins");
  await originInput.fill(fixtureOrigin);
  await page.getByRole("button", { name: "Create widget key" }).click();
  const snippet = await page.locator(".install-card code").innerText();
  const key = snippet.match(/data-publishable-key="([^"]+)"/)?.[1];
  expect(key).toBeTruthy();

  await page.goto(`${fixtureOrigin}/?key=${encodeURIComponent(key!)}&api=${encodeURIComponent(apiOrigin)}`);
  await page.getByRole("button", { name: "Open support chat" }).click();
  await page.getByLabel("Message support").fill("What is the refund window?");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.locator(".bubble-user")).toContainText("refund window");
  await expect(page.locator(".bubble-agent").last()).not.toContainText("I couldn't", {
    timeout: 60_000,
  });
});

test("a second tenant cannot read the first tenant bot", async ({ browser, page }) => {
  await register(page, uniqueAccount("tenant-a"));
  const botId = await createBot(page, "Tenant A private bot");

  const secondContext = await browser.newContext();
  const secondPage = await secondContext.newPage();
  await register(secondPage, uniqueAccount("tenant-b"));
  const status = await secondPage.evaluate(async (id) => {
    const response = await fetch(`/api/backend/bots/${encodeURIComponent(id)}`, {
      cache: "no-store",
    });
    return response.status;
  }, botId);
  expect(status).toBe(404);
  await secondContext.close();
});
