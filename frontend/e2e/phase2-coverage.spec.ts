import { expect, test } from "@playwright/test";
import path from "node:path";
import { completedAnalysis } from "./analysis";

test("Phase 2 captured inventory, versions, filtering, paging and history", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const origin = new URL(
    process.env.PROJECTTRACE_BASE_URL || "http://127.0.0.1:5181",
  ).origin;
  const registration = await page.request.post("/api/auth/register", {
    headers: { Origin: origin },
    data: {
      email: `phase2-${Date.now()}@projecttrace.test`,
      password: "Disposable-phase2-fixture-123!",
      organization: "Phase 2 browser verification",
    },
  });
  expect(registration.ok()).toBeTruthy();
  const headers = {
    Origin: origin,
    "X-CSRF-Token": (await registration.json()).csrf,
  };
  const files = {
    ...Object.fromEntries(
      Array.from({ length: 53 }, (_, i) => [
        `src/app${i}.py`,
        `VALUE = ${i}\n`,
      ]),
    ),
    "unknown.go": "package main\n",
    "broken.py": "def broken(:\n",
    "main.tf": 'resource "aws_s3_bucket" "fixture" {}\n',
    "broken.tf": 'resource "aws_s3_bucket" "broken" {\n',
    "cfn.yaml": "Resources:\n  Bucket: {Type: 'AWS::S3::Bucket'}\n",
    "k8.yaml": "apiVersion: v1\nkind: ConfigMap\nmetadata: {name: fixture}\n",
    "compose.yaml": "services:\n  app: {image: fixture:v1}\n",
    Dockerfile: "FROM scratch\nUSER 65532\n",
  };
  const imported = await page.request.post("/api/import", {
    headers,
    data: { name: "Phase 2 owned fixture", files },
  });
  expect(imported.ok()).toBeTruthy();
  const base = await completedAnalysis(page.request, imported);
  const response = await page.request.post(
    `/api/repositories/${base.repository_id}/analyze`,
    {
      headers,
      data: { base_id: base.snapshot_id, files: { "head.py": "pass\n" } },
    },
  );
  expect(response.ok()).toBeTruthy();
  const head = await completedAnalysis(page.request, response);
  await page.goto("/trust/coverage");
  await page.getByLabel("Global repository").selectOption(base.repository_id);
  await page.getByLabel("Analysis snapshot").selectOption(base.snapshot_id);
  await expect(
    page.getByText(`Snapshot ${base.snapshot_id}`, { exact: false }),
  ).toBeVisible();
  const captured = page.locator("section").filter({
    has: page.getByRole("heading", {
      name: "Captured analysis coverage",
      exact: true,
    }),
  });
  const backend = await (
    await page.request.get(
      `/api/trust/coverage?repository_id=${base.repository_id}&snapshot_id=${base.snapshot_id}`,
    )
  ).json();
  for (const value of [
    backend.branch,
    backend.commit,
    backend.analyzer_version,
    String(backend.profile_version),
    backend.analysis_at,
    backend.ruleset_version,
    backend.quality_gate_version,
  ]) {
    await expect(captured).toContainText(value);
  }
  await expect(captured).toContainText(
    `${backend.summary.files_discovered} discovered files`,
  );
  await expect(captured).toContainText(
    `${backend.summary.source_files_parsed} / ${backend.summary.source_files} source files parsed`,
  );
  await expect(captured).toContainText(
    `${backend.summary.source_analysis_percent}%`,
  );
  await expect(captured).toContainText("Runtime evidence: UNOBSERVED");
  await expect(captured).toContainText("Customer code executed: NO");
  await expect(captured).toContainText("External LLM used: NO");
  await expect(captured).toContainText("Source sent to external AI: NO");
  await expect(
    page.getByRole("region", { name: "Captured language inventory" }),
  ).toContainText("Go");
  await expect(
    captured.getByRole("button", { name: "Next files", exact: true }),
  ).toBeEnabled();
  await captured
    .getByRole("button", { name: "Next files", exact: true })
    .click();
  await expect(
    captured.getByRole("button", { name: "Previous files", exact: true }),
  ).toBeEnabled();
  await page.getByLabel("Find a file").fill("broken.py");
  await page
    .getByRole("combobox", { name: "Analysis state", exact: true })
    .selectOption("PARSE_FAILED");
  await expect(
    page.getByRole("region", { name: "Captured file states" }),
  ).toContainText("broken.py");
  await expect(captured).toContainText("1 matching files");
  await expect(captured).toContainText(
    "A completed parser does not establish complete semantic or security coverage",
  );
  const infrastructure = page.getByRole("region", {
    name: "Infrastructure format coverage",
  });
  for (const format of [
    "TERRAFORM",
    "CLOUDFORMATION",
    "KUBERNETES",
    "COMPOSE",
    "DOCKERFILE",
  ]) {
    await expect(infrastructure).toContainText(format);
  }
  await expect(infrastructure).toContainText("STATIC · PARTIAL");
  await expect(infrastructure).toContainText("Runtime: UNOBSERVED");
  await expect(infrastructure).toContainText(
    "Structured infrastructure parsing failed",
  );
  for (const format of backend.infrastructure) {
    const row = infrastructure.getByRole("row").filter({
      has: page.getByRole("cell", { name: format.format, exact: true }),
    });
    await expect(row.getByRole("cell").nth(1)).toHaveText(
      `${format.files} / ${format.analyzed_files}`,
    );
    await expect(row.getByRole("cell").nth(2)).toHaveText(
      String(format.resources),
    );
    await expect(row.getByRole("cell").nth(3)).toHaveText(
      String(format.parse_failures),
    );
  }
  await page.getByLabel("Find a file").fill("");
  await page
    .getByRole("combobox", { name: "Analysis state", exact: true })
    .selectOption("");
  await page.getByLabel("Analysis snapshot").selectOption(head.id);
  await expect(captured).toContainText(`Snapshot ${head.id}`);
  await expect(captured).toContainText("1 discovered files");
  await expect(page.getByRole("alert")).toHaveCount(0);
  expect(errors).toEqual([]);
  await page.screenshot({
    path: path.join(
      process.env.PROJECTTRACE_PROOF || "test-results",
      "phase2-coverage.png",
    ),
    fullPage: true,
  });
});
