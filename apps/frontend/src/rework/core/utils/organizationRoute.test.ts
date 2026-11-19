// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { isOrganizationRoute, isSpaceSettingsRoute } from "./organizationRoute";

describe("organization routes", () => {
  it("covers Home and the working organization's content, not its teams", () => {
    expect(isOrganizationRoute("/home", undefined)).toBe(true);
    expect(isOrganizationRoute("/team/org/resources", "org")).toBe(true);
    expect(isOrganizationRoute("/team/org", "org")).toBe(true);
    expect(isOrganizationRoute("/team/team-1/resources", "org")).toBe(false);
    expect(isOrganizationRoute("/team/org/resources", undefined)).toBe(false);
    expect(isOrganizationRoute("/homework", "org")).toBe(false);
  });

  it("recognizes a space's settings and usage pages", () => {
    expect(isSpaceSettingsRoute("/team/org/settings/models")).toBe(true);
    expect(isSpaceSettingsRoute("/team/org/usage")).toBe(true);
    expect(isSpaceSettingsRoute("/team/org/resources")).toBe(false);
  });
});
