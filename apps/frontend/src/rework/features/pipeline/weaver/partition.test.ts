// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { WeaverChecks } from "./checks";
import type { StepReport } from "../types";
const mock = vi.hoisted(() => ({ invoke: vi.fn(), fixture: vi.fn(), provision: vi.fn(), baseline: vi.fn() }));
const endpoints = vi.hoisted(
  () => new Proxy({}, { get: (_target, name) => ({ initiate: (args: unknown) => ({ name, args }) }) }),
);
vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  enhancedControlPlaneApi: { endpoints },
}));
vi.mock("./resourceSupport", () => ({
  cp: endpoints,
  assert: (condition: unknown, message: string) => {
    if (!condition) throw new Error(message);
  },
  requireSpace: () => {},
  requireWrite: vi.fn().mockResolvedValue(undefined),
  ingestKnowledgeFixture: mock.fixture,
  provisionDisposableAgent: mock.provision,
}));
vi.mock("../deps/security", () => ({ browserSecurity: () => ({}) }));
vi.mock("../scenarios/securityScenario", () => ({
  runSecurityBaseline: mock.baseline,
  runsActiveContent: () => false,
}));
vi.mock("../../../../security/KeycloakService", () => ({
  KeyCloakService: { ensureFreshToken: vi.fn(async () => true), GetToken: () => "session.payload.signature" },
}));
vi.mock("../useAuthzProbeRun", () => ({
  authedFetch: vi.fn(async (path: string, token?: string) => {
    if (token !== "session.payload.signature") return { status: 401 };
    if (path.endsWith("/me")) return { status: 200, body: { user_id: "operator", platform_roles: [] } };
    return { status: 403 };
  }),
}));
import { weaverScenarios, type WeaverLevel } from "./useWeaverFamilies";
import {
  sharedPlatform,
  organizationCatalogs,
  sharedSecurity,
  documentSecurity,
  sharedObservability,
  spaceObservability,
} from "./platformChecks";
import { sharedAuthorization, spaceAuthorization } from "./authorization";
import { teams } from "./resourceScenarios";
import { authedFetch } from "../useAuthzProbeRun";
import { KeyCloakService } from "../../../../security/KeycloakService";
const context = (level: WeaverLevel) =>
  ({
    userId: "operator",
    spaceId: level,
    spaceKind: level,
    organizationId: "organization",
    dispatch: (request: unknown) => ({ unwrap: () => mock.invoke(request) }),
    read: (endpoint: { initiate: (args: unknown) => unknown }, args: unknown) => mock.invoke(endpoint.initiate(args)),
  }) as unknown as WeaverChecks;
