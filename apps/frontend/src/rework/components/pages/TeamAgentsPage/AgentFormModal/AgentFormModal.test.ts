import { describe, expect, it } from "vitest";
import type {
  AgentTemplateSummary,
  ManagedAgentInstanceSummary,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { buildAgentFormSubmitPayload, extractCapabilityConfigValues } from "./AgentFormModal";
import { CHAT_OPTION_FIELD_KEYS } from "./chatOptionsConfig";

function makeTemplate(configKeys: string[]): AgentTemplateSummary {
  return {
    template_id: "runtime:agent",
    display_name: "Agent",
    mcp_servers: [
      {
        id: "mcp-knowledge-flow-mcp-text",
        require_tools: [],
        config_fields: configKeys.map((key) => ({
          key,
          title: key,
          type: "boolean",
          required: false,
        })),
      },
    ],
  } as AgentTemplateSummary;
}

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
};

describe("buildAgentFormSubmitPayload", () => {
  it("prunes stale undeclared MCP keys before create submit", () => {
    const payload = buildAgentFormSubmitPayload(
      {
        templateId: "runtime:agent",
        displayName: "  DT Aegis  ",
        description: "  Guardrails  ",
        tuningValues: {},
        selectedMcpServerIds: ["mcp-knowledge-flow-mcp-text"],
        mcpConfigValues: {
          "mcp-knowledge-flow-mcp-text": {
            [CHAT_OPTION_FIELD_KEYS.librariesBinding]: true,
            [CHAT_OPTION_FIELD_KEYS.librariesSelection]: false,
          },
        },
        ...EMPTY_CAPABILITY_STATE,
      },
      makeTemplate([CHAT_OPTION_FIELD_KEYS.librariesSelection]),
    );

    expect(payload).toMatchObject({
      displayName: "DT Aegis",
      description: "Guardrails",
      selectedMcpServerIds: ["mcp-knowledge-flow-mcp-text"],
      mcpConfigValues: {
        "mcp-knowledge-flow-mcp-text": {
          [CHAT_OPTION_FIELD_KEYS.librariesSelection]: false,
        },
      },
    });
    expect(payload.mcpConfigValues["mcp-knowledge-flow-mcp-text"]).not.toHaveProperty(
      CHAT_OPTION_FIELD_KEYS.librariesBinding,
    );
  });

  it("prunes stale undeclared MCP keys before edit submit", () => {
    const payload = buildAgentFormSubmitPayload(
      {
        templateId: "runtime:agent",
        displayName: "Existing Agent",
        description: "",
        tuningValues: {},
        selectedMcpServerIds: ["mcp-knowledge-flow-mcp-text"],
        mcpConfigValues: {
          "mcp-knowledge-flow-mcp-text": {
            [CHAT_OPTION_FIELD_KEYS.librariesBinding]: true,
            [CHAT_OPTION_FIELD_KEYS.boundLibraryIds]: ["lib-1"],
            [CHAT_OPTION_FIELD_KEYS.searchPolicyEnabled]: true,
          },
        },
        ...EMPTY_CAPABILITY_STATE,
      },
      makeTemplate([CHAT_OPTION_FIELD_KEYS.searchPolicyEnabled]),
    );

    expect(payload.mcpConfigValues).toEqual({
      "mcp-knowledge-flow-mcp-text": {
        [CHAT_OPTION_FIELD_KEYS.searchPolicyEnabled]: true,
      },
    });
  });

  it("flags templateHasCapabilities false and empties capability selection for MCP-only templates", () => {
    const payload = buildAgentFormSubmitPayload(
      {
        templateId: "runtime:agent",
        displayName: "Agent",
        description: "",
        tuningValues: {},
        selectedMcpServerIds: [],
        mcpConfigValues: {},
        selectedCapabilityIds: ["ghost-cap"],
        capabilityConfigValues: { "ghost-cap": { tone: "warm" } },
      },
      makeTemplate([]),
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
        description: "",
        tuningValues: {},
        selectedMcpServerIds: [],
        mcpConfigValues: {},
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
