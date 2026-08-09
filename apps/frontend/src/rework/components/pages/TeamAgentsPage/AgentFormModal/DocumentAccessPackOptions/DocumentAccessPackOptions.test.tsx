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

// The folder tree mirrors the Advanced `visible_when: bind_libraries` rule — it
// shows only while the "restrict to specific folders" switch is on, so an agent
// that isn't restricted never renders (nor fetches) the picker.

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("@shared/molecules/DocumentLibraryScopePicker/DocumentLibraryScopePicker.tsx", () => ({
  DocumentLibraryScopePicker: () => <div data-testid="folder-tree" />,
}));

vi.mock("../../AgentCreateEditModal/SwitchRow/SwitchRow.tsx", () => ({
  SwitchRow: ({ label }: { label: string }) => <div data-testid="bind-switch">{label}</div>,
}));

import { DocumentAccessPackOptions } from "./DocumentAccessPackOptions";

function render(configValues: Record<string, unknown>): string {
  return renderToStaticMarkup(
    <DocumentAccessPackOptions configValues={configValues} onConfigChange={() => {}} teamId="team-1" />,
  );
}

describe("DocumentAccessPackOptions", () => {
  it("always shows the restrict switch", () => {
    expect(render({})).toContain("bind-switch");
  });

  it("hides the folder tree until libraries are bound", () => {
    expect(render({ bind_libraries: false })).not.toContain("folder-tree");
    expect(render({ bind_libraries: true })).toContain("folder-tree");
  });
});
