import { test, expect } from "./fixtures";
import { completedAnalysis } from "./analysis";

const origin = "http://127.0.0.1:5181";

async function create(page: import("@playwright/test").Page) {
  const registration = await page.request.post("/api/auth/register", {
    headers: { Origin: origin },
    data: {
      email: "admission-owned@projecttrace.test",
      password: "Disposable-admission-fixture-123!",
      organization: "Owned admission fixture",
    },
  });
  expect(registration.status()).toBe(200);
  const receipt = await page.request.post("/api/import", {
    headers: {
      Origin: origin,
      "X-CSRF-Token": (await registration.json()).csrf,
    },
    data: { name: "Owned quota fixture", files: { "app.py": "pass\n" } },
  });
  expect(receipt.status()).toBe(202);
  return receipt;
}

test("owned acceptance admission stays bounded and an exhausted window fails closed", async ({
  page,
}) => {
  test.skip(
    process.env.PROJECTTRACE_E2E_ISOLATED_API !== "1",
    "Quota exhaustion is permitted only against this test's owned API.",
  );
  const receipt = await create(page);
  const jobId = (await receipt.json()).job_id;
  expect((await page.request.get(`/api/record/${jobId}`)).status()).toBe(200);
  let status = 200;
  let accepted = 0;
  while (status === 200 && accepted < 240) {
    status = (await page.request.get("/api/auth/me")).status();
    if (status === 200) accepted++;
  }
  expect(status).toBe(429);
  const job = await page.request.get(`/api/record/${jobId}`);
  expect(job.status()).toBe(429);
  expect(job.headers()["retry-after"]).toBe("60");
  await page.goto("/repositories?import=1");
  await expect(
    page.getByRole("heading", { name: "Workspace access unavailable" }),
  ).toBeVisible();
  await expect(
    page.getByRole("dialog", { name: "Import a repository snapshot" }),
  ).toHaveCount(0);
});

test("the next owned acceptance application has fresh data and admission state", async ({
  page,
}) => {
  test.skip(
    process.env.PROJECTTRACE_E2E_ISOLATED_API !== "1",
    "Requires a disposable per-test API, never an external workspace.",
  );
  const snapshot = await completedAnalysis(page.request, await create(page));
  expect(snapshot.kind).toBe("snapshot");
  const workspace = await page.request.get("/api/workspace");
  expect(workspace.status()).toBe(200);
  expect((await workspace.json()).repositories).toHaveLength(1);
});
