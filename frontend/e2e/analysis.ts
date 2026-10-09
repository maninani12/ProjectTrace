import {
  expect,
  type APIRequestContext,
  type APIResponse,
} from "@playwright/test";

/** Verify real completion in both synchronous and durable queued runtimes. */
export async function completedAnalysis(
  request: APIRequestContext,
  response: APIResponse,
) {
  expect([200, 202]).toContain(response.status());
  const receipt = await response.json();
  let snapshotId = receipt.snapshot_id || receipt.id;
  if (response.status() === 202) {
    let job: { state: string; snapshot_id?: string; error_code?: string };
    await expect
      .poll(
        async () => {
          const current = await request.get(`/api/record/${receipt.job_id}`);
          expect(current.ok()).toBeTruthy();
          job = await current.json();
          return [
            "COMPLETED",
            "COMPLETED_NO_FINDINGS",
            "PARTIAL",
            "FAILED",
            "CANCELLED",
          ].includes(job.state);
        },
        { timeout: 45000, intervals: [100, 250, 500, 1000] },
      )
      .toBe(true);
    expect(
      ["COMPLETED", "COMPLETED_NO_FINDINGS", "PARTIAL"],
      job!.error_code,
    ).toContain(job!.state);
    snapshotId = job!.snapshot_id;
  }
  expect(snapshotId).toBeTruthy();
  const snapshot = await request.get(`/api/record/${snapshotId}`);
  expect(snapshot.ok()).toBeTruthy();
  const result = await snapshot.json();
  expect(result.kind).toBe("snapshot");
  return { ...receipt, ...result, snapshot_id: result.id };
}