async function run(level: WeaverLevel, id: keyof ReturnType<typeof weaverScenarios>, checks = context(level)) {
  const reports: StepReport[] = [];
  await weaverScenarios(level)[id]!(checks, (step) => reports.push(step), new AbortController().signal);
  return reports.filter((step) => step.status !== "running");
}
beforeEach(() => {
  vi.clearAllMocks();
  mock.invoke.mockResolvedValue([]);
});
describe("path scenario ownership", () => {
  it("splits all mixed families at operation boundaries", () => {
    expect(weaverScenarios("shared")).toMatchObject({
      platform: sharedPlatform,
      security: sharedSecurity,
      observability: sharedObservability,
      authorization: sharedAuthorization,
    });
    expect(weaverScenarios("organization")).toMatchObject({ platform: organizationCatalogs, teams });
    for (const level of ["organization", "team", "project", "personal"] as const)
      expect(weaverScenarios(level)).toMatchObject({
        security: documentSecurity,
        observability: spaceObservability,
        authorization: spaceAuthorization,
      });
    for (const level of ["team", "project", "personal"] as const) {
      expect(weaverScenarios(level)).not.toHaveProperty("platform");
      expect(weaverScenarios(level)).not.toHaveProperty("teams");
      expect(weaverScenarios(level)).not.toHaveProperty("identity");
    }
    expect(Object.keys(weaverScenarios("shared"))).toHaveLength(5);
  });
  it.each([
    {
      inventory: [
        {
          runtime_id: "first",
          capabilities: [
            { capability_id: "shared", advertised: true },
            { capability_id: "second", advertised: true },
            { capability_id: "retired", advertised: false },
          ],
        },
        {
          runtime_id: "other",
          capabilities: [
            { capability_id: "shared", advertised: true },
            { capability_id: "withdrawn", advertised: false },
          ],
        },
      ],
      detail: "2 agents, 5 capability offers (3 advertised), 4 model sources.",
    },
    { inventory: [], detail: "2 agents, 0 capability offers (0 advertised), 4 model sources." },
  ])("counts capability offers within runtime inventories: $detail", async ({ inventory, detail }) => {
    mock.invoke.mockImplementation(async ({ name }) => {
      if (name === "organizationAgents") return [{}, {}];
      if (name === "organizationCapabilities") return inventory;
      if (name === "organizationModels") return { sources: [{}, {}, {}, {}] };
      throw new Error("Unexpected catalog request");
    });
    expect(await run("organization", "platform")).toEqual([
      expect.objectContaining({ id: "catalogs", status: "passed", detail }),
    ]);
  });
  it("never accesses selected scope in shared security and authorization", async () => {
    const checks = { userId: "operator" } as WeaverChecks;
    for (const name of ["spaceId", "spaceKind", "organizationId"])
      Object.defineProperty(checks, name, {
        get: () => {
          throw new Error("Selected scope accessed");
        },
      });
    for (const id of ["security", "authorization"] as const)
      expect((await run("shared", id, checks)).some((step) => step.status === "failed")).toBe(false);
    expect(mock.fixture).not.toHaveBeenCalled();
    expect(
      vi
        .mocked(authedFetch)
        .mock.calls.some(([path]) => path.includes("/entries") || path.includes("/authorize/space")),
    ).toBe(false);
  });
  it("runs the shared prompt management scenario in every space and reads the marketplace only at the organization level", async () => {
    mock.invoke.mockImplementation(async ({ name }) => {
      if (name === "marketplaceEntries") return { items: [{ id: "published" }] };
      if (name === "createPromptCategory") throw new Error("Fixture creation stopped");
      throw new Error("Unexpected prompt request");
    });
    for (const level of ["organization", "team", "project", "personal"] as const) {
      const reports = await run(level, "prompts");
      expect(reports).toContainEqual(expect.objectContaining({ id: "prompt-space", status: "passed" }));
      expect(mock.invoke).toHaveBeenCalledWith({
        name: "createPromptCategory",
        args: { spaceId: level, promptCategoryRequest: { name: expect.any(String) } },
      });
    }
    expect(mock.invoke.mock.calls.filter(([request]) => request.name === "marketplaceEntries")).toEqual([
      [{ name: "marketplaceEntries", args: { marketplaceSpaceId: "organization", kind: "prompt" } }],
    ]);
  });
  it("makes no requests for unsupported organization runtime families", async () => {
    for (const id of ["agents", "conversations", "web"] as const)
      expect(await run("organization", id)).toEqual([
        expect.objectContaining({ status: "skipped", detail: expect.stringContaining("organization level") }),
      ]);
    expect(mock.invoke).not.toHaveBeenCalled();
    expect(mock.provision).not.toHaveBeenCalled();
  });
  it("reports organization retrieval and tabular limits even when upload fails", async () => {
    const { runStep } = await import("../step");
    mock.fixture.mockImplementation(
      async (
        _checks,
        _signal,
        _input,
        reporting: {
          report: (step: StepReport) => void;
          id: string;
          title: string;
        },
      ) =>
        runStep(reporting.report, reporting.id, reporting.title, async () => {
          throw new Error("Fixture failed");
        }),
    );
    const reports = await run("organization", "knowledge");
    expect(reports).toContainEqual(
      expect.objectContaining({ id: "knowledge.ingest", status: "failed", error: "Fixture failed" }),
    );
    for (const id of ["runtime-retrieval", "knowledge.sql.csv", "knowledge.sql.xlsx"])
      expect(reports).toContainEqual(
        expect.objectContaining({ id, status: "skipped", detail: expect.stringContaining("organization level") }),
      );
    expect(mock.provision).not.toHaveBeenCalled();
  });
  it("does not query space usage for organization or personal levels", async () => {
    for (const level of ["organization", "personal"] as const)
      expect(await run(level, "observability")).toEqual([
        expect.objectContaining({ id: "space-usage", status: "skipped" }),
      ]);
    expect(mock.invoke).not.toHaveBeenCalled();
  });
  it("queries team and project usage with each selected space", async () => {
    mock.invoke.mockImplementation(async ({ name }) =>
      name === "authorizeSpace"
        ? { allowed: true }
        : {
            totals: { turns: 0, input_tokens: 0, output_tokens: 0, cache_read_tokens: 0, cache_creation_tokens: 0 },
            series: [],
            by_agent: [],
            by_model: [],
            since: "2026-01-01T00:00:00Z",
            until: "2026-01-02T00:00:00Z",
            interval: "day",
          },
    );
    for (const level of ["team", "project"] as const) {
      expect(await run(level, "observability")).toEqual([
        expect.objectContaining({ id: "space-usage", status: "passed" }),
      ]);
      expect(mock.invoke).toHaveBeenCalledWith(
        expect.objectContaining({ name: "spaceUsage", args: expect.objectContaining({ spaceId: level }) }),
      );
    }
  });
  it("checks only selected content authorization at every scope level", async () => {
    vi.mocked(authedFetch).mockImplementation(async (path) => {
      if (path.endsWith("/authorize/space")) return { status: 200, body: { allowed: true } };
      return { status: 200, body: null };
    });
    for (const level of ["organization", "team", "project", "personal"] as const) {
      const reports = await run(level, "authorization");
      expect(reports).toEqual([expect.objectContaining({ id: "authorization-selected-space", status: "passed" })]);
      expect(authedFetch).toHaveBeenCalledWith(
        `/control-plane/v1/spaces/${level}/entries`,
        "session.payload.signature",
      );
    }
    expect(authedFetch).toHaveBeenCalledTimes(8);
    expect(KeyCloakService.ensureFreshToken).toHaveBeenCalledTimes(4);
  });
  it("does not query scoped authorization when the session cannot be refreshed", async () => {
    vi.mocked(KeyCloakService.ensureFreshToken).mockResolvedValueOnce(false);
    expect(await run("team", "authorization")).toEqual([
      expect.objectContaining({ status: "failed", error: expect.stringContaining("Sign in again") }),
    ]);
    expect(authedFetch).not.toHaveBeenCalled();
  });
});

