// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { StepReport } from "../types";
import type { WeaverChecks } from "./checks";
const mock = vi.hoisted(() => ({ invoke: vi.fn(), provision: vi.fn(), deletion: vi.fn() }));
vi.mock("./runtime", () => ({ TEST_ASSISTANT: "diagnostic" }));
vi.mock("./resourceSupport", () => ({
  cp: new Proxy({}, { get: (_target, name) => ({ initiate: (args: unknown) => ({ name, args }) }) }),
  assert: (condition: unknown, message: string) => {
    if (!condition) throw new Error(message);
  },
  requireSpace: (_checks: unknown, signal: AbortSignal) => signal.throwIfAborted(),
  requireWrite: async (_checks: unknown, signal: AbortSignal) => signal.throwIfAborted(),
  expectAbsent: async () => {},
  folderListed: async () => false,
  provisionDisposableAgent: mock.provision,
  waitForDeletion: mock.deletion,
}));
import { teams } from "./resourceScenarios";
const checks = {
  spaceId: "selected",
  spaceKind: "organization",
  organizationId: "organization",
  userId: "operator",
  dispatch: (request: unknown) => ({ unwrap: () => mock.invoke(request) }),
} as unknown as WeaverChecks;
let editor: boolean;
let retired: boolean;
let controller: AbortController;
let reports: StepReport[];
let failure: string | undefined;
let abortAt: string | undefined;
beforeEach(() => {
  vi.clearAllMocks();
  editor = false;
  retired = false;
  failure = undefined;
  abortAt = undefined;
  controller = new AbortController();
  reports = [];
  mock.provision.mockResolvedValue(null);
  mock.deletion.mockResolvedValue({ completed: true, detail: "Physical deletion completed." });
  mock.invoke.mockImplementation(async ({ name }) => {
    if (name === "grant") editor = true;
    if (name === abortAt) controller.abort();
    if (name === failure) throw { status: 500 };
    switch (name) {
      case "wikiAvailability":
        return { enabled: false };
      case "authorizeSpace":
        return { allowed: true };
      case "createSpace":
        return { id: "disposable" };
      case "mySpaces":
        return retired ? [] : [{ id: "disposable", kind: "team", roles: ["owner"] }];
      case "spaceMembers":
        return { items: [{ user: { id: "operator" }, roles: ["owner"] }] };
      case "entries":
        if (!editor) throw { status: 403 };
        return { total: 0, items: [{ kind: "folder", data: { id: "folder", space_id: "disposable" } }] };
      case "createPrompt":
        if (!editor) throw { status: 403 };
        return { prompt_id: "prompt", text: "Team-scoped disposable text." };
      case "getPrompt":
        return { prompt_id: "prompt", space_id: "disposable", text: "Team-scoped disposable text." };
      case "createFolder":
        return { id: "folder" };
      case "revoke":
        editor = false;
        return;
      case "deleteSpace":
        retired = true;
        return {
          target_kind: "team",
          target_id: "disposable",
          target_parent_id: "organization",
          actor_subject: "operator",
        };
      default:
        return;
    }
  });
});
const run = () => teams(checks, (step) => reports.push(step), controller.signal);
const calls = (name: string) =>
  mock.invoke.mock.calls.map(([request]) => request).filter((request) => request.name === name);
describe("disposable team editor lifecycle", () => {
  it("grants only on the new team after owner-only denial and revokes before retirement", async () => {
    await run();
    expect(calls("grant")).toEqual([{ name: "grant", args: { id: "disposable", user: "operator", role: "editor" } }]);
    expect(calls("revoke")).toHaveLength(1);
    for (const id of ["teams.read", "teams.grantEditor", "teams.prompt", "teams.folder", "teams.revokeEditor"])
      expect(reports.find((step) => step.id === id && step.status === "passed")).toBeDefined();
    expect(calls("createPrompt")).toHaveLength(3);
    expect(mock.provision.mock.calls[0][0]).toMatchObject({ spaceId: "disposable", spaceKind: "team" });
    expect(retired).toBe(true);
    expect(editor).toBe(false);
    expect(calls("deleteSpace")).toEqual([{ name: "deleteSpace", args: { id: "disposable", immediate: true } }]);
  });
  it("does not grant or run positives after failed governance", async () => {
    failure = "spaceMembers";
    await run();
    expect(calls("grant")).toHaveLength(0);
    expect(calls("createPrompt")).toHaveLength(0);
    expect(retired).toBe(true);
  });
  it("revokes when the grant response fails after applying it", async () => {
    failure = "grant";
    await run();
    expect(calls("revoke")).toHaveLength(1);
    expect(calls("createFolder")).toHaveLength(0);
    expect(retired).toBe(true);
    expect(editor).toBe(false);
  });
  it("revokes and retires after cancellation during a grant", async () => {
    abortAt = "grant";
    await run();
    expect(calls("revoke")).toHaveLength(1);
    expect(retired).toBe(true);
    expect(editor).toBe(false);
  });
  it("retires even if explicit revocation fails", async () => {
    failure = "revoke";
    await run();
    expect(calls("revoke")).toHaveLength(2);
    expect(retired).toBe(true);
    expect(reports.some((step) => step.id === "teams.editorCleanup" && step.status === "failed")).toBe(true);
  });
});
