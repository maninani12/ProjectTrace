import { test, expect, type Browser, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFileSync } from "node:fs";
import path from "node:path";

test.use({ trace: "off" });
const qa = process.env.PROJECTTRACE_ADMIN_QA;
const origin = new URL(process.env.PROJECTTRACE_BASE_URL || "http://127.0.0.1:5181").origin;
type Person = { id?: string; email: string; password: string };
type Objective = { id: string; record_id: string; version: number; state: string };
type Journey = { id: string; version: number; state: string; snapshot_id: string; objectives: Objective[]; progress: { total: number; approved: number }; comparison?: unknown };

async function signed(browser: Browser, person: Person) {
  const context = await browser.newContext({ baseURL: origin });
  const page = await context.newPage();
  const login = await page.request.post("/api/auth/login", { headers: { Origin: origin }, data: { email: person.email, password: person.password } });
  expect(login.status()).toBe(200);
  const headers = { Origin: origin, "X-CSRF-Token": (await login.json()).csrf };
  return { context, page, headers };
}

async function openPath(page: Page, id: string) {
  await page.goto("/learning");
  const paths = await page.request.get("/api/learning/journeys");
  expect(paths.status()).toBe(200);
  const entries = (await paths.json()).items;
  const index = entries.findIndex((item: { id: string }) => item.id === id);
  expect(index).toBeGreaterThanOrEqual(0);
  await page.locator(".learning-path-list button").nth(index).click();
  await expect(page.locator(".learning-objectives li").first()).toBeVisible();
}

