import { test, expect } from "@playwright/test";
import path from "node:path";

test("real workspace ZIP import, claims, evidence, question and second-snapshot drift", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const registration = await page.request.post("/api/auth/register", {
    headers: { Origin: "http://127.0.0.1:5181" },
    data: {
      email: `fixture-${Date.now()}@projecttrace.test`,
      password: "Strong-fixture-password-123!",
      organization: "Real import browser fixture",
    },
  });
  expect(registration.ok()).toBeTruthy();
  await page.goto("/#repositories");
  await expect(page.getByRole("status")).toContainText(
    "No repository imported",
  );
  await expect(
    page.getByText("Import a repository to begin analysis.", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Import repository", exact: true })
    .click();
  await page
    .getByLabel("Repository name", { exact: true })
    .fill("native-real-fixture");
  await page
    .getByLabel("Source archive", { exact: true })
    .setInputFiles(path.resolve("e2e/fixtures/native-fixture.zip"));
  await page
    .getByRole("button", { name: "Analyze source snapshot", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "native-real-fixture", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("status")).toContainText("Analysis completed");
  await expect(page.getByText("DEMO DATA", { exact: true })).toHaveCount(0);
  const nav = page.getByRole("navigation", { name: "Main navigation" });
  await nav.getByRole("button", { name: "Claim Ledger", exact: true }).click();
  await page.getByLabel("Status filter").selectOption("CONTRADICTED");
  await page.getByRole("button", { name: /Authentication uses JWT\./ }).click();
  const inspector = page.getByRole("dialog", { name: "Evidence inspector" });
  await expect(
    inspector.getByText("CONTRADICTED", { exact: true }),
  ).toBeVisible();
  await inspector
    .getByRole("button", { name: "Evidence", exact: true })
    .click();
  await expect(
    inspector.getByText("app.py", { exact: false }).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "Close dialog", exact: true }).click();
  await nav.getByRole("button", { name: "Drift", exact: true }).click();
  await expect(
    page.getByText("No historical drift detected.", { exact: true }),
  ).toBeVisible();
  await nav
    .getByRole("button", { name: "Ask Engineering", exact: true })
    .click();
  await page
    .getByLabel("Engineering question")
    .fill("How is authentication implemented?");
  await page.getByRole("button", { name: "Investigate with evidence" }).click();
  await expect(
    page.getByRole("heading", { name: /session authentication/ }),
  ).toBeVisible();
  await nav.getByRole("button", { name: "Repositories", exact: true }).click();
  await page
    .getByRole("button", { name: "Upload new snapshot", exact: true })
    .click();
  await page
    .getByLabel("Source archive", { exact: true })
    .setInputFiles(path.resolve("e2e/fixtures/native-fixture-updated.zip"));
  await page
    .getByRole("button", { name: "Analyze and compare snapshot", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await nav.getByRole("button", { name: /^Drift/ }).click();
  await expect(page.locator("tbody tr")).not.toHaveCount(0);
  await nav.getByRole("button", { name: "Audit Trail", exact: true }).click();
  await expect(
    page.getByText("ANALYSIS COMPLETED", { exact: true }).first(),
  ).toBeVisible();
  expect(errors).toEqual([]);
});
