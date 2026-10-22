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
import { beforeEach, expect, it, vi } from "vitest";
import { ModelDiscoveryStatus } from "./ModelDiscoveryStatus";

const access = vi.hoisted(() => ({ canAdmin: false }));
vi.mock("@rework/core/hooks/useUserCapabilities", () => ({
  useUserCapabilities: () => access,
}));

beforeEach(() => {
  access.canAdmin = false;
});

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, values?: { sources?: string; services?: string }) =>
      `${key}${values?.sources ?? values?.services ?? ""}`,
  }),
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

it("shows a source refresh failure outside the collapsed settings", () => {
  const html = renderToStaticMarkup(
    <ModelDiscoveryStatus
      data={{
        sources: [
          {
            source_id: "west",
            yaml_url: "https://west.example/v1/models",
            effective_url: "https://west.example/v1/models",
            available_models: [],
            removed_models: [],
            new_ids: [],
            last_error: "timeout",
          },
        ],
      }}
      discoveredSourceIds={["west"]}
      refreshing={false}
      refreshError={false}
      refresh={async () => undefined}
    />,
  );
  expect(html).toContain("rework.admin.capabilities.discovery.failedSourceswest");
  expect(html.indexOf("failedSourceswest")).toBeLessThan(html.indexOf("<details>"));
});

it("warns about unreachable agent services without claiming discovery failed", () => {
  const html = renderToStaticMarkup(
    <ModelDiscoveryStatus
      data={{ sources: [] }}
      discoveredSourceIds={["gateway"]}
      refreshing={false}
      refreshError={false}
      unverifiedRuntimes={[{ runtime_id: "fred-agents", base_url: "http://localhost:8010" }]}
      refresh={async () => undefined}
    />,
  );

  expect(html).toContain("discovery.unverifiedRuntimes");
  expect(html).toContain("<code>fred-agents</code> (<code>http://localhost:8010</code>)");
  expect(html).not.toContain("discovery.refreshFailed");
  expect(html).not.toContain("discovery.unregisteredSource");
  expect(html).not.toContain("discovery.none");
});

it("still reports an unregistered source advertised by a reachable pod", () => {
  const html = renderToStaticMarkup(
    <ModelDiscoveryStatus
      data={{ sources: [] }}
      discoveredSourceIds={["reachable", "unknown"]}
      refreshing={false}
      refreshError={false}
      unverifiedRuntimes={[{ runtime_id: "pod-b", base_url: "http://localhost:8013" }]}
      verifiedSourceIds={["reachable"]}
      refresh={async () => undefined}
    />,
  );

  expect(html).toContain("discovery.unregisteredSourcereachable");
  expect(html).not.toContain("unknown");
});

it("shows the effective URL without edit controls to a delegated feature manager", () => {
  const source = {
    source_id: "gateway",
    yaml_url: "https://models.example/v1/models",
    effective_url: "https://override.example/v1/models",
    override_url: "https://override.example/v1/models",
  };
  const render = () =>
    renderToStaticMarkup(
      <ModelDiscoveryStatus
        data={{ sources: [source] }}
        discoveredSourceIds={["gateway"]}
        refreshing={false}
        refreshError={false}
        refresh={async () => undefined}
      />,
    );

  const delegated = render();
  expect(delegated).toContain(source.effective_url);
  expect(delegated).not.toContain("discovery.save");
  expect(delegated).not.toContain("discovery.reset");
  expect(delegated).not.toContain("<input");

  access.canAdmin = true;
  const admin = render();
  expect(admin).toContain("discovery.save");
  expect(admin).toContain("discovery.reset");
  expect(admin).not.toContain("discovery.yamlUrl");
});

it("shows a separate URL editor for each discovery source", () => {
  access.canAdmin = true;
  const html = renderToStaticMarkup(
    <ModelDiscoveryStatus
      data={{
        sources: [
          {
            source_id: "mistral",
            yaml_url: "https://api.mistral.ai/v1/models",
            effective_url: "https://api.mistral.ai/v1/models",
          },
          {
            source_id: "gateway",
            yaml_url: "https://models.example/v1/models",
            effective_url: "https://models.example/v1/models",
          },
        ],
      }}
      discoveredSourceIds={["mistral", "gateway"]}
      refreshing={false}
      refreshError={false}
      refresh={async () => undefined}
    />,
  );

  expect(html).toContain("mistral");
  expect(html).toContain("gateway");
  expect(html.match(/<input/g)).toHaveLength(2);
  expect(html.match(/discovery\.save/g)).toHaveLength(2);
  expect(html.match(/discovery\.reset/g)).toHaveLength(2);
});
