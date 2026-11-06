// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it, vi } from "vitest";
import { recoverCampaign, runCampaign, validateJournal, type CampaignJournal } from "./campaign";
import type { WeaverChecks } from "./checks";
import { authedFetch } from "../useAuthzProbeRun";
import { waitForDeletion } from "./resourceSupport";
vi.mock("../useAuthzProbeRun", () => ({ authedFetch: vi.fn() }));
vi.mock("./resourceSupport", () => ({
  cp: Object.fromEntries(
    ["me", "mySpaces", "deleteSpace", "deletionStatus", "projectDeletionStatus", "createSpace", "frontendConfig"].map(
      (name) => [name, { initiate: (args: unknown) => ({ name, args }) }],
    ),
  ),
  waitForDeletion: vi.fn(async () => ({ completed: true, detail: "Completed" })),
}));
const journal: CampaignJournal = {
  version: 1,
  operatorId: "operator",
  parentId: "00000000-0000-4000-8000-000000000010",
  scope: "00000000-0000-4000-8000-000000000000",
};
function fixture(saved: CampaignJournal | null, spaces: unknown[] = []) {
  const dispatch = vi.fn((action: { name: string }) => ({
    unwrap: async (): Promise<unknown> =>
      action.name === "me"
        ? { user_id: "operator", platform_roles: ["platform_admin"] }
        : action.name === "frontendConfig"
          ? { user_auth: { enabled: true } }
          : spaces,
  }));
  const context = {
    dispatch,
    userId: "operator",
    spaceId: "00000000-0000-4000-8000-000000000010",
    organizationId: "organization",
  } as unknown as WeaverChecks;
  return { context, storage: { read: () => saved, save: vi.fn() }, report: vi.fn(), dispatch };
}
describe("isolated role campaign recovery", () => {
  it("rejects recovery identifiers outside the scoped format", () => {
    expect(() => validateJournal({ ...journal, scope: "../unrelated" })).toThrow("Invalid recovery");
  });
  it("does not delete a project whose fixture identity differs", async () => {
    const { context, storage, report, dispatch } = fixture(
      { ...journal, projectId: "00000000-0000-4000-8000-000000000001" },
      [
        {
          kind: "project",
          roles: ["owner"],
          id: "00000000-0000-4000-8000-000000000002",
          parent_id: "00000000-0000-4000-8000-000000000010",
          name: `selftest-role-${journal.scope}`,
        },
      ],
    );
    await recoverCampaign(context, storage, report);
    expect(report).toHaveBeenLastCalledWith(expect.objectContaining({ status: "failed" }));
    expect(storage.save).not.toHaveBeenCalled();
    expect(dispatch.mock.calls.map(([action]) => action.name)).not.toContain("deleteSpace");
  });
  it("recovers a lost deletion response using only a read-only receipt lookup", async () => {
    const projectId = "00000000-0000-4000-8000-000000000001";
    const { context, storage, report, dispatch } = fixture({ ...journal, projectId });
    dispatch.mockImplementation((action: { name: string }) => ({
      unwrap: async () =>
        action.name === "me"
          ? { user_id: "operator", platform_roles: ["platform_admin"] }
          : action.name === "mySpaces"
            ? []
            : {
                id: "00000000-0000-4000-8000-000000000002",
                target_id: projectId,
                target_parent_id: journal.parentId,
                target_kind: "project",
                roles: ["owner"],
                actor_subject: journal.operatorId,
                status: "completed",
              },
    }));
    await recoverCampaign(context, storage, report);
    expect(storage.save).toHaveBeenLastCalledWith(null);
    expect(dispatch.mock.calls.map(([action]) => action.name)).toContain("projectDeletionStatus");
    expect(dispatch.mock.calls.map(([action]) => action.name)).not.toContain("deleteSpace");
  });
  it.each([false, true])("releases the next campaign after retirement with future retention: %s", async (future) => {
    const projectId = "00000000-0000-4000-8000-000000000001";
    const { context, storage, report, dispatch } = fixture({
      ...journal,
      projectId,
      deletionId: "00000000-0000-4000-8000-000000000002",
    });
    dispatch.mockImplementation((action: { name: string }) => ({
      unwrap: async () =>
        action.name === "me"
          ? { user_id: "operator", platform_roles: ["platform_admin"] }
          : action.name === "mySpaces"
            ? []
            : {
                id: "00000000-0000-4000-8000-000000000002",
                target_id: projectId,
                target_parent_id: journal.parentId,
                target_kind: "project",
                roles: ["owner"],
                actor_subject: journal.operatorId,
                status: "queued",
                due_at: new Date(Date.now() + (future ? 60_000 : -60_000)).toISOString(),
              },
    }));
    vi.mocked(waitForDeletion).mockImplementationOnce(async (_checks, receipt) => ({
      completed: false,
      receipt,
      detail: "Deletion remains scheduled",
    }));
    await recoverCampaign(context, storage, report);
    expect(storage.save).toHaveBeenLastCalledWith(null);
    expect(report).toHaveBeenLastCalledWith(
      expect.objectContaining(
        future
          ? { status: "skipped", detail: "Deletion remains scheduled", optional: false }
          : { status: "failed", error: "Project retirement is verified; physical deletion has not completed" },
      ),
    );
    expect(dispatch.mock.calls.map(([action]) => action.name)).not.toContain("deleteSpace");
  });
  it("recovers an interruption before create by reconciling the exact unique fixture name", async () => {
    const projectId = "00000000-0000-4000-8000-000000000001";
    const saved = { ...journal };
    let created = false;
    let deleted = false;
    const { context, storage, report, dispatch } = fixture(saved);
    dispatch.mockImplementation((action: { name: string }) => ({
      unwrap: async () => {
        if (action.name === "me") return { user_id: "operator", platform_roles: ["platform_admin"] };
        if (action.name === "createSpace") {
          created = true;
          return { id: projectId };
        }
        if (action.name === "mySpaces")
          return created && !deleted
            ? [
                {
                  id: projectId,
                  kind: "project",
                  roles: ["owner"],
                  name: `selftest-role-${journal.scope}`,
                  parent_id: journal.parentId,
                },
              ]
            : [];
        if (action.name === "deleteSpace") deleted = true;
        return {
          id: "00000000-0000-4000-8000-000000000002",
          target_id: projectId,
          target_parent_id: journal.parentId,
          target_kind: "project",
          roles: ["owner"],
          actor_subject: journal.operatorId,
          status: "completed",
        };
      },
    }));
    await recoverCampaign(context, storage, report);
    expect(storage.save).toHaveBeenLastCalledWith(null);
    expect(dispatch.mock.calls.map(([action]) => action.name)).toContain("createSpace");
    expect(report).toHaveBeenLastCalledWith(expect.objectContaining({ status: "passed" }));
  });
  it("retains identifiers when exact-name reconciliation cannot be verified", async () => {
    const { context, storage, report } = fixture(journal);
    await recoverCampaign(context, storage, report);
    expect(storage.save).not.toHaveBeenCalled();
    expect(report).toHaveBeenLastCalledWith(
      expect.objectContaining({ status: "failed", error: expect.stringContaining("reconciled") }),
    );
  });
  it("clears cleanup identifiers after a definitive rejected creation", async () => {
    vi.mocked(authedFetch)
      .mockReset()
      .mockResolvedValueOnce({ status: 200, body: { user_id: "target" } })
      .mockResolvedValueOnce({
        status: 200,
        body: [{ id: "00000000-0000-4000-8000-000000000010", roles: ["member"] }],
      });
    const { context, storage, report, dispatch } = fixture(null);
    dispatch.mockImplementation((action: { name: string }) => ({
      unwrap: async () => {
        if (action.name === "frontendConfig") return { user_auth: { enabled: true } };
        if (action.name === "me") return { user_id: "operator", platform_roles: ["platform_admin"] };
        if (action.name === "createSpace") throw { status: 409, data: { detail: "private-server-body" } };
        return [{ id: "00000000-0000-4000-8000-000000000010", kind: "team", roles: ["owner", "editor"] }];
      },
    }));
    await runCampaign(context, "private-token", storage, report, new AbortController().signal);
    expect(storage.save).toHaveBeenLastCalledWith(null);
    expect(JSON.stringify(report.mock.calls)).not.toContain("private-server-body");
    expect(dispatch.mock.calls.map(([action]) => action.name)).not.toContain("deleteSpace");
  });
  it("refuses mutations when the second credential is the operator", async () => {
    vi.mocked(authedFetch).mockResolvedValueOnce({
      status: 200,
      body: { user_id: "operator", platform_roles: ["platform_admin"] },
    });
    const { context, storage, report, dispatch } = fixture(null);
    await runCampaign(context, "private-token", storage, report, new AbortController().signal);
    expect(storage.save).not.toHaveBeenCalled();
    expect(dispatch).toHaveBeenCalledTimes(2);
    expect(JSON.stringify(report.mock.calls)).not.toContain("private-token");
    expect(report).toHaveBeenLastCalledWith(expect.objectContaining({ status: "failed" }));
  });
});
