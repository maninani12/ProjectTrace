import { test, expect } from "@playwright/test";
import path from "node:path";

const origin = new URL(
  process.env.PROJECTTRACE_BASE_URL || "http://127.0.0.1:5181",
).origin;
const proof = process.env.PROJECTTRACE_PROOF || "test-results";

test("native profiles, static cloud risk and credential-gated AWS inventory", async ({
  page,
}) => {
  const registration = await page.request.post("/api/auth/register", {
    headers: { Origin: origin },
    data: {
      email: `native-${Date.now()}@projecttrace.test`,
      password: "Disposable-browser-password-123!",
      organization: "Native browser validation",
    },
  });
  expect(registration.ok()).toBeTruthy();
  const headers = {
    Origin: origin,
    "X-CSRF-Token": (await registration.json()).csrf,
  };
  const source = {
    "README.md": "Production storage is private.",
    "main.tf": 'resource "aws_s3_bucket" "production" { acl = "public-read" }',
    "app.py":
      'def query():\n value = request.args["query"]\n db.execute(f"SELECT {value}")',
    "package-lock.json":
      '{"lockfileVersion":3,"packages":{"node_modules/fixture":{"version":"1.0.0","license":"GPL-3.0-only"}}}',
  };
  const imported = await page.request.post("/api/import", {
    headers,
    data: { name: "native-cloud-fixture", files: source },
  });
  expect(imported.ok()).toBeTruthy();
  const repository = (await imported.json()).repository_id;
  await page.goto("/settings");
  await page.getByLabel("Global repository").selectOption(repository);
  await expect(
    page.getByText("Repository overrides", { exact: false }),
  ).toBeVisible();
  await page.getByLabel("Native gate scope").selectOption("NEW_FINDINGS");
  await page.getByLabel("Restricted licenses").fill("GPL-3.0-only");
  await page
    .getByRole("button", {
      name: "Save gate, license and infrastructure policy",
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "Profile saved" }),
  ).toBeVisible();
  const profile = await (
    await page.request.get(`/api/native/profile?repository_id=${repository}`)
  ).json();
  expect(profile.gate_scope).toBe("NEW_FINDINGS");
  expect(profile.licenses.restricted).toEqual(["GPL-3.0-only"]);
  await page.screenshot({
    path: path.join(proof, "native-profile-policy.png"),
    fullPage: true,
  });
  const next = await page.request.post(
    `/api/repositories/${repository}/analyze`,
    { headers, data: { files: source } },
  );
  expect(next.ok()).toBeTruthy();
  const workspace = await (
    await page.request.get(`/api/workspace?repository_id=${repository}`)
  ).json();
  expect(
    workspace.finding.some(
      (item: { rule: string }) => item.rule === "PT-LICENSE-001",
    ),
  ).toBeTruthy();
  const nav = page.getByRole("navigation", { name: "Main navigation" });
  await nav.getByRole("button", { name: "Cloud Assets", exact: true }).click();
  await expect(
    page.getByText("aws_s3_bucket.production", { exact: true }),
  ).toBeVisible();
  await nav.getByRole("button", { name: "Risk Paths", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /Declared public access/ }),
  ).toBeVisible();
  await nav.getByRole("button", { name: "Cloud", exact: true }).click();
  await page.getByLabel("Cloud repository").selectOption(repository);
  await page.getByLabel("AWS account ID").fill("123456789012");
  await page
    .getByRole("button", { name: "Sync read-only AWS inventory", exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: /credential/i }),
  ).toBeVisible();
  await page.screenshot({
    path: path.join(proof, "native-aws-credential-gate.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
});
