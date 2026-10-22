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
import { expect, it, vi } from "vitest";
import { ModelDiscoveryStatus } from "./ModelDiscoveryStatus";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string, values?: { sources?: string }) => `${key}${values?.sources ?? ""}` }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError: vi.fn() }),
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useSetModelDiscoveryUrlMutation: () => [vi.fn(), { isLoading: false }],
}));

it("shows a confirmed disappearance separately from available models", () => {
  const html = renderToStaticMarkup(
    <ModelDiscoveryStatus
      data={{
        sources: [
          {
            source_id: "gateway",
            yaml_url: "https://models.example/v1/models",
            effective_url: "https://models.example/v1/models",
            override_url: null,
            available_models: [{ id: "model-b", name: "chat-b", provider: "openai" }],
            removed_models: [{ id: "model-a", name: "chat-a", provider: "openai", display_name: "Old chat" }],
            new_ids: ["model-b"],
          },
        ],
      }}
      discoveredSourceIds={["gateway"]}
      refreshing={false}
      refreshError={false}
      refresh={async () => undefined}
    />,
  );
  expect(html).toContain("https://models.example/v1/models");
  expect(html).toContain("Old chat (chat-a)");
  expect(html).toContain("rework.admin.capabilities.discovery.unavailable");
  expect(html).not.toContain("chat-b)");
});

it("explains why discovered models have no editable source", () => {
  const html = renderToStaticMarkup(
    <ModelDiscoveryStatus
      data={{ sources: [] }}
      discoveredSourceIds={["gateway"]}
      refreshing={false}
      refreshError={false}
      refresh={async () => undefined}
    />,
  );

  expect(html).toContain("rework.admin.capabilities.discovery.unregisteredSource");
  expect(html).not.toContain("rework.admin.capabilities.discovery.none");
});

it("warns when one discovered source is missing from a mixed status", () => {
  const html = renderToStaticMarkup(
    <ModelDiscoveryStatus
      data={{
        sources: [
          {
            source_id: "other",
            yaml_url: "https://other.example/v1/models",
            effective_url: "https://other.example/v1/models",
            available_models: [],
            removed_models: [],
            new_ids: [],
          },
        ],
      }}
      discoveredSourceIds={["other", "gateway"]}
      refreshing={false}
      refreshError={false}
      refresh={async () => undefined}
    />,
  );

  expect(html).toContain("rework.admin.capabilities.discovery.unregisteredSource");
  expect(html).toContain("gateway");
});
