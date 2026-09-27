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
import type { CapabilitySelectionState } from "../toolPackLogic";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

import { SimpleCapabilitiesView } from "./SimpleCapabilitiesView";

const NOT_SUPPORTED_KEY = "rework.teams.formAgent.capabilities.notSupported";

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
const TEAM_RESOURCES_KEY = "rework.teams.formAgent.capabilities.packs.teamResources.title";
const ATTACHMENTS_KEY = "rework.teams.formAgent.capabilities.packs.conversationAttachments.title";
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

  it("hides both resource packs when document_access is closed, whatever else is open", () => {
    // The reading capabilities are granted, but both packs hang on
    // document_access — conversation_attachments does not even list it.
    const html = render(new Set(["document_summarize", "document_verbatim", "document_extract"]), true);
    expect(html).not.toContain(TEAM_RESOURCES_KEY);
    expect(html).not.toContain(ATTACHMENTS_KEY);
  });

  it("keeps both resource packs as soon as document_access is open", () => {
    const html = render(new Set(["document_access"]), true);
    expect(html).toContain(TEAM_RESOURCES_KEY);
    expect(html).toContain(ATTACHMENTS_KEY);
  });

  it("keeps the wiki pack independent of the packs beside it in its section", () => {
    const html = render(new Set(["team_wiki"]), true);
    expect(html).toContain(WIKI_KEY);
    expect(html).not.toContain(TEAM_RESOURCES_KEY);
  });

  it("always keeps reasoning, which enables no capability at all", () => {
    expect(render(new Set(), true)).toContain(REASONING_KEY);
  });
});

describe("SimpleCapabilitiesView supportsCapabilities", () => {
  it("shows the not-supported message when the template opts out, even with nothing selected", () => {
    expect(render(new Set(), false)).toContain(NOT_SUPPORTED_KEY);
  });

  it("does not show the not-supported message for a supporting template with zero team-granted capabilities", () => {
    // availableIds empty here too — only supportsCapabilities distinguishes
    // "team has no grants" from "template doesn't support selection".
    expect(render(new Set(), true)).not.toContain(NOT_SUPPORTED_KEY);
  });
});
