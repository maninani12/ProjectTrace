import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import ClaimComparisons from "./ClaimComparisons";
import type { ClaimComparison } from "./ClaimComparisons";

afterEach(cleanup);
const comparison: ClaimComparison = {
  claim_key: "jwt",
  text: "Authentication uses JWT.",
  path: "README.md",
  line: 2,
  document: { id: "doc", path: "README.md", hash: "doc-digest" },
  before: {
    claim_id: "old-claim",
    status: "VERIFIED",
    reason: "JWT syntax captured.",
    evidence: [{ id: "old-source", path: "app.py", hash: "jwt-digest" }],
    evidence_truncated: false,
  },
  after: {
    claim_id: "new-claim",
    status: "CONTRADICTED",
    reason: "Session configuration captured.",
    evidence: [{ id: "new-source", path: "app.py", hash: "session-digest" }],
    evidence_truncated: false,
  },
};

it("shows the captured claim, both verdicts, hashes and authorized inspection targets", () => {
  const inspect = vi.fn();
  render(<ClaimComparisons items={[comparison]} onInspect={inspect} />);
  expect(
    screen.getByRole("heading", {
      name: "Original claim: Authentication uses JWT.",
    }),
  ).toBeVisible();
  expect(screen.getByText("VERIFIED")).toBeVisible();
  expect(screen.getByText("CONTRADICTED")).toBeVisible();
  expect(screen.getByText("SHA-256: session-digest")).toBeVisible();
  for (const label of [
    "Inspect original documentation",
    "Inspect BASE source: app.py",
    "Inspect HEAD source: app.py",
    "Inspect HEAD claim",
  ])
    fireEvent.click(screen.getByRole("button", { name: label }));
  expect(inspect.mock.calls.map(([id]) => id)).toEqual([
    "doc",
    "old-source",
    "new-source",
    "new-claim",
  ]);
});

it("presents unknown evidence without implying a contradiction or inventing a source", () => {
  render(
    <ClaimComparisons
      items={[
        {
          ...comparison,
          after: {
            status: "UNVERIFIED",
            reason: "No supported evidence.",
            evidence: [],
            evidence_truncated: false,
          },
        },
      ]}
      onInspect={vi.fn()}
    />,
  );
  expect(screen.getByText("UNVERIFIED")).toBeVisible();
  expect(
    screen.getByText("No conclusive source evidence captured."),
  ).toBeVisible();
  expect(
    screen.queryByRole("button", { name: /Inspect HEAD source/ }),
  ).not.toBeInTheDocument();
});

it("allows legacy changes without comparison references", () => {
  render(<ClaimComparisons items={[]} onInspect={vi.fn()} />);
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});
