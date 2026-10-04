import { test, expect } from "@playwright/test";
import path from "node:path";
const proof = process.env.PROJECTTRACE_PROOF || "test-results";
test("CEO and engineer evidence workflow", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page.getByRole("button", { name: "Explore Northstar demo" }).click();
  await page.getByRole("button", { name: "Close dialog", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Engineering, backed by evidence." }),
  ).toBeVisible();
  await page.screenshot({
    path: path.join(proof, "overview.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Inspect the evidence", exact: true })
    .click();
  const inspector = page.getByRole("dialog", { name: "Evidence inspector" });
  await expect(
    inspector.getByRole("heading", { name: "Authentication uses JWT." }),
  ).toBeVisible();
  await expect(
    inspector.getByText("CONTRADICTED", { exact: true }),
  ).toBeVisible();
  await inspector.getByRole("button", { name: "History", exact: true }).click();
  await expect(inspector.getByText("STALE", { exact: true })).toBeVisible();
  await page.screenshot({ path: path.join(proof, "claim-history.png") });
  await inspector.getByRole("button", { name: "Review", exact: true }).click();
  await inspector
    .getByLabel("Reason", { exact: true })
    .fill(
      "Confirmed the authentication change against current session middleware.",
    );
  await inspector.getByRole("button", { name: "Record review" }).click();
  await expect(inspector.getByText("CONFIRMED", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Close dialog", exact: true }).click();
  const nav = page.getByRole("navigation", { name: "Main navigation" });
  await nav.getByRole("button", { name: "Claim Ledger", exact: true }).click();
  await page.getByLabel("Status filter").selectOption("CONTRADICTED");
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await nav
    .getByRole("button", { name: "Ask Engineering", exact: true })
    .click();
  await page.getByRole("button", { name: "Investigate with evidence" }).click();
  await expect(
    page.getByRole("heading", {
      name: /current static evidence configures server-side session/,
    }),
  ).toBeVisible();
  await page.screenshot({
    path: path.join(proof, "investigation.png"),
    fullPage: true,
  });
  await nav.getByRole("button", { name: "Pull Requests", exact: true }).click();
  await expect(
    page.getByText("ProjectTrace gate", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: path.join(proof, "pull-request.png"),
    fullPage: true,
  });
  for (const name of [
    "Systems",
    "Components",
    "Repositories",
    "Findings",
    "Code Quality",
    "Security",
    "Dependencies",
    "Infrastructure",
    "Cloud",
    "Drift",
    "Architecture",
    "Evidence",
    "Evidence Graph",
    "Policies",
    "Audit Trail",
    "Integrations",
    "Settings",
  ]) {
    await nav
      .getByRole("button", { name: new RegExp("^" + name + "(?: \\d+)?$") })
      .click();
    await expect(
      page.getByRole("heading", { name, exact: true }),
    ).toBeVisible();
    await page.screenshot({
      path: path.join(proof, name.toLowerCase().replaceAll(" ", "-") + ".png"),
      fullPage: true,
    });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
  }
  await nav.getByRole("button", { name: "Audit Trail", exact: true }).click();
  await expect(
    page.getByText("HUMAN REVIEW", { exact: true }).first(),
  ).toBeVisible();
  expect(errors).toEqual([]);
});
test("mobile review and honest unsupported investigation", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Explore Northstar demo" }).click();
  await page.getByRole("button", { name: "Close dialog", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Engineering, backed by evidence." }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: path.join(proof, "mobile-overview.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Ask Engineering", exact: true })
    .click();
  await page
    .getByLabel("Engineering question", { exact: true })
    .fill("What is the temperature on Jupiter?");
  await page.getByRole("button", { name: "Investigate with evidence" }).click();
  await expect(
    page.getByRole("heading", { name: /Insufficient evidence/ }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
});
