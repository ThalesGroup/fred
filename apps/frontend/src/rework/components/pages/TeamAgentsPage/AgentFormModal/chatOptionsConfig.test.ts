import { describe, expect, it } from "vitest";
import type { ManagedMcpServerRef } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { CHAT_OPTION_FIELD_KEYS, sanitizeMcpConfigValuesForTemplate } from "./chatOptionsConfig";

function makeServer(
  id: string,
  keys: string[],
): ManagedMcpServerRef {
  return {
    id,
    require_tools: [],
    config_fields: keys.map((key) => ({
      key,
      title: key,
      type: "boolean",
      required: false,
    })),
  } as ManagedMcpServerRef;
}

describe("sanitizeMcpConfigValuesForTemplate", () => {
  it("removes undeclared keys and empty server entries", () => {
    expect(
      sanitizeMcpConfigValuesForTemplate(
        {
          "mcp-knowledge-flow-mcp-text": {
            [CHAT_OPTION_FIELD_KEYS.librariesBinding]: true,
            [CHAT_OPTION_FIELD_KEYS.librariesSelection]: false,
          },
          "stale-server": {
            [CHAT_OPTION_FIELD_KEYS.searchPolicyEnabled]: true,
          },
        },
        [makeServer("mcp-knowledge-flow-mcp-text", [CHAT_OPTION_FIELD_KEYS.librariesSelection])],
      ),
    ).toEqual({
      "mcp-knowledge-flow-mcp-text": {
        [CHAT_OPTION_FIELD_KEYS.librariesSelection]: false,
      },
    });
  });

  it("preserves declared keys for each server", () => {
    expect(
      sanitizeMcpConfigValuesForTemplate(
        {
          "mcp-knowledge-flow-mcp-text": {
            [CHAT_OPTION_FIELD_KEYS.searchPolicyEnabled]: true,
            [CHAT_OPTION_FIELD_KEYS.searchPolicy]: "hybrid",
          },
        },
        [
          makeServer("mcp-knowledge-flow-mcp-text", [
            CHAT_OPTION_FIELD_KEYS.searchPolicyEnabled,
            CHAT_OPTION_FIELD_KEYS.searchPolicy,
          ]),
        ],
      ),
    ).toEqual({
      "mcp-knowledge-flow-mcp-text": {
        [CHAT_OPTION_FIELD_KEYS.searchPolicyEnabled]: true,
        [CHAT_OPTION_FIELD_KEYS.searchPolicy]: "hybrid",
      },
    });
  });
});
