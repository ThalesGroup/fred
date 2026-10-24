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
import type { CapabilityEnablementItem } from "../../../../../slices/legacyControlPlane/legacyControlPlaneOpenApi";
import { ModelIdentityCell } from "./ModelIdentityCell";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string, options?: { count?: number }) => `${key}:${options?.count ?? ""}` }),
}));

vi.mock("./ModelDisplayNameEditor", () => ({
  ModelDisplayNameEditor: () => null,
}));

vi.mock("./ModelDetailTooltip", () => ({
  ModelDetailTooltip: () => null,
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
    expect(markup).toContain("modelSpecs.contextExact:128000");
    expect(markup).toContain("modelSpecs.context:");
    expect(markup).toContain("modelSpecs.input:");
    expect(markup).toContain("modelSpecs.output:");
    expect(markup).not.toContain("neurology");
  });

  it("keeps an id-only model free of invented limits", () => {
    const markup = renderToStaticMarkup(<ModelIdentityCell capability={capability} dimmed={false} />);
    expect(markup).toContain("upstream-chat");
    expect(markup).not.toContain("modelSpecs.");
  });

  it("does not present a discovered model type without a portable type field", () => {
    const markup = renderToStaticMarkup(
      <ModelIdentityCell
        capability={{
          ...capability,
          model_discovery_source_id: "openai",
          model_capabilities: ["chat"],
        }}
        dimmed={false}
      />,
    );
    expect(markup).toContain("modelSpecs.source");
    expect(markup).not.toContain("modelSpecs.capabilities.chat");
    expect(markup).not.toContain("modelSpecs.typeUnknown");
  });

  it("does not show a redundant chat chip when the upstream confirms it", () => {
    const markup = renderToStaticMarkup(
      <ModelIdentityCell
        capability={{
          ...capability,
          model_discovery_source_id: "mistral",
          model_capabilities: ["chat"],
          model_chat_capability_verified: true,
        }}
        dimmed={false}
      />,
    );
    expect(markup).not.toContain("modelSpecs.capabilities.chat");
  });
});
