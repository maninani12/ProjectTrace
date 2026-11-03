import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Operator-owned local control, like scripts/local_api.py. Never exposed over HTTP.
export function localRuntimeStop(
  stopFile = fileURLToPath(new URL("../../data/local-ui.stop", import.meta.url)),
) {
  return {
    name: "projecttrace-local-runtime-stop",
    apply: (_config, environment) => environment.command === "serve" && environment.mode !== "test",
    configureServer(server) {
      const readyFile = `${stopFile}.ready`;
      const pid = String(process.pid);
      fs.mkdirSync(path.dirname(stopFile), { recursive: true });
      // Publish readiness after an old server has closed during Vite config reload.
      server.httpServer?.once("listening", () => fs.writeFileSync(readyFile, pid));
      let closing = false;
      const matches = (file) => {
        try {
          return fs.readFileSync(file, "utf8") === pid;
        } catch {
          return false;
        }
      };
      const timer = setInterval(async () => {
        if (closing || !matches(stopFile)) return;
        closing = true;
        clearInterval(timer);
        try {
          await server.close();
          console.log("ProjectTrace local UI closed gracefully.");
          process.exit(0);
        } catch (error) {
          console.error("ProjectTrace local UI shutdown failed:", error.name);
          process.exitCode = 1;
        }
      }, 250);
      timer.unref();
      server.httpServer?.once("close", () => {
        clearInterval(timer);
        for (const file of [stopFile, readyFile]) {
          if (matches(file)) fs.unlinkSync(file);
        }
      });
    },
  };
}
