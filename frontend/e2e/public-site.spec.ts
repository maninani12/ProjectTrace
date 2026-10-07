import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import path from "node:path";
import { guideTopics } from "../src/public/guideContent";

const proof = process.env.PROJECTTRACE_PROOF || "test-results";

test("public investigation, keyboard flow and anonymous privacy", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  const requests: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("request", (request) => requests.push(request.url()));
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    /Know what your software actually does/,
  );
  await expect(
    page.getByRole("link", { name: /Analyze a Repository/ }).first(),
  ).toHaveAttribute("href", /\/signup\?next=/);
  expect(
    requests.some(
      (url) =>
        url.includes("/api/workspace") || /\/Graph-|\/WorkspaceApp-/.test(url),
    ),
  ).toBeFalsy();
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "Skip to content" }),
  ).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#public-main")).toBeFocused();
  const example = page.getByRole("region", {
    name: "Authentication investigation example",
  });
  await example.getByRole("button", { name: /Before change/ }).click();
  await expect(example.getByText("VERIFIED", { exact: true })).toBeVisible();
  await example.getByRole("button", { name: /Change detected/ }).click();
  await expect(example.getByText("STALE", { exact: true })).toBeVisible();
  await example.getByRole("button", { name: /Evidence checked/ }).click();
  await page.getByRole("button", { name: /Authentication uses JWT/ }).click();
  const inspector = page.getByRole("dialog", {
    name: "Authentication uses JWT.",
  });
  await expect(
    inspector.getByText("auth/session.py", { exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(inspector).not.toBeVisible();
  const access = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  await testInfo.attach("public-accessibility", {
    body: JSON.stringify(access.violations),
    contentType: "application/json",
  });
  expect(access.violations).toEqual([]);
  expect(errors).toEqual([]);
});

test("landing creates a real empty workspace and imports a fresh ZIP", async ({
  page,
}) => {
  const identity = `public-${Date.now()}@projecttrace.test`;
  const password = `Disposable-public-test-${Date.now()}!`;
  await page.goto("/");
  const analyze = page
    .getByRole("link", { name: /Analyze a Repository/ })
    .first();
  await expect(analyze).toHaveAttribute("href", /\/signup\?next=/);
  await analyze.click();
  await page
    .getByLabel("Workspace name", { exact: true })
    .fill("Public workflow validation");
  await page.getByLabel("Email", { exact: true }).fill(identity);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page
    .getByRole("button", { name: "Create workspace & continue" })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Import a repository snapshot",
  });
  await expect(dialog).toBeVisible();
  const empty = await (await page.request.get("/api/workspace")).json();
  expect(empty.demo).toBe(false);
  expect(empty.repositories).toEqual([]);
  await dialog
    .getByLabel("Repository name", { exact: true })
    .fill("public-import-fixture");
  await dialog
    .getByLabel("Source archive", { exact: true })
    .setInputFiles(path.join(process.cwd(), "e2e/fixtures/native-fixture.zip"));
  await dialog.getByRole("button", { name: "Analyze source snapshot" }).click();
  await expect(dialog).not.toBeVisible({ timeout: 30000 });
  const workspace = await (await page.request.get("/api/workspace")).json();
  expect(workspace.repositories).toHaveLength(1);
  expect(workspace.repositories[0].name).toBe("public-import-fixture");
  expect(workspace.repositories[0].snapshot).toBeTruthy();
  await page.screenshot({
    path: path.join(proof, "public-fresh-import.png"),
    fullPage: true,
  });
  await page.getByRole("link", { name: /What is Repositories/ }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Repository Analysis",
  );
  await page.goto("/");
  await expect(
    page.getByRole("link", { name: "Open ProjectTrace", exact: true }).first(),
  ).toBeVisible();
  await expect(page.locator("body")).not.toContainText(
    "Public workflow validation",
  );
  await page.goto("/app");
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.getByLabel("Email", { exact: true }).fill(identity);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Engineering, backed by evidence." }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "ProjectTrace Guide", exact: true })
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "ProjectTrace in 60 Seconds",
  );
});

