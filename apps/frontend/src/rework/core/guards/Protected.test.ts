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

import { describe, it, expect } from "vitest";
import {
  adminLandingPath,
  canEnterAdminSection,
  isProtectedAllowed,
  type ProtectedCapabilities,
  type ProtectedRequirement,
} from "./Protected";

const NONE: ProtectedCapabilities = {
  canAdmin: false,
  canObservePlatform: false,
  canManageTeams: false,
  canManagePlatformAccess: false,
  canManageFeatures: false,
  canEditPlatformPrompt: false,
};

const caps = (held: Partial<ProtectedCapabilities>): ProtectedCapabilities => ({ ...NONE, ...held });

/** Each requirement and the one flag that satisfies it on its own. */
const REQUIREMENTS: [ProtectedRequirement, keyof ProtectedCapabilities][] = [
  ["admin", "canAdmin"],
  ["observer", "canObservePlatform"],
  ["teams", "canManageTeams"],
  ["platformAccess", "canManagePlatformAccess"],
  ["features", "canManageFeatures"],
  ["platformPrompt", "canEditPlatformPrompt"],
];

describe("isProtectedAllowed", () => {
  it.each(REQUIREMENTS)('allows the holder of the matching role for requires="%s"', (requires, flag) => {
    expect(isProtectedAllowed(requires, caps({ [flag]: true }))).toBe(true);
  });

  it.each(REQUIREMENTS)('allows a platform_admin for requires="%s"', (requires) => {
    expect(isProtectedAllowed(requires, caps({ canAdmin: true }))).toBe(true);
  });

  it.each(REQUIREMENTS)('denies a user with no role for requires="%s"', (requires) => {
    expect(isProtectedAllowed(requires, NONE)).toBe(false);
  });

  it("does not let one delegated role stand in for another", () => {
    const teamManager = caps({ canManageTeams: true });
    expect(isProtectedAllowed("features", teamManager)).toBe(false);
    expect(isProtectedAllowed("platformPrompt", teamManager)).toBe(false);
    expect(isProtectedAllowed("admin", teamManager)).toBe(false);
    expect(isProtectedAllowed("platformAccess", teamManager)).toBe(false);
    const accessManager = caps({ canManagePlatformAccess: true });
    expect(isProtectedAllowed("teamRoster", accessManager)).toBe(true);
    expect(isProtectedAllowed("teams", accessManager)).toBe(false);
    expect(isProtectedAllowed("admin", accessManager)).toBe(false);
  });

  it("denies a platform_observer the admin tier", () => {
    expect(isProtectedAllowed("admin", caps({ canObservePlatform: true }))).toBe(false);
  });
});

describe("canEnterAdminSection", () => {
  it.each(REQUIREMENTS)("opens the admin shell for a holder of %s", (_requires, flag) => {
    expect(canEnterAdminSection(caps({ [flag]: true }))).toBe(true);
  });

  it("keeps a user with no platform role out", () => {
    expect(canEnterAdminSection(NONE)).toBe(false);
  });
});

describe("adminLandingPath", () => {
  it("sends an access-only manager to Platform Access", () => {
    expect(adminLandingPath(caps({ canManagePlatformAccess: true }))).toBe("/admin/platform-access");
  });

  it("keeps the platform administrator landing on teams", () => {
    expect(adminLandingPath(caps({ canAdmin: true }))).toBe("/admin/teams");
  });
});
