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
import type { ReactNode } from "react";
import type { Team, TeamWithPermissions } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

const h = vi.hoisted(() => ({
  teams: { data: [] as Team[] } as { data?: Team[] },
  bootstrap: {
    activeTeam: { id: "personal-me" } as TeamWithPermissions | undefined,
    availableTeams: [{ id: "personal-me" }, { id: "fredlab" }] as Team[],
    bootstrap: undefined,
    isLoading: false,
    refetch: vi.fn(),
  },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

// `renderToStaticMarkup` has no router context, so a real `Link`/`Navigate`
// throws (`useContext(...) is null`) the moment a member card wraps itself
// in one — stand in with plain markup, same as other page tests that don't
// need actual routing behaviour asserted.
vi.mock("react-router-dom", () => ({
  Link: ({ to, children, className }: { to: string; children: ReactNode; className?: string }) => (
    <a href={to} className={className}>
      {children}
    </a>
  ),
  Navigate: ({ to }: { to: string }) => <div data-testid="navigate" data-to={to} />,
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
      refetch: vi.fn(),
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
        { id: "fredlab", name: "fredlab", is_member: false, visibility: "public" } as Team,
      ],
    };
    const html = render();
    expect(html).not.toContain("team-card-personal-other-user");
    expect(html).toContain("team-card-fredlab");
  });
});

describe("MarketplaceTeams private-team exclusion", () => {
  beforeEach(() => {
    h.bootstrap = {
      activeTeam: { id: "personal-me" } as TeamWithPermissions,
      availableTeams: [{ id: "personal-me" }, { id: "fredlab" }] as Team[],
      bootstrap: undefined,
      isLoading: false,
      refetch: vi.fn(),
    };
  });

  // #2398: the server withholds the ReBAC `public` relation from a private
  // team, but that filter is skipped when authorization is disabled — the
  // page must not depend on it to keep a private team out of "discover".
  it("never renders a private team the caller is not a member of", () => {
    h.teams = {
      data: [
        { id: "acme", name: "acme", is_member: false, visibility: "private" } as Team,
        { id: "globex", name: "globex", is_member: false, visibility: "public" } as Team,
      ],
    };
    const html = render();
    expect(html).not.toContain("team-card-acme");
    expect(html).toContain("team-card-globex");
  });

  it("still renders a private team the caller is a member of", () => {
    h.teams = {
      data: [{ id: "fredlab", name: "fredlab", is_member: true, visibility: "private" } as Team],
    };
    expect(render()).toContain("team-card-fredlab");
  });

  // #2433: private is the platform default, so a payload missing the field
  // (version-skew backend) must err on non-disclosure — discover lists only
  // teams that are explicitly public.
  it("never renders a non-member team whose visibility is absent from the payload", () => {
    h.teams = {
      data: [
        { id: "skewed", name: "skewed", is_member: false } as Team,
        { id: "globex", name: "globex", is_member: false, visibility: "public" } as Team,
      ],
    };
    const html = render();
    expect(html).not.toContain("team-card-skewed");
    expect(html).toContain("team-card-globex");
  });
});

describe("MarketplaceTeams card navigability", () => {
  beforeEach(() => {
    h.bootstrap = {
      activeTeam: { id: "personal-me" } as TeamWithPermissions,
      availableTeams: [{ id: "personal-me" }, { id: "fredlab" }] as Team[],
      bootstrap: undefined,
      isLoading: false,
      refetch: vi.fn(),
    };
  });

  it("only wraps member-team cards in a navigation link, regardless of platform-admin status", () => {
    h.teams = {
      data: [
        { id: "fredlab", name: "fredlab", is_member: true } as Team,
        { id: "acme", name: "acme", is_member: false, visibility: "public" } as Team,
      ],
    };
    const html = render();
    expect(html).toContain(`<a href="/team/fredlab/agents"`);
    expect(html).not.toContain('href="/team/acme/agents"');
  });
});

describe("MarketplaceTeams search", () => {
  beforeEach(() => {
    h.bootstrap = {
      activeTeam: { id: "personal-me" } as TeamWithPermissions,
      availableTeams: [{ id: "personal-me" }, { id: "fredlab" }] as Team[],
      bootstrap: undefined,
      isLoading: false,
      refetch: vi.fn(),
    };
    h.teams = {
      data: [
        { id: "fredlab", name: "Fred Lab", is_member: true } as Team,
        { id: "acme", name: "Acme", is_member: false, visibility: "public" } as Team,
      ],
    };
  });

  it("renders every team when no search query is set", () => {
    const html = render();
    expect(html).toContain("team-card-fredlab");
    expect(html).toContain("team-card-acme");
  });
});