test("six responsive widths, dark theme, reduced motion and the complete Guide", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  for (const width of [1440, 1280, 1024, 768, 390, 360]) {
    await page.setViewportSize({ width, height: 950 });
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: path.join(proof, `public-hero-${width}.png`),
    });
    if (width === 1440 || width === 390)
      await page.screenshot({
        path: path.join(proof, `public-full-${width}.png`),
        fullPage: true,
      });
  }
  await page.getByRole("button", { name: "Menu", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Close menu", exact: true }),
  ).toHaveAttribute("aria-expanded", "true");
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "Menu", exact: true }),
  ).toBeFocused();
  await page.getByRole("button", { name: "Menu", exact: true }).click();
  await page.getByLabel("Appearance").selectOption("dark");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.keyboard.press("Escape");
  await page.screenshot({
    path: path.join(proof, "public-dark-mobile.png"),
    fullPage: true,
  });
  const darkAccess = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  await testInfo.attach("dark-public-accessibility", {
    body: JSON.stringify(darkAccess.violations),
    contentType: "application/json",
  });
  expect(darkAccess.violations).toEqual([]);
  await page.goto("/guide/product-map");
  await expect(
    page
      .getByRole("navigation", { name: "Guide topics", exact: true })
      .getByRole("link"),
  ).toHaveCount(34);
  await page
    .getByRole("navigation", { name: "Interactive product map" })
    .getByRole("link", { name: /Claim Ledger/ })
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Claim Ledger",
  );
  await page
    .getByRole("button", { name: "Technical details", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Technical details", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: path.join(proof, "guide-dark-mobile.png"),
    fullPage: true,
  });
  const guideAccess = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  await testInfo.attach("guide-accessibility", {
    body: JSON.stringify(guideAccess.violations),
    contentType: "application/json",
  });
  expect(guideAccess.violations).toEqual([]);
  const topics = await page
    .getByRole("navigation", { name: "Guide topics", exact: true })
    .getByRole("link")
    .evaluateAll((links) => links.map((link) => link.getAttribute("href")!));
  for (const route of topics) {
    await page.goto(route);
    await expect(
      page.getByRole("heading", { name: "Limits to keep in view" }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/guide/drift?mode=technical");
  await page.getByLabel("Appearance").selectOption("light");
  await page.screenshot({
    path: path.join(proof, "guide-desktop.png"),
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("demo failure is recoverable and unknown paths have useful navigation", async ({
  page,
}) => {
  await page.route("**/api/auth/demo", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "The demo is temporarily unavailable." }),
    }),
  );
  await page.goto("/demo");
  await expect(page.getByRole("alert")).toContainText(
    "The demo is temporarily unavailable.",
  );
  await expect(page.getByRole("button", { name: "Retry demo" })).toBeVisible();
  await page.unroute("**/api/auth/demo");
  await page.getByRole("button", { name: "Retry demo" }).click();
  await expect(
    page.getByRole("dialog", { name: "Follow one engineering change" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Close dialog", exact: true }).click();
  await expect(
    page
      .getByText("DEMO WORKSPACE", { exact: true })
      .or(page.getByText("DEMO DATA", { exact: true })),
  ).toBeVisible();
  await page.goto("/this-page-does-not-exist");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "This path has no page.",
  );
  await expect(
    page.getByRole("link", { name: "Return Home", exact: true }),
  ).toHaveAttribute("href", "/");
});

test("production public HTML works without JavaScript and hydrates without graph downloads", async ({
  browser,
}, testInfo) => {
  test.skip(
    !process.env.PROJECTTRACE_STATIC_BASE_URL,
    "Set a local production preview URL to validate prerendering.",
  );
  const origin = process.env.PROJECTTRACE_STATIC_BASE_URL!;
  const offline = await browser.newContext({ javaScriptEnabled: false });
  const staticPage = await offline.newPage();
  const publicPages: [string, string][] = [
    ["/", "Know what your software actually does."],
    ["/guide", "ProjectTrace in 60 Seconds"],
    ...guideTopics.map((topic): [string, string] => [
      `/guide/${topic.id}`,
      topic.title,
    ]),
    ["/trust", "Security built around evidence."],
    ["/privacy", "What happens to your source."],
    ["/docs", "ProjectTrace documentation."],
    ["/about", "Engineering knowledge should keep up."],
    ["/changelog", "Changes you can trace."],
  ];
  for (const [route, title] of publicPages) {
    const response = await staticPage.goto(origin + route);
    expect(response?.status()).toBe(200);
    await expect(staticPage.locator("#root")).toHaveAttribute(
      "data-prerender-path",
      route,
    );
    await expect(staticPage.getByRole("heading", { level: 1 })).toHaveText(
      title,
    );
    expect(await staticPage.locator('meta[name="description"]').count()).toBe(
      1,
    );
  }
  await offline.close();
  const context = await browser.newContext();
  const page = await context.newPage();
  const errors: string[] = [],
    loaded: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("request", (request) => loaded.push(request.url()));
  await page.goto(origin);
  await page
    .getByRole("region", { name: "Authentication investigation example" })
    .getByRole("button", { name: /Before change/ })
    .click();
  await expect(
    page
      .getByRole("region", { name: "Authentication investigation example" })
      .getByText("VERIFIED", { exact: true }),
  ).toBeVisible();
  expect(loaded.some((url) => /\/Graph-|\/WorkspaceApp-/.test(url))).toBe(
    false,
  );
  await page.goto(origin + "/guide/drift");
  await page
    .getByRole("button", { name: "Technical details", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Technical details", exact: true }),
  ).toBeVisible();
  await testInfo.attach("production-network", {
    body: JSON.stringify({ loaded, errors }),
    contentType: "application/json",
  });
  expect(errors).toEqual([]);
  await context.close();
});