it.each(["valid", "negative", "mismatch", "duplicate", "invalid-date"])(
  "validates usage evidence: %s",
  async (mode) => {
    const totals = { turns: 1, input_tokens: 10, output_tokens: 2, cache_read_tokens: 0, cache_creation_tokens: 0 };
    const point = { ...totals, start: "2026-01-01T00:00:00Z" };
    const usage = {
      totals,
      series: [point],
      by_agent: [],
      by_model: [],
      since: point.start,
      until: "2026-01-02T00:00:00Z",
      interval: "day",
    };
    if (mode === "negative") totals.input_tokens = -1;
    if (mode === "mismatch") totals.turns = 2;
    if (mode === "duplicate") usage.series.push({ ...point });
    if (mode === "invalid-date") usage.until = "invalid";
    mock.invoke.mockImplementation(async ({ name }) => (name === "authorizeSpace" ? { allowed: true } : usage));
    const results = await run("team", "observability");
    expect(results).toContainEqual(
      expect.objectContaining({ id: "space-usage", status: mode === "valid" ? "passed" : "failed" }),
    );
  },
);

it.each(["ready", "degraded", "unknown", "updating"])(
  "checks workload state instead of snapshot presence: %s",
  async (state) => {
    mock.invoke.mockResolvedValue({
      observed_at: "2026-01-01T00:00:00Z",
      services: [{ desired: 1, ready: state === "ready" ? 1 : 0, state }],
      unavailable_sources: [],
      truncated_sources: [],
    });
    const steps: StepReport[] = [];
    await sharedObservability(context("team"), (step) => steps.push(step), new AbortController().signal);
    expect(steps).toContainEqual(
      expect.objectContaining({ id: "technical-status", status: state === "ready" ? "passed" : "failed" }),
    );
  },
);
