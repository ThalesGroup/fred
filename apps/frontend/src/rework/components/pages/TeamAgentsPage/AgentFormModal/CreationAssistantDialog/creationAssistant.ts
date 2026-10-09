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

/** Pure logic of the creation assistant: request building, draft selection and application, error copy. */

import type {
  AgentDraftRequest,
  AgentDraftResult,
  ManagedAgentFieldSpec,
  CapabilityCatalogEntry,
} from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import { applyPackToggle, type CapabilitySelectionState, derivePackChecked, isPackSelectable } from "../toolPackLogic";
import { CAP_DOCUMENT_ACCESS, TOOL_PACK_SECTIONS } from "../toolPacks";

export const DRAFT_DESCRIPTION_MAX_LENGTH = 4000;

const SYSTEM_PROMPT_KEY = "prompts.system";

/** The template's main system-prompt field: `prompts.system`, else its first prompt-typed field. */
export function findSystemPromptField(fields: ManagedAgentFieldSpec[]): ManagedAgentFieldSpec | undefined {
  const promptFields = fields.filter((field) => field.type === "prompt");
  return promptFields.find((field) => field.key === SYSTEM_PROMPT_KEY) ?? promptFields[0];
}

type BuildRequestInput = {
  description: string;
  language: string;
  agentName: string;
  agentRole: string;
  capabilities: CapabilityCatalogEntry[];
  translate: (key: string) => string;
};

/** Names and descriptions are i18n keys: only the client can send them in the user's language. */
export function buildAgentDraftRequest({
  description,
  language,
  agentName,
  agentRole,
  capabilities,
  translate,
}: BuildRequestInput): AgentDraftRequest {
  return {
    description: description.trim(),
    language: language.split("-")[0] || "en",
    agent_name: agentName.trim() || null,
    agent_role: agentRole.trim() || null,
    capabilities: capabilities.map((capability) => ({
      id: capability.id,
      name: translate(capability.name),
      description: capability.description ? translate(capability.description) : "",
    })),
  };
}

/** Recommended ids the template still advertises, deduplicated, in the model's order. */
export function availableRecommendedIds(recommended: string[], availableIds: ReadonlySet<string>): string[] {
  return [...new Set(recommended)].filter((id) => availableIds.has(id));
}

const DOCUMENT_PACKS = TOOL_PACK_SECTIONS.flatMap((section) => section.packs).filter((pack) => pack.documentSource);

/**
 * Replace the capability selection with the recommendation. Reasoning and the
 * existing per-capability settings are kept. A recommended document access does
 * not say which source, so both document packs are turned on (full rationale:
 * add-agent-creation-assistant design.md).
 */
export function applyRecommendedCapabilities(
  recommended: string[],
  state: CapabilitySelectionState,
  availableIds: ReadonlySet<string>,
): CapabilitySelectionState {
  const next: CapabilitySelectionState = {
    ...state,
    selectedCapabilityIds: availableRecommendedIds(recommended, availableIds),
  };
  if (!next.selectedCapabilityIds.includes(CAP_DOCUMENT_ACCESS)) return next;
  return DOCUMENT_PACKS.reduce((acc, pack) => applyPackToggle(pack, true, acc, availableIds), next);
}

const REASONING_PACK = TOOL_PACK_SECTIONS.flatMap((section) => section.packs).find((pack) => pack.kind === "reasoning");

/** i18n key of the reasoning tile: the Simple view's reasoning pack title. */
export const REASONING_LABEL_KEY = REASONING_PACK?.titleKey ?? "";

/** The assistant always proposes reasoning wherever the Simple view offers its reasoning pack. */
export function isReasoningOffered(availableIds: ReadonlySet<string>): boolean {
  return !!REASONING_PACK && isPackSelectable(REASONING_PACK, availableIds);
}

/** A proposal the user can tick in the review step, besides capabilities. */
export type DraftItem = "systemPrompt" | "name" | "role" | "description";
export const DRAFT_ITEMS: DraftItem[] = ["systemPrompt", "name", "role", "description"];

