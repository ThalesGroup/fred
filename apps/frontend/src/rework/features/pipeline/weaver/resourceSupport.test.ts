// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { beforeEach, describe, expect, it, vi } from "vitest";
import type { StepReport } from "../types";
import { tabularFixtures } from "../scenarios/formats";
import type { WeaverChecks } from "./checks";

const mock = vi.hoisted(() => ({
  invoke: vi.fn(),
  imported: vi.fn(),
  echo: vi.fn(),
  runImport: vi.fn().mockResolvedValue(undefined),
}));
vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  enhancedControlPlaneApi: {
    endpoints: new Proxy({}, { get: (_target, name) => ({ initiate: (args: unknown) => ({ name, args }) }) }),
  },
}));
vi.mock("../../imports/managerImportRun", () => ({
  managerActor: () => "actor",
  runManagerImport: mock.runImport,
  managerImportsSnapshot: () => mock.imported(),
  dismissManagerImport: vi.fn().mockResolvedValue(undefined),
}));
vi.mock("./runtime", () => ({
  TEST_ASSISTANT: "fred.github.test_assistant",
  checkAgentRuntime: mock.echo,
  checkKnowledgeRuntime: vi.fn(),
  checkConversationRuntime: vi.fn(),
  runRuntimeProbe: vi.fn(),
}));
import { agents, prompts } from "./resourceScenarios";
import { expectAbsent, ingestKnowledgeFixture, waitForDeletion, provisionDisposableAgent } from "./resourceSupport";

const checks = {
  spaceId: "space",
  spaceKind: "team",
  organizationId: "organization",
  userId: "person",
  dispatch: (request: unknown) => ({ unwrap: () => mock.invoke(request) }),
  read: (endpoint: { initiate: (args: unknown) => unknown }, args: unknown) => mock.invoke(endpoint.initiate(args)),
} as unknown as WeaverChecks;

beforeEach(() => {
  vi.useRealTimers();
  localStorage.clear();
  vi.clearAllMocks();
  const locked = new Set<string>();
  vi.stubGlobal("navigator", {
    locks: {
      request: async (name: string, _options: unknown, body: (lock: object | null) => Promise<void>) => {
        if (locked.has(name)) return body(null);
        locked.add(name);
        try {
          await body({ name });
        } finally {
          locked.delete(name);
        }
      },
    },
  });
  mock.imported.mockReturnValue([
    {
      folderId: "folder",
      receipt: {
        status: "stored",
        document_id: "document",
        request_key: "upload",
        folder_id: "folder",
        space_id: "space",
      },
    },
  ]);
});

const receipt = (overrides: Record<string, unknown> = {}) =>
  ({
    id: "operation",
    target_id: "document",
    target_kind: "document",
    target_parent_id: "space",
    actor_subject: "person",
    organization_id: "organization",
    status: "completed",
    due_at: new Date().toISOString(),
    ...overrides,
  }) as Parameters<typeof waitForDeletion>[1];

