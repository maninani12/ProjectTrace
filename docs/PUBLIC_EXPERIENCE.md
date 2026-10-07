# Public experience and ProjectTrace Guide — 1.4.0

The public route `/` explains ProjectTrace before authentication. `/app` opens the existing authorized workspace. Existing canonical workspace URLs and legacy hash links remain supported; `/app/...` aliases redirect to those canonical URLs.

## First visit and import

Select **Analyze a Repository** to create a local workspace or sign in. Successful registration opens **Repositories → Import a repository snapshot** directly. Supply a repository name and an authorized source ZIP, then select **Analyze source snapshot**. Registration creates an empty real workspace. **Explore Demo** explicitly signs into the labeled Northstar workspace and opens its guided investigation. Production mode disables local registration and demo login.

Existing accounts keep their credentials and repositories. The public navigation learns only three booleans from `/api/auth/options`: authenticated, local registration available and demo available. It never requests private workspace records to render marketing. The endpoint uses the existing no-store and admission middleware. Return destinations accept only known internal workspace paths.

## Permanent Guide

`/guide` and 31 `/guide/:topic` pages cover the product from a 60-second introduction to source/privacy limits. Each module explains what it is, why it matters, inputs, outputs, a concrete example, connections, next action and limitations. Simple and technical modes share the same evidence boundaries. Search, a glossary and an interactive eight-stage product map help visitors navigate.

Authenticated navigation has a permanent **Learn → ProjectTrace Guide** entry and context links below each major page description. The command palette also opens the Guide. These links do not expose private source through public pages.

## Design and demonstration

Public and workspace views share fonts, theme tokens, status badges and source rendering. Light/dark/system appearance persists in the browser. Mobile navigation supports Escape and focus return; reduced-motion preferences are respected. The public JWT-to-session investigation and three finding inspectors use explicitly synthetic Northstar fixture excerpts. They do not load tenant source, animate a fake scan, claim a deployment or invent customers, prices, metrics or testimonials.

## Build and hosting

From `frontend`, run `npm ci` and `npm run build`. The build emits 38 public HTML pages: home, Guide index, 31 Guide modules and five documents. Each route gets directory-index HTML and a `.html` alias so extension-free Vite preview URLs resolve to the correct prerendered page. Graph, workspace and Guide bundles are loaded on demand. Matching prerendered routes hydrate; workspace/unknown fallback routes mount normally.

The default build uses `noindex,nofollow`, a disallow-all robots file and an empty sitemap because this installation has no public domain. To publish, set `PROJECTTRACE_PUBLIC_ORIGIN` to the actual authorized HTTP(S) origin before building. The build then supplies canonical and social URLs plus a 38-route sitemap. The SVG social asset is an original vector; platform-specific social-card rendering has not been verified.

Static hosting must serve existing route HTML before applying the SPA fallback. For example, a reverse proxy can resolve `$uri.html`, `$uri/index.html`, then `/index.html`. Proxy `/api` to FastAPI separately, with explicit CORS origins, HTTPS and operator security headers. Authenticated routes require the API. Client 404/error screens provide useful navigation; HTTP error status and operational 500 handling belong to the hosting layer. No public hosting or domain setup was performed.

Local production preview:

```powershell
Set-Location frontend
npm.cmd run build
npm.cmd exec -- vite preview --host 127.0.0.1 --port 5183 --strictPort
```

Development remains on port 5181 and API on 8011. The test-only port 5183 is not an authorized browser mutation origin; use 5181 for login/import workflows unless the operator deliberately configures a new origin.

## Verification and limits

Playwright checks anonymous privacy, keyboard interaction, synthetic inspectors, real registration/import/login, demo retry, all 31 Guide topics, six viewport widths, dark mode and reduced motion. Production checks assert the correct route and heading for all 38 pages with JavaScript disabled, then validate interactive hydration without eager workspace/graph downloads. Axe checks cover the public page in light/dark modes and the Guide; they are not a complete accessibility certification.

Lighthouse reports are local lab measurements. Field INP, real-user usability, public CDN behavior and sustained production capacity remain unmeasured. See `FINAL_PRODUCT_VALIDATION.md` for exact scores, test counts and preserved native capabilities. The Guide and public claims must be updated whenever engine coverage or operator data practices change.
