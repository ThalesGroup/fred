import { describe, expect, it } from "vitest";
import type { AgentTemplateSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { buildAgentFormSubmitPayload } from "./AgentFormModal";
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
      },
      makeTemplate([CHAT_OPTION_FIELD_KEYS.searchPolicyEnabled]),
    );

    expect(payload.mcpConfigValues).toEqual({
      "mcp-knowledge-flow-mcp-text": {
        [CHAT_OPTION_FIELD_KEYS.searchPolicyEnabled]: true,
      },
    });
  });
});
