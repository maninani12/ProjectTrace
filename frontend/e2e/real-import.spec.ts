import { test, expect } from "@playwright/test";
import path from "node:path";
const origin = new URL(
  process.env.PROJECTTRACE_BASE_URL || "http://127.0.0.1:5181",
).origin;
const proof = process.env.PROJECTTRACE_PROOF || "test-results";

test("real workspace ZIP import, claims, evidence, question and second-snapshot drift", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const email = `fixture-${Date.now()}@projecttrace.test`;
  const password = "Strong-fixture-password-123!";
  const registration = await page.request.post("/api/auth/register", {
    headers: { Origin: origin },
    data: {
      email,
      password,
      organization: "Real import browser fixture",
    },
  });
  expect(registration.ok()).toBeTruthy();
  const identity = await registration.json();
  expect(
    (
      await page.request.post("/api/auth/logout", {
        headers: { Origin: origin, "X-CSRF-Token": identity.csrf },
        data: {},
      })
    ).ok(),
  ).toBeTruthy();
  await page.goto("/#repositories");
  await expect(page).toHaveURL(/\/repositories$/);
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
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
  await expect(
    page.getByRole("region", { name: "Native analyzer coverage" }),
  ).toBeVisible();
  const first = await (await page.request.get("/api/workspace")).json();
  expect(first.repositories).toHaveLength(1);
  expect(first.job[0].finished_at).toBeTruthy();
  expect(first.repositories[0].snapshot.id).toBeTruthy();
  const firstRepository = first.repositories[0].id;
  const firstSnapshot = first.repositories[0].snapshot.id;
  await page.screenshot({
    path: path.join(proof, "real-repository.png"),
    fullPage: true,
  });
  const nav = page.getByRole("navigation", { name: "Main navigation" });
  await nav.getByRole("button", { name: "Overview", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "Engineering, backed by evidence.",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("region", { name: "Native analyzer coverage" })
      .getByText("SAST", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: path.join(proof, "real-overview.png"),
    fullPage: true,
  });
  await nav.getByRole("button", { name: "Claim Ledger", exact: true }).click();
  await expect(page).toHaveURL(/\/claims$/);
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
  await inspector.getByRole("button", { name: "Review", exact: true }).click();
  await inspector
    .getByLabel("Reason", { exact: true })
    .fill(
      "Reviewed the source snapshot and confirmed the session authentication evidence.",
    );
  await inspector
    .getByRole("button", { name: "Record review", exact: true })
    .click();
  await expect(inspector.getByText("CONFIRMED", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Close dialog", exact: true }).click();
  await nav.getByRole("button", { name: "Code Quality", exact: true }).click();
  await page
    .getByRole("navigation", { name: "Code Quality views" })
    .getByRole("button", { name: "Findings", exact: true })
    .click();
  await expect(
    page.getByRole("button", {
      name: /Cyclomatic complexity exceeds threshold/,
    }),
  ).toBeVisible();
  await nav.getByRole("button", { name: "Security", exact: true }).click();
  await expect(
    page.getByRole("button", { name: /Dynamic SQL reaches an execution sink/ }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: /Credential-shaped value in source/ })
    .click();
  await expect(
    page.getByRole("dialog").getByText("EXAMPLE CREDENTIAL", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("dialog").getByText(/fake_fixture_secret_123456789/),
  ).toHaveCount(0);
  await expect(
    page.getByRole("dialog").getByText("PT-SECRET-001", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Close dialog", exact: true }).click();
  await nav.getByRole("button", { name: "Dependencies", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Dependencies", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Check advisories", exact: true }),
  ).toBeDisabled();
  await expect(
    page
      .locator("tbody")
      .getByRole("button", { name: "lodash Direct dependency", exact: true }),
  ).toBeVisible();
  await expect(
    page.locator("tbody").getByText("NOT CHECKED", { exact: true }).first(),
  ).toBeVisible();
  await page.screenshot({
    path: path.join(proof, "real-dependencies.png"),
    fullPage: true,
  });
  const sbom = await page.request.get("/api/sbom/" + firstSnapshot);
  expect(sbom.ok()).toBeTruthy();
  expect((await sbom.json()).bomFormat).toBe("CycloneDX");
  await nav
    .getByRole("button", { name: "Infrastructure", exact: true })
    .click();
  await page
    .getByRole("navigation", { name: "Infrastructure views" })
    .getByRole("button", { name: "Findings", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: /Privileged container enabled/ }),
  ).toBeVisible();
  await nav.getByRole("button", { name: "Evidence", exact: true }).click();
  await expect(page.locator(".source-code")).toBeVisible();
  await page.screenshot({
    path: path.join(proof, "real-evidence.png"),
    fullPage: true,
  });
  await nav
    .getByRole("button", { name: "Evidence Graph", exact: true })
    .click();
  await expect(page.locator(".react-flow__node").first()).toBeVisible();
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
  await expect(page.getByRole("status")).toContainText("Analysis completed");
  await nav.getByRole("button", { name: /^Drift/ }).click();
  await expect(page.locator("tbody tr")).not.toHaveCount(0);
  await expect(
    page.getByRole("region", { name: "Snapshot change impact" }),
  ).toBeVisible();
  await page.screenshot({
    path: path.join(proof, "real-drift-impact.png"),
    fullPage: true,
  });
  await nav.getByRole("button", { name: "Policies", exact: true }).click();
  await expect(
    page.getByText("Default policy v1", { exact: false }),
  ).toBeVisible();
  await nav.getByRole("button", { name: "Audit Trail", exact: true }).click();
  await expect(
    page.getByText("ANALYSIS COMPLETED", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("HUMAN REVIEW", { exact: true }).first(),
  ).toBeVisible();
  await nav.getByRole("button", { name: "Connections", exact: true }).click();
  await expect(page).toHaveURL(/\/settings\/connections$/);
  await expect(
    page.getByText(/ProjectTrace native analysis works independently/),
  ).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/\/audit$/);
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Audit Trail", exact: true }),
  ).toBeVisible();
  await page.goto("/#Integrations");
  await expect(page).toHaveURL(/\/settings\/connections$/);
  await expect(
    page.getByRole("heading", { name: "Connections", exact: true }),
  ).toBeVisible();
  const isolated = await page
    .context()
    .browser()!
    .newContext({ baseURL: origin });
  const other = await isolated.request.post("/api/auth/register", {
    headers: { Origin: origin },
    data: {
      email: `isolated-${Date.now()}@projecttrace.test`,
      password,
      organization: "Separate browser fixture",
    },
  });
  expect(other.ok()).toBeTruthy();
  const otherWorkspace = await (
    await isolated.request.get("/api/workspace")
  ).json();
  expect(otherWorkspace.repositories).toHaveLength(0);
  expect(otherWorkspace.claim).toHaveLength(0);
  expect(
    (
      await isolated.request.get(
        "/api/workspace?repository_id=" + firstRepository,
      )
    ).status(),
  ).toBe(404);
  expect(
    (await isolated.request.get("/api/sbom/" + firstSnapshot)).status(),
  ).toBe(404);
  await isolated.close();
  expect(errors).toEqual([]);
});
