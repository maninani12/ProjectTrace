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
import type { Repository } from "./api";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  setCSRF("");
});
function show(
  repositories: Repository[] = [],
  initialTarget = "NEW",
  onDone = vi.fn(),
) {
  return render(
    <ImportDialog
      repositories={repositories}
      initialTarget={initialTarget}
      onRefresh={vi.fn()}
      onClose={vi.fn()}
      onDone={onDone}
      onConnect={vi.fn()}
    />,
  );
}
const publicRepository: Repository = {
  id: "public-repo-id",
  name: "owner/repo",
  system: "Imported System",
  component: "owner/repo",
  owner: "Engineering Team",
  provider: "GITHUB_PUBLIC",
  snapshot: {
    id: "captured-base", branch: "release", commit: "a".repeat(40),
    file_count: 2, changed_files: [], status: "COMPLETED_NO_FINDINGS",
    gate: { overall: "PASS", mode: "REPORT", results: [] },
    scope: { repository: "owner/repo", repository_id: "public-repo-id",
      system: "Imported System", component: "owner/repo", branch: "release",
      commit: "a".repeat(40), snapshot_id: "captured-base", analysis_at: "2026-10-31",
      analyzer_version: "1.6.0" },
  },
};
const zipRepository: Repository = {
  ...publicRepository,
  id: "zip-repo-id",
  name: "zip-repo",
  provider: "ZIP",
};

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

it("targets an existing public repository and labels the import as a BASE/HEAD comparison", async () => {
  setCSRF("fixture-csrf");
  const fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ repository_id: publicRepository.id }),
  });
  const onDone = vi.fn();
  vi.stubGlobal("fetch", fetch);
  show([publicRepository, zipRepository], publicRepository.id, onDone);

  expect(screen.getByLabelText("Public import destination")).toHaveValue(
    publicRepository.id,
  );
  expect(screen.getByLabelText("Public repository URL")).toHaveValue(
    "https://github.com/owner/repo",
  );
  expect(
    screen.getByLabelText("Public import destination").querySelectorAll("option"),
  ).toHaveLength(2);
  expect(
    screen.getByRole("button", { name: "Analyze and compare public snapshot" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("note", { name: "Public comparison BASE" })).toHaveTextContent(
    "BASE captured-base · release · " + "a".repeat(40),
  );

  fireEvent.click(
    screen.getByRole("button", { name: "Analyze and compare public snapshot" }),
  );
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toMatchObject({
    url: "https://github.com/owner/repo",
    repository_id: publicRepository.id,
    base_snapshot_id: "captured-base",
  });
  expect(onDone).toHaveBeenCalledWith(publicRepository.id);
});

it("keeps a new public import separate from an existing repository", async () => {
  setCSRF("fixture-csrf");
  const fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ repository_id: "new-public-repo" }),
  });
  vi.stubGlobal("fetch", fetch);
  show([publicRepository, zipRepository]);
  fireEvent.click(screen.getByRole("button", { name: "Public GitHub URL" }));
  fireEvent.change(screen.getByLabelText("Public repository URL"), {
    target: { value: "https://github.com/another/project" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Import public snapshot" }));
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
  const payload = JSON.parse(fetch.mock.calls[0][1].body);
  expect(payload.url).toBe("https://github.com/another/project");
  expect(payload).not.toHaveProperty("repository_id");
  expect(payload).not.toHaveProperty("base_snapshot_id");
});

it("retains the displayed BASE through workspace refresh and failed-submit retry", async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: false, text: async () => "Provider unavailable" });
  vi.stubGlobal("fetch", fetch);
  const view = show([publicRepository], publicRepository.id);
  const submit = () => fireEvent.click(screen.getByRole("button", {
    name: "Analyze and compare public snapshot",
  }));
  submit();
  await screen.findByRole("alert");
  view.rerender(<ImportDialog repositories={[{ ...publicRepository,
    snapshot: { ...publicRepository.snapshot!, id: "newer-snapshot" },
  }]} initialTarget={publicRepository.id} onRefresh={vi.fn()} onClose={vi.fn()}
    onDone={vi.fn()} onConnect={vi.fn()} />);
  expect(screen.getByRole("note", { name: "Public comparison BASE" })).toHaveTextContent("BASE captured-base");
  submit();
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
  expect(fetch.mock.calls[1][1].body).toBe(fetch.mock.calls[0][1].body);
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
