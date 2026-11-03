import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { once } from "node:events";
import { setTimeout as delay } from "node:timers/promises";
import { test } from "node:test";

test("real Vite ignores another PID and closes on its own local request", { timeout: 15000 }, async () => {
  const root = await mkdtemp(path.join(tmpdir(), "projecttrace-ui-stop-"));
  const stop = path.join(root, "ui.stop");
  const plugin = new URL("./local-runtime.mjs", import.meta.url).href;
  const vite = import.meta.resolve("vite");
  const code = `
    import { createServer } from ${JSON.stringify(vite)};
    import { localRuntimeStop } from ${JSON.stringify(plugin)};
    const server = await createServer({configFile:false, root:${JSON.stringify(root)},
      plugins:[localRuntimeStop(${JSON.stringify(stop)})],
      server:{host:'127.0.0.1',port:0}});
    server.middlewares.use('/probe', (_req, res) => res.end('ready'));
    await server.listen();
    console.log(JSON.stringify({port:server.httpServer.address().port}));
  `;
  const child = spawn(process.execPath, ["--input-type=module", "-e", code], { stdio: ["ignore", "pipe", "pipe"] });
  const exited = once(child, "exit");
  let output = "";
  let errors = "";
  child.stdout.on("data", (chunk) => { output += chunk; });
  child.stderr.on("data", (chunk) => { errors += chunk; });
  try {
    const deadline = Date.now() + 7000;
    while (!output.includes('"port":') && Date.now() < deadline && child.exitCode === null) await delay(50);
    const line = output.split("\n").find((line) => line.startsWith('{"port":'));
    assert.ok(line, errors);
    const url = `http://127.0.0.1:${JSON.parse(line).port}/probe`;
    assert.equal(await readFile(`${stop}.ready`, "utf8"), String(child.pid));
    await writeFile(stop, String(child.pid + 1));
    await delay(600);
    assert.equal((await fetch(url)).status, 404);
    await writeFile(stop, String(child.pid));
    const result = await Promise.race([exited, delay(5000).then(() => "timeout")]);
    assert.deepEqual(result, [0, null], errors);
    await assert.rejects(fetch(url));
  } finally {
    // Ask only this owned child to close; never force-kill on a test failure.
    if (child.exitCode === null) await writeFile(stop, String(child.pid));
  }
});
