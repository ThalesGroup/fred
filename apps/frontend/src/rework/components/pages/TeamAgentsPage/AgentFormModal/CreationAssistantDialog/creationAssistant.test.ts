// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { describe, expect, it } from "vitest";
import type {
  CapabilityCatalogEntry,
  ManagedAgentFieldSpec,
} from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import { derivePackChecked } from "../toolPackLogic";
import {
  CAP_DOCUMENT_ACCESS,
  CAP_DOCUMENT_SIMILARITY,
  CAP_HTML_ARTIFACT,
  CAP_TEAM_WIKI,
  CAP_WRITABLE_DOCUMENT,
  DOC_ACCESS_ATTACHMENTS,
  DOC_ACCESS_TEAM_DOCUMENTS,
  TOOL_PACK_SECTIONS,
} from "../toolPacks";
import type { AgentDraftResult } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  applyRecommendedCapabilities,
  availableRecommendedIds,
  buildAgentDraftRequest,
  findSystemPromptField,
  agentDraftErrorKey,
  isReasoningOffered,
  offeredDraftItems,
  overwrittenItems,
  REASONING_LABEL_KEY,
  selectedDraft,
} from "./creationAssistant";

const field = (key: string, type: string) => ({ key, type, title: key }) as unknown as ManagedAgentFieldSpec;
const capability = (id: string) =>
  ({ id, name: `capability.${id}.name`, description: `capability.${id}.description` }) as CapabilityCatalogEntry;

describe("findSystemPromptField", () => {
  it("prefers prompts.system over an earlier prompt field", () => {
    const fields = [field("prompts.extra", "prompt"), field("prompts.system", "prompt")];
    expect(findSystemPromptField(fields)?.key).toBe("prompts.system");
  });

  it("falls back to the first prompt-typed field and ignores other types", () => {
    const fields = [field("prompts.note", "text-multiline"), field("prompts.custom", "prompt")];
    expect(findSystemPromptField(fields)?.key).toBe("prompts.custom");
    expect(findSystemPromptField([field("prompts.note", "text-multiline")])).toBeUndefined();
  });
});

describe("buildAgentDraftRequest", () => {
  it("sends translated capability names, the base language and trimmed identity", () => {
    const request = buildAgentDraftRequest({
      description: "  Answers HR questions  ",
      language: "fr-FR",
      agentName: " RH ",
      agentRole: "",
      capabilities: [capability(CAP_TEAM_WIKI)],
      translate: (key) => `T(${key})`,
    });
    expect(request).toEqual({
      description: "Answers HR questions",
      language: "fr",
      agent_name: "RH",
      agent_role: null,
      capabilities: [
        {
          id: CAP_TEAM_WIKI,
          name: "T(capability.team_wiki.name)",
          description: "T(capability.team_wiki.description)",
        },
      ],
    });
  });
});

describe("availableRecommendedIds", () => {
  it("drops unavailable ids and duplicates, keeping the model's order", () => {
    const available = new Set([CAP_HTML_ARTIFACT, CAP_TEAM_WIKI]);
    expect(availableRecommendedIds([CAP_TEAM_WIKI, "ghost", CAP_HTML_ARTIFACT, CAP_TEAM_WIKI], available)).toEqual([
      CAP_TEAM_WIKI,
      CAP_HTML_ARTIFACT,
    ]);
  });
});

describe("applyRecommendedCapabilities", () => {
  const state = {
    selectedCapabilityIds: [CAP_WRITABLE_DOCUMENT],
    capabilityConfigValues: { [CAP_TEAM_WIKI]: { mode: "read_write" } },
    reasoningEnabled: true,
  };

  it("replaces the selection and keeps reasoning and existing settings", () => {
    const available = new Set([CAP_WRITABLE_DOCUMENT, CAP_TEAM_WIKI, CAP_HTML_ARTIFACT]);
    const next = applyRecommendedCapabilities([CAP_TEAM_WIKI, "ghost"], state, available);
    expect(next.selectedCapabilityIds).toEqual([CAP_TEAM_WIKI]);
    expect(next.reasoningEnabled).toBe(true);
    expect(next.capabilityConfigValues).toEqual(state.capabilityConfigValues);
  });

  it("turns document access on through both document packs", () => {
    const available = new Set([CAP_DOCUMENT_ACCESS, CAP_DOCUMENT_SIMILARITY, CAP_TEAM_WIKI]);
    const withSourceOff = {
      ...state,
      capabilityConfigValues: {
        ...state.capabilityConfigValues,
        [CAP_DOCUMENT_ACCESS]: { [DOC_ACCESS_ATTACHMENTS]: false },
      },
    };
    const next = applyRecommendedCapabilities([CAP_DOCUMENT_ACCESS], withSourceOff, available);
    expect(next.selectedCapabilityIds).toEqual(expect.arrayContaining([CAP_DOCUMENT_ACCESS, CAP_DOCUMENT_SIMILARITY]));
    expect(next.selectedCapabilityIds).not.toContain(CAP_TEAM_WIKI);
    expect(next.capabilityConfigValues[CAP_DOCUMENT_ACCESS]).toMatchObject({
      [DOC_ACCESS_ATTACHMENTS]: true,
      [DOC_ACCESS_TEAM_DOCUMENTS]: true,
    });
    const documentPacks = TOOL_PACK_SECTIONS.flatMap((section) => section.packs).filter((pack) => pack.documentSource);
    expect(documentPacks).toHaveLength(2);
    for (const pack of documentPacks) expect(derivePackChecked(pack, next, available)).toBe(true);
  });

  it("leaves document access off when the team may not use it", () => {
    const next = applyRecommendedCapabilities([CAP_DOCUMENT_ACCESS], state, new Set([CAP_TEAM_WIKI]));
    expect(next.selectedCapabilityIds).toEqual([]);
  });
});

