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

// The composer's reasoning row (REASON-01 level 4) is a SWITCH, not a checkbox:
// the same on/off decision is a switch on the admin models page and on the agent
// form, and three different affordances for one setting is how a user stops
// trusting that they are the same setting.

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { ReasoningControl } from "./ReasoningControl";
import type { ChatTurnControlComposerState } from "../types";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("@shared/atoms/Icon/Icon", () => ({
  default: ({ type }: { type: string }) => <i data-icon={type} />,
}));

function composerState(over: Partial<ChatTurnControlComposerState> = {}): ChatTurnControlComposerState {
  return {
    teamId: "fredlab",
    onAttach: () => undefined,
    selectedLibraryIds: [],
    onSelectedLibraryIdsChange: () => undefined,
    selectedDocumentUids: [],
    onSelectedDocumentUidsChange: () => undefined,
    searchPolicy: "hybrid",
    onSearchPolicyChange: () => undefined,
    ragScope: "all",
    onRagScopeChange: () => undefined,
    reasoning: false,
    onReasoningChange: () => undefined,
    ...over,
  } as ChatTurnControlComposerState;
}

function render(reasoning: boolean): string {
  return renderToStaticMarkup(
    <ReasoningControl
      params={{}}
      composer={composerState({ reasoning })}
      open={false}
      onToggleOpen={() => undefined}
    />,
  );
}

describe("ReasoningControl (REASON-01 level 4)", () => {
  it("renders a switch row, not a checkbox row", () => {
    const html = render(false);
    expect(html).toContain('role="menuitemcheckbox"');
    // The former affordance. Asserted absent because swapping it back would
    // otherwise pass every other test in this file.
    expect(html).not.toContain("check_box");
  });

  it("reflects the off state", () => {
    const html = render(false);
    expect(html).toContain('aria-checked="false"');
    expect(html).toContain('data-on="false"');
  });

  it("reflects the on state", () => {
    const html = render(true);
    expect(html).toContain('aria-checked="true"');
    expect(html).toContain('data-on="true"');
  });

  it("does not mark the row as a selected menu option", () => {
    // A toggled-on row stays a row, not a chosen option — highlighting it like
    // one is what made the old checkbox version read as a picker.
    expect(render(true)).not.toContain("data-selected");
  });

  it("labels the row and opens no submenu", () => {
    const html = render(false);
    expect(html).toContain("chatbot.composerSettings.reasoningRowLabel");
    // The row IS the control: a chevron would promise a panel that never opens.
    expect(html).not.toContain("chevron_right");
  });
});
