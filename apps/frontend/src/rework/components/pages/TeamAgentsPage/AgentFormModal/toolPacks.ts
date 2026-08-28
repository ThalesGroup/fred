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

/**
 * Capability packs — hardcoded source of truth for the agent form's **Simple**
 * capabilities view (#2220).
 *
 * A "pack" is a user-facing grouping of related backend capabilities that make
 * sense together, so a non-technical user can enable a whole coherent feature
 * ("let this agent use the team's resources") with one switch instead of
 * reasoning about individual capabilities (RAG vs. tabular vs. summarize…).
 *
 * This is deliberately a **front-only presentation layer** over the existing
 * capability model: enabling a pack just flips the underlying
 * `selectedCapabilityIds` / `capabilityConfigValues` the form already stores —
 * no admin "Features" change, no backend/DB change. See `toolPackLogic.ts` for
 * how pack on/off state is derived from, and written back to, that selection.
 *
 * The `document_access` tool is shared by two packs ("team resources" and
 * "conversation attachments") and its mode is COMPUTED from their combination
 * (see `toolPackLogic.ts` / the truth table below) rather than owned by one:
 *
 *   Team resources | Attachments | corpus searchable | attach files | search scope
 *   ---------------+-------------+-------------------+--------------+-------------------
 *        off       |     off     |        no         |     no       | (tool off)
 *        off       |     on      |        no         |     yes      | attachments only
 *        on        |     off     |        yes        |     no       | corpus
 *        on        |     on      |        yes        |     yes      | corpus + attachments
 *
 * One day this registry becomes admin-editable; today it is static and
 * intentionally the only place to edit pack content.
 */

/** Reasoning is a form field (`reasoningEnabled`), not a `CapabilityManifest`
 *  capability — the reasoning pack toggles that field instead of a capability
 *  id. Every other pack maps to real backend capability ids. */
export type ToolPackKind = "capabilities" | "reasoning";

/** How a pack contributes to the shared `document_access` tool. Two packs
 *  contribute (corpus vs. attachments); their combination computes the tool's
 *  single config (see the truth table above). */
export type DocumentAccessIntent = "corpus" | "attachments";

/** One line in a pack's expandable "included capabilities" list. */
export interface ToolPackIncludedCapability {
  /** Backend capability id, checked against the team's `available_capabilities`
   *  to render the admin-enabled (success) / not-enabled (error) badge. */
  capabilityId: string;
  /** i18n key for the display label. Reuses the capability's own existing name
   *  key (set in the #2220 copy pass) — no duplicated strings. */
  labelKey: string;
}

export interface ToolPack {
  /** Stable UI-only pack id (not a backend id). */
  id: string;
  kind: ToolPackKind;
  /** Material Symbols icon name (rendered 48px, on-surface). */
  icon: string;
  titleKey: string;
  descriptionKey: string;
  /** Capabilities shown in the pack's expandable list, each with an admin-status
   *  badge. Display only — activation is driven by the fields below. */
  includes: ToolPackIncludedCapability[];
  /**
   * Plain on/off capability ids this pack enables (the "available" ones). Does
   * NOT include `document_access`, whose config is computed from
   * `documentAccessIntent` because two packs share it.
   */
  enablesCapabilityIds: string[];
  /** Contribution to the shared `document_access` tool, if any. */
  documentAccessIntent?: DocumentAccessIntent;
}

export interface ToolPackSection {
  /** Stable UI-only section id. */
  id: string;
  titleKey: string;
  packs: ToolPack[];
  /** When true, the section renders an empty-state placeholder (no packs yet). */
  emptyState?: boolean;
}

// --- Backend capability ids these packs map onto (verified against the runtime
//     manifests + mcp_catalog.yaml). Named constants so a rename surfaces here
//     rather than in scattered string literals; also consumed by toolPackLogic. ---
export const CAP_DOCUMENT_ACCESS = "document_access";
export const CAP_DOCUMENT_SUMMARIZE = "document_summarize";
export const CAP_TABULAR = "mcp-knowledge-flow-mcp-tabular";
export const CAP_WRITABLE_DOCUMENT = "writable_document";
export const CAP_PPT_FILLER = "ppt_filler";
// Independent backend capabilities that the Simple view groups under one
// document-work pack, while the Advanced view keeps each toggle separate. What
// they have in common is the unit they operate on: a document the agent has
// already identified by uid — read it, extract from it, compare it — as opposed
// to the corpus-wide discovery the team-resources pack covers.
export const CAP_DOCUMENT_VERBATIM = "document_verbatim";
export const CAP_DOCUMENT_EXTRACT = "document_extract";
export const CAP_DOCUMENT_SIMILARITY = "document_similarity";

/** `document_access` config field keys the resource packs compute. */
export const DOC_ACCESS_SEARCH_ATTACHMENTS_ONLY = "search_attachments_only";
export const DOC_ACCESS_SHOW_ATTACH_FILES_CONTROL = "show_attach_files_control";

const PACK_TEAM_RESOURCES = "team_resources";
const PACK_CONVERSATION_ATTACHMENTS = "conversation_attachments";

