import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import EnterpriseTrust from "./EnterpriseTrust";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function showCoverage(coverage: object) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: unknown) => ({
      ok: true,
      json: async () =>
        String(url).includes("/trust/coverage?")
          ? coverage
          : String(url).includes("/trust/capabilities")
            ? { languages: [], scale: {} }
            : String(url).includes("/trust/rule-health")
              ? { groups: [], limitations: [] }
              : String(url).includes("/trust/policy")
                ? {
                    version: 1,
                    source_egress: "NO_EXTERNAL_SOURCE_EGRESS",
                    ai_mode: "DISABLED",
                  }
                : { items: [], total: 0 },
    })),
  );
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <EnterpriseTrust role="VIEWER" />
    </QueryClientProvider>,
  );
}

it("keeps legacy authority unmeasured and offers only implemented inventory states", async () => {
  showCoverage({
    state: "LEGACY_NOT_MEASURED",
    summary: {},
    languages: [],
    items: [],
    total: 0,
  });
  expect(await screen.findByText(/LEGACY_NOT_MEASURED/)).toBeInTheDocument();
  expect(
    screen.getByText(/Customer code executed: Not measured/),
  ).toBeInTheDocument();
  expect(
    within(screen.getByLabelText("Analysis state")).queryByRole("option", {
      name: "SUPPORTED",
    }),
  ).not.toBeInTheDocument();
});

it("renders captured authority instead of substituting frontend assumptions", async () => {
  showCoverage({
    state: "PARTIAL",
    summary: {
      files_discovered: 2,
      source_files: 2,
      source_files_parsed: 1,
      source_analysis_percent: 50,
    },
    languages: [],
    items: [],
    total: 0,
    authority: "STATIC / DECLARED",
    runtime_evidence: "UNOBSERVED",
    customer_code_executed: false,
    external_llm_used: false,
    source_sent_to_external_ai: false,
  });
  expect(
    await screen.findByText(/Customer code executed: NO/),
  ).toHaveTextContent("External LLM used: NO");
  expect(screen.getByText(/Customer code executed: NO/)).toHaveTextContent(
    "Source sent to external AI: NO",
  );
  expect(screen.getByText(/2 discovered files/)).toHaveTextContent(
    "analysis coverage 50%",
  );
});
