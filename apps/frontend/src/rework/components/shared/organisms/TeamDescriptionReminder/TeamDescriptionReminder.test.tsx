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
import type { ReactNode } from "react";
import type { TeamWithPermissions } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("react-router-dom", () => ({
  Link: ({ to, children }: { to: string; children: ReactNode }) => <a href={to}>{children}</a>,
}));

import TeamDescriptionReminder from "./TeamDescriptionReminder.tsx";

function team(overrides: Partial<TeamWithPermissions>): TeamWithPermissions {
  return { id: "team-1", name: "Team One", permissions: ["can_read"], ...overrides } as TeamWithPermissions;
}

const html = (value: TeamWithPermissions | undefined, withSettingsLink = true) =>
  renderToStaticMarkup(<TeamDescriptionReminder team={value} withSettingsLink={withSettingsLink} />);

describe("TeamDescriptionReminder", () => {
  it("asks a team admin to describe a team that still has the default description", () => {
    const markup = html(team({ description_is_placeholder: true, permissions: ["can_read", "can_update_info"] }));
    expect(markup).toContain("rework.teamDescription.reminder.title");
    expect(markup).toContain('href="/team/team-1/settings/parameters"');
    expect(markup).toContain('data-color="info"');
  });

  it("drops the link on the settings page", () => {
    const markup = html(team({ description_is_placeholder: true, permissions: ["can_update_info"] }), false);
    expect(markup).toContain("rework.teamDescription.reminder.title");
    expect(markup).not.toContain("href=");
  });

  it("stays hidden for a member who is not a team admin", () => {
    expect(html(team({ description_is_placeholder: true }))).toBe("");
  });

  it("stays hidden once the team is described, and for a personal space", () => {
    expect(html(team({ description_is_placeholder: false, permissions: ["can_update_info"] }))).toBe("");
    expect(html(team({ id: "personal-me", permissions: ["can_read", "can_update_agents"] }))).toBe("");
    expect(html(undefined)).toBe("");
  });
});
