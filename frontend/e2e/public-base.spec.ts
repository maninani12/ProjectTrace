import { test, expect } from "./fixtures";
import { completedAnalysis } from "./analysis";

test("public import displays and submits the captured BASE on provider failure", async ({ page }) => {
  const origin = new URL(
    process.env.PROJECTTRACE_BASE_URL || "http://127.0.0.1:5181",
  ).origin;
  const registration = await page.request.post("/api/auth/register", {
    headers: { Origin: origin },
    data: { email: `public-base-${Date.now()}@projecttrace.test`,
      password: "Strong-fixture-password-123!", organization: "Public BASE browser fixture" },
  });
  expect(registration.status()).toBe(200);
  const identity = await registration.json();
  const imported = await page.request.post("/api/import", {
    headers: { Origin: origin, "X-CSRF-Token": identity.csrf },
    data: { name: "owned-fixture", files: { "README.md": "# Owned baseline\n" } },
  });
  const base = await completedAnalysis(page.request, imported);
  // Browser contract fixture only: real API ingestion above, public provider
  // workspace projection below. No real GitHub request or production hook.
  const workspace = await (await page.request.get("/api/workspace?summary=1")).json();
  const repositories = await (await page.request.get("/api/repositories?offset=0&limit=25")).json();
  for (const body of [workspace, repositories]) {
    body.repositories = body.repositories.map((repo: { id: string }) =>
      repo.id === base.repository_id ? { ...repo, provider: "GITHUB_PUBLIC", name: "owner/repo" } : repo);
  }
  await page.route(/\/api\/(?:workspace|repositories)\?/, (route) =>
    route.fulfill({ json: route.request().url().includes("/api/workspace?") ? workspace : repositories }));
  let submitted: Record<string, string> | undefined;
  await page.route("**/api/github/public/import", async (route) => {
    submitted = route.request().postDataJSON();
    await route.fulfill({ status: 503, json: { detail: "Owned provider unavailable" } });
  });
  await page.goto("/repositories");
  await page.getByRole("button", { name: "Upload new snapshot", exact: true }).click();
  const note = page.getByRole("note", { name: "Public comparison BASE" });
  await expect(note).toContainText(`BASE ${base.snapshot_id}`);
  await page.getByLabel("Branch, tag or commit (optional)").fill("release");
  await page.getByRole("button", { name: "Analyze and compare public snapshot" }).click();
  await expect(page.getByRole("alert")).toContainText("Owned provider unavailable");
  expect(submitted).toMatchObject({ repository_id: base.repository_id,
    base_snapshot_id: base.snapshot_id, ref: "release" });
  await expect(note).toContainText(`BASE ${base.snapshot_id}`);
  await page.unrouteAll({ behavior: "wait" });
});
