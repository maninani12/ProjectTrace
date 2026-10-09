import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ImportDialog } from "./WorkspaceApp";
import { setCSRF } from "./api";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  setCSRF("");
});
function show() {
  return render(
    <ImportDialog
      repositories={[]}
      initialTarget="NEW"
      onRefresh={vi.fn()}
      onClose={vi.fn()}
      onDone={vi.fn()}
      onConnect={vi.fn()}
    />,
  );
}
it("submits a public URL/ref with CSRF and a stable request identity on retry", async () => {
  setCSRF("fixture-csrf");
  const fetch = vi
    .fn()
    .mockResolvedValue({
      ok: false,
      text: async () =>
        JSON.stringify({
          detail: {
            message: "Provider unavailable.",
            remediation: "Retry retained source.",
          },
        }),
    });
  vi.stubGlobal("fetch", fetch);
  show();
  fireEvent.click(screen.getByRole("button", { name: "Public GitHub URL" }));
  fireEvent.change(screen.getByLabelText("Public repository URL"), {
    target: { value: "https://github.com/owner/repo" },
  });
  fireEvent.change(screen.getByLabelText("Branch, tag or commit (optional)"), {
    target: { value: "release" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Import public snapshot" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Provider unavailable. Retry retained source.",
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Import public snapshot" }),
  );
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
  const [path, options] = fetch.mock.calls[0];
  expect(path).toBe("/api/github/public/import");
  expect(options.headers["X-CSRF-Token"]).toBe("fixture-csrf");
  expect(JSON.parse(options.body)).toMatchObject({
    url: "https://github.com/owner/repo",
    ref: "release",
  });
  expect(fetch.mock.calls[1][1].body).toBe(options.body);
});
it("shows exact intake budget and actionable remediation", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue({
        ok: false,
        text: async () =>
          JSON.stringify({
            detail: {
              message: "Archive too large.",
              budget: "REPOSITORY_MAX_BYTES",
              actual: 101,
              maximum: 100,
              remediation: "Import a component.",
            },
          }),
      }),
  );
  show();
  fireEvent.change(screen.getByLabelText("Repository name"), {
    target: { value: "service" },
  });
  fireEvent.change(screen.getByLabelText("Source archive"), {
    target: { files: [new File(["data"], "source.zip")] },
  });
  fireEvent.submit(screen.getByRole("button", { name: "Analyze source snapshot" }).closest("form")!);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "REPOSITORY_MAX_BYTES: 101 / 100. Import a component.",
  );
});
