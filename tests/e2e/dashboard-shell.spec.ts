import { expect, test } from "@playwright/test";

import { register, uniqueAccount } from "./helpers";

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
