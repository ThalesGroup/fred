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
