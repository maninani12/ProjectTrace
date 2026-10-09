import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { AnalysisCoverage, Badge, ImpactSummary } from "./WorkspaceApp";
import type { Workspace } from "./api";
import { cleanup } from "@testing-library/react";
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
describe("ProjectTrace interface", () => {
  it("distinguishes a rate-limited identity read from an unauthenticated session", async () => {
    window.history.replaceState({}, "", "/repositories");
    let status = 429;
    vi.stubGlobal(
      "fetch",
      vi.fn((url) =>
        Promise.resolve(
          String(url).endsWith("/auth/me")
            ? {
                ok: false,
                status,
                text: async () =>
                  JSON.stringify({
                    detail:
                      status === 429
                        ? "Rate limit exceeded; retry later."
                        : "Authentication required.",
                  }),
              }
            : {
                ok: true,
                status: 200,
                json: async () => ({
                  authenticated: false,
                  local_registration: true,
                  demo_available: true,
                }),
              },
        ),
      ),
    );
    render(<App />);
    expect(
      await screen.findByRole("heading", {
        name: "Workspace access unavailable",
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Rate limit exceeded");
    expect(
      screen.queryByLabelText("Password", { exact: true }),
    ).not.toBeInTheDocument();
    status = 401;
    fireEvent.click(screen.getByRole("button", { name: "Retry access" }));
    expect(
      await screen.findByLabelText("Password", { exact: true }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Workspace access unavailable" }),
    ).not.toBeInTheDocument();
  });
  it("communicates status with text", () => {
    render(<Badge value="CONTRADICTED" />);
    expect(screen.getByText("CONTRADICTED")).toBeInTheDocument();
  });
  it("offers the deterministic demo and secure login", async () => {
    window.history.replaceState({}, "", "/login");
    vi.stubGlobal(
      "fetch",
      vi.fn((url) =>
        String(url).endsWith("/auth/options")
          ? Promise.resolve({
              ok: true,
              json: async () => ({
                authenticated: false,
                local_registration: true,
                demo_available: true,
              }),
            })
          : Promise.resolve({
              ok: false,
              text: async () => '{"detail":"Sign in"}',
            }),
      ),
    );
    render(
      <QueryClientProvider client={new QueryClient()}>
        <App />
      </QueryClientProvider>,
    );
    expect(
      await screen.findByRole("button", { name: /Explore Northstar demo/ }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toHaveAttribute(
      "type",
      "password",
    );
  });
  it("shows actionable login errors", async () => {
    window.history.replaceState({}, "", "/login");
    vi.stubGlobal(
      "fetch",
      vi.fn((url) =>
        String(url).endsWith("/auth/options")
          ? Promise.resolve({
              ok: true,
              json: async () => ({
                authenticated: false,
                local_registration: true,
                demo_available: true,
              }),
            })
          : Promise.resolve({
              ok: false,
              text: async () => '{"detail":"Run the demo seed command"}',
            }),
      ),
    );
    render(
      <QueryClientProvider client={new QueryClient()}>
        <App />
      </QueryClientProvider>,
    );
    fireEvent.click(
      await screen.findByRole("button", { name: /Explore Northstar demo/ }),
    );
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Run the demo seed command",
      ),
    );
  });
  it("exposes a failed analyzer without hiding a completed engine", () => {
    render(
      <AnalysisCoverage
        data={
          {
            repositories: [
              {
                id: "one",
                name: "Real repository",
                snapshot: null,
                latest_job: {
                  id: "job",
                  state: "PARTIAL",
                  engines: {
                    SAST: { state: "COMPLETED", supported_files: 2 },
                    OSV: {
                      state: "FAILED",
                      errors: ["Advisory lookup unavailable."],
                    },
                  },
                },
              },
            ],
          } as unknown as Workspace
        }
      />,
    );
    expect(screen.getByText("PARTIAL")).toBeInTheDocument();
    expect(screen.getByText("COMPLETED")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Advisory lookup unavailable.",
    );
  });
  it("renders graph-derived impact and opens its current affected claim", () => {
    const onOpen = vi.fn();
    const claim = {
      id: "claim",
      text: "Authentication uses JWT.",
      status: "CONTRADICTED",
    };
    render(
      <ImpactSummary
        data={
          {
            repositories: [
              {
                id: "one",
                name: "Changed repository",
                snapshot: {
                  id: "head",
                  impact: {
                    base_id: "base",
                    changed_files: ["auth.py"],
                    affected_claims: ["claim"],
                    verification: { reused: 3, reverified: 1 },
                  },
                },
              },
            ],
            claim: [claim],
            finding: [],
            graph_node: [],
          } as unknown as Workspace
        }
        onOpen={onOpen}
      />,
    );
    expect(
      screen.getByText(
        "1 declared claims reverified · 3 declared claims reused from unchanged evidence",
      ),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: /Authentication uses JWT/ }),
    );
    expect(onOpen).toHaveBeenCalledWith(claim);
  });
  it("keeps a queued repository visible before any snapshot exists", async () => {
    window.history.replaceState({}, "", "/repositories");
    const data = {
      organization: "Fresh workspace",
      demo: false,
      analysis: { state: "QUEUED" },
      repositories: [
        {
          id: "queued",
          name: "Pending source",
          provider: "LOCAL",
          owner: "Owner",
          system: "System",
          component: "Component",
          snapshot: null,
          latest_job: { id: "job", state: "QUEUED" },
        },
      ],
      claim: [],
      finding: [],
      evidence: [],
      dependency: [],
      drift: [],
      pr: [],
      review: [],
      exception: [],
      job: [],
      graph_node: [],
      edge: [],
      counts: {
        complete: true,
        totals: { claim: 0, finding: 0 },
        claim_status: {},
        material_findings: 0,
        repositories: {},
      },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (path: string) => ({
        ok: true,
        json: async () =>
          path.endsWith("/auth/me")
            ? {
                email: "owner@example.test",
                role: "ORG_OWNER",
                csrf: "csrf",
                demo: false,
              }
            : data,
      })),
    );
    render(
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <App />
      </QueryClientProvider>,
    );
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "Pending source" }),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByText("Awaiting snapshot", { exact: true }),
    ).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Analysis queued");
    expect(screen.queryByText("Analysis completed")).not.toBeInTheDocument();
    window.history.replaceState({}, "", "/");
  });
});
