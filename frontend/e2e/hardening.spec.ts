import { expect, test } from "@playwright/test";

const origin = new URL(
  process.env.PROJECTTRACE_BASE_URL || "http://127.0.0.1:5181",
).origin;

test("captured comparisons, component corrections, historical coverage and paged graph", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const registration = await page.request.post("/api/auth/register", {
    headers: { Origin: origin },
    data: {
      email: `hardening-${Date.now()}@projecttrace.test`,
      password: "Disposable-hardening-fixture-123!",
      organization: "Hardening browser verification",
    },
  });
  expect(registration.ok()).toBeTruthy();
  const headers = {
    Origin: origin,
    "X-CSRF-Token": (await registration.json()).csrf,
  };
  const files = Object.fromEntries(
    Array.from({ length: 60 }, (_, index) => [
      `service/module${index}.py`,
      `def transform${index}(value):\n    return value + ${index}\n`,
    ]),
  );
  const initial = await page.request.post("/api/import", {
    headers,
    data: { name: "hardening-browser-fixture", files },
  });
  expect(initial.ok()).toBeTruthy();
  const base = await initial.json();
  await page.goto("/settings");
  await page.getByLabel("Global repository").selectOption(base.repository_id);
  await page.getByRole("button", { name: "Add boundary", exact: true }).click();
  await page.getByLabel("Component folder 1", { exact: true }).fill("service");
  await page
    .getByLabel("Component name 1", { exact: true })
    .fill("Service API");
  await page
    .getByRole("button", { name: "Save component assignments" })
    .click();
  await expect(
    page
      .getByRole("status")
      .filter({ hasText: "Saved. Component assignments" }),
  ).toBeVisible();
  const assignment = await page.request.get(
    `/api/repositories/${base.repository_id}/components`,
  );
  expect((await assignment.json()).configuration.components).toEqual([
    { root: "service", name: "Service API" },
  ]);

  const next = await page.request.post(
    `/api/repositories/${base.repository_id}/analyze`,
    {
      headers,
      data: {
        base_id: base.snapshot_id,
        files: {
          ...files,
          "service/module0.py":
            "def transform0(values=[]):\n    return values\n",
        },
      },
    },
  );
  expect(next.ok()).toBeTruthy();
  const head = await next.json();
  await page.goto("/engineering-changes");
  await page
    .getByRole("button", { name: "Inspect engineering change" })
    .first()
    .click();
  const detail = page.getByRole("region", {
    name: "Engineering change details",
  });
  await expect(detail).toContainText(base.snapshot_id);
  await expect(detail).toContainText(head.id);
  await expect(detail).toContainText("service/module0.py");
  await expect(detail).toContainText("Runtime:");

  await page.goto("/trust/coverage");
  await page
    .getByRole("combobox", { name: "Analysis snapshot", exact: true })
    .selectOption(base.snapshot_id);
  await expect(
    page.getByText(`Snapshot ${base.snapshot_id}`, { exact: false }),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "Analysis snapshot", exact: true })
    .selectOption(head.id);
  await expect(
    page.getByText(`Snapshot ${head.id}`, { exact: false }),
  ).toBeVisible();

  await page.goto("/graph");
  const listing = page.waitForResponse(
    (response) =>
      response.url().includes("/api/graph/nodes?") &&
      response.url().includes("node_class=ARTIFACT"),
  );
  await page
    .getByRole("combobox", { name: "Node type", exact: true })
    .selectOption("ARTIFACT");
  const first = await (await listing).json();
  expect(first.total).toBeGreaterThan(50);
  expect(first.items).toHaveLength(50);
  const paged = page.waitForResponse(
    (response) =>
      response.url().includes("/api/graph/nodes?") &&
      response.url().includes("offset=50"),
  );
  await page.getByRole("button", { name: "Next nodes", exact: true }).click();
  expect((await (await paged).json()).items.length).toBeLessThanOrEqual(50);
  await expect(page.getByRole("alert")).toHaveCount(0);
  expect(errors).toEqual([]);
});
