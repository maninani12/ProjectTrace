import { test, expect } from "@playwright/test";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";

test("a rate-limited identity read preserves the session and offers access retry", async ({
  page,
}) => {
  test.skip(
    !process.env.PROJECTTRACE_LARGE_ACCOUNT,
    "Needs the authorized current-record mirror.",
  );
  const account = JSON.parse(
    readFileSync(process.env.PROJECTTRACE_LARGE_ACCOUNT!, "utf8"),
  );
  const login = await page.request.post("/api/auth/login", {
    headers: { Origin: new URL(process.env.PROJECTTRACE_BASE_URL!).origin },
    data: { email: account.email, password: account.password },
  });
  expect(login.status()).toBe(200);
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({
      status: 429,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Rate limit exceeded; retry later." }),
    }),
  );
  await page.goto("/repositories");
  await expect(
    page.getByRole("heading", { name: "Workspace access unavailable" }),
  ).toBeVisible();
  await expect(page.getByRole("alert")).toContainText("Rate limit exceeded");
  await expect(page.getByLabel("Password", { exact: true })).toHaveCount(0);
  await page.unroute("**/api/auth/me");
  await page.getByRole("button", { name: "Retry access", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "spring petclinic", exact: true }),
  ).toBeVisible();
});

test("two current ZIPs load independently, show honest diagnostics and pin Explore scope", async ({
  page,
}) => {
  test.skip(
    !process.env.PROJECTTRACE_LARGE_ACCOUNT,
    "Needs the authorized current-record mirror.",
  );
  const account = JSON.parse(
    readFileSync(process.env.PROJECTTRACE_LARGE_ACCOUNT!, "utf8"),
  );
  const proof = process.env.PROJECTTRACE_PROOF!;
  mkdirSync(proof, { recursive: true });
  const login = await page.request.post("/api/auth/login", {
    headers: { Origin: new URL(process.env.PROJECTTRACE_BASE_URL!).origin },
    data: { email: account.email, password: account.password },
  });
  expect(login.status()).toBe(200);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  let summaries = 0;
  await page.route("**/api/workspace?summary=1**", (route) => {
    summaries++;
    return route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        detail: "Summary must be independent of repository listing",
      }),
    });
  });
  const times = [];
  for (let i = 0; i < 8; i++) {
    const started = performance.now();
    const listing = page.waitForResponse((response) =>
      response.url().includes("/api/repositories?offset="),
    );
    await page.goto("/repositories");
    const payload = await (await listing).json();
    expect(payload.repositories).toHaveLength(2);
    expect(
      payload.repositories.every(
        (repo: {
          snapshot: { status: string };
          latest_job: { state: string };
        }) =>
          repo.snapshot.status === "PARTIAL" &&
          repo.latest_job.state === "PARTIAL",
      ),
    ).toBe(true);
    await expect(
      page.getByRole("heading", { name: "spring petclinic", exact: true }),
    ).toBeVisible();
    await expect(page.getByText("21269", { exact: true })).toBeVisible();
    await expect(page.getByText("183", { exact: true })).toBeVisible();
    await expect(
      page.getByText("Loading repositories…", { exact: false }),
    ).toHaveCount(0);
    times.push(performance.now() - started);
  }
  expect(summaries).toBe(0);
  expect(Math.max(...times)).toBeLessThan(15000);
  const spring = page.locator("article.repo-card").filter({
    has: page.getByRole("heading", { name: "spring petclinic", exact: true }),
  });
  await spring
    .getByText("Analysis diagnostics · PARTIAL", { exact: true })
    .click();
  await expect(spring.getByText(/3 recorded diagnostics/)).toBeVisible();
  await expect(spring.getByText(/84 \/ 119 source files parsed/)).toBeVisible();
  await page.screenshot({
    path: path.join(proof, "two-current-repositories.png"),
    fullPage: true,
  });
  await page.unroute("**/api/workspace?summary=1**");
  const response = page.waitForResponse(
    (r) =>
      r.url().includes("/api/workspace/records?") &&
      r.url().includes("view=Evidence"),
  );
  await spring.getByRole("button", { name: "Explore" }).click();
  const records = await (await response).json();
  expect(records.snapshot_ids).toEqual({
    "684f260f-d5bb-461c-b024-2da4d883eeea":
      "01a120f6-3ebe-7f6d-9854-53e62443f253",
  });
  expect(records.total).toBe(140);
  expect(
    records.items.every(
      (item: { repository_id: string }) =>
        item.repository_id === "684f260f-d5bb-461c-b024-2da4d883eeea",
    ),
  ).toBe(true);
  await expect(page.getByLabel("Global repository")).toHaveValue(
    "684f260f-d5bb-461c-b024-2da4d883eeea",
  );
  await expect(
    page.getByText("1–50 of 140 matching records", { exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
  writeFileSync(
    path.join(proof, "repository-browser.json"),
    JSON.stringify(
      {
        page_ready_milliseconds: times,
        maximum_milliseconds: Math.max(...times),
        summary_requests_on_repository_page: summaries,
        explore_snapshot_ids: records.snapshot_ids,
        errors,
      },
      null,
      2,
    ),
  );
});

test("repository read failure is recoverable without retrying analysis or inventing zeros", async ({
  page,
}) => {
  test.skip(
    !process.env.PROJECTTRACE_LARGE_ACCOUNT,
    "Needs the authorized current-record mirror.",
  );
  const account = JSON.parse(
    readFileSync(process.env.PROJECTTRACE_LARGE_ACCOUNT!, "utf8"),
  );
  const login = await page.request.post("/api/auth/login", {
    headers: { Origin: new URL(process.env.PROJECTTRACE_BASE_URL!).origin },
    data: { email: account.email, password: account.password },
  });
  expect(login.status()).toBe(200);
  let mutations = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().includes("/retry"))
      mutations++;
  });
  await page.route("**/api/repositories?offset=**", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Controlled repository read failure" }),
    }),
  );
  await page.goto("/repositories");
  await expect(
    page
      .getByRole("alert")
      .filter({ hasText: "Controlled repository read failure" }),
  ).toBeVisible();
  await expect(
    page.getByText("Repository data unavailable", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("0 claims", { exact: true })).toHaveCount(0);
  await expect(
    page.getByText("Loading repositories…", { exact: false }),
  ).toHaveCount(0);
  await page.unroute("**/api/repositories?offset=**");
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "spring petclinic", exact: true }),
  ).toBeVisible();
  expect(mutations).toBe(0);
});
