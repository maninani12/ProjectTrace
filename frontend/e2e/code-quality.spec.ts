import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import path from "node:path";

test("native quality views, stable evidence review, profile and real coverage import", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const registration = await page.request.post("/api/auth/register", {
    headers: { Origin: "http://127.0.0.1:5181" },
    data: {
      email: `quality-${Date.now()}@projecttrace.test`,
      password: `Disposable-quality-test-${Date.now()}!`,
      organization: "Quality browser verification",
    },
  });
  expect(registration.status()).toBe(200);
  const identity = await registration.json();
  const body =
    Array.from({ length: 12 }, (_, i) => `    value${i} = value + ${i}`).join(
      "\n",
    ) + "\n    return value0";
  const files = {
    "app.py": `def work(items=[]):\n    return items\n\ndef first(value):\n${body}\n\ndef second(value):\n${body}\n`,
    CODEOWNERS: "/app.py @quality-team\n",
    "test_app.py": "def test_fixture():\n    assert True\n",
  };
  const imported = await page.request.post("/api/import", {
    headers: { Origin: "http://127.0.0.1:5181", "X-CSRF-Token": identity.csrf },
    data: { name: "Quality browser fixture", files },
  });
  expect(imported.status()).toBe(200);
  const repository = await imported.json();
  await page.goto("/quality");
  await expect(
    page.getByRole("heading", { name: /Native quality gate/ }),
  ).toBeVisible();
  const nav = page.getByRole("navigation", { name: "Code Quality views" });
  await nav.getByRole("button", { name: "Findings", exact: true }).click();
  await page
    .getByRole("button", { name: "Inspect Mutable literal default parameter" })
    .click();
  const inspector = page.getByRole("dialog", { name: "Evidence inspector" });
  await expect(
    inspector.getByRole("region", { name: "Source code excerpt" }),
  ).toContainText("def work(items=[])");
  await expect(inspector.getByText("Owner: @quality-team")).toBeVisible();
  await inspector.getByRole("button", { name: "Review", exact: true }).click();
  await inspector
    .getByLabel("Reason", { exact: true })
    .fill("Verified the mutable default against the recorded source.");
  await inspector.getByRole("button", { name: "Record review" }).click();
  await expect(inspector.getByText("CONFIRMED", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Close dialog", exact: true }).click();
  for (const name of [
    "New Code",
    "Maintenance Hotspots",
    "Metrics",
    "Coverage",
    "Duplication",
    "Trends",
    "Rules & Profiles",
  ]) {
    await nav.getByRole("button", { name, exact: true }).click();
    await expect(
      page.getByRole("status").filter({ hasText: /Loading/ }),
    ).toHaveCount(0);
    if (name === "Metrics") {
      await page.getByRole("button", { name: "Inspect work" }).click();
      await expect(
        page.getByRole("region", { name: "Source code excerpt" }),
      ).toContainText("def work");
    }
    if (name === "Duplication") {
      await page
        .getByRole("button", { name: "Inspect result" })
        .first()
        .click();
      await expect(
        page.getByRole("heading", { name: "Duplicate occurrences" }),
      ).toBeVisible();
    }
    if (name === "Rules & Profiles") {
      await page
        .getByLabel("BASE for subsequent analysis", { exact: true })
        .selectOption(repository.snapshot_id);
      await page.getByRole("button", { name: "Save quality profile" }).click();
      await expect(
        page.getByRole("status").filter({ hasText: "Profile saved" }),
      ).toBeVisible();
    }
  }
  const head = await page.request.post(
    `/api/repositories/${repository.repository_id}/analyze`,
    {
      headers: {
        Origin: "http://127.0.0.1:5181",
        "X-CSRF-Token": identity.csrf,
      },
      data: {
        files: {
          ...files,
          "new.py": "def introduced(values={}):\n    return values\n",
        },
      },
    },
  );
  expect(head.status()).toBe(200);
  const snapshot = await head.json();
  await page.reload();
  await nav.getByRole("button", { name: "New Code", exact: true }).click();
  await expect(
    page.getByRole("button", {
      name: "Inspect Mutable literal default parameter",
    }),
  ).toHaveCount(1);
  await nav.getByRole("button", { name: "Coverage", exact: true }).click();
  await page.getByText("Import a coverage report", { exact: true }).click();
  await page.getByLabel("Report file", { exact: true }).setInputFiles({
    name: "lcov.info",
    mimeType: "text/plain",
    buffer: Buffer.from(
      "SF:app.py\nDA:1,1\nDA:2,1\nend_of_record\nSF:new.py\nDA:1,1\nDA:2,0\nend_of_record\n",
    ),
  });
  await page
    .getByLabel("Declared producer commit", { exact: true })
    .fill(snapshot.commit);
  await page.getByRole("button", { name: "Import report into HEAD" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Imported VALID" }),
  ).toBeVisible();
  await expect(page.getByText(/Line coverage 75/)).toBeVisible();
  for (const width of [1440, 1280, 1024, 768, 390, 360]) {
    await page.setViewportSize({ width, height: 900 });
    await nav.getByRole("button", { name: "Overview", exact: true }).click();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: path.join(
        process.env.PROJECTTRACE_PROOF || "test-results",
        `quality-${width}.png`,
      ),
      fullPage: true,
    });
  }
  const accessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  await testInfo.attach("quality-accessibility", {
    body: JSON.stringify(accessibility.violations),
    contentType: "application/json",
  });
  expect(accessibility.violations).toEqual([]);
  await page.evaluate(() => localStorage.setItem("pt-theme", "dark"));
  await page.reload();
  await expect(
    page.getByRole("heading", { name: /Native quality gate/ }),
  ).toBeVisible();
  await page.screenshot({
    path: path.join(
      process.env.PROJECTTRACE_PROOF || "test-results",
      "quality-dark-360.png",
    ),
    fullPage: true,
  });
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  expect(errors).toEqual([]);
});