function fixtureApi(
  options: {
    survivingFolder?: boolean;
    survivingDocument?: boolean;
    foreignContent?: boolean;
    retentionMs?: number;
    tabularRows?: number;
  } = {},
) {
  let deleted = false;
  let folderDeleted = false;
  const folder = { id: "folder", name: "Self-test original", space_id: "space", created_at: "creation" };
  mock.invoke.mockImplementation(
    async ({ name, args }: { name: string; args?: { parentId?: string; rename?: { name: string } } }) => {
      if (name === "authorizeSpace") return { allowed: true };
      if (name === "createFolder") {
        deleted = false;
        folderDeleted = false;
        return { ...folder };
      }
      if (name === "renameFolder") {
        folder.name = args!.rename!.name;
        return { ...folder };
      }
      if (name === "entries") {
        if (!args?.parentId)
          return {
            items: folderDeleted && !options.survivingFolder ? [] : [{ kind: "folder", data: folder }],
            total: folderDeleted && !options.survivingFolder ? 0 : 1,
          };
        const items =
          !deleted || options.survivingDocument
            ? [{ kind: "document", data: { id: "document", created_by: "person" } }]
            : [];
        if (options.foreignContent) items.push({ kind: "document", data: { id: "foreign", created_by: "other" } });
        return {
          items,
          total: items.length,
          processing: {
            document: {
              status: "succeeded",
              chunks: options.tabularRows ? 0 : 1,
              vectors: options.tabularRows ? 0 : 1,
              rows: options.tabularRows,
            },
          },
        };
      }
      if (name === "deleteDocument") {
        deleted = true;
        return receipt({
          status: options.retentionMs ? "queued" : "completed",
          due_at: new Date(Date.now() + (options.retentionMs ?? 0)).toISOString(),
        });
      }
      if (name === "deletionStatus") return receipt();
      if (name === "deleteFolder") {
        folderDeleted = true;
        return undefined;
      }
      throw new Error("Unexpected request");
    },
  );
}

describe("owned resource cleanup", () => {
  it("rejects a surviving renamed folder even when browsing its children returns an empty list", async () => {
    fixtureApi({ survivingFolder: true });
    const fixture = await ingestKnowledgeFixture(checks, new AbortController().signal);
    await fixture.renameFolder("Self-test renamed");
    await expect(fixture.cleanup()).rejects.toThrow("Deleted folder remains");
  });

  it("does not delete a folder while its retired document remains visible", async () => {
    fixtureApi({ survivingDocument: true });
    const fixture = await ingestKnowledgeFixture(checks, new AbortController().signal);
    await expect(fixture.cleanup()).rejects.toThrow("Deleted document remains");
    expect(mock.invoke.mock.calls.some(([request]) => request.name === "deleteFolder")).toBe(false);
  });

  it("refuses recursive deletion if another person adds content to the disposable folder", async () => {
    fixtureApi({ foreignContent: true });
    const fixture = await ingestKnowledgeFixture(checks, new AbortController().signal);
    await expect(fixture.cleanup()).rejects.toThrow("unrecognized content");
    expect(mock.invoke.mock.calls.some(([request]) => request.name === "deleteFolder")).toBe(false);
  });

  it("requests immediate cleanup and permits a new fixture after cleanup fails", async () => {
    fixtureApi({ retentionMs: 7 * 86400_000 });
    const first = await ingestKnowledgeFixture(checks, new AbortController().signal);
    await expect(first.cleanup()).rejects.toThrow("retention policy");
    expect(mock.invoke.mock.calls).toContainEqual([
      { name: "deleteDocument", args: { id: "document", immediate: true } },
    ]);
    await ingestKnowledgeFixture(checks, new AbortController().signal);
    const creations = mock.invoke.mock.calls.filter(([request]) => request.name === "createFolder");
    expect(creations).toHaveLength(2);
    expect(creations[0][0].args.createFolder.name).not.toBe(creations[1][0].args.createFolder.name);
    expect(localStorage.length).toBe(0);
  });

  it("allows independent fixtures without browser recovery locks", async () => {
    fixtureApi();
    vi.stubGlobal("navigator", {});
    await ingestKnowledgeFixture(checks, new AbortController().signal);
    await ingestKnowledgeFixture(checks, new AbortController().signal);
    expect(mock.invoke.mock.calls.filter(([request]) => request.name === "createFolder")).toHaveLength(2);
  });

  it("resolves the current upload receipt before cleaning up a failed import", async () => {
    fixtureApi();
    mock.imported.mockReturnValue([{ key: "upload", folderId: "folder", spaceId: "space" }]);
    mock.runImport.mockRejectedValueOnce(new Error("Upload acknowledgement lost"));
    const respond = mock.invoke.getMockImplementation()!;
    mock.invoke.mockImplementation(async (request: { name: string }) =>
      request.name === "receipt"
        ? { request_key: "upload", folder_id: "folder", space_id: "space", status: "stored", document_id: "document" }
        : respond(request),
    );
    await expect(ingestKnowledgeFixture(checks, new AbortController().signal)).rejects.toThrow(
      "Upload acknowledgement lost",
    );
    expect(mock.invoke.mock.calls).toContainEqual([{ name: "receipt", args: { id: "upload" } }]);
    expect(mock.invoke.mock.calls.some(([request]) => request.name === "deleteFolder")).toBe(true);
  });

  it("accepts only not-found as read-based deletion evidence", async () => {
    await expect(
      expectAbsent(async () => {
        throw { status: 403 };
      }),
    ).rejects.toEqual({ status: 403 });
    await expect(
      expectAbsent(async () => {
        throw { status: 404 };
      }),
    ).resolves.toBeUndefined();
  });

  it("rejects an errored receipt", async () => {
    await expect(waitForDeletion(checks, receipt({ error_code: "failure" }))).rejects.toThrow("reported an error");
  });

  it("continues without waiting for retention and verifies the completed receipt on recovery", async () => {
    vi.useFakeTimers();
    const start = Date.now();
    const pending = receipt({ status: "queued", due_at: new Date(start + 60_000).toISOString() });
    mock.invoke.mockImplementation(async () => ({
      ...pending,
      status: Date.now() >= start + 90_000 ? "completed" : "queued",
    }));
    await expect(waitForDeletion(checks, pending)).resolves.toMatchObject({ completed: false });
    expect(mock.invoke).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(90_000);
    const recovered = waitForDeletion(checks, pending);
    await vi.advanceTimersByTimeAsync(2000);
    await expect(recovered).resolves.toMatchObject({ completed: true });
    vi.useRealTimers();
  });

  it("rejects a status receipt for another target", async () => {
    vi.useFakeTimers();
    mock.invoke.mockResolvedValue(receipt({ target_id: "different" }));
    const outcome = waitForDeletion(checks, receipt({ status: "queued" }));
    const assertion = expect(outcome).rejects.toThrow("identity changed");
    await vi.advanceTimersByTimeAsync(2000);
    await assertion;
    vi.useRealTimers();
  });
});

