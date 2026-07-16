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

// The Capabilities dashboard is data-driven from the aggregated enablement list.
// `t` is mocked to echo its key, so we assert on which key each state uses and
// that catalog rows surface the enabled-team count and health.

import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { CapabilityEnablementItem } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

const h = vi.hoisted(() => ({
  list: { data: undefined, isLoading: false, isError: false } as {
    data?: { items?: CapabilityEnablementItem[] };
    isLoading: boolean;
    isError: boolean;
  },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? key,
    i18n: { language: "en" },
  }),
}));

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useAdminCapabilitiesQuery: () => h.list,
  useListTeamsQuery: () => ({ data: [] }),
  useSetCapabilityDefaultOnMutation: () => [vi.fn(), { isLoading: false }],
}));

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarn: vi.fn(), showInfo: vi.fn() }),
}));

// Isolate the page from the drawer (which drags in TuningFieldRenderer + prompt hooks).
vi.mock("./CapabilityTeamMatrixDrawer", () => ({
  CapabilityTeamMatrixDrawer: () => null,
}));

import CapabilitiesPage from "./CapabilitiesPage";

function cap(over: Partial<CapabilityEnablementItem> & Pick<CapabilityEnablementItem, "id">): CapabilityEnablementItem {
  return {
    name: `cap.${over.id}`,
    version: "1.0.0",
    icon: "extension",
    team_scope: "admin_gated",
    default_on: false,
    enabled_team_ids: [],
    team_settings_fields: [],
    ...over,
  };
}

function render(): string {
  return renderToStaticMarkup(<CapabilitiesPage />);
}

describe("CapabilitiesPage states", () => {
  beforeEach(() => {
    h.list = { data: undefined, isLoading: false, isError: false };
  });

  it("shows the loading state while the catalog is fetching", () => {
    h.list = { data: undefined, isLoading: true, isError: false };
    expect(render()).toContain("rework.admin.capabilities.loading");
  });

  it("shows the error state when the catalog fails to load", () => {
    h.list = { data: undefined, isLoading: false, isError: true };
    expect(render()).toContain("rework.admin.capabilities.loadError");
  });

  it("shows the empty state when no capability is advertised", () => {
    h.list = { data: { items: [] }, isLoading: false, isError: false };
    expect(render()).toContain("rework.admin.capabilities.empty");
  });
});

describe("CapabilitiesPage catalog rows", () => {
  it("renders each capability with enabled-team count and neutral health", () => {
    h.list = {
      data: {
        items: [
          cap({ id: "document_access", team_scope: "default_on", default_on: true, enabled_team_ids: ["nb", "ops"] }),
          cap({ id: "web_search", team_scope: "admin_gated", default_on: false, enabled_team_ids: ["nb"] }),
        ],
      },
      isLoading: false,
      isError: false,
    };
    const html = render();

    // Enabled-team counts come from enabled_team_ids length.
    expect(html).toContain(">2<");
    expect(html).toContain(">1<");

    // Health is neutral (no resting per-capability count until the sweep, #1975).
    expect(html).toContain("rework.admin.capabilities.health.pending");
    expect(html).not.toContain("rework.admin.capabilities.health.suspended");

    // Manage-teams action is offered per row.
    expect(html).toContain("rework.admin.capabilities.manageTeams");
  });

  it("reflects the default-on flag on the toggle (checked only for default-on caps)", () => {
    h.list = {
      data: { items: [cap({ id: "only_on", default_on: true })] },
      isLoading: false,
      isError: false,
    };
    expect(render()).toContain("checked");
  });
});
