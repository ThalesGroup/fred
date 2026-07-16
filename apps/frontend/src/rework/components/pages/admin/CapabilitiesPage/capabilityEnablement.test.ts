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
  filterTeamsByName,
  isCapabilityOnForTeam,
  isCapabilityUnused,
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

  it("reports an opt-out of a default-on capability as `off`, not `inherited`", () => {
    const cap = { default_on: true, enabled_team_ids: [], disabled_team_ids: ["nb"] };
    expect(teamCapabilityState(cap, "nb")).toBe("off");
  });

  it("lets an explicit opt-out beat an explicit grant (FGA: disable overrides enable)", () => {
    const cap = { default_on: true, enabled_team_ids: ["nb"], disabled_team_ids: ["nb"] };
    expect(teamCapabilityState(cap, "nb")).toBe("off");
  });
});

describe("isCapabilityOnForTeam", () => {
  it("is true for explicit and inherited, false for off", () => {
    expect(isCapabilityOnForTeam({ default_on: false, enabled_team_ids: ["nb"] }, "nb")).toBe(true);
    expect(isCapabilityOnForTeam({ default_on: true, enabled_team_ids: [] }, "nb")).toBe(true);
    expect(isCapabilityOnForTeam({ default_on: false, enabled_team_ids: [] }, "nb")).toBe(false);
  });

  it("is false for a team that opted out of a default-on capability", () => {
    expect(isCapabilityOnForTeam({ default_on: true, enabled_team_ids: [], disabled_team_ids: ["nb"] }, "nb")).toBe(
      false,
    );
  });
});

describe("enabledTeamCount", () => {
  it("counts explicit grants when the capability is not default-on", () => {
    expect(enabledTeamCount({ default_on: false, enabled_team_ids: ["a", "b", "c"], total_team_count: 12 })).toBe(3);
    expect(enabledTeamCount({ default_on: false })).toBe(0);
  });

  it("counts the roster minus opt-outs when the capability is default-on", () => {
    expect(
      enabledTeamCount({
        default_on: true,
        enabled_team_ids: ["a"],
        disabled_team_ids: ["b", "c"],
        total_team_count: 12,
      }),
    ).toBe(10);
  });

  it("counts the whole roster for a default-on capability nobody opted out of", () => {
    expect(enabledTeamCount({ default_on: true, enabled_team_ids: [], total_team_count: 12 })).toBe(12);
  });

  it("returns null (unknown) for a default-on capability with no roster", () => {
    // Keycloak disabled → total_team_count is 0; 0 would read as "nobody".
    expect(enabledTeamCount({ default_on: true, total_team_count: 0 })).toBeNull();
    expect(enabledTeamCount({ default_on: true })).toBeNull();
  });

  it("never goes negative when opt-outs outnumber the roster", () => {
    expect(enabledTeamCount({ default_on: true, disabled_team_ids: ["a", "b", "c"], total_team_count: 2 })).toBe(0);
  });
});

describe("isCapabilityUnused", () => {
  it("is true for a non-default-on capability nobody was granted", () => {
    expect(isCapabilityUnused({ default_on: false, enabled_team_ids: [] })).toBe(true);
    expect(isCapabilityUnused({ default_on: false })).toBe(true);
  });

  it("is false as soon as one team holds an explicit grant", () => {
    expect(isCapabilityUnused({ default_on: false, enabled_team_ids: ["nb"] })).toBe(false);
  });

  it("is false for a default-on capability, which reaches every team", () => {
    expect(isCapabilityUnused({ default_on: true, enabled_team_ids: [], total_team_count: 12 })).toBe(false);
  });

  it("is false for a default-on capability with an unknown roster", () => {
    // Unknown reach is not zero reach — dimming here would be a lie.
    expect(isCapabilityUnused({ default_on: true, total_team_count: 0 })).toBe(false);
  });

  it("is true for a default-on capability every team opted out of", () => {
    expect(isCapabilityUnused({ default_on: true, disabled_team_ids: ["a", "b"], total_team_count: 2 })).toBe(true);
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

describe("filterTeamsByName (matrix drawer search)", () => {
  const teams = [{ name: "Nightly Build" }, { name: "Ops" }, { name: "Data Science" }];

  it("matches case-insensitively on a substring", () => {
    expect(filterTeamsByName(teams, "night")).toEqual([{ name: "Nightly Build" }]);
    expect(filterTeamsByName(teams, "OPS")).toEqual([{ name: "Ops" }]);
  });

  it("treats a blank or whitespace-only query as no filter", () => {
    expect(filterTeamsByName(teams, "")).toEqual(teams);
    expect(filterTeamsByName(teams, "   ")).toEqual(teams);
  });

  it("ignores leading/trailing whitespace around the query", () => {
    expect(filterTeamsByName(teams, "  ops ")).toEqual([{ name: "Ops" }]);
  });

  it("returns an empty list when nothing matches", () => {
    expect(filterTeamsByName(teams, "zzz")).toEqual([]);
  });
});