export const TOOL_PACK_SECTIONS: ToolPackSection[] = [
  {
    id: "data_knowledge",
    titleKey: "rework.teams.formAgent.capabilities.sections.dataKnowledge",
    packs: [
      {
        id: PACK_TEAM_RESOURCES,
        kind: "capabilities",
        icon: "database",
        titleKey: "rework.teams.formAgent.capabilities.packs.teamResources.title",
        descriptionKey: "rework.teams.formAgent.capabilities.packs.teamResources.description",
        // The filesystem capability (mcp-knowledge-flow-fs) is deliberately NOT
        // part of this pack: the /fs runtime boundary is not agent/team-scoped
        // yet (#2334, AGENT-FILESYSTEM-HARDENING-RFC F1). Do not re-add it here
        // until that lands.
        includes: [
          { capabilityId: CAP_DOCUMENT_ACCESS, labelKey: "capability.document_access.name" },
          { capabilityId: CAP_TABULAR, labelKey: "mcp.servers.tabular.name" },
          { capabilityId: CAP_DOCUMENT_SUMMARIZE, labelKey: "capability.document_summarize.name" },
        ],
        // document_access is handled via documentAccessIntent (computed config);
        // the rest are plain on/off.
        enablesCapabilityIds: [CAP_TABULAR, CAP_DOCUMENT_SUMMARIZE],
        documentAccessIntent: "corpus",
      },
      {
        id: PACK_CONVERSATION_ATTACHMENTS,
        kind: "capabilities",
        icon: "attach_file",
        titleKey: "rework.teams.formAgent.capabilities.packs.conversationAttachments.title",
        descriptionKey: "rework.teams.formAgent.capabilities.packs.conversationAttachments.description",
        // Visible included list is summarize only (per spec); the attach-files
        // control is delivered by document_access (via documentAccessIntent).
        includes: [{ capabilityId: CAP_DOCUMENT_SUMMARIZE, labelKey: "capability.document_summarize.name" }],
        enablesCapabilityIds: [CAP_DOCUMENT_SUMMARIZE],
        documentAccessIntent: "attachments",
      },
      {
        // One Simple-view card grouping the capabilities that work on documents
        // the agent already identified: verbatim read, exhaustive extraction,
        // and targeted comparison. Plain pack — enabling it selects all three
        // ids; the Advanced view still toggles each on its own. The `id` stays
        // `document_reading` (UI-only, but it is what the pack's copy keys and
        // any muscle memory are attached to).
        id: "document_reading",
        kind: "capabilities",
        icon: "article",
        titleKey: "rework.teams.formAgent.capabilities.packs.documentReading.title",
        descriptionKey: "rework.teams.formAgent.capabilities.packs.documentReading.description",
        includes: [
          { capabilityId: CAP_DOCUMENT_VERBATIM, labelKey: "capability.document_verbatim.name" },
          { capabilityId: CAP_DOCUMENT_EXTRACT, labelKey: "capability.document_extract.name" },
          { capabilityId: CAP_DOCUMENT_SIMILARITY, labelKey: "capability.document_similarity.name" },
        ],
        enablesCapabilityIds: [CAP_DOCUMENT_VERBATIM, CAP_DOCUMENT_EXTRACT, CAP_DOCUMENT_SIMILARITY],
      },
    ],
  },
  {
    id: "document_production",
    titleKey: "rework.teams.formAgent.capabilities.sections.documentProduction",
    packs: [
      {
        id: "word_document",
        kind: "capabilities",
        icon: "description",
        titleKey: "rework.teams.formAgent.capabilities.packs.wordDocument.title",
        descriptionKey: "rework.teams.formAgent.capabilities.packs.wordDocument.description",
        includes: [{ capabilityId: CAP_WRITABLE_DOCUMENT, labelKey: "capability.writable_document.name" }],
        enablesCapabilityIds: [CAP_WRITABLE_DOCUMENT],
      },
      {
        id: "powerpoint_document",
        kind: "capabilities",
        icon: "slideshow",
        titleKey: "rework.teams.formAgent.capabilities.packs.powerpointDocument.title",
        descriptionKey: "rework.teams.formAgent.capabilities.packs.powerpointDocument.description",
        includes: [{ capabilityId: CAP_PPT_FILLER, labelKey: "capability.ppt_filler.name" }],
        enablesCapabilityIds: [CAP_PPT_FILLER],
      },
    ],
  },
  {
    id: "intelligence_orchestration",
    titleKey: "rework.teams.formAgent.capabilities.sections.intelligenceOrchestration",
    packs: [
      {
        id: "reasoning",
        kind: "reasoning",
        icon: "neurology",
        titleKey: "rework.teams.formAgent.capabilities.packs.reasoning.title",
        descriptionKey: "rework.teams.formAgent.capabilities.packs.reasoning.description",
        includes: [],
        enablesCapabilityIds: [],
      },
    ],
  },
  {
    id: "actions_integration",
    titleKey: "rework.teams.formAgent.capabilities.sections.actionsIntegration",
    packs: [],
    emptyState: true,
  },
];
