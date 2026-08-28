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
  result: { data: undefined, isLoading: false, isError: false } as {
    data?: { catalog_revision: string; items: Array<Record<string, string>> };
    isLoading: boolean;
    isError: boolean;
  },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string, options?: { defaultValue?: string }) => options?.defaultValue ?? key }),
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
  name: "applications.example.name",
  description: "applications.example.description",
  icon: "extension",
  host_api_version: "1",
  contract_digest: "sha256:ea2a1abadce9b3f3b9b0b9390e8f042e819389dbe6b6bc62a14a0b67a646013a",
};

function render() {
  return renderToStaticMarkup(<TeamApplicationsPage />);
}

describe("TeamApplicationsPage", () => {
  beforeEach(() => {
    h.isPersonalTeam = false;
    h.result = { data: undefined, isLoading: false, isError: false };
  });

  it("renders the generic empty state when the authorized catalog is empty", () => {
    h.result.data = { catalog_revision: "revision", items: [] };
    expect(render()).toContain("teamAppsPage.noAppDescription");
  });

  it("links a compatible authorized application under the selected team", () => {
    h.result.data = { catalog_revision: "revision", items: [application] };
    const html = render();
    expect(html).toContain('href="/team/team-1/apps/example"');
    expect(html).toContain("applications.example.name");
    expect(html).not.toContain("teamAppsPage.localUnavailable");
  });

  it("keeps an authorized version mismatch visible but not executable", () => {
    h.result.data = { catalog_revision: "revision", items: [{ ...application, version: "2.0.0" }] };
    const html = render();
    expect(html).toContain("teamAppsPage.localUnavailable");
    expect(html).not.toContain('href="/team/team-1/apps/example"');
  });

  it("never offers applications in a personal space", () => {
    h.isPersonalTeam = true;
    h.result.data = { catalog_revision: "revision", items: [application] };
    const html = render();
    expect(html).toContain("teamAppsPage.noAppDescription");
    expect(html).not.toContain('href="/team/team-1/apps/example"');
  });
});
