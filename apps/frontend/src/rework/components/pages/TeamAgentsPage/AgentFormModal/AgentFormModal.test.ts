import { describe, expect, it } from "vitest";
import type {
  AgentTemplateSummary,
  ManagedAgentInstanceSummary,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { buildAgentFormSubmitPayload, extractCapabilityConfigValues } from "./AgentFormModal";

function makeCapabilityTemplate(capabilityIds: string[]): AgentTemplateSummary {
  return {
    template_id: "runtime:agent",
    display_name: "Agent",
    available_capabilities: capabilityIds.map((id) => ({
      id,
      version: "1",
      name: id,
      description: id,
      icon: "extension",
      config_fields: [{ key: "tone", title: "Tone", type: "string" }],
    })),
  } as AgentTemplateSummary;
}

const EMPTY_CAPABILITY_STATE = {
  selectedCapabilityIds: [] as string[],
  capabilityConfigValues: {} as Record<string, Record<string, unknown>>,
  capabilityAssetFiles: {} as Record<string, Record<string, File | undefined>>,
  capabilityBlockingErrors: {} as Record<string, string | null>,
};

describe("buildAgentFormSubmitPayload", () => {
  it("trims display name, role, and description on create submit", () => {
    const payload = buildAgentFormSubmitPayload(
      {
        templateId: "runtime:agent",
        displayName: "  DT Aegis  ",
        role: "  Guardian  ",
        description: "  Guardrails  ",
        tuningValues: {},
        ...EMPTY_CAPABILITY_STATE,
      },
      makeCapabilityTemplate([]),
    );

    expect(payload).toMatchObject({
      displayName: "DT Aegis",
      role: "Guardian",
      description: "Guardrails",
    });
  });

  it("flags templateHasCapabilities false and empties capability selection for capability-less templates", () => {
    const payload = buildAgentFormSubmitPayload(
      {
        templateId: "runtime:agent",
        displayName: "Agent",
        role: "",
        description: "",
        tuningValues: {},
        ...EMPTY_CAPABILITY_STATE,
        selectedCapabilityIds: ["ghost-cap"],
        capabilityConfigValues: { "ghost-cap": { tone: "warm" } },
      },
      makeCapabilityTemplate([]),
    );

    expect(payload.templateHasCapabilities).toBe(false);
    expect(payload.selectedCapabilityIds).toEqual([]);
    expect(payload.capabilityConfigValues).toEqual({});
  });

  it("keeps config only for selected, template-advertised capabilities", () => {
    const payload = buildAgentFormSubmitPayload(
      {
        templateId: "runtime:agent",
        displayName: "Agent",
        role: "",
        description: "",
        tuningValues: {},
        ...EMPTY_CAPABILITY_STATE,
        // "gone" is not advertised; "unselected" is advertised but not ticked.
        selectedCapabilityIds: ["ppt-filler", "gone"],
        capabilityConfigValues: {
          "ppt-filler": { tone: "formal" },
          unselected: { tone: "casual" },
          gone: { tone: "warm" },
        },
      },
      makeCapabilityTemplate(["ppt-filler", "unselected"]),
    );

    expect(payload.templateHasCapabilities).toBe(true);
    expect(payload.selectedCapabilityIds).toEqual(["ppt-filler"]);
    expect(payload.capabilityConfigValues).toEqual({ "ppt-filler": { tone: "formal" } });
  });

  it("keeps MCP capabilities like any other capability (#1988 — MCP capability ids are plain catalog server ids)", () => {
    const payload = buildAgentFormSubmitPayload(
      {
        templateId: "runtime:agent",
        displayName: "Agent",
        role: "",
        description: "",
        tuningValues: {},
        ...EMPTY_CAPABILITY_STATE,
        selectedCapabilityIds: ["knowledge-flow-mcp-text"],
        capabilityConfigValues: {
          "knowledge-flow-mcp-text": { "chat_options.libraries_binding": true },
        },
      },
      makeCapabilityTemplate(["knowledge-flow-mcp-text"]),
    );

    expect(payload.templateHasCapabilities).toBe(true);
    expect(payload.selectedCapabilityIds).toEqual(["knowledge-flow-mcp-text"]);
    expect(payload.capabilityConfigValues).toEqual({
      "knowledge-flow-mcp-text": { "chat_options.libraries_binding": true },
    });
  });
});

describe("extractCapabilityConfigValues", () => {
  it("unwraps the stored {schema_version, config} envelope into flat config", () => {
    const stored: ManagedAgentInstanceSummary["capability_config"] = {
      "ppt-filler": { schema_version: "1", config: { tone: "formal", slides: 12 } },
      empty: { schema_version: "1", config: {} },
    };

    expect(extractCapabilityConfigValues(stored)).toEqual({
      "ppt-filler": { tone: "formal", slides: 12 },
      empty: {},
    });
  });

  it("returns an empty object when no capability config is stored", () => {
    expect(extractCapabilityConfigValues(undefined)).toEqual({});
  });
});