for (const mode of ["NEW_HIRE", "INTERNAL_TRANSFER"] as const) {
  test(`learning ${mode} uses real published knowledge and independent reviews`, async ({ browser }, info) => {
    test.skip(!qa, "Requires the preserved private learning QA fixture.");
    test.setTimeout(180000);
    const fixture = JSON.parse(readFileSync(path.join(qa!, "learning-account.secret"), "utf8"));
    const target = fixture.repositories[0];
    const previous = fixture.repositories[1];
    const manager = await signed(browser, fixture.owner);
    const participant = await signed(browser, fixture.participant);
    const mentor = await signed(browser, fixture.mentor);
    const errors: string[] = [];
    for (const page of [manager.page, participant.page, mentor.page]) page.on("pageerror", e => errors.push(e.message));
    await manager.page.goto("/learning");
    await manager.page.getByRole("combobox", { name: "Knowledge project", exact: true }).selectOption(target.id);
    await expect(manager.page.getByRole("heading", { name: "Assign a learning path" })).toBeVisible();
    await manager.page.getByLabel("Onboarding mode").selectOption(mode);
    if (mode === "INTERNAL_TRANSFER") await manager.page.getByLabel("Previous project").selectOption(previous.id);
    await manager.page.getByLabel("Learning role").selectOption("BACKEND");
    await manager.page.getByLabel("Find participants and mentors").fill("learning-");
    const participantChoice = manager.page.getByRole("combobox", { name: "Participant", exact: true });
    await expect(participantChoice.locator("option", { hasText: fixture.participant.email })).toHaveCount(1);
    await participantChoice.selectOption(fixture.participant.id);
    await manager.page.getByRole("combobox", { name: "Mentor", exact: true }).selectOption(fixture.mentor.id);
    await manager.page.getByLabel("Existing skills (comma separated)").fill("Java, Spring");
    const assigned = manager.page.waitForResponse(r => r.url().endsWith("/api/learning/journeys") && r.request().method() === "POST");
    await manager.page.getByRole("button", { name: "Assign evidence-backed path" }).click();
    const created = await assigned;
    expect(created.status()).toBe(200);
    let journey = await created.json() as Journey;
    expect(journey.snapshot_id).toBe(target.snapshot_id);
    expect(journey.objectives.length).toBeGreaterThan(0);
    expect(Boolean(journey.comparison)).toBe(mode === "INTERNAL_TRANSFER");

    await openPath(participant.page, journey.id);
    const first = participant.page.locator(".learning-objectives li").first();
    const capturedKnowledge = participant.page.waitForResponse(r =>
      r.url().endsWith(`/api/record/${journey.objectives[0].record_id}`) && r.request().method() === "GET");
    await first.getByRole("button", { name: "Inspect objective knowledge" }).click();
    expect((await capturedKnowledge).status()).toBe(200);
    await expect(participant.page.getByRole("button", { name: "Close" }).first()).toBeVisible();
    await participant.page.getByRole("button", { name: "Close" }).first().click();
    const answer = "Controlled browser assessment: the captured engineering evidence supports a static explanation within this published repository snapshot; runtime behavior remains unobserved.";
    await first.getByLabel("Evidence-backed explanation").fill(answer);
    await first.getByRole("button", { name: "Submit assessment" }).click();
    await expect(first.getByText("Submitted captured citations: 1")).toBeVisible();

    await openPath(mentor.page, journey.id);
    const firstReview = mentor.page.locator(".learning-objectives li").first();
    await expect(firstReview.getByLabel("Assessment score")).toHaveValue("");
    await firstReview.getByLabel("Assessment score").selectOption("4");
    await firstReview.getByLabel("Mentor feedback").fill("Controlled browser mentor review: the explanation cites the captured project and distinguishes static evidence from runtime proof.");
    await firstReview.getByRole("button", { name: "Submit mentor review" }).click();
    await expect(firstReview.getByText(/APPROVED/)).toBeVisible();
    // The remaining objectives use their actual role-bound APIs. The first
    // response and mentor review above exercise the complete browser forms.
    const detail = await participant.page.request.get(`/api/learning/journeys/${journey.id}`);
    journey = await detail.json();
    for (const objective of journey.objectives.filter(row => row.state !== "APPROVED")) {
      const submitted = await participant.page.request.post(`/api/learning/journeys/${journey.id}/objectives/${objective.id}/submit`, {
        headers: participant.headers, data: { version: objective.version, answer, evidence_ids: [objective.record_id] } });
      expect(submitted.status()).toBe(200);
      const current = (await submitted.json()).objectives.find((row: Objective) => row.id === objective.id);
      const reviewed = await mentor.page.request.post(`/api/learning/journeys/${journey.id}/objectives/${objective.id}/review`, {
        headers: mentor.headers, data: { version: current.version, score: 4, notes: "Controlled role-bound mentor review of a captured source explanation and its limitations." } });
      expect(reviewed.status()).toBe(200);
    }
    await openPath(manager.page, journey.id);
    await manager.page.getByLabel("Manager completion review").fill("Controlled browser manager review confirms every objective has an independent mentor assessment against the published source snapshot.");
    await manager.page.getByRole("button", { name: "Complete learning revision" }).click();
    await expect(manager.page.getByText(/MENTOR · APPROVED/).first()).toBeVisible();
    await expect(manager.page.getByText("MANAGER · COMPLETED", { exact: false })).toBeVisible();
    const completion = await manager.page.request.get(`/api/learning/journeys/${journey.id}`);
    const result = await completion.json();
    expect(result.state).toBe("COMPLETED");
    expect(result.progress.approved).toBe(result.progress.total);
    expect(result.completion_records.at(-1).snapshot_id).toBe(target.snapshot_id);
    await manager.page.screenshot({ path: info.outputPath(`${mode.toLowerCase()}-completed.png`), fullPage: true });
    await manager.page.setViewportSize({ width: 390, height: 844 });
    expect(await manager.page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2)).toBe(true);
    const accessibility = await new AxeBuilder({ page: manager.page }).analyze();
    expect(accessibility.violations.filter(v => v.impact === "critical" || v.impact === "serious")).toEqual([]);
    expect(errors).toEqual([]);
    await manager.context.close(); await participant.context.close(); await mentor.context.close();
  });
}
