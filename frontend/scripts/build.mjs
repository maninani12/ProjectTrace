import { build } from "vite";
import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { gzipSync } from "node:zlib";

const root = process.cwd();
if (!(await fs.stat(path.join(root, "src/main.tsx"))).isFile())
  throw new Error("Run from the ProjectTrace frontend directory.");
await build({ build: { manifest: true } });
const scratch = path.resolve(root, ".prerender");
if (path.dirname(scratch) !== root || path.basename(scratch) !== ".prerender")
  throw new Error("Unsafe temporary build path.");
try {
  await build({
    build: { ssr: "src/prerender.tsx", outDir: scratch, emptyOutDir: true },
  });
  const { render, publicPages, metadata } = await import(
    pathToFileURL(path.join(scratch, "prerender.js")).href
  );
  const template = await fs.readFile(
    path.join(root, "dist/index.html"),
    "utf8",
  );
  const configuredOrigin = process.env.PROJECTTRACE_PUBLIC_ORIGIN || "";
  let origin = "";
  if (configuredOrigin) {
    const url = new URL(configuredOrigin);
    if (
      !["https:", "http:"].includes(url.protocol) ||
      url.username ||
      url.password ||
      url.search ||
      url.hash ||
      url.pathname !== "/"
    )
      throw new Error(
        "PROJECTTRACE_PUBLIC_ORIGIN must be an authorized HTTP(S) origin without credentials, query or path.",
      );
    origin = url.origin;
  }
  const escape = (value) =>
    value
      .replaceAll("&", "&amp;")
      .replaceAll('"', "&quot;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;");
  for (const route of publicPages) {
    const meta = metadata(route);
    const canonical = origin ? `${origin}${route}` : "";
    const schema =
      route === "/"
        ? [
            {
              "@context": "https://schema.org",
              "@type": "SoftwareApplication",
              name: "ProjectTrace",
              applicationCategory: "DeveloperApplication",
              operatingSystem: "Web",
              description: meta.description,
              ...(canonical ? { url: canonical } : {}),
            },
            {
              "@context": "https://schema.org",
              "@type": "FAQPage",
              mainEntity: meta.faqs.map(([question, answer]) => ({
                "@type": "Question",
                name: question,
                acceptedAnswer: { "@type": "Answer", text: answer },
              })),
            },
          ]
        : [];
    const head = `<title>${escape(meta.title)}</title><meta name="description" content="${escape(meta.description)}"/><meta property="og:title" content="${escape(meta.title)}"/><meta property="og:description" content="${escape(meta.description)}"/><meta property="og:type" content="website"/><meta name="twitter:card" content="summary_large_image"/><meta name="twitter:title" content="${escape(meta.title)}"/><meta name="twitter:description" content="${escape(meta.description)}"/>${canonical ? `<link rel="canonical" href="${escape(canonical)}"/><meta property="og:url" content="${escape(canonical)}"/><meta property="og:image" content="${escape(origin)}/social-preview.svg"/>` : '<meta name="robots" content="noindex,nofollow"/>'}${schema.length ? `<script type="application/ld+json">${JSON.stringify(schema).replaceAll("<", "\\u003c")}</script>` : ""}`;
    const html = template
      .replace(/<meta name="description"[^>]*>/, "")
      .replace(/<title>.*?<\/title>/s, head)
      .replace(
        '<div id="root"></div>',
        `<div id="root" data-prerender-path="${escape(route)}">${await render(route)}</div>`,
      );
    const destination =
      route === "/"
        ? path.join(root, "dist/index.html")
        : path.join(root, "dist", route.slice(1), "index.html");
    await fs.mkdir(path.dirname(destination), { recursive: true });
    await fs.writeFile(destination, html);
    // Vite/static hosts resolve clean URLs through .html before the SPA fallback.
    // Keep directory indexes for hosts that resolve trailing-slash URLs.
    if (route !== "/")
      await fs.writeFile(
        path.join(root, "dist", route.slice(1) + ".html"),
        html,
      );
  }
  await fs.writeFile(
    path.join(root, "dist/robots.txt"),
    origin
      ? `User-agent: *\nAllow: /\nDisallow: /app\nDisallow: /login\nDisallow: /signup\nDisallow: /demo\nSitemap: ${origin}/sitemap.xml\n`
      : "User-agent: *\nDisallow: /\n# Configure PROJECTTRACE_PUBLIC_ORIGIN before publishing.\n",
  );
  await fs.writeFile(
    path.join(root, "dist/sitemap.xml"),
    `<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${origin ? publicPages.map((route) => `<url><loc>${escape(origin + route)}</loc></url>`).join("") : ""}</urlset>`,
  );
  const manifest = JSON.parse(
    await fs.readFile(path.join(root, "dist/.vite/manifest.json"), "utf8"),
  );
  const entry = Object.keys(manifest).find((key) => manifest[key].isEntry);
  const reachable = new Set();
  function visit(key) {
    if (reachable.has(key)) return;
    reachable.add(key);
    for (const child of manifest[key].imports || []) visit(child);
  }
  visit(entry);
  const initialScripts = await Promise.all(
    [...reachable].map(async (key) => {
      const file = manifest[key].file;
      const bytes = await fs.readFile(path.join(root, "dist", file));
      return { file, bytes: bytes.length, gzipBytes: gzipSync(bytes).length };
    }),
  );
  const graphLoadedByPublicEntry = initialScripts.some(({ file }) =>
    /\/Graph-/.test(file),
  );
  if (graphLoadedByPublicEntry)
    throw new Error("Public entry must not eagerly import the graph.");
  await fs.writeFile(
    path.join(root, "dist/public-build.json"),
    JSON.stringify(
      {
        release: "1.4.0",
        pages: publicPages.length,
        routes: publicPages,
        staticContent: true,
        canonicalOriginConfigured: !!origin,
        graphLoadedByPublicEntry,
        initialScripts,
      },
      null,
      2,
    ),
  );
  console.log(
    `Prerendered ${publicPages.length} public routes. Canonical origin ${origin ? "configured" : "unconfigured: local noindex"}.`,
  );
} finally {
  // The resolved directory was verified above; never remove a caller-provided path.
  await fs.rm(scratch, { recursive: true, force: true });
}
