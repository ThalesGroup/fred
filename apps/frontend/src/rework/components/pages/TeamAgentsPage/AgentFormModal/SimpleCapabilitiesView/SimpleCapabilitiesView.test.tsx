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

// supportsCapabilities must be read verbatim from the template, never
// inferred from availableIds — an empty availableIds also happens when a
// supporting template's capabilities are all outside the team's can_use
// grant, which is a different UI state (unavailable, not unsupported).

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { CapabilityCatalogEntry } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import type { CapabilitySelectionState } from "../toolPackLogic";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("../../../../../features/capabilities/configWidgetRegistry.ts", () => ({
  configWidgetFor: () => undefined,
}));

import { SimpleCapabilitiesView } from "./SimpleCapabilitiesView";

const INCLUDED_SECTION_KEY = "rework.teams.formAgent.capabilities.builtIn.section";
const INCLUDED_BADGE_KEY = "rework.teams.formAgent.capabilities.builtIn.badge";
const NOTHING_INCLUDED_KEY = "rework.teams.formAgent.capabilities.builtIn.none";
const DOCUMENT_ACCESS: CapabilityCatalogEntry = {
  id: "document_access",
  version: "1",
  name: "capability.document_access.name",
  description: "capability.document_access.description",
  icon: "extension",
} as CapabilityCatalogEntry;

const selection: CapabilitySelectionState = {
  selectedCapabilityIds: [],
  capabilityConfigValues: {},
  reasoningEnabled: false,
};

function render(availableIds: ReadonlySet<string>, supportsCapabilities: boolean): string {
  return renderToStaticMarkup(
    <SimpleCapabilitiesView
      availableIds={availableIds}
      supportsCapabilities={supportsCapabilities}
      selection={selection}
      disabled={false}
      onSelectionChange={() => {}}
    />,
  );
}

const DATA_KNOWLEDGE_KEY = "rework.teams.formAgent.capabilities.sections.dataKnowledge";
const DOCUMENT_PRODUCTION_KEY = "rework.teams.formAgent.capabilities.sections.documentProduction";
const ATTACHMENTS_KEY = "rework.teams.formAgent.capabilities.packs.attachments.title";
const TEAM_DOCUMENTS_KEY = "rework.teams.formAgent.capabilities.packs.teamDocuments.title";
const WIKI_KEY = "rework.teams.formAgent.capabilities.packs.teamWiki.title";
const WORD_KEY = "rework.teams.formAgent.capabilities.packs.wordDocument.title";
const PPT_KEY = "rework.teams.formAgent.capabilities.packs.powerpointDocument.title";
const REASONING_KEY = "rework.teams.formAgent.capabilities.packs.reasoning.title";

describe("SimpleCapabilitiesView hides packs the team cannot use", () => {
  it("keeps a pack with at least one admin-enabled capability", () => {
    expect(render(new Set(["writable_document"]), true)).toContain(WORD_KEY);
  });

  it("hides a pack whose every capability is closed to the team", () => {
    // The switch would be dead: applyPackToggle adds nothing, derivePackChecked
    // can never be true.
    expect(render(new Set(["writable_document"]), true)).not.toContain(PPT_KEY);
  });

  it("hides the whole section when none of its packs survives", () => {
    const html = render(new Set(["writable_document"]), true);
    expect(html).toContain(DOCUMENT_PRODUCTION_KEY);
    expect(html).not.toContain(DATA_KNOWLEDGE_KEY);
  });

  it("hides both document packs when document access is closed", () => {
    const html = render(new Set(["document_summarize", "document_verbatim", "document_extract"]), true);
    expect(html).not.toContain(ATTACHMENTS_KEY);
    expect(html).not.toContain(TEAM_DOCUMENTS_KEY);
  });

  it("shows the two document packs when document access is open", () => {
    const html = render(new Set(["document_access"]), true);
    expect(html).toContain(ATTACHMENTS_KEY);
    expect(html).toContain(TEAM_DOCUMENTS_KEY);
    expect(html).not.toContain("rework.teams.formAgent.capabilities.packs.teamResources.title");
    expect(html).not.toContain("search_attachments_only");
  });

  it("keeps the wiki pack independent of the packs beside it in its section", () => {
    const html = render(new Set(["team_wiki"]), true);
    expect(html).toContain(WIKI_KEY);
    expect(html).not.toContain(TEAM_DOCUMENTS_KEY);
  });

  it("always keeps reasoning, which enables no capability at all", () => {
    expect(render(new Set(), true)).toContain(REASONING_KEY);
  });
});

function renderIncluded(includedCapabilities: CapabilityCatalogEntry[]): string {
  return renderToStaticMarkup(
    <SimpleCapabilitiesView
      availableIds={new Set(includedCapabilities.map((capability) => capability.id))}
      supportsCapabilities={false}
      includedCapabilities={includedCapabilities}
      renderIncludedOptions={(capability) => <span>{`options:${capability.id}`}</span>}
      selection={selection}
      disabled={false}
      onSelectionChange={() => {}}
    />,
  );
}

describe("SimpleCapabilitiesView for an agent without free selection", () => {
  it("lists an included capability as always on, with its configuration", () => {
    const html = renderIncluded([DOCUMENT_ACCESS]);

    expect(html).toContain(INCLUDED_SECTION_KEY);
    expect(html).toContain("capability.document_access.name");
    expect(html).toContain(INCLUDED_BADGE_KEY);
    // A badge, not a switch: nothing to turn off.
    expect(html).not.toContain('type="checkbox"');
    expect(html).toContain("options:document_access");
  });

  it("offers no capability pack beside it, even one the team could use", () => {
    const html = renderIncluded([DOCUMENT_ACCESS]);

    expect(html).not.toContain(DATA_KNOWLEDGE_KEY);
    expect(html).not.toContain(TEAM_DOCUMENTS_KEY);
    expect(html).toContain(REASONING_KEY);
  });

  it("says so neutrally when the agent includes nothing", () => {
    const html = renderIncluded([]);

    expect(html).toContain(NOTHING_INCLUDED_KEY);
    expect(html).not.toContain(INCLUDED_BADGE_KEY);
  });

  it("is not shown for a supporting template with zero team-granted capabilities", () => {
    // availableIds empty here too — only supportsCapabilities distinguishes
    // "team has no grants" from "template has no free selection".
    const html = render(new Set(), true);

    expect(html).not.toContain(INCLUDED_SECTION_KEY);
    expect(html).not.toContain(NOTHING_INCLUDED_KEY);
  });
});
