import { expect, test, type Locator } from "@playwright/test";

import { register, uniqueAccount } from "./helpers";

async function expectCompactControl(control: Locator) {
  const box = await control.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.width).toBeGreaterThanOrEqual(15);
  expect(box!.width).toBeLessThanOrEqual(20);
  expect(box!.height).toBeGreaterThanOrEqual(15);
  expect(box!.height).toBeLessThanOrEqual(20);
}

test("dashboard shell keeps one responsive account menu and a collapsible desktop sidebar", async ({
  page,
}) => {
  const account = uniqueAccount("shell");
  await register(page, account);

  const sidebar = page.locator(".sidebar");
  const main = page.locator(".dashboard-main");
  const expandedSidebar = await sidebar.boundingBox();
  const expandedMain = await main.boundingBox();

  await expect(page.locator(".workspace-switcher")).toHaveCount(0);
  await expect(page.locator(".sidebar-tip")).toHaveCount(0);
  await expect(page.locator(".header-user")).toHaveCount(0);
  await expect(page.getByLabel(`Current organization: ${account.organization}, owner workspace`)).toBeVisible();

  await page.getByRole("button", { name: "Collapse navigation" }).click();
  await expect(page.getByRole("button", { name: "Expand navigation" })).toBeVisible();
  const collapsedSidebar = await sidebar.boundingBox();
  const collapsedMain = await main.boundingBox();
  expect(collapsedSidebar!.width).toBeLessThan(expandedSidebar!.width);
  expect(collapsedMain!.x).toBeLessThan(expandedMain!.x);
  await expect(page.locator(".sidebar .brand-word")).toBeHidden();
  await expect(page.locator('.nav-item[href="/dashboard"] span')).toBeHidden();

  await page.getByRole("button", { name: "Expand navigation" }).click();
  const accountButton = page.getByRole("button", { name: "Open account menu" });
  await accountButton.click();
  await expect(page.getByRole("menu", { name: "Account actions" })).toBeVisible();
  await expect(page.getByRole("menuitem", { name: "Account settings" })).toHaveAttribute(
    "href",
    "/dashboard/account",
  );
  await expect(page.getByRole("menuitem", { name: "Delete account" })).toHaveAttribute(
    "href",
    "/dashboard/account#delete-account",
  );
  await expect(page.getByRole("menuitem", { name: "Sign out" })).toBeVisible();

  await page.locator(".breadcrumb").click();
  await expect(page.getByRole("menu", { name: "Account actions" })).toHaveCount(0);
  await accountButton.click();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("menu", { name: "Account actions" })).toHaveCount(0);
  await expect(accountButton).toBeFocused();

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(sidebar).toHaveClass(/sidebar-open/);
  await page.getByRole("button", { name: "Open account menu" }).click();
  const mobileMenu = page.getByRole("menu", { name: "Account actions" });
  await expect(mobileMenu).toBeVisible();
  const menuBox = await mobileMenu.boundingBox();
  expect(menuBox!.x).toBeGreaterThanOrEqual(0);
  expect(menuBox!.x + menuBox!.width).toBeLessThanOrEqual(390);

  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login(?:\?|$)/);
  const cookies = await page.context().cookies();
  expect(
    cookies.some(
      (cookie) => cookie.name === "sa_access_token" || cookie.name === "sa_refresh_token",
    ),
  ).toBe(false);
});

test("shared dashboard checkboxes, radios, and empty states stay compact", async ({ page }) => {
  await register(page, uniqueAccount("controls"));

  await page.goto("/dashboard/voice");
  await expect(page.getByRole("heading", { name: "Let support speak with care." })).toBeVisible();
  const voiceCheckboxes = page.locator('.voice-form input[type="checkbox"]');
  await expect(voiceCheckboxes).toHaveCount(3);
  for (let index = 0; index < 3; index += 1) {
    await expectCompactControl(voiceCheckboxes.nth(index));
  }

  const voiceEmptyTitle = page.locator(".empty-state strong", {
    hasText: "No voice agent configured.",
  });
  const voiceEmptyCopy = page.locator(".empty-state span", {
    hasText: "Add a number above",
  });
  await expect(voiceEmptyTitle).toBeVisible();
  await expect(voiceEmptyCopy).toBeVisible();
  const voiceTitleBox = await voiceEmptyTitle.boundingBox();
  const voiceCopyBox = await voiceEmptyCopy.boundingBox();
  expect(voiceCopyBox!.y).toBeGreaterThanOrEqual(voiceTitleBox!.y + voiceTitleBox!.height);

  await page.getByText("Allow outbound calls", { exact: true }).click();
  const nestedConsent = page.getByText("I have consent for outbound calling in my region.");
  await expect(nestedConsent).toBeVisible();
  await expectCompactControl(nestedConsent.locator("..").locator('input[type="checkbox"]'));

  await page.goto("/dashboard/channels");
  await expect(page.getByRole("heading", { name: "Meet customers where they already are." })).toBeVisible();
  const channelRadios = page.locator('.channel-option input[type="radio"]');
  await expect(channelRadios).toHaveCount(3);
  for (let index = 0; index < 3; index += 1) {
    await expectCompactControl(channelRadios.nth(index));
  }
  await expectCompactControl(page.locator('.channel-form input[type="checkbox"]'));
  await expect(page.locator(".empty-state", { hasText: "No channels connected yet." })).toBeVisible();
});
