import { describe, expect, it } from "vitest";
import { legacyRoute, pageForRoute, routeForPage, routes } from "./routes";

describe("canonical routes and existing shared links", () => {
  it("maps every navigation page to an explicit route", () => {
    for (const [page, route] of Object.entries(routes))
      expect(pageForRoute(routeForPage(page))).toBe(page);
    expect(routeForPage("Claim Ledger")).toBe("/claims");
    expect(routeForPage("Connections")).toBe("/settings/connections");
  });
  it("preserves named, slugged and renamed legacy hashes", () => {
    expect(legacyRoute("#Claim%20Ledger")).toBe("/claims");
    expect(legacyRoute("#evidence-graph")).toBe("/graph");
    expect(legacyRoute("#Integrations")).toBe("/settings/connections");
    expect(legacyRoute("#/repositories")).toBe("/repositories");
  });
  it("ignores malformed and unrelated fragments", () => {
    expect(legacyRoute("#%E0%A4%A")).toBeNull();
    expect(legacyRoute("#main")).toBeNull();
    expect(legacyRoute("#https://example.com")).toBeNull();
  });
});
