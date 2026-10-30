// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { describe, expect, it } from "vitest";
import type { ProtectedCapabilities } from "./Protected";
import { adminIndexPath, organizationOwnerPages } from "./organizationOwnerPages";

const NONE: ProtectedCapabilities = {
  canAdmin: false,
  canObservePlatform: false,
  canManageTeams: false,
  canManagePlatformAccess: false,
  canManageFeatures: false,
  canEditPlatformPrompt: false,
};
const access = (held: Partial<ProtectedCapabilities>, supervision = false, platformAccessEnabled = false) => ({
  capabilities: { ...NONE, ...held },
  supervision,
  platformAccessEnabled,
});
const paths = (...args: Parameters<typeof access>) => organizationOwnerPages(access(...args)).map((page) => page.to);

describe("organizationOwnerPages", () => {
  it("puts Supervision first when the person may open it", () => {
    expect(paths({ canManageFeatures: true }, true)).toEqual(["/admin/supervision", "/admin/features"]);
  });

  it("lists only the pages the person may open, in menu order", () => {
    expect(paths({ canManageFeatures: true })).toEqual(["/admin/features"]);
    expect(paths({ canAdmin: true }, true, true)).toEqual([
      "/admin/supervision",
      "/admin/teams",
      "/admin/platform-roles",
      "/admin/tasks",
      "/admin/analytics",
      "/admin/platform-prompt",
      "/admin/annonces",
      "/admin/interface",
      "/admin/marketplaces",
      "/admin/migration",
      "/admin/corpus-audit",
      "/admin/self-test",
      "/admin/platform-access",
    ]);
  });

  it("leaves Platform access out when the deployment disables it", () => {
    expect(paths({ canManagePlatformAccess: true })).toEqual(["/admin/teams"]);
    expect(paths({ canManagePlatformAccess: true }, false, true)).toEqual(["/admin/teams", "/admin/platform-access"]);
  });
});

describe("adminIndexPath", () => {
  it("lands on the first organization menu page: Supervision when allowed", () => {
    expect(adminIndexPath({ ...access({ canManageFeatures: true }, true), platformOwner: true })).toBe(
      "/admin/supervision",
    );
  });

  it("lands on the first allowed page without Supervision", () => {
    expect(adminIndexPath({ ...access({ canManageFeatures: true }), platformOwner: true })).toBe("/admin/features");
    expect(adminIndexPath({ ...access({ canObservePlatform: true }), platformOwner: false })).toBe("/admin/analytics");
  });

  it("opens the platform space for a platform admin with no organization page", () => {
    expect(adminIndexPath({ ...access({}), platformOwner: true })).toBe("/admin/organizations");
  });

  it("keeps everyone else out", () => {
    expect(adminIndexPath({ ...access({}), platformOwner: false })).toBe("/unauthorized");
  });
});
