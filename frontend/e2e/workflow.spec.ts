import { test, expect } from "@playwright/test";
import path from "node:path";
const proof = process.env.PROJECTTRACE_PROOF || "test-results";
test("a delayed review response cannot reopen a closed evidence inspector", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Explore Northstar demo" }).click();
  await page.getByRole("button", { name: "Close dialog", exact: true }).click();
  await page
    .getByRole("button", { name: "Inspect the evidence", exact: true })
    .click();
  const inspector = page.getByRole("dialog", { name: "Evidence inspector" });
  await inspector.getByRole("button", { name: "Review", exact: true }).click();
  await inspector
    .getByLabel("Reason", { exact: true })
    .fill("Confirmed source evidence while testing a delayed review response.");
  let release!: () => void;
  let stored!: () => void;
  const delayed = new Promise<void>((resolve) => {
    release = resolve;
  });
  const saved = new Promise<void>((resolve) => {
    stored = resolve;
  });
  await page.route("**/api/record/*/review", async (route) => {
    const response = await route.fetch();
    expect(response.status()).toBe(200);
    stored();
    await delayed;
    await route.fulfill({ response });
  });
  await inspector.getByRole("button", { name: "Record review" }).click();
  await saved;
  await inspector
    .getByRole("button", { name: "Close dialog", exact: true })
    .click();
  await expect(inspector).toHaveCount(0);
  const response = page.waitForResponse(
    (result) =>
      result.url().endsWith("/review") && result.request().method() === "POST",
  );
  const refreshed = page.waitForResponse((result) =>
    result.url().includes("/api/workspace?summary=1"),
  );
  release();
  expect((await response).status()).toBe(200);
  // The review completion invalidates the workspace. Wait for that refresh
  // so this assertion observes the callback, rather than an earlier render.
  expect((await refreshed).status()).toBe(200);
  await expect(
    page.getByRole("button", { name: "Claim Ledger", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Claim Ledger", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Claim Ledger", exact: true }),
  ).toBeVisible();
  await expect(inspector).toHaveCount(0);
});

test("investigation pins displayed snapshots and ignores a response after its scope changes", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Explore Northstar demo" }).click();
  await page.getByRole("button", { name: "Close dialog", exact: true }).click();
  await page
    .getByRole("button", { name: "Ask Engineering", exact: true })
    .click();
  let release!: () => void;
  let stored!: () => void;
  const delayed = new Promise<void>((resolve) => {
    release = resolve;
  });
  const saved = new Promise<void>((resolve) => {
    stored = resolve;
  });
  await page.route("**/api/ask", async (route) => {
    const payload = route.request().postDataJSON();
    expect(payload.repository_id).toBe("identity");
    expect(payload.snapshot_ids).toHaveLength(1);
    const response = await route.fetch();
    expect(response.status()).toBe(200);
    const answer = await response.json();
    expect(answer.snapshot_ids).toEqual({ identity: payload.snapshot_ids[0] });
    stored();
    await delayed;
    await route.fulfill({ response });
  });
  await page.getByRole("button", { name: "Investigate with evidence" }).click();
  await saved;
  await page.getByLabel("Investigation repository").selectOption("clean");
  const response = page.waitForResponse((result) =>
    result.url().endsWith("/api/ask"),
  );
  release();
  const delayedResponse = await response;
  expect(delayedResponse.status()).toBe(200);
  await delayedResponse.finished();
  await page.evaluate(
    () =>
      new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
      ),
  );
  await expect(
    page.getByRole("heading", {
      name: /current static evidence configures server-side session/,
    }),
  ).toHaveCount(0);
  await page.unroute("**/api/ask");
  const next = page.waitForResponse((result) =>
    result.url().endsWith("/api/ask"),
  );
  await page.getByRole("button", { name: "Investigate with evidence" }).click();
  const answer = await (await next).json();
  expect(Object.keys(answer.snapshot_ids)).toEqual(["clean"]);
  await expect(
    page.getByRole("heading", {
      name: /current static evidence configures server-side session/,
    }),
  ).toHaveCount(0);
});

test("CEO and engineer evidence workflow", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/login");
  await page.getByRole("button", { name: "Explore Northstar demo" }).click();
  await page.getByRole("button", { name: "Close dialog", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Engineering, backed by evidence." }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Native analyzer coverage" }),
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
  await expect(page.locator("tbody tr")).toHaveCount(2);
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
    "Secrets",
    "Infrastructure",
    "Cloud",
    "Cloud Assets",
    "Cloud Identities",
    "Exposure",
    "Risk Paths",
    "Drift",
    "Architecture",
    "API Integrity",
    "Evidence",
    "Evidence Graph",
    "Policies",
    "Reviews",
    "Audit Trail",
    "Connections",
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
  await page.goto("/login");
  await page.getByRole("button", { name: "Explore Northstar demo" }).click();
  await page.getByRole("button", { name: "Close dialog", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Engineering, backed by evidence." }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Native analyzer coverage" }),
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
