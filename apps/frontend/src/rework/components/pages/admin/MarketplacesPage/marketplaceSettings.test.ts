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

import { describe, expect, it } from "vitest";
import type { TeamMarketplaceSettings } from "../../../../../slices/legacyControlPlane/legacyControlPlaneOpenApi";
import { choiceColor, overrideForChoice, parseQuota, publishingChoice, turnsTeamOff } from "./marketplaceSettings";

const team = (override: boolean | null, effective: boolean): TeamMarketplaceSettings => ({
  team_id: "t",
  team_name: "T",
  agents_publishing_enabled_override: override,
  agents_publish_quota_override: null,
  agents_publishing_enabled: effective,
  agents_publish_quota: 5,
  published_count: 0,
});

describe("marketplaceSettings", () => {
  it("maps overrides to choices and back", () => {
    expect(publishingChoice(team(null, true))).toBe("default");
    expect(publishingChoice(team(true, true))).toBe("enabled");
    expect(publishingChoice(team(false, false))).toBe("disabled");
    expect(overrideForChoice("default")).toBeNull();
    expect(overrideForChoice("enabled")).toBe(true);
    expect(overrideForChoice("disabled")).toBe(false);
  });

  it("detects only an on → off change of the effective switch", () => {
    expect(turnsTeamOff(team(true, true), "default", false)).toBe(true);
    expect(turnsTeamOff(team(true, true), "default", true)).toBe(false);
    expect(turnsTeamOff(team(null, true), "disabled", true)).toBe(true);
    expect(turnsTeamOff(team(false, false), "default", false)).toBe(false);
  });

  it("accepts only whole quotas of at least 1", () => {
    expect(parseQuota("3")).toBe(3);
    expect(parseQuota(" 12 ")).toBe(12);
    for (const invalid of ["", "0", "-1", "2.5", "abc"]) expect(parseQuota(invalid)).toBeNull();
  });

  it("colours Enabled success and Disabled error, Default keeps the group colour", () => {
    expect(choiceColor("enabled")).toBe("success");
    expect(choiceColor("disabled")).toBe("error");
    expect(choiceColor("default")).toBeUndefined();
  });
});
