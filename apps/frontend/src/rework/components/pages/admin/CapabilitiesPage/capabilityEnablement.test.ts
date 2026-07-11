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
import type { FieldSpec } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  enabledTeamCount,
  isCapabilityOnForTeam,
  scopeBadge,
  seedSettingsFromFields,
  teamCapabilityState,
} from "./capabilityEnablement";

describe("teamCapabilityState (RFC §8.5 tri-state)", () => {
  it("reports an explicit grant as `enabled`", () => {
    const cap = { default_on: false, enabled_team_ids: ["nb", "ops"] };
    expect(teamCapabilityState(cap, "nb")).toBe("enabled");
  });

  it("reports a default-on capability with no grant as `inherited`", () => {
    const cap = { default_on: true, enabled_team_ids: ["ops"] };
    expect(teamCapabilityState(cap, "nb")).toBe("inherited");
  });

  it("reports an admin-gated capability with no grant as `off`", () => {
    const cap = { default_on: false, enabled_team_ids: [] };
    expect(teamCapabilityState(cap, "nb")).toBe("off");
  });

  it("prefers the explicit grant over inheritance", () => {
    const cap = { default_on: true, enabled_team_ids: ["nb"] };
    expect(teamCapabilityState(cap, "nb")).toBe("enabled");
  });

  it("treats a missing enabled_team_ids list as empty", () => {
    const cap = { default_on: false };
    expect(teamCapabilityState(cap, "nb")).toBe("off");
  });
});

describe("isCapabilityOnForTeam", () => {
  it("is true for explicit and inherited, false for off", () => {
    expect(isCapabilityOnForTeam({ default_on: false, enabled_team_ids: ["nb"] }, "nb")).toBe(true);
    expect(isCapabilityOnForTeam({ default_on: true, enabled_team_ids: [] }, "nb")).toBe(true);
    expect(isCapabilityOnForTeam({ default_on: false, enabled_team_ids: [] }, "nb")).toBe(false);
  });
});

describe("enabledTeamCount", () => {
  it("counts explicit grants and tolerates the absent list", () => {
    expect(enabledTeamCount({ enabled_team_ids: ["a", "b", "c"] })).toBe(3);
    expect(enabledTeamCount({})).toBe(0);
  });
});

describe("scopeBadge", () => {
  it("maps default_on and admin_gated to distinct tones", () => {
    expect(scopeBadge("default_on").tone).toBe("default-on");
    expect(scopeBadge("admin_gated").tone).toBe("admin-gated");
    expect(scopeBadge("default_on").labelKey).not.toBe(scopeBadge("admin_gated").labelKey);
  });
});

describe("seedSettingsFromFields", () => {
  const fields: FieldSpec[] = [
    { key: "retention_days", type: "integer", title: "Retention", default: 30 },
    { key: "mode", type: "select", title: "Mode", enum: ["fast", "rich"], default: "fast" },
    { key: "note", type: "string", title: "Note" },
  ];

  it("seeds declared defaults and skips fields without one", () => {
    expect(seedSettingsFromFields(fields)).toEqual({ retention_days: 30, mode: "fast" });
  });

  it("lets existing settings override the declared defaults", () => {
    expect(seedSettingsFromFields(fields, { retention_days: 7, note: "hello" })).toEqual({
      retention_days: 7,
      mode: "fast",
      note: "hello",
    });
  });

  it("returns an empty object for no fields", () => {
    expect(seedSettingsFromFields(undefined)).toEqual({});
  });
});
