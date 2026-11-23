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
import { beforeEach, describe, expect, it, vi } from "vitest";

let givenName: string | null = null;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { name?: string }) => (opts?.name ? `${key}:${opts.name}` : key),
  }),
}));
vi.mock("../../../../security/KeycloakService", () => ({
  KeyCloakService: { GetUserGivenName: () => givenName },
}));
vi.mock("@shared/atoms/ButtonGroup/ButtonGroup.tsx", () => ({
  default: ({
    items,
    selectedIndex,
    onSelectedIndexChange,
  }: {
    items: { label: string }[];
    selectedIndex: number;
    onSelectedIndexChange: (index: number) => void;
  }) => (
    <div>
      {`tabs:${items.map((i) => i.label).join(",")}`}
      {items.map((item, index) => (
        <button
          key={item.label}
          type="button"
          data-label={item.label}
          data-selected={index === selectedIndex}
          onClick={() => onSelectedIndexChange(index)}
        >
          {item.label}
        </button>
      ))}
    </div>
  ),
}));
vi.mock("./HomeSearch/HomeSearch.tsx", () => ({ default: () => null }));
vi.mock("./RecentAgents/RecentAgents.tsx", () => ({ default: () => null }));
vi.mock("./ActivityKpis/ActivityKpis.tsx", () => ({ default: () => null }));
vi.mock("./ResponsibleAiSection/ResponsibleAiSection.tsx", () => ({
  default: ({ kpiAvailable = true }: { kpiAvailable?: boolean }) =>
    kpiAvailable ? "responsible:full" : "responsible:cleanup",
}));
vi.mock("./TopAgents/TopAgents.tsx", () => ({ default: () => null }));
vi.mock("./TopTeams/TopTeams.tsx", () => ({ default: () => null }));
vi.mock("./MarketplaceTopPrompts/MarketplaceTopPrompts.tsx", () => ({ default: () => null }));
vi.mock("./AdvancedQuickAccess/AdvancedQuickAccess.tsx", () => ({
  default: ({ featured, askAgent }: { featured: unknown[]; askAgent?: { display_name: string } | null }) =>
    `advanced:${featured.length}:${askAgent?.display_name ?? "none"}`,
}));
const kpi = vi.hoisted(() => ({ available: true }));
const homeQuery = vi.hoisted(() => ({ current: { data: undefined as unknown, isLoading: false } }));
vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useMyHomeQuery: () => homeQuery.current,
}));
vi.mock("../../../../hooks/useFrontendBootstrap", () => ({
  useFrontendBootstrap: () => ({ bootstrap: { kpi_analytics_available: kpi.available }, isLoading: false }),
}));

import HomePage from "./HomePage";

describe("HomePage greeting", () => {
  beforeEach(() => {
    givenName = null;
    homeQuery.current = { data: { layout: "classic", featured: [] }, isLoading: false };
    kpi.available = true;
  });

  it("drops activity metrics without a KPI store but keeps cleanup available", () => {
    expect(renderToStaticMarkup(<HomePage />)).toContain(
      "tabs:rework.home.tabs.quickAccess,rework.home.tabs.activity,rework.home.tabs.trending",
    );
    kpi.available = false;
    const html = renderToStaticMarkup(<HomePage />);
    expect(html).toContain("tabs:rework.home.tabs.quickAccess,rework.home.tabs.trending");
    expect(html).toContain("responsible:cleanup");
    expect(html).not.toContain("responsible:full");
  });

  it("keeps Trends selected when KPI availability changes", () => {
    const container = document.createElement("div");
    const root = createRoot(container);
    try {
      act(() => root.render(<HomePage />));
      act(() => (container.querySelector('[data-label="rework.home.tabs.trending"]') as HTMLButtonElement).click());
      kpi.available = false;
      act(() => root.render(<HomePage />));
      expect(container.querySelector('[data-label="rework.home.tabs.trending"]')?.getAttribute("data-selected")).toBe(
        "true",
      );
    } finally {
      act(() => root.unmount());
    }
  });

  it("greets with the token given name, like the chat welcome does", () => {
    givenName = "Ada";
    expect(renderToStaticMarkup(<HomePage />)).toContain("rework.home.greetingNamed:Ada");
  });

  it("falls back to the unnamed greeting rather than showing an identifier", () => {
    const html = renderToStaticMarkup(<HomePage />);
    expect(html).toContain("rework.home.greeting<");
    expect(html).not.toContain("greetingNamed");
  });
});

describe("HomePage mode", () => {
  beforeEach(() => {
    givenName = null;
  });

  it("shows the advanced quick access with the featured and question agents", () => {
    homeQuery.current = {
      data: { layout: "advanced", featured: [{}, {}], ask_agent: { display_name: "Juriste" } },
      isLoading: false,
    };
    const html = renderToStaticMarkup(<HomePage />);
    expect(html).toContain("advanced:2:Juriste");
    expect(html).not.toContain("rework.home.subtitle");
  });

  it("keeps the classic home when the mode cannot be read", () => {
    homeQuery.current = { data: undefined, isLoading: false };
    expect(renderToStaticMarkup(<HomePage />)).toContain("rework.home.subtitle");
  });

  it("renders neither home while the mode loads", () => {
    homeQuery.current = { data: undefined, isLoading: true };
    const html = renderToStaticMarkup(<HomePage />);
    expect(html).not.toContain("rework.home.subtitle");
    expect(html).not.toContain("advanced:");
  });
});
