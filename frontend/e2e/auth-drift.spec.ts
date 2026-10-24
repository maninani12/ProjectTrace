import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { completedAnalysis } from "./analysis";

const fixture = JSON.parse(
  fs.readFileSync(path.resolve("../samples/auth-drift.json"), "utf8"),
);
const origin = new URL(
  process.env.PROJECTTRACE_BASE_URL || "http://127.0.0.1:5181",
).origin;

test("authentication documentation drift shows original claim and immutable BASE/HEAD source", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const registration = await page.request.post("/api/auth/register", {
    headers: { Origin: origin },
    data: {
      email: `auth-drift-${Date.now()}@projecttrace.test`,
      password: "Strong-fixture-password-123!",
      organization: "Auth drift browser fixture",
    },
  });
  expect(registration.status()).toBe(200);
  const identity = await registration.json();
  const headers = { Origin: origin, "X-CSRF-Token": identity.csrf };
  const imported = await page.request.post("/api/import", {
    headers,
    data: { name: "Authentication drift", files: fixture.base },
  });
  const base = await completedAnalysis(page.request, imported);
  const analyzed = await page.request.post(
    `/api/repositories/${base.repository_id}/analyze`,
    { headers, data: { base_id: base.snapshot_id, files: fixture.head } },
  );
  const head = await completedAnalysis(page.request, analyzed);
  await page.goto("/engineering-changes");
  await page
    .getByRole("button", { name: "Inspect engineering change", exact: true })
    .click();
  const detail = page.getByRole("region", {
    name: "Engineering change details",
  });
  await expect(
    detail.getByText(`BASE ${base.snapshot_id} → HEAD ${head.id}`, {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    detail.getByRole("heading", {
      name: "Original claim: Authentication uses JWT.",
    }),
  ).toBeVisible();
  const comparison = page.getByRole("region", {
    name: "Claim evidence comparison",
  });
  await expect(comparison.getByText("VERIFIED", { exact: true })).toBeVisible();
  await expect(
    comparison.getByText("CONTRADICTED", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: test.info().outputPath("auth-drift-comparison.png"),
    fullPage: true,
  });
  for (const [label, source] of [
    ["BASE", "jwt.encode"],
    ["HEAD", "SessionMiddleware"],
  ]) {
    await comparison
      .getByRole("button", {
        name: `Inspect ${label} source: app.py`,
        exact: true,
      })
      .click();
    const inspector = page.getByRole("dialog", { name: "Evidence inspector" });
    await expect(inspector.locator("pre")).toContainText(source);
    await page.screenshot({
      path: test
        .info()
        .outputPath(`auth-drift-${label.toLowerCase()}-source.png`),
    });
    await inspector
      .getByRole("button", { name: "Close dialog", exact: true })
      .click();
  }
  await comparison
    .getByRole("button", { name: "Inspect HEAD claim", exact: true })
    .click();
  const inspector = page.getByRole("dialog", { name: "Evidence inspector" });
  await inspector.getByRole("button", { name: "History", exact: true }).click();
  await expect(inspector.getByText("STALE", { exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});
