import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import TrustExceptions from "./TrustExceptions";
import EngineeringChanges from "./EngineeringChanges";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
const renderQuery = (node: React.ReactNode) =>
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      {node}
    </QueryClientProvider>,
  );

it("lets a privileged reviewer revoke an exception with reason and current version", async () => {
  const fetch = vi.fn(async (_url: unknown, options?: RequestInit) => ({
    ok: true,
    json: async () =>
      options?.method === "POST"
        ? {}
        : {
            total: 1,
            has_more: false,
            basis: "Context must match",
            items: [
              {
                id: "exception-1",
                version: 4,
                target: "issue",
                owner: "team",
                approver: "reviewer",
                reason: "Temporary review",
                expires_at: "2030-01-01",
                state: "ACTIVE",
              },
            ],
          },
  }));
  vi.stubGlobal("fetch", fetch);
  renderQuery(<TrustExceptions repository="ALL" role="SECURITY_REVIEWER" />);
  fireEvent.click(
    await screen.findByRole("button", { name: "Manage exception" }),
  );
  fireEvent.change(screen.getByLabelText("Reason"), {
    target: { value: "Revoke controlled temporary exception" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Revoke exception" }));
  await waitFor(() =>
    expect(
      fetch.mock.calls.some(
        ([, options]) =>
          options?.method === "POST" &&
          String(options.body).includes('"expected_version":4') &&
          String(options.body).includes('"action":"REVOKE"'),
      ),
    ).toBe(true),
  );
});

it("explains that engineering changes require an explicit comparison", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      json: async () => ({ total: 0, has_more: false, items: [] }),
    })),
  );
  renderQuery(<EngineeringChanges repository="ALL" onOpen={() => {}} />);
  expect(
    await screen.findByText(/An initial import establishes the baseline/),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Time window")).toHaveValue("7");
});