it.each(["disabled", "accepted", "wrong-reason"])("checks agent admission and restoration: %s", async (behavior) => {
  let deleted = false;
  const agent = {
    agent_instance_id: "agent",
    source_agent_id: "generic",
    template_id: "template",
    logical_name: "logical",
    display_name: "label",
    tuning_field_values: {},
    status: "enabled",
  };
  mock.invoke.mockImplementation(
    async ({ name, args }: { name: string; args?: { updateAgentInstanceRequest?: object } }) => {
      if (name === "authorizeSpace") return { allowed: true };
      if (name === "spaceAgentTemplates")
        return [
          {
            source_agent_id: "generic",
            template_id: "template",
            team_instantiable: true,
            status: "available",
            default_tuning_fields: [],
          },
        ];
      if (name === "createAgentInstance") return agent;
      if (name === "updateAgentInstance") {
        Object.assign(agent, args?.updateAgentInstanceRequest);
        return agent;
      }
      if (name === "getAgentInstance") {
        if (deleted) throw { status: 404 };
        return agent;
      }
      if (name === "prepareExecution") {
        if (agent.status === "disabled" && behavior !== "accepted")
          throw { status: 409, data: { code: behavior === "disabled" ? "agent_instance_disabled" : "other" } };
        return { agent_instance_id: "agent", space_id: "space" };
      }
      if (name === "listAgentInstances") return { items: deleted ? [] : [agent] };
      if (name === "deleteAgentInstance") {
        deleted = true;
        return undefined;
      }
      throw new Error("Unexpected request");
    },
  );
  const reports: StepReport[] = [];
  await agents(checks, (step) => reports.push(step), new AbortController().signal);
  expect(reports).toEqual(
    expect.arrayContaining([
      expect.objectContaining({ id: "agents.update", status: "passed" }),
      expect.objectContaining({ id: "agents.status", status: behavior === "disabled" ? "passed" : "failed" }),
      expect.objectContaining({ id: "runtime-echo", status: "skipped", optional: false }),
      expect.objectContaining({ id: "agents.cleanup", status: "passed" }),
    ]),
  );
  expect(agent.status).toBe("enabled");
  expect(mock.echo).not.toHaveBeenCalled();
});

