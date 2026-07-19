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
  PERSONAL_SCOPE_ROW_ID,
  capabilityPersonalScopeChoice,
  enabledTeamCount,
  excludePersonalTeams,
  filterTeamsByName,
  isCapabilityOnForTeam,
  isCapabilityUnused,
  isPersonalTeamId,
  personalSpaceCount,
  seedSettingsFromFields,
  sortTeamsForMatrix,
  teamCapabilityChoice,
  teamCapabilityState,
  teamMatrixStatus,
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

describe("teamCapabilityChoice (explicit tri-state position)", () => {
  it("reports the explicit grant and the explicit opt-out", () => {
    const cap = { default_on: true, enabled_team_ids: ["nb"], disabled_team_ids: ["legal"] };
    expect(teamCapabilityChoice(cap, "nb")).toBe("enabled");
    expect(teamCapabilityChoice(cap, "legal")).toBe("disabled");
  });

  it("reports `default` when no explicit tuple exists, whatever the platform default", () => {
    // The *choice* is "default" either way — only the effective state differs.
    expect(teamCapabilityChoice({ default_on: true, enabled_team_ids: [] }, "nb")).toBe("default");
    expect(teamCapabilityChoice({ default_on: false, enabled_team_ids: [] }, "nb")).toBe("default");
  });

  it("lets the opt-out beat the grant (FGA: disable overrides enable)", () => {
    const cap = { default_on: false, enabled_team_ids: ["nb"], disabled_team_ids: ["nb"] };
    expect(teamCapabilityChoice(cap, "nb")).toBe("disabled");
  });
});

describe("capabilityPersonalScopeChoice (RFC §8.4 personal-space class)", () => {
  it("reflects the capability's personal_scope tri-state", () => {
    expect(capabilityPersonalScopeChoice({ personal_scope: "enabled" })).toBe("enabled");
    expect(capabilityPersonalScopeChoice({ personal_scope: "disabled" })).toBe("disabled");
    expect(capabilityPersonalScopeChoice({ personal_scope: "default" })).toBe("default");
  });

  it("defaults to `default` when the field is absent (older payloads)", () => {
    expect(capabilityPersonalScopeChoice({})).toBe("default");
  });
});

describe("isPersonalTeamId / excludePersonalTeams", () => {
  it("recognizes the personal-space id prefix", () => {
    expect(isPersonalTeamId("personal-abc")).toBe(true);
    expect(isPersonalTeamId("team-a")).toBe(false);
    expect(isPersonalTeamId(undefined)).toBe(false);
    expect(isPersonalTeamId(null)).toBe(false);
  });

  it("drops every personal space from the roster", () => {
    const teams = [{ id: "team-a" }, { id: "personal-u1" }, { id: "team-b" }, { id: "personal-u2" }];
    expect(excludePersonalTeams(teams).map((t) => t.id)).toEqual(["team-a", "team-b"]);
  });

  it("uses a reserved synthetic row id that no team id can collide with", () => {
    expect(PERSONAL_SCOPE_ROW_ID).toBe("__personal_scope__");
    expect(isPersonalTeamId(PERSONAL_SCOPE_ROW_ID)).toBe(false);
  });
});

