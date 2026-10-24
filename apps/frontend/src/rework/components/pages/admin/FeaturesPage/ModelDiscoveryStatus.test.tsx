// @vitest-environment happy-dom
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

import { act } from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, expect, it, vi } from "vitest";
import { ModelDiscoveryStatus } from "./ModelDiscoveryStatus";

const access = vi.hoisted(() => ({ canAdmin: false }));
const dismissRemovedModel = vi.hoisted(() => vi.fn(() => ({ unwrap: async () => ({}) })));
vi.mock("@rework/core/hooks/useUserCapabilities", () => ({
  useUserCapabilities: () => access,
}));

beforeEach(() => {
  access.canAdmin = false;
  dismissRemovedModel.mockClear();
});

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, values?: { source?: string; sources?: string; services?: string; id?: string }) =>
      `${key}${values?.source ?? values?.sources ?? values?.services ?? values?.id ?? ""}`,
  }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError: vi.fn() }),
}));
vi.mock("../../../../../slices/legacyControlPlane/legacyControlPlaneApiEnhancements", () => ({
  useSetModelDiscoveryUrlMutation: () => [vi.fn(), { isLoading: false }],
  useDismissRemovedModelMutation: () => [dismissRemovedModel, { isLoading: false }],
}));

it("lists a confirmed absence with a cleanup action outside the available-model table", () => {
  access.canAdmin = true;
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
    />,
  );
  expect(html).toContain("https://models.example/v1/models");
  expect(html).toContain("rework.admin.capabilities.discovery.showRemoved");
  expect(html).not.toContain("rework.admin.capabilities.discovery.removedModelIdchat-a");
  expect(html).not.toContain("Old chat (chat-a)");
  expect(html).toContain("rework.admin.capabilities.discovery.summary");
  expect(html).toContain("rework.admin.capabilities.discovery.discoveryUrls");
  expect(html).not.toContain("chat-b)");
});

it("dismisses the selected absence by source and model ID", async () => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  access.canAdmin = true;
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  try {
    await act(async () =>
      root.render(
        <ModelDiscoveryStatus
          data={{
            sources: [
              {
                source_id: "mistral",
                yaml_url: "https://api.mistral.ai/v1/models",
                effective_url: "https://api.mistral.ai/v1/models",
                removed_models: [{ id: "model__openai__old", name: "old", provider: "openai" }],
              },
            ],
          }}
          discoveredSourceIds={["mistral"]}
          refreshing={false}
          refreshError={false}
        />,
      ),
    );
    const showRemoved = Array.from(container.querySelectorAll<HTMLButtonElement>("button")).find((item) =>
      item.textContent?.includes("rework.admin.capabilities.discovery.showRemoved"),
    );
    await act(async () => showRemoved?.click());
    expect(document.body.textContent).toContain("rework.admin.capabilities.discovery.removedModelIdold");
    const button = document.body.querySelector<HTMLButtonElement>(
      'button[aria-label="rework.admin.capabilities.discovery.removeFromList"]',
    );
    expect(button).toBeTruthy();
    await act(async () => button?.click());
    expect(dismissRemovedModel).not.toHaveBeenCalled();
    expect(document.body.textContent).toContain("rework.admin.capabilities.discovery.removeConfirmTitle");
    const confirm = Array.from(document.body.querySelectorAll<HTMLButtonElement>('[role="alertdialog"] button')).find(
      (item) => item.textContent?.includes("rework.admin.capabilities.discovery.removeFromList"),
    );
    await act(async () => confirm?.click());
    expect(dismissRemovedModel).toHaveBeenCalledWith({ sourceId: "mistral", modelId: "model__openai__old" });
  } finally {
    await act(async () => root.unmount());
    container.remove();
  }
});

it("explains why discovered models have no editable source", () => {
  const html = renderToStaticMarkup(
    <ModelDiscoveryStatus
      data={{ sources: [] }}
      discoveredSourceIds={["gateway"]}
      refreshing={false}
      refreshError={false}
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
    />,
  );
  expect(html).toContain("rework.admin.capabilities.discovery.failedSourceswest: timeout");
  expect(html.indexOf("failedSourceswest: timeout")).toBeLessThan(html.indexOf("<details"));
});

it("warns about unreachable agent services without claiming discovery failed", () => {
  const html = renderToStaticMarkup(
    <ModelDiscoveryStatus
      data={{ sources: [] }}
      discoveredSourceIds={["gateway"]}
      refreshing={false}
      refreshError={false}
      unverifiedRuntimes={[{ runtime_id: "fred-agents", base_url: "http://localhost:8010" }]}
    />,
  );

  expect(html).toContain("discovery.unverifiedRuntimes");
  expect(html).toContain("<code>fred-agents</code> (<code>http://localhost:8010</code>)");
  expect(html).not.toContain("discovery.refreshFailed");
  expect(html).not.toContain("discovery.unregisteredSource");
  expect(html).not.toContain("discovery.none");
});

it("does not call a source unregistered while another pod is unreachable", () => {
  const html = renderToStaticMarkup(
    <ModelDiscoveryStatus
      data={{ sources: [] }}
      discoveredSourceIds={["reachable", "unknown"]}
      refreshing={false}
      refreshError={false}
      unverifiedRuntimes={[{ runtime_id: "pod-b", base_url: "http://localhost:8013" }]}
    />,
  );

  expect(html).toContain("discovery.unverifiedRuntimes");
  expect(html).not.toContain("discovery.unregisteredSource");
});

it("keeps an unregistered-source warning for a verified pod during another pod's outage", () => {
  const html = renderToStaticMarkup(
    <ModelDiscoveryStatus
      data={{ sources: [] }}
      discoveredSourceIds={["reachable", "unknown"]}
      refreshing={false}
      refreshError={false}
      unverifiedRuntimes={[{ runtime_id: "pod-b", base_url: "http://localhost:8013" }]}
      verifiedSourceIds={["reachable"]}
    />,
  );

  expect(html).toContain("discovery.unverifiedRuntimes");
  expect(html).toContain("discovery.unregisteredSourcereachable");
  expect(html).not.toContain("discovery.unregisteredSourceunknown");
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
    />,
  );

  expect(html).toContain("mistral");
  expect(html).toContain("gateway");
  expect(html.match(/<h3/g)).toHaveLength(2);
  expect(html.match(/<input/g)).toHaveLength(2);
  expect(html).toContain('aria-label="rework.admin.capabilities.discovery.sourceUrlAriamistral"');
  expect(html).toContain('aria-label="rework.admin.capabilities.discovery.sourceUrlAriagateway"');
  expect(html.match(/discovery\.save/g)).toHaveLength(2);
  expect(html.match(/discovery\.reset/g)).toHaveLength(2);
});
