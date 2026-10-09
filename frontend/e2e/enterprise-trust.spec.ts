import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import path from "node:path";
import { completedAnalysis } from "./analysis";

test("tenant trust controls, audit integrity and native infrastructure evidence", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const origin = new URL(
    process.env.PROJECTTRACE_BASE_URL || "http://127.0.0.1:5181",
  ).origin;
  const response = await page.request.post("/api/auth/register", {
    headers: { Origin: origin },
    data: {
      email: `enterprise-${Date.now()}@projecttrace.test`,
      password: "Disposable-enterprise-password-123!",
      organization: "Enterprise browser fixture",
    },
  });
  expect(response.status()).toBe(200);
  const identity = await response.json();
  const imported = await page.request.post("/api/import", {
    headers: { Origin: origin, "X-CSRF-Token": identity.csrf },
    data: {
      name: "Infrastructure browser fixtures",
      files: {
        "main.tf":
          'resource "aws_db_instance" "fixture" { publicly_accessible = true }',
        Dockerfile:
          "FROM alpine:3 AS build\nRUN echo fixture\nFROM scratch\nCOPY --from=build /app /app\nUSER 65532\n",
        "compose.yaml":
          "services:\n  app:\n    image: fixture:v1\n    privileged: true\n",
        "rbac.yaml":
          "kind: Role\nmetadata: {name: fixture}\nrules: [{apiGroups: [''], resources: ['pods'], verbs: ['*']}]\n",
      },
    },
  });
  await completedAnalysis(page.request, imported);
  await page.goto("/trust/coverage");
  await expect(
    page.getByRole("heading", { name: "Language & parser coverage" }),
  ).toBeVisible();
  await expect(
    page.getByText("NO_EXTERNAL_SOURCE_EGRESS", { exact: true }),
  ).toBeVisible();
  const coordinates = page.getByRole("checkbox", {
    name: /Allow package coordinates/,
  });
  await expect(coordinates).not.toBeChecked();
  await coordinates.check();
  await expect(
    page
      .getByRole("status", { name: "" })
      .filter({ hasText: "Tenant policy saved" }),
  ).toBeVisible();
  await expect(coordinates).toBeChecked();
  await page
    .getByRole("button", { name: "Verify audit chain", exact: true })
    .click();
  await expect(page.getByText(/^VERIFIED ·/)).toBeVisible();
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.screenshot({
    path: path.join(
      process.env.PROJECTTRACE_PROOF || "test-results",
      "enterprise-trust.png",
    ),
    fullPage: true,
  });
  await page.goto("/infrastructure");
  const tabs = page.getByRole("navigation", { name: "Infrastructure views" });
  await expect(
    page.getByRole("heading", { name: "Native infrastructure inventory" }),
  ).toBeVisible();
  for (const name of [
    "Findings",
    "Resources",
    "Terraform",
    "CloudFormation",
    "Kubernetes",
    "Compose",
    "Dockerfile",
    "Coverage",
    "Rules & Profiles",
  ]) {
    await tabs.getByRole("button", { name, exact: true }).click();
    await expect(
      page.getByRole("status").filter({ hasText: "Loading infrastructure" }),
    ).toHaveCount(0);
    if (name === "Compose") {
      await page
        .getByRole("button", {
          name: "Privileged container enabled",
          exact: true,
        })
        .click();
      await expect(
        page.getByRole("region", { name: "Source code excerpt" }),
      ).toContainText("privileged: true");
      await page
        .getByRole("button", { name: "Close dialog", exact: true })
        .click();
    }
  }
  await tabs.getByRole("button", { name: "Overview", exact: true }).click();
  for (const width of [1440, 768, 390, 360]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
  }
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.screenshot({
    path: path.join(
      process.env.PROJECTTRACE_PROOF || "test-results",
      "infrastructure-mobile.png",
    ),
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
