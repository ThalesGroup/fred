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
import { beforeEach, describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({
  isPersonalTeam: false,
  language: "en",
  result: { data: undefined, isLoading: false, isError: false } as {
    data?: { items: Array<Record<string, unknown>> };
    isLoading: boolean;
    isError: boolean;
  },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: h.language } }),
}));
vi.mock("react-router-dom", () => ({
  Link: ({ to, children, className }: { to: string; children: React.ReactNode; className: string }) => (
    <a href={to} className={className}>
      {children}
    </a>
  ),
}));
vi.mock("../../../../hooks/useSelectedTeam.ts", () => ({
  useSelectedTeam: () => ({ teamId: "team-1", isPersonalTeam: h.isPersonalTeam }),
}));
vi.mock("@rework/features/applications/useTeamApplications.ts", () => ({
  useTeamApplications: () => h.result,
}));

import TeamApplicationsPage from "./TeamApplicationsPage.tsx";

const application = {
  id: "example",
  version: "1.0.0",
  name: { en: "Example", fr: "Exemple" },
  description: { en: "An example application", fr: "Une application d'exemple" },
  icon: "extension",
  ui_prefix: "/apps/example",
};

function render() {
  return renderToStaticMarkup(<TeamApplicationsPage />);
}

describe("TeamApplicationsPage", () => {
  beforeEach(() => {
    h.isPersonalTeam = false;
    h.language = "en";
    h.result = { data: undefined, isLoading: false, isError: false };
  });

  it("renders the generic empty state when the authorized catalog is empty", () => {
    h.result.data = { items: [] };
    expect(render()).toContain("teamAppsPage.noAppDescription");
  });

  it("links an authorized application under the selected team", () => {
    h.result.data = { items: [application] };
    const html = render();
    expect(html).toContain('href="/team/team-1/apps/example"');
    expect(html).toContain("Example");
    expect(html).toContain("An example application");
  });

  // Labels travel with the application rather than in Fred's own bundle, so the
  // card has to resolve them against the active language, not a fixed one.
  it("renders application labels in the active locale", () => {
    h.language = "fr";
    h.result.data = { items: [application] };
    const html = render();
    expect(html).toContain("Exemple");
    expect(html).not.toContain("Example");
  });

  it("never offers applications in a personal space", () => {
    h.isPersonalTeam = true;
    h.result.data = { items: [application] };
    const html = render();
    expect(html).toContain("teamAppsPage.noAppDescription");
    expect(html).not.toContain('href="/team/team-1/apps/example"');
  });
});