/** The ticked proposals; an absent key leaves that part of the form unchanged. */
export type AppliedDraft = {
  systemPrompt?: string;
  name?: string;
  role?: string;
  description?: string;
  capabilityIds?: string[];
  reasoning?: true;
};

/** Form values the draft could replace; "" (or []) when the user has not written one. */
export type DraftTargets = {
  systemPrompt: string;
  name: string;
  role: string;
  description: string;
  capabilityIds: string[];
  /** The form's per-capability settings: Apply may change the document access sources. */
  capabilityConfigValues: Record<string, Record<string, unknown>>;
};

export type OverwrittenItem = DraftItem | "capabilities";

/** The proposals the draft offers: non-empty values, and the prompt only when the template has a prompt field. */
export function offeredDraftItems(result: AgentDraftResult, hasPromptField: boolean): DraftItem[] {
  return DRAFT_ITEMS.filter((item) =>
    item === "systemPrompt" ? hasPromptField && !!result.system_prompt.trim() : !!result[item]?.trim(),
  );
}

/** What Apply writes: ticked items only; capabilities only when at least one is ticked. */
export function selectedDraft(
  result: AgentDraftResult,
  ticked: ReadonlySet<DraftItem>,
  tickedCapabilityIds: string[],
  reasoningTicked = false,
): AppliedDraft {
  const draft: AppliedDraft = {};
  if (ticked.has("systemPrompt")) draft.systemPrompt = result.system_prompt;
  for (const item of ["name", "role", "description"] as const) {
    const value = result[item];
    if (ticked.has(item) && value) draft[item] = value;
  }
  if (tickedCapabilityIds.length > 0) draft.capabilityIds = tickedCapabilityIds;
  if (reasoningTicked) draft.reasoning = true;
  return draft;
}

/**
 * Ticked items that would replace a value the user already has, which Apply must confirm first.
 * Reasoning is never listed: switching it on adds an option, it erases nothing the user wrote.
 */
export function overwrittenItems(
  draft: AppliedDraft,
  current: DraftTargets,
  availableIds: ReadonlySet<string>,
): OverwrittenItem[] {
  const replaced: OverwrittenItem[] = DRAFT_ITEMS.filter((item) => {
    const next = draft[item];
    const existing = current[item].trim();
    return next !== undefined && existing !== "" && existing !== next.trim();
  });
  if (
    draft.capabilityIds &&
    current.capabilityIds.length > 0 &&
    capabilitiesChange(draft.capabilityIds, current, availableIds)
  )
    replaced.push("capabilities");
  return replaced;
}

/** Compares what Apply would write (selection and document sources) with the form, not the ticked ids. */
function capabilitiesChange(recommended: string[], current: DraftTargets, availableIds: ReadonlySet<string>): boolean {
  const before: CapabilitySelectionState = {
    selectedCapabilityIds: current.capabilityIds,
    capabilityConfigValues: current.capabilityConfigValues,
    reasoningEnabled: false,
  };
  const after = applyRecommendedCapabilities(recommended, before, availableIds);
  const ids = new Set(after.selectedCapabilityIds);
  const sameSelection =
    ids.size === new Set(before.selectedCapabilityIds).size && before.selectedCapabilityIds.every((id) => ids.has(id));
  const sources = (state: CapabilitySelectionState) =>
    DOCUMENT_PACKS.map((pack) => derivePackChecked(pack, state, availableIds)).join();
  return !sameSelection || sources(after) !== sources(before);
}

/** i18n key of the message shown for a failed draft. */
export function agentDraftErrorKey(error: unknown): string {
  const status = (error as { status?: unknown } | null)?.status;
  const base = "rework.teams.formAgent.creationAssistant.errors";
  if (status === 403) return `${base}.forbidden`;
  // 404: the template is no longer one this team can enroll.
  if (status === 404 || status === 501) return `${base}.unsupported`;
  if (status === 504 || status === "TIMEOUT_ERROR") return `${base}.timeout`;
  if (status === 503 || status === "FETCH_ERROR") return `${base}.unavailable`;
  if (status === 422) return `${base}.invalid`;
  return `${base}.failed`;
}
