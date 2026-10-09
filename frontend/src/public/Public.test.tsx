import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import App from "../App";
import { ThemeProvider } from "../Theme";
import { InvestigationDemo } from "./InvestigationDemo";
import Guide from "./Guide";
import AuthPage, { safeReturnTo } from "./AuthPage";
import { PublicSession } from "./PublicShell";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
describe("Public product experience", () => {
  it("explains the product without fetching private workspace data", async () => {
    window.history.replaceState({}, "", "/");
    const fetcher = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        authenticated: false,
        local_registration: true,
        demo_available: true,
      }),
    });
    vi.stubGlobal("fetch", fetcher);
    render(<App />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Know what your software actually does.",
    );
    await waitFor(() =>
      expect(
        screen.getAllByRole("link", { name: /Analyze a Repository/ })[0],
      ).toHaveAttribute("href", expect.stringContaining("/signup?next=")),
    );
    expect(
      fetcher.mock.calls.every(([url]) => String(url) === "/api/auth/options"),
    ).toBe(true);
    expect(
      screen.getByText(/Live account validation is still unverified/),
    ).toBeInTheDocument();
  });
  it("lets a visitor inspect the actual historical example stages", () => {
    render(<InvestigationDemo />);
    const example = within(
      screen.getByRole("region", {
        name: "Authentication investigation example",
      }),
    );
    expect(example.getByText("CONTRADICTED")).toBeInTheDocument();
    fireEvent.click(example.getByRole("button", { name: /Before change/ }));
    expect(example.getByText("VERIFIED")).toBeInTheDocument();
    expect(example.getByText("import jwt")).toBeInTheDocument();
    fireEvent.click(example.getByRole("button", { name: /Change detected/ }));
    expect(example.getByText("STALE")).toBeInTheDocument();
    expect(example.getByText(/The implementation changed/)).toBeInTheDocument();
  });
  it("supports topic search and a separate technical explanation", async () => {
    render(
      <MemoryRouter initialEntries={["/guide/drift"]}>
        <Routes>
          <Route path="/guide/:topic" element={<Guide />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Drift",
    );
    expect(
      screen.queryByRole("heading", { name: "Technical details" }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Technical details" }));
    expect(
      screen.getByRole("heading", { name: "Technical details" }),
    ).toBeInTheDocument();
    fireEvent.change(
      screen.getByRole("searchbox", { name: "Find a guide topic" }),
      { target: { value: "zzzz-no-topic" } },
    );
    expect(screen.getByRole("status")).toHaveTextContent("No matching topics");
    fireEvent.change(
      screen.getByRole("searchbox", { name: "Find a guide topic" }),
      { target: { value: "dependency" } },
    );
    expect(
      within(
        screen.getByRole("navigation", { name: "Guide topics" }),
      ).getByRole("link", { name: /Dependencies/ }),
    ).toBeInTheDocument();
  });
  it("keeps unknown guide paths out of authenticated navigation", () => {
    render(
      <MemoryRouter initialEntries={["/guide/unknown"]}>
        <Routes>
          <Route path="/guide/:topic" element={<Guide />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Guide topic not found",
    );
    expect(
      screen.getByRole("link", { name: "Open the Guide" }),
    ).toHaveAttribute("href", "/guide");
  });
  it("rejects external, malformed and arbitrary return destinations", () => {
    for (const value of [
      "https://evil.example/repositories",
      "//evil.example",
      "javascript:alert(1)",
      "/unknown",
      "/\\evil.example",
      "/%2F%2Fevil.example",
    ])
      expect(safeReturnTo(value)).toBe("/app");
    expect(safeReturnTo("/repositories?import=1&secret=hidden")).toBe(
      "/repositories?import=1",
    );
    expect(safeReturnTo("/claims")).toBe("/claims");
  });
  it("hides local registration when the server disables it", () => {
    render(
      <ThemeProvider>
        <PublicSession.Provider
          value={{
            authenticated: false,
            local_registration: false,
            demo_available: false,
            ready: true,
          }}
        >
          <MemoryRouter>
            <AuthPage register />
          </MemoryRouter>
        </PublicSession.Provider>
      </ThemeProvider>,
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      "Local account creation is disabled",
    );
    expect(
      screen.queryByRole("button", { name: "Create workspace & continue" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
  });
  it("shows an unavailable account-options read without asserting registration is disabled", () => {
    render(
      <ThemeProvider>
        <PublicSession.Provider
          value={{
            authenticated: false,
            local_registration: false,
            demo_available: false,
            ready: true,
            error: "Rate limit reached. Try again in one minute.",
          }}
        >
          <MemoryRouter>
            <AuthPage register />
          </MemoryRouter>
        </PublicSession.Provider>
      </ThemeProvider>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Rate limit reached");
    expect(
      screen.getByRole("button", { name: "Create workspace & continue" }),
    ).toBeDisabled();
    expect(
      screen.queryByText(/Local account creation is disabled/),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Retry connection" }),
    ).toBeInTheDocument();
  });
  it("creates an empty local workspace and returns directly to source import", async () => {
    const fetcher = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        email: "test@example.com",
        role: "ORG_OWNER",
        csrf: "test-only-csrf",
        demo: false,
      }),
    });
    vi.stubGlobal("fetch", fetcher);
    function Destination() {
      const location = useLocation();
      return <h1>{location.pathname + location.search}</h1>;
    }
    render(
      <ThemeProvider>
        <PublicSession.Provider
          value={{
            authenticated: false,
            local_registration: true,
            demo_available: true,
            ready: true,
          }}
        >
          <MemoryRouter
            initialEntries={["/signup?next=%2Frepositories%3Fimport%3D1"]}
          >
            <Routes>
              <Route path="/signup" element={<AuthPage register />} />
              <Route path="/repositories" element={<Destination />} />
            </Routes>
          </MemoryRouter>
        </PublicSession.Provider>
      </ThemeProvider>,
    );
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "test@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "Synthetic-test-password-123!" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Create workspace & continue" }),
    );
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
        "/repositories?import=1",
      ),
    );
    expect(fetcher).toHaveBeenCalledTimes(1);
    const [url, request] = fetcher.mock.calls[0];
    expect(url).toBe("/api/auth/register");
    expect(JSON.parse(request.body)).toEqual({
      email: "test@example.com",
      password: "Synthetic-test-password-123!",
      organization: "ProjectTrace",
    });
    expect(request.credentials).toBe("include");
  });
});