describe("tabular diagnostic fixture", () => {
  for (const extension of ["csv", "xlsx"] as const)
    it(`accepts published ${extension} rows without vector content`, async () => {
      fixtureApi({ tabularRows: 2 });
      const format = tabularFixtures("token").find((item) => item.id === extension)!;
      const file = await format.build();
      const fixture = await ingestKnowledgeFixture(checks, new AbortController().signal, {
        file,
        marker: format.marker,
        tabular: true,
      });
      expect(fixture.text).toBe(format.marker);
      expect(mock.runImport.mock.calls[0][2][0].file).toBe(file);
      await fixture.cleanup();
    });

  it("does not provision or upload when the tabular capability is not permitted", async () => {
    mock.invoke.mockImplementation(async ({ name }: { name: string }) => {
      if (name === "authorizeSpace") return { allowed: true };
      if (name === "spaceAgentTemplates")
        return [
          {
            template_id: "template",
            source_agent_id: "fred.github.test_assistant",
            source_runtime_id: "runtime",
            status: "available",
            team_instantiable: true,
          },
        ];
      if (name === "spaceCapabilityPolicies")
        return [
          {
            runtime_id: "runtime",
            source_enabled: true,
            reachable: true,
            offers: [{ capability_id: "mcp-knowledge-flow-mcp-tabular", advertised: true, permitted: false }],
          },
        ];
      throw new Error("A denied capability must not create resources");
    });
    await expect(
      provisionDisposableAgent(checks, new AbortController().signal, "tabular", "fred.github.test_assistant", [
        "mcp-knowledge-flow-mcp-tabular",
      ]),
    ).rejects.toThrow("tabular SQL capability");
    expect(
      mock.invoke.mock.calls.some(([request]) =>
        ["createAgentInstance", "createFolder", "upload"].includes(request.name),
      ),
    ).toBe(false);
  });

  it("selects only the authorized tabular capability on the diagnostic agent", async () => {
    mock.invoke.mockImplementation(async ({ name, args }: { name: string; args?: unknown }) => {
      if (name === "authorizeSpace") return { allowed: true };
      if (name === "spaceAgentTemplates")
        return [
          {
            template_id: "template",
            source_agent_id: "fred.github.test_assistant",
            source_runtime_id: "runtime",
            status: "available",
            team_instantiable: true,
            available_capabilities: [{ id: "managed-mcp:central-tabular", mcp_service: "knowledge_flow_tabular" }],
          },
        ];
      if (name === "spaceCapabilityPolicies")
        return [
          {
            source_id: "$mcp",
            origin: "managed_mcp",
            source_enabled: true,
            reachable: true,
            offers: [{ capability_id: "managed-mcp:central-tabular", advertised: true, permitted: true }],
          },
        ];
      if (name === "createAgentInstance") return args;
      throw new Error("Unexpected operation");
    });
    const value = await provisionDisposableAgent(
      checks,
      new AbortController().signal,
      "tabular",
      "fred.github.test_assistant",
      ["mcp-knowledge-flow-mcp-tabular"],
    );
    expect(value).toMatchObject({ createAgentInstanceRequest: { capability_ids: ["managed-mcp:central-tabular"] } });
  });
});