describe("sortTeamsForMatrix", () => {
  const teams = [
    { id: "d2", name: "Zulu (default)" },
    { id: "off", name: "Legal (disabled)" },
    { id: "on2", name: "Ops (enabled)" },
    { id: "d1", name: "Alpha (default)" },
    { id: "on1", name: "Data (enabled)" },
  ];
  const cap = { default_on: false, enabled_team_ids: ["on1", "on2"], disabled_team_ids: ["off"] };

  it("orders enabled, then disabled, then the default majority, alphabetically within groups", () => {
    expect(sortTeamsForMatrix(teams, cap).map((t) => t.id)).toEqual(["on1", "on2", "off", "d1", "d2"]);
  });

  it("does not mutate the input list", () => {
    const before = [...teams];
    sortTeamsForMatrix(teams, cap);
    expect(teams).toEqual(before);
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

  it("ignores personal-space tuples — those belong to personalSpaceCount", () => {
    // Explicit personal grants (e.g. leftovers from the withdrawn
    // personal_defaults seeding) must not inflate the TEAM count…
    expect(enabledTeamCount({ default_on: false, enabled_team_ids: ["a", "personal-u1", "personal-u2"] })).toBe(1);
    // …and personal opt-outs must not subtract from a roster that never
    // contained them.
    expect(enabledTeamCount({ default_on: true, disabled_team_ids: ["personal-u1", "b"], total_team_count: 12 })).toBe(
      11,
    );
  });
});

describe("personalSpaceCount (RFC §8.4 personal-space class)", () => {
  it("counts the whole personal roster when the class is enabled", () => {
    expect(personalSpaceCount({ default_on: false, personal_scope: "enabled", total_personal_space_count: 40 })).toBe(
      40,
    );
  });

  it("subtracts explicit per-space opt-outs from a class-on roster", () => {
    expect(
      personalSpaceCount({
        default_on: false,
        personal_scope: "enabled",
        disabled_team_ids: ["personal-u1", "legal"],
        total_personal_space_count: 40,
      }),
    ).toBe(39);
  });

  it("inherits default-on when the class position is default", () => {
    expect(personalSpaceCount({ default_on: true, personal_scope: "default", total_personal_space_count: 40 })).toBe(
      40,
    );
    expect(personalSpaceCount({ default_on: true, total_personal_space_count: 40 })).toBe(40);
  });

  it("returns null (unknown) when the class is on but the user directory is unavailable", () => {
    expect(
      personalSpaceCount({ default_on: false, personal_scope: "enabled", total_personal_space_count: 0 }),
    ).toBeNull();
    expect(personalSpaceCount({ default_on: true, personal_scope: "default" })).toBeNull();
  });

  it("counts only explicit per-space grants when the class is off", () => {
    // Explicit grants survive both class-off and personal_disabled (FGA:
    // `enabled` is outside the `but not personal_block` subtraction).
    expect(
      personalSpaceCount({
        default_on: true,
        personal_scope: "disabled",
        enabled_team_ids: ["personal-u1", "ops"],
        total_personal_space_count: 40,
      }),
    ).toBe(1);
    expect(personalSpaceCount({ default_on: false, personal_scope: "default", total_personal_space_count: 40 })).toBe(
      0,
    );
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

  it("stays false when every team opted out but personal spaces still inherit default-on", () => {
    expect(isCapabilityUnused({ default_on: true, disabled_team_ids: ["a", "b"], total_team_count: 2 })).toBe(false);
  });

  it("is true for a default-on capability every team opted out of, once personal spaces are blocked too", () => {
    expect(
      isCapabilityUnused({
        default_on: true,
        disabled_team_ids: ["a", "b"],
        total_team_count: 2,
        personal_scope: "disabled",
        total_personal_space_count: 40,
      }),
    ).toBe(true);
  });

  it("is false when only the personal-space class reaches anyone", () => {
    expect(
      isCapabilityUnused({
        default_on: false,
        enabled_team_ids: [],
        personal_scope: "enabled",
        total_personal_space_count: 40,
      }),
    ).toBe(false);
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

  it("finds a team from the global registry the caller doesn't belong to (e.g. fredlab)", () => {
    // Regression: the drawer used to source its team list from the caller-scoped
    // `/teams` endpoint, so a team the admin wasn't a member of (like `fredlab`)
    // never reached this filter at all and a search for it always came up empty.
    const registry = [...teams, { name: "fredlab" }];
    expect(filterTeamsByName(registry, "fredlab")).toEqual([{ name: "fredlab" }]);
    expect(filterTeamsByName(registry, "FredLab")).toEqual([{ name: "fredlab" }]);
  });
});

describe("teamMatrixStatus (drawer loading/error/empty precedence)", () => {
  const base = { teamsLoading: false, teamsError: false, registryEmpty: false, hasQuery: false, visibleCount: 3 };

  it("is 'ready' when the registry loaded with teams and no active search", () => {
    expect(teamMatrixStatus(base)).toBe("ready");
  });

  it("is 'loading' while the registry query is in flight, above every other state", () => {
    expect(teamMatrixStatus({ ...base, teamsLoading: true })).toBe("loading");
    expect(teamMatrixStatus({ ...base, teamsLoading: true, teamsError: true, registryEmpty: true })).toBe("loading");
  });

  it("is 'error' when the registry query failed, and never silently becomes an empty list", () => {
    expect(teamMatrixStatus({ ...base, teamsError: true })).toBe("error");
    expect(teamMatrixStatus({ ...base, teamsError: true, registryEmpty: true })).toBe("error");
  });

  it("is 'registryEmpty' when no team exists at all, distinct from a search yielding nothing", () => {
    expect(teamMatrixStatus({ ...base, registryEmpty: true })).toBe("registryEmpty");
    // Even with a stray query typed in, "no teams exist" outranks "no match".
    expect(teamMatrixStatus({ ...base, registryEmpty: true, hasQuery: true, visibleCount: 0 })).toBe("registryEmpty");
  });

  it("is 'searchEmpty' only when teams exist but the active search matches none", () => {
    expect(teamMatrixStatus({ ...base, hasQuery: true, visibleCount: 0 })).toBe("searchEmpty");
  });

  it("is not 'searchEmpty' when a query is active but still matches something", () => {
    expect(teamMatrixStatus({ ...base, hasQuery: true, visibleCount: 1 })).toBe("ready");
  });
});
