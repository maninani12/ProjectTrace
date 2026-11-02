import { test, expect } from "./fixtures";
import { completedAnalysis } from "./analysis";

test("quality history retains observations and discloses an unresolved comparison fixture", async ({ page }) => {
  const origin = "http://127.0.0.1:5181";
  const registration = await page.request.post("/api/auth/register", {
    headers: { Origin: origin }, data: { email: `native-history-${Date.now()}@projecttrace.test`,
      password: "Strong-native-fixture-password-123!", organization: "Native history browser fixture" },
  });
  expect(registration.status()).toBe(200);
  const identity = await registration.json();
  const headers = { Origin: origin, "X-CSRF-Token": identity.csrf };
  const files = { "nested/app.py": "def work(items=[]):\n    return items\n" };
  const base = await completedAnalysis(page.request, await page.request.post("/api/import", {
    headers, data: { name: "Native history fixture", files },
  }));
  const head = await completedAnalysis(page.request, await page.request.post(
    `/api/repositories/${base.repository_id}/analyze`, { headers, data: { base_id: base.snapshot_id, files } }));
  const findings = await (await page.request.get(`/api/code-quality/${base.repository_id}/findings?snapshot_id=${head.id}`)).json();
  const finding = findings.items.find((f: { rule: string }) => f.rule === "PT-QUALITY-011");
  const history = await (await page.request.get(`/api/findings/${finding.id}/history`)).json();
  expect(history.items.map((e: { status: string }) => e.status).sort()).toEqual(["INTRODUCED", "SEEN"]);
  const overview = await (await page.request.get(`/api/code-quality/${base.repository_id}/overview?snapshot_id=${head.id}`)).json();
  expect(overview.summary.resolved).toBe(0);
  // Controlled view fixture only; backend legacy/provenance semantics are
  // exercised with persisted snapshots in test_native_snapshot_continuity.py.
  overview.comparison_identity_unresolved = true;
  overview.gate = { ...overview.gate, status: "REVIEW_REQUIRED", results: [{
    policy: "Quality: comparison identity", result: "REVIEW_REQUIRED",
    reason: "Identity comparison is unresolved.",
  }] };
  await page.route(/\/api\/code-quality\/[^/]+\/overview/, (route) => route.fulfill({ json: overview }));
  await page.goto("/quality");
  await expect(page.getByRole("alert")).toContainText("introductions and resolutions are unverified");
  await expect(page.getByText("Quality: comparison identity", { exact: true })).toBeVisible();
  await page.getByRole("navigation", { name: "Code Quality views" }).getByRole("button", { name: "Findings", exact: true }).click();
  await expect(page.getByRole("button", { name: "Inspect Mutable literal default parameter" })).toBeVisible();
  await page.unrouteAll({ behavior: "wait" });
});
