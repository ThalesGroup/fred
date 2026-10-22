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

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { CapabilityEnablementItem } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { ModelIdentityCell } from "./ModelIdentityCell";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string, options?: { count?: number }) => `${key}:${options?.count ?? ""}` }),
}));

vi.mock("./ModelDisplayNameEditor", () => ({
  ModelDisplayNameEditor: () => null,
}));

const capability: CapabilityEnablementItem = {
  id: "model:discovered.gateway.id",
  name: "upstream-chat",
  model_display_name: "Gateway Chat",
  kind: "model",
  icon: "tune",
  version: "1.0.0",
  team_scope: "admin_gated",
  default_on: false,
  enabled_team_ids: [],
  team_settings_fields: [],
};

describe("ModelIdentityCell", () => {
  it("shows the wire id and each supplied token limit", () => {
    const markup = renderToStaticMarkup(
      <ModelIdentityCell
        capability={{
          ...capability,
          model_context_window_tokens: 128000,
          model_max_input_tokens: 120000,
          model_max_output_tokens: 8000,
        }}
        dimmed={false}
      />,
    );
    expect(markup).toContain("Gateway Chat");
    expect(markup).toContain("upstream-chat");
    expect(markup).toContain("modelSpecs.context:128000");
    expect(markup).toContain("modelSpecs.input:120000");
    expect(markup).toContain("modelSpecs.output:8000");
  });

  it("keeps an id-only model free of invented limits", () => {
    const markup = renderToStaticMarkup(<ModelIdentityCell capability={capability} dimmed={false} />);
    expect(markup).toContain("upstream-chat");
    expect(markup).not.toContain("modelSpecs.");
  });
});