describe("selected resource scope", () => {
  it.each(["organization", "team", "project", "personal"] as const)(
    "skips prompt writes without write access in a selected %s",
    async (spaceKind) => {
      const reports: StepReport[] = [];
      mock.invoke.mockImplementation(async ({ name }) =>
        name === "authorizeSpace" ? { allowed: false } : { items: [] },
      );
      await prompts({ ...checks, spaceKind }, (step) => reports.push(step), new AbortController().signal);
      expect(reports).toContainEqual(expect.objectContaining({ id: "prompt-space", status: "skipped" }));
      expect(mock.invoke.mock.calls.map(([request]) => request.name)).toEqual(
        spaceKind === "organization" ? ["marketplaceEntries", "authorizeSpace", "authorizeSpace"] : ["authorizeSpace"],
      );
      if (spaceKind === "organization")
        expect(reports).toContainEqual(expect.objectContaining({ id: "prompts.publicationCreate", status: "skipped" }));
    },
  );
  it("skips organization agent provisioning before sending requests", async () => {
    await expect(
      provisionDisposableAgent({ ...checks, spaceKind: "organization" }, new AbortController().signal, "agent"),
    ).rejects.toThrow("team, project or personal");
    expect(mock.invoke).not.toHaveBeenCalled();
  });
  it.each(["team", "personal", "project"] as const)(
    "provisions agents in the selected supported %s",
    async (spaceKind) => {
      mock.invoke.mockImplementation(async ({ name, args }) => {
        if (name === "authorizeSpace") return { allowed: true };
        if (name === "spaceAgentTemplates")
          return [
            { template_id: "template", source_agent_id: "generic", team_instantiable: true, status: "available" },
          ];
        if (name === "createAgentInstance") return args;
        throw new Error("Unexpected request");
      });
      await expect(
        provisionDisposableAgent({ ...checks, spaceKind }, new AbortController().signal, "agent"),
      ).resolves.toMatchObject({ spaceId: checks.spaceId });
    },
  );
});

describe("run-scoped fixture reporting", () => {
  const uploadId = "knowledge.ingest";

  function reportedFixture(reports: StepReport[]) {
    return ingestKnowledgeFixture(checks, new AbortController().signal, undefined, {
      report: (step: StepReport) => reports.push(step),
      id: uploadId,
      title: "Upload and index a disposable document",
    });
  }

  function finalSteps(reports: StepReport[]) {
    const finished = reports.filter((step) => step.status !== "running");
    expect(new Set(finished.map((step) => step.id)).size).toBe(finished.length);
    return finished;
  }

  it("starts a fresh upload despite stale browser cleanup records", async () => {
    fixtureApi();
    localStorage.setItem("selftest-weaver-folder:actor:space:knowledge", "old unresolved cleanup");
    const reports: StepReport[] = [];
    const fixture = await reportedFixture(reports);
    expect(finalSteps(reports)).toEqual([expect.objectContaining({ id: uploadId, status: "passed" })]);
    expect(mock.runImport).toHaveBeenCalledTimes(1);
    await fixture!.cleanup();
  });

  it("reports a fresh upload failure once without a previous-cleanup step", async () => {
    fixtureApi();
    const respond = mock.invoke.getMockImplementation()!;
    mock.invoke.mockImplementation(async (request: { name: string; args?: { parentId?: string } }) =>
      request.name === "entries" && request.args?.parentId ? { items: [], total: 0 } : respond(request),
    );
    mock.runImport.mockRejectedValueOnce(new Error("Fresh upload failed."));
    const reports: StepReport[] = [];
    await expect(reportedFixture(reports)).resolves.toBeNull();
    expect(finalSteps(reports)).toEqual([
      expect.objectContaining({ id: uploadId, status: "failed", error: "Fresh upload failed." }),
    ]);
    expect(mock.runImport).toHaveBeenCalledTimes(1);
  });

  it("reports a successful fresh upload once without inventing previous cleanup", async () => {
    fixtureApi();
    const reports: StepReport[] = [];
    const fixture = await reportedFixture(reports);
    expect(finalSteps(reports)).toEqual([expect.objectContaining({ id: uploadId, status: "passed" })]);
    expect(mock.runImport).toHaveBeenCalledTimes(1);
    await fixture!.cleanup();
  });
});
