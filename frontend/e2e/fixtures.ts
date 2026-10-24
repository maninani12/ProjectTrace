/** Each owned CI acceptance test gets a fresh application, database and admission window.
 * Existing external/private QA instances remain opt-in and are never reset.
 */
import { test as base, expect } from "@playwright/test";
import { spawn } from "node:child_process";
import { mkdtemp, open } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

export { expect } from "@playwright/test";
export type {
  Browser,
  Page,
  APIRequestContext,
  APIResponse,
} from "@playwright/test";

export const test = base.extend<{ ownedBackend: void }>({
  ownedBackend: [
    async ({}, use, info) => {
      if (process.env.PROJECTTRACE_E2E_ISOLATED_API !== "1") {
        await use();
        return;
      }
      if (
        process.env.PROJECTTRACE_ADMIN_QA ||
        process.env.PROJECTTRACE_BASE_URL
      )
        throw new Error(
          "Owned backend isolation cannot reset an external/private QA target.",
        );
      let occupied = false;
      try {
        await fetch("http://127.0.0.1:8011/health");
        occupied = true;
      } catch {
        /* no owned listener yet */
      }
      if (occupied)
        throw new Error(
          "Refusing to replace an existing API on the owned acceptance port.",
        );
      const root = path.resolve("..");
      const runtime = await mkdtemp(
        path.join(tmpdir(), "projecttrace-acceptance-"),
      );
      const log = await open(info.outputPath("owned-api.log"), "w");
      const env = {
        ...process.env,
        JOB_MODE: "local",
        // Match the original acceptance server: seeded demo and real signup.
        APP_ENV: "demo",
        DATABASE_URL: `sqlite:///${path.join(runtime, "application.db")}`,
        ANALYSIS_KEY_FILE: path.join(runtime, "analysis-input.key"),
        SOURCE_BLOB_DIR: path.join(runtime, "blobs"),
        SOURCE_UPLOAD_DIR: path.join(runtime, "uploads"),
      };
      const python = process.env.PROJECTTRACE_PYTHON || "python";
      const start = (args: string[]) =>
        spawn(python, args, {
          cwd: root,
          env,
          stdio: ["ignore", log.fd, log.fd],
        });
      const exited = (child: ReturnType<typeof start>) =>
        new Promise<number | null>((resolve, reject) => {
          child.once("error", reject);
          child.once("exit", resolve);
        });
      let server: ReturnType<typeof start> | undefined;
      let stopped: Promise<number | null> | undefined;
      try {
        for (const args of [
          ["-m", "alembic", "upgrade", "head"],
          ["-m", "backend.seed"],
        ]) {
          const code = await exited(start(args));
          expect(code, "Owned acceptance database initialization").toBe(0);
        }
        server = start([
          "-m",
          "uvicorn",
          "backend.main:app",
          "--host",
          "127.0.0.1",
          "--port",
          "8011",
        ]);
        stopped = exited(server);
        await expect
          .poll(
            async () => {
              if (server!.exitCode !== null)
                throw new Error(
                  "Owned acceptance API exited; inspect owned-api.log",
                );
              try {
                return (await fetch("http://127.0.0.1:8011/ready")).ok;
              } catch {
                return false;
              }
            },
            { timeout: 15000, intervals: [100, 250, 500] },
          )
          .toBe(true);
        const options = await fetch("http://127.0.0.1:8011/api/auth/options");
        expect(options.status, "Owned acceptance auth metadata").toBe(200);
        expect(
          (await options.json()).demo_available,
          "Owned acceptance must preserve the seeded demo workflows",
        ).toBe(true);
        await use();
      } finally {
        if (server && server.exitCode === null) server.kill("SIGTERM");
        if (stopped) {
          const deadline = setTimeout(() => server?.kill("SIGKILL"), 10000);
          try {
            await stopped;
          } finally {
            clearTimeout(deadline);
          }
        }
        await log.close();
        // Retain this synthetic runtime under the OS temp directory for recovery.
        // Never upload its database, encryption key or session data as artifacts.
      }
    },
    { auto: true },
  ],
});
