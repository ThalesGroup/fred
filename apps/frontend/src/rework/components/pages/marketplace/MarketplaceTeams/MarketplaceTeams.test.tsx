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

// Regression coverage for #2068: `GET /teams` (via `useListTeamsQuery`)
// intentionally includes personal spaces — it also feeds the bootstrap-driven
// sidebar/team switcher — but the marketplace must never list one, including
// the caller's own. `t` is mocked to echo its key so we can assert on which
// section (yourTeams/otherTeams) rendered which team id.

import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Team, TeamWithPermissions } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

const h = vi.hoisted(() => ({
  teams: { data: [] as Team[] } as { data?: Team[] },
  bootstrap: {
    activeTeam: { id: "personal-me" } as TeamWithPermissions | undefined,
    availableTeams: [{ id: "personal-me" }, { id: "fredlab" }] as Team[],
    bootstrap: undefined,
    isLoading: false,
  },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useListTeamsQuery: () => h.teams,
}));

vi.mock("../../../../../hooks/useFrontendBootstrap", () => ({
  useFrontendBootstrap: () => h.bootstrap,
}));

vi.mock("@shared/organisms/TeamCard/TeamCard.tsx", () => ({
  default: ({ team }: { team: Team }) => <div data-testid={`team-card-${team.id}`}>{team.id}</div>,
}));

import MarketplaceTeams from "./MarketplaceTeams";

function render(): string {
  return renderToStaticMarkup(<MarketplaceTeams />);
}

describe("MarketplaceTeams personal-space exclusion", () => {
  beforeEach(() => {
    h.bootstrap = {
      activeTeam: { id: "personal-me" } as TeamWithPermissions,
      availableTeams: [{ id: "personal-me" }, { id: "fredlab" }] as Team[],
      bootstrap: undefined,
      isLoading: false,
    };
  });

  it("never renders the caller's own personal space, even though it is a member", () => {
    h.teams = {
      data: [
        { id: "personal-me", name: "personal", is_member: true } as Team,
        { id: "fredlab", name: "fredlab", is_member: true } as Team,
      ],
    };
    const html = render();
    expect(html).not.toContain("team-card-personal-me");
    expect(html).toContain("team-card-fredlab");
  });

  it("never renders another user's personal space in the discover section", () => {
    h.teams = {
      data: [
        { id: "personal-me", name: "personal", is_member: true } as Team,
        { id: "personal-other-user", name: "personal", is_member: false } as Team,
        { id: "fredlab", name: "fredlab", is_member: false } as Team,
      ],
    };
    const html = render();
    expect(html).not.toContain("team-card-personal-other-user");
    expect(html).toContain("team-card-fredlab");
  });
});
