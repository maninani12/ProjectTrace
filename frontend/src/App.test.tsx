import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App, { Badge } from "./App";
import { cleanup } from "@testing-library/react";
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
describe("ProjectTrace interface", () => {
  it("communicates status with text", () => {
    render(<Badge value="CONTRADICTED" />);
    expect(screen.getByText("CONTRADICTED")).toBeInTheDocument();
  });
  it("offers the deterministic demo and secure login", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue({
          ok: false,
          text: async () => '{"detail":"Sign in"}',
        }),
    );
    render(
      <QueryClientProvider client={new QueryClient()}>
        <App />
      </QueryClientProvider>,
    );
    expect(
      screen.getByRole("button", { name: /Explore Northstar demo/ }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toHaveAttribute(
      "type",
      "password",
    );
  });
  it("shows actionable login errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue({
          ok: false,
          text: async () => '{"detail":"Run the demo seed command"}',
        }),
    );
    render(
      <QueryClientProvider client={new QueryClient()}>
        <App />
      </QueryClientProvider>,
    );
    fireEvent.click(
      screen.getByRole("button", { name: /Explore Northstar demo/ }),
    );
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Run the demo seed command",
      ),
    );
  });
});
