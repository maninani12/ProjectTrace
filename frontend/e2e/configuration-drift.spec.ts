import { test, expect } from "./fixtures";
import fs from "node:fs";
import path from "node:path";
import { completedAnalysis } from "./analysis";

const fixture = JSON.parse(
  fs.readFileSync(path.resolve("../samples/configuration-drift.json"), "utf8"),
);
const origin = new URL(
  process.env.PROJECTTRACE_BASE_URL || "http://127.0.0.1:5181",
).origin;

test("configuration drift shows scoped BASE and HEAD source evidence", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const registration = await page.request.post("/api/auth/register", {
    headers: { Origin: origin },
    data: {
      email: `configuration-drift-${Date.now()}@projecttrace.test`,
      password: "Strong-fixture-password-123!",
      organization: "Configuration drift browser fixture",
    },
  });
  expect(registration.status()).toBe(200);
  const identity = await registration.json();
  const headers = { Origin: origin, "X-CSRF-Token": identity.csrf };
  const imported = await page.request.post("/api/import", {
    headers,
    data: { name: "Configuration drift", files: fixture.base },
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
      name: "Original claim: Production storage is private.",
    }),
  ).toBeVisible();
  const comparison = page.getByRole("region", {
    name: "Claim evidence comparison",
  });
  await expect(comparison.getByText("UNVERIFIED", { exact: true })).toBeVisible();
  await expect(
    comparison.getByText("CONTRADICTED", { exact: true }),
  ).toBeVisible();
  await expect(comparison.getByText("live deployment is unobserved")).toBeVisible();
  await comparison
    .getByRole("button", {
      name: "Inspect HEAD source: main.tf",
      exact: true,
    })
    .click();
  const inspector = page.getByRole("dialog", { name: "Evidence inspector" });
  await expect(inspector.locator("pre")).toContainText('acl = "public-read"');
  await inspector.getByRole("button", { name: "Close dialog", exact: true }).click();
  expect(errors).toEqual([]);
});
