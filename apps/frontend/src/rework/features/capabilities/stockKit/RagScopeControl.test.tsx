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

// The row offers only the scopes the agent's document sources allow.

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { ChatTurnControlComposerState } from "../types";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("@shared/molecules/EnumSelectRow/EnumSelectRow", () => ({
  EnumSelectRow: ({ options }: { options: { value: string }[] }) => (
    <ul>
      {options.map((option) => (
        <li key={option.value}>{`option:${option.value}`}</li>
      ))}
    </ul>
  ),
}));

import { RagScopeControl } from "./RagScopeControl";

function render(params: Record<string, unknown>): string {
  return renderToStaticMarkup(
    <RagScopeControl
      params={params}
      composer={{ ragScope: "hybrid", onRagScopeChange: () => {} } as unknown as ChatTurnControlComposerState}
      open
      onToggleOpen={() => {}}
    />,
  );
}

describe("RagScopeControl options", () => {
  it("offers every scope when the params do not narrow them", () => {
    const html = render({ default: "hybrid" });
    expect(html).toContain("option:corpus_only");
    expect(html).toContain("option:hybrid");
    expect(html).toContain("option:general_only");
  });

  it("offers only the listed scopes", () => {
    const html = render({ default: "hybrid", options: ["hybrid", "general_only"] });
    expect(html).not.toContain("option:corpus_only");
    expect(html).toContain("option:hybrid");
    expect(html).toContain("option:general_only");
  });
});
