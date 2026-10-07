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

/** Simple-view packs map user-facing switches to the agent's capability selection.
 * The two document packs each turn on one `document_access` source.
 */

/** Reasoning is a form field (`reasoningEnabled`), not a `CapabilityManifest`
 *  capability — the reasoning pack toggles that field instead of a capability
 *  id. Every other pack maps to real backend capability ids. */
export type ToolPackKind = "capabilities" | "reasoning";

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
  /** Capability ids selected by this pack when available to the team. */
  enablesCapabilityIds: string[];
  /** The `document_access` source this pack turns on. */
  documentSource?: DocumentSource;
}

export interface ToolPackSection {
  /** Stable UI-only section id. */
  id: string;
  titleKey: string;
  packs: ToolPack[];
}

// --- Backend capability ids these packs map onto (verified against the runtime
//     manifests + mcp_catalog.yaml). Named constants so a rename surfaces here
//     rather than in scattered string literals; also consumed by toolPackLogic. ---
export const CAP_DOCUMENT_ACCESS = "document_access";
export const CAP_DOCUMENT_SUMMARIZE = "document_summarize";
// A corpus search mode, not a reading tool: Knowledge Flow runs it over the
// corpus targets and never the conversation's attachments, so only the Team
// documents pack grants it.
export const CAP_DOCUMENT_SIMILARITY = "document_similarity";
// CSV and Excel attachments expose SQL datasets through tabular tools.
export const CAP_TABULAR = "mcp-knowledge-flow-mcp-tabular";
export const CAP_WRITABLE_DOCUMENT = "writable_document";
export const CAP_PPT_FILLER = "ppt_filler";
export const CAP_HTML_ARTIFACT = "html_artifact";
// Both document packs grant the reading tools; Advanced keeps separate toggles.
export const CAP_DOCUMENT_VERBATIM = "document_verbatim";
export const CAP_DOCUMENT_EXTRACT = "document_extract";
export const CAP_TEAM_WIKI = "team_wiki";

/** `document_access` source keys, one per document pack. */
export const DOC_ACCESS_ATTACHMENTS = "attachments";
export const DOC_ACCESS_TEAM_DOCUMENTS = "team_documents";
export type DocumentSource = typeof DOC_ACCESS_ATTACHMENTS | typeof DOC_ACCESS_TEAM_DOCUMENTS;

const PACK_TEAM_WIKI = "team_wiki";

const SHARED_DOCUMENT_INCLUDES: ToolPackIncludedCapability[] = [
  { capabilityId: CAP_DOCUMENT_ACCESS, labelKey: "capability.document_access.name" },
  { capabilityId: CAP_TABULAR, labelKey: "mcp.servers.tabular.name" },
  { capabilityId: CAP_DOCUMENT_SUMMARIZE, labelKey: "capability.document_summarize.name" },
];
const READING_INCLUDES: ToolPackIncludedCapability[] = [
  { capabilityId: CAP_DOCUMENT_VERBATIM, labelKey: "capability.document_verbatim.name" },
  { capabilityId: CAP_DOCUMENT_EXTRACT, labelKey: "capability.document_extract.name" },
];
const SIMILARITY_INCLUDE: ToolPackIncludedCapability = {
  capabilityId: CAP_DOCUMENT_SIMILARITY,
  labelKey: "capability.document_similarity.name",
};
const ATTACHMENTS_INCLUDES = [...SHARED_DOCUMENT_INCLUDES, ...READING_INCLUDES];
const TEAM_DOCUMENTS_INCLUDES = [...SHARED_DOCUMENT_INCLUDES, SIMILARITY_INCLUDE, ...READING_INCLUDES];

export const TOOL_PACK_SECTIONS: ToolPackSection[] = [
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
    id: "data_knowledge",
    titleKey: "rework.teams.formAgent.capabilities.sections.dataKnowledge",
    packs: [
      {
        id: DOC_ACCESS_ATTACHMENTS,
        kind: "capabilities",
        icon: "attach_file",
        titleKey: "rework.teams.formAgent.capabilities.packs.attachments.title",
        descriptionKey: "rework.teams.formAgent.capabilities.packs.attachments.description",
        includes: ATTACHMENTS_INCLUDES,
        enablesCapabilityIds: ATTACHMENTS_INCLUDES.map((entry) => entry.capabilityId),
        documentSource: DOC_ACCESS_ATTACHMENTS,
      },
      {
        id: DOC_ACCESS_TEAM_DOCUMENTS,
        kind: "capabilities",
        icon: "database",
        titleKey: "rework.teams.formAgent.capabilities.packs.teamDocuments.title",
        descriptionKey: "rework.teams.formAgent.capabilities.packs.teamDocuments.description",
        includes: TEAM_DOCUMENTS_INCLUDES,
        enablesCapabilityIds: TEAM_DOCUMENTS_INCLUDES.map((entry) => entry.capabilityId),
        documentSource: DOC_ACCESS_TEAM_DOCUMENTS,
      },
      {
        // Same icon as the wiki's own entry in the team navigation panel, so the
        // pack and the thing it grants access to read as one feature.
        id: PACK_TEAM_WIKI,
        kind: "capabilities",
        icon: "book_2",
        titleKey: "rework.teams.formAgent.capabilities.packs.teamWiki.title",
        descriptionKey: "rework.teams.formAgent.capabilities.packs.teamWiki.description",
        includes: [{ capabilityId: CAP_TEAM_WIKI, labelKey: "capability.team_wiki.name" }],
        enablesCapabilityIds: [CAP_TEAM_WIKI],
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
      {
        id: "web_page",
        kind: "capabilities",
        icon: "code",
        titleKey: "rework.teams.formAgent.capabilities.packs.webPage.title",
        descriptionKey: "rework.teams.formAgent.capabilities.packs.webPage.description",
        includes: [{ capabilityId: CAP_HTML_ARTIFACT, labelKey: "capability.html_artifact.name" }],
        enablesCapabilityIds: [CAP_HTML_ARTIFACT],
      },
    ],
  },
];
