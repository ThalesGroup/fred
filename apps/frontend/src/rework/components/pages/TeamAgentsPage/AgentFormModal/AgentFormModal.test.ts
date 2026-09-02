import { describe, expect, it } from "vitest";
import type {
  AgentTemplateSummary,
  ManagedAgentInstanceSummary,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  buildAgentFormSubmitPayload,
  defaultCapabilitySelection,
  defaultReasoningSelection,
  extractCapabilityConfigValues,
} from "./AgentFormModal";

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

describe("defaultReasoningSelection", () => {
  it("seeds both fields from the template's declared defaults", () => {
    // #2473: platform_ops declares both, so a new instance opens with the
    // Reasoning card ticked and its nested "start in Boost" switch on.
    const template = {
      ...makeCapabilityTemplate([]),
      reasoning_enabled: true,
      reasoning_default_on: true,
    } as AgentTemplateSummary;

    expect(defaultReasoningSelection(template)).toEqual({
      reasoningEnabled: true,
      reasoningDefaultOn: true,
    });
  });

  it("seeds the offer without the default-on switch", () => {
    // The two are independent: a template may offer reasoning while still
    // leaving new conversations starting in Rapide.
    const template = {
      ...makeCapabilityTemplate([]),
      reasoning_enabled: true,
      reasoning_default_on: false,
    } as AgentTemplateSummary;

    expect(defaultReasoningSelection(template)).toEqual({
      reasoningEnabled: true,
      reasoningDefaultOn: false,
    });
  });

  it("defaults to off for a template that declares neither, and for none", () => {
    // The pre-#2473 behaviour, and what an older pod's payload yields — the
    // form must not invent a reasoning offer no template asked for.
    expect(defaultReasoningSelection(makeCapabilityTemplate([]))).toEqual({
      reasoningEnabled: false,
      reasoningDefaultOn: false,
    });
    expect(defaultReasoningSelection(undefined)).toEqual({
      reasoningEnabled: false,
      reasoningDefaultOn: false,
    });
  });
});

describe("defaultCapabilitySelection", () => {
  it("pre-ticks the template's declared defaults", () => {
    const template = {
      ...makeCapabilityTemplate(["platform_postgres", "other_tool"]),
      default_capability_ids: ["platform_postgres"],
    };

    expect(defaultCapabilitySelection(template)).toEqual(["platform_postgres"]);
  });

  it("drops a default the template does not advertise to this team", () => {
    // `available_capabilities` is `can_use`-filtered server-side, so an
    // admin-gated default the team is not enabled for arrives absent from it.
    // It must not be pre-ticked — the save would 403 on an explicit selection.
    const template = {
      ...makeCapabilityTemplate(["other_tool"]),
      default_capability_ids: ["platform_postgres"],
    };

    expect(defaultCapabilitySelection(template)).toEqual([]);
  });

  it("returns nothing for a template declaring no defaults, or no template", () => {
    expect(defaultCapabilitySelection(makeCapabilityTemplate(["other_tool"]))).toEqual([]);
    expect(defaultCapabilitySelection(undefined)).toEqual([]);
  });
});

describe("buildAgentFormSubmitPayload", () => {
  it("trims display name, role, description, and usage statement on create submit", () => {
    const payload = buildAgentFormSubmitPayload(
      {
        templateId: "runtime:agent",
        displayName: "  DT Aegis  ",
        role: "  Guardian  ",
        description: "  Guardrails  ",
        usageStatement: "  Screens inbound requests for policy violations.  ",
        reasoningEnabled: false,
        reasoningDefaultOn: false,
        tuningValues: {},
        ...EMPTY_CAPABILITY_STATE,
      },
      makeCapabilityTemplate([]),
    );

    expect(payload).toMatchObject({
      displayName: "DT Aegis",
      role: "Guardian",
      description: "Guardrails",
      usageStatement: "Screens inbound requests for policy violations.",
      reasoningEnabled: false,
    });
  });

  it("flags templateHasCapabilities false and empties capability selection for capability-less templates", () => {
    const payload = buildAgentFormSubmitPayload(
      {
        templateId: "runtime:agent",
        displayName: "Agent",
        role: "",
        description: "",
        usageStatement: "",
        reasoningEnabled: false,
        reasoningDefaultOn: false,
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
        usageStatement: "",
        reasoningEnabled: false,
        reasoningDefaultOn: false,
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
        usageStatement: "",
        reasoningEnabled: false,
        reasoningDefaultOn: false,
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

  it("carries the reasoning preselection even while the offer is off (REASON-01 Amendment B)", () => {
    // The two reasoning fields are independent on purpose. If the payload
    // builder dropped the preselection whenever the offer was off, an author
    // who toggled the offer off and back on would silently lose their default —
    // the backend keeps the value inert precisely so it survives that round trip.
    const payload = buildAgentFormSubmitPayload(
      {
        templateId: "runtime:agent",
        displayName: "Agent",
        role: "",
        description: "",
        usageStatement: "",
        reasoningEnabled: false,
        reasoningDefaultOn: true,
        tuningValues: {},
        ...EMPTY_CAPABILITY_STATE,
      },
      makeCapabilityTemplate([]),
    );

    expect(payload).toMatchObject({ reasoningEnabled: false, reasoningDefaultOn: true });
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
