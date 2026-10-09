import { test, expect } from "@playwright/test";
import { completedAnalysis } from "./analysis";

const origin = new URL(
  process.env.PROJECTTRACE_BASE_URL || "http://127.0.0.1:5181",
).origin;

test("scoped repository counts, session organization change and visible read failure recovery", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const label = Date.now();
  const password = "Disposable-stability-fixture-123!";
  const firstEmail = `stability-first-${label}@projecttrace.test`;
  const registered = await page.request.post("/api/auth/register", {
    headers: { Origin: origin },
    data: { email: firstEmail, password, organization: "Release scope first" },
  });
  expect(registered.status()).toBe(200);
  const csrf = (await registered.json()).csrf;
  const headers = { Origin: origin, "X-CSRF-Token": csrf };
  const snapshots = [];
  for (const name of ["Scope A", "Scope B"]) {
    const imported = await page.request.post("/api/import", {
      headers,
      data: {
        name,
        files: {
          "README.md": "This service uses session authentication.",
          "app.py": "import flask\nfrom flask import session\n",
        },
      },
    });
    snapshots.push(await completedAnalysis(page.request, imported));
  }
  await page.goto("/claims");
  const repositoryMenu = page.getByLabel("Global repository");
  await expect(repositoryMenu.locator("option")).toHaveCount(3);
  await repositoryMenu.selectOption(snapshots[0].repository_id);
  const scoped = await (
    await page.request.get(
      `/api/workspace?summary=1&repository_id=${snapshots[0].repository_id}`,
    )
  ).json();
  await expect(
    page.getByText(
      new RegExp(`of ${scoped.counts.totals.claim} matching records`),
    ),
  ).toBeVisible();
  await expect(repositoryMenu.locator("option")).toHaveCount(3);
  await repositoryMenu.selectOption(snapshots[1].repository_id);
  await expect(page.getByText(/matching records/)).toBeVisible();
  const pageResult = await (
    await page.request.get(
      `/api/workspace/records?view=Claim%20Ledger&repository_id=${snapshots[1].repository_id}`,
    )
  ).json();
  expect(
    pageResult.items.every(
      (item: { repository_id: string }) =>
        item.repository_id === snapshots[1].repository_id,
    ),
  ).toBe(true);

  await page.route("**/api/workspace?summary=1**", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Controlled read failure" }),
    }),
  );
  await page.goto("/overview");
  await expect(
    page.getByRole("alert").filter({ hasText: "Controlled read failure" }),
  ).toBeVisible({ timeout: 20000 });
  await expect(
    page.getByText("Loading engineering evidence", { exact: false }),
  ).toHaveCount(0);
  await expect(page.getByText("0 claims", { exact: true })).toHaveCount(0);
  await page.unroute("**/api/workspace?summary=1**");
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "Controlled read failure" }),
  ).toHaveCount(0);
  await expect(repositoryMenu.locator("option")).toHaveCount(3);

  const identity = await (await page.request.get("/api/auth/me")).json();
  await page.request.post("/api/auth/logout", {
    headers: { Origin: origin, "X-CSRF-Token": identity.csrf },
    data: {},
  });
  const second = await page.request.post("/api/auth/register", {
    headers: { Origin: origin },
    data: {
      email: `stability-second-${label}@projecttrace.test`,
      password,
      organization: "Release scope second",
    },
  });
  expect(second.status()).toBe(200);
  await page.goto("/repositories");
  await expect(page.getByRole("status")).toContainText(
    "No repository imported",
  );
  await expect(page.getByText("Scope A", { exact: true })).toHaveCount(0);
  expect(
    (await page.request.get(`/api/record/${snapshots[0].id}`)).status(),
  ).toBe(404);
  const secondIdentity = await (await page.request.get("/api/auth/me")).json();
  await page.request.post("/api/auth/logout", {
    headers: { Origin: origin, "X-CSRF-Token": secondIdentity.csrf },
    data: {},
  });
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(firstEmail);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(repositoryMenu.locator("option")).toHaveCount(3);
  expect(errors).toEqual([]);
});
