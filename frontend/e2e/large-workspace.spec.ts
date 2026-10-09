import { test, expect } from "@playwright/test";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";

test("exact large snapshot has complete counts, bounded pages and responsive graph reads", async ({
  page,
}) => {
  test.skip(
    !process.env.PROJECTTRACE_LARGE_ACCOUNT,
    "Needs an authorized private mirror fixture account.",
  );
  const account = JSON.parse(
    readFileSync(process.env.PROJECTTRACE_LARGE_ACCOUNT!, "utf8"),
  );
  const proof = process.env.PROJECTTRACE_PROOF || "test-results";
  mkdirSync(proof, { recursive: true });
  const origin = new URL(process.env.PROJECTTRACE_BASE_URL!).origin;
  const requests: { path: string; status: number; milliseconds: number }[] = [];
  const starts = new Map<string, number>();
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => starts.set(request.url(), performance.now()));
  page.on("response", (response) => {
    if (response.url().includes("/api/"))
      requests.push({
        path: new URL(response.url()).pathname + new URL(response.url()).search,
        status: response.status(),
        milliseconds:
          performance.now() - (starts.get(response.url()) || performance.now()),
      });
  });
  const login = await page.request.post("/api/auth/login", {
    headers: { Origin: origin },
    data: { email: account.email, password: account.password },
  });
  expect(login.status()).toBe(200);
  const begun = performance.now();
  await page.goto("/overview");
  // The mirror may contain another published ZIP; select this acceptance scope.
  await page.getByLabel("Global repository").selectOption("4f7304f9-c355-467f-8799-785e74b83cdf");
  await expect(
    page.getByText("934 directly verified", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("1500 claims", { exact: true })).toBeVisible();
  await expect(page.getByText("1368", { exact: true })).toBeVisible();
  await expect(page.getByText(/Workspace result limit reached/)).toHaveCount(0);
  await expect(
    page.getByText("Loading engineering evidence", { exact: true }),
  ).toHaveCount(0);
  const overviewMilliseconds = performance.now() - begun;
  await page.screenshot({
    path: path.join(proof, "large-overview.png"),
    fullPage: true,
  });
  const nav = page.getByRole("navigation", { name: "Main navigation" });
  await nav.getByRole("button", { name: "Claim Ledger", exact: true }).click();
  await expect(
    page.getByText("1–50 of 1500 matching records", { exact: true }),
  ).toBeVisible();
  const first = await (
    await page.request.get(
      "/api/workspace/records?view=Claim%20Ledger&limit=50&repository_id=4f7304f9-c355-467f-8799-785e74b83cdf",
    )
  ).json();
  expect(first.total).toBe(1500);
  expect(first.items).toHaveLength(50);
  await page.getByRole("button", { name: "Next records", exact: true }).click();
  await expect(
    page.getByText("51–100 of 1500 matching records", { exact: true }),
  ).toBeVisible();
  const second = await (
    await page.request.get(
      "/api/workspace/records?view=Claim%20Ledger&limit=50&offset=50&repository_id=4f7304f9-c355-467f-8799-785e74b83cdf",
    )
  ).json();
  expect(
    second.items.every(
      (item: { id: string }) =>
        !first.items.some((old: { id: string }) => old.id === item.id),
    ),
  ).toBeTruthy();
  await page.getByLabel("Status filter").selectOption("VERIFIED");
  await expect(
    page.getByText("1–50 of 934 matching records", { exact: true }),
  ).toBeVisible();
  await nav.getByRole("button", { name: "Findings", exact: true }).click();
  await expect(
    page.getByText("1–50 of 7904 matching records", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("182", { exact: true })).toBeVisible();
  await expect(page.getByText("1186", { exact: true })).toBeVisible();
  const findings = await (
    await page.request.get("/api/workspace/records?view=Findings&limit=50&repository_id=4f7304f9-c355-467f-8799-785e74b83cdf")
  ).json();
  const repository = findings.items[0].repository_id;
  const sid = findings.snapshot_ids[repository];
  const components = await page.request.get(
    `/api/graph/nodes?repository_id=${repository}&snapshot_id=${sid}&node_class=COMPONENT&limit=50`,
  );
  expect(components.status()).toBe(200);
  const evidence = await (
    await page.request.get("/api/workspace/records?view=Evidence&limit=1&repository_id=4f7304f9-c355-467f-8799-785e74b83cdf")
  ).json();
  const graph = await page.request.get(
    `/api/graph/neighborhood?node_id=${evidence.items[0].id}&limit=50`,
  );
  expect(graph.status()).toBe(200);
  expect((await graph.json()).total).toBeGreaterThan(0);
  expect(errors).toEqual([]);
  writeFileSync(
    path.join(proof, "large-browser.json"),
    JSON.stringify(
      {
        overviewMilliseconds,
        requests,
        errors,
        claimCount: first.total,
        findingCount: findings.total,
        sourceInspectionValidated: false,
      },
      null,
      2,
    ),
  );
});
