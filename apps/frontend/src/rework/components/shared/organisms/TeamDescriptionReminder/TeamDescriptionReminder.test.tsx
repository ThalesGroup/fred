// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import type { Space } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

const access = vi.hoisted(() => ({ offered: true, allowed: true }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@core/hooks/useSpaceAccess", () => ({ useSpaceAccess: () => access }));
vi.mock("react-router-dom", () => ({
  Link: ({ to, children }: { to: string; children: ReactNode }) => <a href={to}>{children}</a>,
}));
import TeamDescriptionReminder from "./TeamDescriptionReminder";

const space: Space = {
  id: "team-1",
  kind: "team",
  name: "Team",
  description: null,
  parent_id: "org",
  personal_owner: null,
  path: ["org", "team-1"],
};
const html = (overrides: Partial<Space> = {}) =>
  renderToStaticMarkup(<TeamDescriptionReminder space={{ ...space, ...overrides }} />);

beforeEach(() => {
  access.offered = true;
  access.allowed = true;
});
describe("TeamDescriptionReminder", () => {
  it("links an undescribed team to its parameters using Weaver management permission", () => {
    expect(html()).toContain('href="/team/team-1/settings/parameters"');
    expect(html()).toContain('data-color="info"');
  });
  it("keeps the navigation hint during a permission recheck, then hides on refusal", () => {
    access.allowed = false;
    expect(html()).toContain("rework.teamDescription.reminder.title");
    access.offered = false;
    expect(html()).toBe("");
  });
  it("disappears after the canonical description is saved", () => {
    expect(html({ description: "Research into safer AI systems." })).toBe("");
  });
  it.each(["organization", "project", "personal"] as const)("does not solicit a description for %s", (kind) => {
    expect(html({ kind })).toBe("");
  });
});
