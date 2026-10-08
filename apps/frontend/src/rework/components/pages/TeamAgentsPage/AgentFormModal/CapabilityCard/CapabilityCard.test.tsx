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

// A `ui.visible_when` gate that is itself hidden hides its dependants: a stored
// `bind_libraries` must not show the library picker while team documents is off.

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { CapabilityCatalogEntry } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("../../../../../features/capabilities/configWidgetRegistry.ts", () => ({
  configWidgetFor: () => undefined,
}));

vi.mock("../TuningFieldRenderer.tsx", () => ({
  TuningFieldRenderer: ({ field }: { field: { key: string } }) => <span>{`field:${field.key}`}</span>,
}));

import { CapabilityConfigForm } from "./CapabilityCard";

const FIELDS = [
  { key: "team_documents", type: "boolean", title: "t", default: true },
  { key: "bind_libraries", type: "boolean", title: "b", default: false, ui: { visible_when: "team_documents" } },
  { key: "library_tag_ids", type: "array", title: "l", ui: { visible_when: "bind_libraries" } },
] as NonNullable<CapabilityCatalogEntry["config_fields"]>;

function render(configValues: Record<string, unknown>): string {
  return renderToStaticMarkup(
    <CapabilityConfigForm
      capability={{ id: "document_access" } as CapabilityCatalogEntry}
      configFields={FIELDS}
      configValues={configValues}
      disabled={false}
      assetFiles={{}}
      onConfigChange={() => {}}
      onAssetFileChange={() => {}}
      onBlockingErrorChange={() => {}}
    />,
  );
}

describe("CapabilityConfigForm visible_when", () => {
  it("shows the picker while its whole gate chain is on", () => {
    expect(render({ team_documents: true, bind_libraries: true })).toContain("field:library_tag_ids");
  });

  it("hides the picker when its gate is hidden, even if the gate's value is on", () => {
    const html = render({ team_documents: false, bind_libraries: true });
    expect(html).not.toContain("field:bind_libraries");
    expect(html).not.toContain("field:library_tag_ids");
  });
});