describe("agentDraftErrorKey", () => {
  it.each([
    [{ status: 403 }, "forbidden"],
    [{ status: 501 }, "unsupported"],
    [{ status: 404 }, "unsupported"],
    [{ status: 504 }, "timeout"],
    [{ status: "TIMEOUT_ERROR" }, "timeout"],
    [{ status: 503 }, "unavailable"],
    [{ status: "FETCH_ERROR" }, "unavailable"],
    [{ status: 422 }, "invalid"],
    [{ status: 502 }, "failed"],
    [new Error("boom"), "failed"],
  ])("maps %o to %s", (error, suffix) => {
    expect(agentDraftErrorKey(error)).toBe(`rework.teams.formAgent.creationAssistant.errors.${suffix}`);
  });
});

const DRAFT: AgentDraftResult = {
  name: "HR helper",
  role: "Answers HR questions",
  description: null,
  system_prompt: "You answer HR questions.",
  capability_ids: ["team_wiki"],
};
const EMPTY = {
  systemPrompt: "",
  name: "",
  role: "",
  description: "",
  capabilityIds: [],
  capabilityConfigValues: {},
};
const AVAILABLE = new Set([CAP_TEAM_WIKI, CAP_HTML_ARTIFACT, CAP_DOCUMENT_ACCESS, CAP_DOCUMENT_SIMILARITY]);

describe("draft selection", () => {
  it("offers non-empty values only, and the prompt only with a prompt field", () => {
    expect(offeredDraftItems(DRAFT, true)).toEqual(["systemPrompt", "name", "role"]);
    expect(offeredDraftItems(DRAFT, false)).toEqual(["name", "role"]);
  });

  it("applies ticked items only, and capabilities only when one is ticked", () => {
    expect(selectedDraft(DRAFT, new Set(["name", "systemPrompt"]), [])).toEqual({
      name: "HR helper",
      systemPrompt: "You answer HR questions.",
    });
    expect(selectedDraft(DRAFT, new Set(["description"]), ["team_wiki"])).toEqual({ capabilityIds: ["team_wiki"] });
  });

  it("lists only ticked items that replace a different, non-empty value", () => {
    const draft = { name: "HR helper", role: "Answers HR questions", capabilityIds: ["team_wiki"] };
    expect(overwrittenItems(draft, EMPTY, AVAILABLE)).toEqual([]);
    expect(
      overwrittenItems(
        draft,
        { ...EMPTY, name: "HR helper ", role: "Old role", capabilityIds: ["html_artifact"] },
        AVAILABLE,
      ),
    ).toEqual(["role", "capabilities"]);
    expect(
      overwrittenItems({ name: "X" }, { ...EMPTY, role: "Kept", capabilityIds: ["team_wiki"] }, AVAILABLE),
    ).toEqual([]);
    expect(
      overwrittenItems({ capabilityIds: ["team_wiki"] }, { ...EMPTY, capabilityIds: ["team_wiki"] }, AVAILABLE),
    ).toEqual([]);
  });
});

describe("capability overwrite", () => {
  const draft = { capabilityIds: [CAP_DOCUMENT_ACCESS] };
  const applied = applyRecommendedCapabilities(
    [CAP_DOCUMENT_ACCESS],
    { selectedCapabilityIds: [], capabilityConfigValues: {}, reasoningEnabled: false },
    AVAILABLE,
  );
  const afterFirstApply = {
    ...EMPTY,
    capabilityIds: applied.selectedCapabilityIds,
    capabilityConfigValues: applied.capabilityConfigValues,
  };

  it("does not ask again when re-applying the same draft", () => {
    // The form holds what Apply wrote (both document packs), not the ticked id alone.
    expect(afterFirstApply.capabilityIds.length).toBeGreaterThan(1);
    expect(overwrittenItems(draft, afterFirstApply, AVAILABLE)).toEqual([]);
  });

  it("asks when Apply would turn a document source back on", () => {
    const attachmentsOff = {
      ...afterFirstApply,
      capabilityConfigValues: {
        [CAP_DOCUMENT_ACCESS]: { [DOC_ACCESS_ATTACHMENTS]: false, [DOC_ACCESS_TEAM_DOCUMENTS]: true },
      },
    };
    expect(overwrittenItems(draft, attachmentsOff, AVAILABLE)).toEqual(["capabilities"]);
  });
});

describe("reasoning proposal", () => {
  it("follows the Simple view's reasoning pack: offered whatever the team's capabilities, under its title", () => {
    expect(isReasoningOffered(new Set())).toBe(true);
    expect(isReasoningOffered(new Set([CAP_TEAM_WIKI]))).toBe(true);
    expect(REASONING_LABEL_KEY).toBe("rework.teams.formAgent.capabilities.packs.reasoning.title");
  });

  it("is applied only when ticked, and never counts as an overwrite", () => {
    expect(selectedDraft(DRAFT, new Set(), [], true)).toEqual({ reasoning: true });
    expect(selectedDraft(DRAFT, new Set(), [], false)).toEqual({});
    expect(overwrittenItems({ reasoning: true }, { ...EMPTY, capabilityIds: ["team_wiki"] }, AVAILABLE)).toEqual([]);
  });
});
