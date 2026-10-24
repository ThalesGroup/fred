// Copyright Thales 2026
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0

import type {
  FrontendBootstrap,
  PlatformRoleRelation,
  PlatformRolesResponse,
  Team,
  TeamMember,
  TeamWithPermissions,
  UserTeamRelation,
} from "../../../../slices/legacyControlPlane/legacyControlPlaneOpenApi";
import { runStep, SkipStep } from "../step";
import type { Reporter } from "../types";
import type { AccountRequest } from "./promptFixture";
import { PLATFORM_ROLES, TEAM_ROLES, expectedTeamPermissions } from "./rolePermissions";
import { verifiedPromptIdForCommand } from "./promptFixture";
import { newRunScope } from "./runScope";

const CP = "/control-plane/v1";
export const CAMPAIGN_JOURNAL_KEY = "selftest-role-campaign-v1";
export const CAMPAIGN_LOCK = "selftest-role-campaign";
export interface CampaignJournal {
  version: 1;
  adminId: string;
  targetId: string;
  originalRoles: PlatformRoleRelation[];
  scope: string;
  teamNames: string[];
  prompts: Array<{ teamId: string; name: string; text: string; command: string }>;
}
export interface CampaignDeps {
  request: AccountRequest;
  readJournal: () => CampaignJournal | null;
  saveJournal: (journal: CampaignJournal | null) => void;
}
function same(actual: readonly string[], expected: readonly string[]): boolean {
  return [...actual].sort().join(",") === [...expected].sort().join(",");
}
function check(status: number, expected: number, path: string): void {
  if (status !== expected) throw new Error(`${path}: HTTP ${status}, expected ${expected}`);
}
async function bootstrap(deps: Pick<CampaignDeps, "request">, token: string): Promise<FrontendBootstrap> {
  const response = await deps.request(`${CP}/frontend/bootstrap`, token);
  check(response.status, 200, "/frontend/bootstrap");
  const body = response.body as FrontendBootstrap;
  if (!body?.current_user?.id || !Array.isArray(body.permissions?.platform_roles))
    throw new Error("Invalid bootstrap identity or roles");
  return body;
}
async function roster(deps: Pick<CampaignDeps, "request">, token: string): Promise<PlatformRolesResponse> {
  const response = await deps.request(`${CP}/users/platform-roles`, token);
  check(response.status, 200, "/users/platform-roles");
  const body = response.body as PlatformRolesResponse;
  if (
    !Array.isArray(body?.holders) ||
    body.holders.some(
      (holder) =>
        !holder.user?.id ||
        !Array.isArray(holder.relations) ||
        holder.relations.some((role) => !PLATFORM_ROLES.includes(role)),
    )
  )
    throw new Error("Invalid direct role roster");
  return body;
}
function direct(body: PlatformRolesResponse, id: string): PlatformRoleRelation[] {
  return body.holders.find((holder) => holder.user.id === id)?.relations ?? [];
}
async function setPlatform(
  deps: Pick<CampaignDeps, "request">,
  token: string,
  targetId: string,
  wanted: PlatformRoleRelation[],
): Promise<void> {
  const current = direct(await roster(deps, token), targetId);
  const path = `${CP}/users/${encodeURIComponent(targetId)}/platform-roles`;
  // Add before removing so restoration never loses a grant unnecessarily.
  for (const role of wanted.filter((role) => !current.includes(role))) {
    const response = await deps.request(path, token, { method: "POST", body: { relation: role } });
    check(response.status, 204, path);
  }
  for (const role of current.filter((role) => !wanted.includes(role))) {
    const response = await deps.request(`${path}/${role}`, token, { method: "DELETE" });
    check(response.status, 204, path);
  }
  const observed = direct(await roster(deps, token), targetId);
  if (!same(observed, wanted)) throw new Error(`Direct grants differ: expected [${wanted}], observed [${observed}]`);
}
function validateJournal(journal: CampaignJournal): void {
  if (
    journal.version !== 1 ||
    !journal.adminId ||
    !journal.targetId ||
    journal.adminId === journal.targetId ||
    !/^[a-zA-Z0-9-]+$/.test(journal.scope) ||
    !Array.isArray(journal.originalRoles) ||
    journal.originalRoles.some((role) => !PLATFORM_ROLES.includes(role)) ||
    !Array.isArray(journal.prompts) ||
    journal.prompts.some(
      (prompt) =>
        !prompt.teamId ||
        !prompt.name.startsWith("selftest-role-prompt-") ||
        !prompt.text.startsWith("role-write-marker-") ||
        !prompt.command.startsWith("selftest-role-"),
    ) ||
    !Array.isArray(journal.teamNames) ||
    journal.teamNames.some((name) => !["public", "private"].some((v) => name === `selftest-role-${journal.scope}-${v}`))
  )
    throw new Error("Invalid recovery journal; do not mutate grants or teams");
}
const description = (journal: CampaignJournal) =>
  `Disposable role campaign ${journal.scope}; admin ${journal.adminId}; target ${journal.targetId}`;
async function registry(deps: Pick<CampaignDeps, "request">, token: string): Promise<Team[]> {
  const response = await deps.request(`${CP}/teams/all?include_membership=false`, token);
  check(response.status, 200, "/teams/all");
  if (!Array.isArray(response.body)) throw new Error("Invalid team registry");
  return response.body as Team[];
}

export async function recoverRoleCampaign(adminToken: string, deps: CampaignDeps, report: Reporter): Promise<void> {
  const saved = deps.readJournal();
  if (!saved) return;
  const valid = await runStep(
    report,
    "campaign-recovery-identity",
    "Verify the administrator for role restoration",
    async () => {
      validateJournal(saved);
      const admin = await bootstrap(deps, adminToken);
      const roles = await roster(deps, adminToken);
      if (
        admin.current_user.id !== saved.adminId ||
        !roles.caller_is_bootstrap_root ||
        roles.holders.some((h) => h.user.id === saved.targetId && h.is_bootstrap_root)
      )
        throw new Error("Recovery requires the original bootstrap root and a distinct test account");
      return { value: true, detail: `restore ${saved.targetId}: [${saved.originalRoles.join(", ")}]` };
    },
  );
  if (!valid) return;
  let clean = true;
  // Each operation has its own step: one failed cleanup must not block the rest.
  for (const role of PLATFORM_ROLES) {
    const ok = await runStep(report, `campaign-restore-${role}`, `Restore test account role ${role}`, async () => {
      const held = direct(await roster(deps, adminToken), saved.targetId).includes(role);
      const wanted = saved.originalRoles.includes(role);
      if (held !== wanted) {
        const path = `${CP}/users/${encodeURIComponent(saved.targetId)}/platform-roles`;
        const response = await deps.request(
          wanted ? path : `${path}/${role}`,
          adminToken,
          wanted ? { method: "POST", body: { relation: role } } : { method: "DELETE" },
        );
        check(response.status, 204, path);
      }
      if (direct(await roster(deps, adminToken), saved.targetId).includes(role) !== wanted)
        throw new Error(`Role ${role} was not restored`);
      return { value: true };
    });
    clean = !!ok && clean;
  }
  const unsafeTeams = new Set<string>();
  for (const [index, prompt] of [...saved.prompts].entries()) {
    const ok = await runStep(
      report,
      `campaign-recover-prompt-${index}`,
      `Verify campaign prompt cleanup: ${prompt.name}`,
      async () => {
        const teams = await registry(deps, adminToken);
        const team = teams.find((team) => team.id === prompt.teamId);
        if (
          prompt.teamId !== `personal-${saved.adminId}` &&
          (!team || !saved.teamNames.includes(team.name) || team.description !== description(saved))
        )
          throw new Error(`Cannot verify team ownership for prompt ${prompt.name}; manual inspection required`);
        const base = `${CP}/teams/${encodeURIComponent(prompt.teamId)}/prompts`;
        const id = await verifiedPromptIdForCommand(
          deps.request,
          base,
          adminToken,
          prompt.command,
          prompt.name,
          prompt.text,
        );
        if (id) {
          const path = `${base}/${encodeURIComponent(id)}`;
          check((await deps.request(path, adminToken, { method: "DELETE" })).status, 204, path);
          check((await deps.request(path, adminToken)).status, 404, path);
        }
        saved.prompts = saved.prompts.filter((entry) => entry !== prompt);
        deps.saveJournal(saved);
        return { value: true };
      },
    );
    if (!ok) unsafeTeams.add(prompt.teamId);
    clean = !!ok && clean;
  }
  for (const [index, name] of [...saved.teamNames].entries()) {
    const ok = await runStep(report, `campaign-delete-team-${index}`, `Remove campaign team ${name}`, async () => {
      const matches = (await registry(deps, adminToken)).filter((team) => team.name === name);
      for (const team of matches) {
        if (unsafeTeams.has(team.id)) throw new Error(`Resolve prompt cleanup before deleting ${name}`);
        if (!team.id || team.id.startsWith("personal-") || team.description !== description(saved))
          throw new Error(`Team ${name} does not match the recovery fixture; manual inspection required`);
        const response = await deps.request(`${CP}/teams/${encodeURIComponent(team.id)}`, adminToken, {
          method: "DELETE",
        });
        check(response.status, 204, `delete ${name}`);
      }
      if ((await registry(deps, adminToken)).some((team) => team.name === name))
        throw new Error(`Team ${name} remains in the registry`);
      saved.teamNames = saved.teamNames.filter((entry) => entry !== name);
      deps.saveJournal(saved);
      return { value: true };
    });
    clean = !!ok && clean;
  }
  await runStep(report, "campaign-restored", "Verify original grants and complete campaign recovery", async () => {
    if (!clean || !same(direct(await roster(deps, adminToken), saved.targetId), saved.originalRoles))
      throw new Error(
        `Recovery incomplete for ${saved.targetId}; retained journal contains original roles and team names`,
      );
    deps.saveJournal(null);
    return { value: true, detail: "original direct grants restored; run teams absent from registry" };
  });
}
async function teamRoles(
  deps: Pick<CampaignDeps, "request">,
  token: string,
  teamId: string,
  targetId: string,
): Promise<UserTeamRelation[]> {
  const path = `${CP}/teams/${encodeURIComponent(teamId)}/members`;
  const response = await deps.request(path, token);
  check(response.status, 200, path);
  if (!Array.isArray(response.body)) throw new Error("Invalid member roster");
  const members = response.body as TeamMember[];
  const roles = members.find((m) => m.user?.id === targetId)?.relations ?? [];
  if (!Array.isArray(roles) || roles.some((role) => !TEAM_ROLES.includes(role)))
    throw new Error("Invalid direct team roles");
  return roles;
}
async function setTeam(
  deps: Pick<CampaignDeps, "request">,
  token: string,
  teamId: string,
  targetId: string,
  wanted: UserTeamRelation[],
): Promise<void> {
  const base = `${CP}/teams/${encodeURIComponent(teamId)}/members`;
  let current = await teamRoles(deps, token, teamId, targetId);
  if (!wanted.length && current.length) {
    check(
      (await deps.request(`${base}/${encodeURIComponent(targetId)}`, token, { method: "DELETE" })).status,
      202,
      base,
    );
  } else {
    for (const role of wanted.filter((role) => !current.includes(role))) {
      check(
        (
          await deps.request(base, token, {
            method: "POST",
            body: { user_id: targetId, relation: role === "pending_team_admin" ? "team_admin" : role },
          })
        ).status,
        204,
        base,
      );
    }
    current = await teamRoles(deps, token, teamId, targetId);
    for (const role of current.filter((role) => !wanted.includes(role))) {
      check(
        (await deps.request(`${base}/${encodeURIComponent(targetId)}/roles/${role}`, token, { method: "DELETE" }))
          .status,
        204,
        base,
      );
    }
  }
  current = await teamRoles(deps, token, teamId, targetId);
  if (!same(current, wanted))
    throw new Error(`Team ${teamId}: expected direct roles [${wanted}], observed [${current}]`);
}
function assertAccess(status: number, allowed: boolean, path: string): void {
  if (allowed ? status === 200 : status === 403 || status === 404) return;
  throw new Error(`${path}: HTTP ${status}, expected ${allowed ? "200" : "403 or 404"}`);
}
export const CAMPAIGN_PLATFORM_CASES: PlatformRoleRelation[][] = [[], ...PLATFORM_ROLES.map((role) => [role])];
export function campaignTeamCases(adminRole: UserTeamRelation): UserTeamRelation[][] {
  return [
    [],
    ["team_member"],
    ["team_editor"],
    ["team_analyst"],
    [adminRole],
    [adminRole, "team_editor", "team_analyst"],
  ];
}
async function promptWrite(
  deps: CampaignDeps,
  token: string,
  adminToken: string,
  teamId: string,
  allowed: boolean,
  onCreated?: (id: string) => Promise<void>,
): Promise<void> {
  const scope = newRunScope();
  const name = scope.name("selftest-role-prompt"),
    text = scope.name("role-write-marker"),
    command = `selftest-role-${scope.token.toLowerCase()}`;
  const base = `${CP}/teams/${encodeURIComponent(teamId)}/prompts`;
  let id: string | null = null;
  try {
    const response = await deps.request(base, token, { method: "POST", body: { name, text, command } });
    id = await verifiedPromptIdForCommand(deps.request, base, adminToken, command, name, text);
    if (allowed) {
      check(response.status, 201, base);
      if (!id || (response.body as { id?: string } | null)?.id !== id)
        throw new Error(`Cannot identify ${name}; retained for recovery`);
      await onCreated?.(id);
    } else {
      assertAccess(response.status, false, base);
      if (id) throw new Error(`Denied write persisted ${name}`);
    }
  } finally {
    if (id) {
      const path = `${base}/${encodeURIComponent(id)}`;
      check((await deps.request(path, adminToken, { method: "DELETE" })).status, 204, path);
      check((await deps.request(path, adminToken)).status, 404, path);
    }
  }
}

export async function roleCampaignScenario(
  adminToken: string,
  targetToken: string,
  deps: CampaignDeps,
  report: Reporter,
  signal?: AbortSignal,
): Promise<void> {
  const preflight = await runStep(
    report,
    "campaign-preflight",
    "Verify two accounts and automatic role campaign prerequisites",
    async () => {
      if (deps.readJournal()) throw new Error("Restore the previous campaign before starting another one");
      const admin = await bootstrap(deps, adminToken);
      const target = await bootstrap(deps, targetToken);
      if (admin.current_user.id === target.current_user.id)
        throw new Error("The second credential belongs to the administrator");
      const roles = await roster(deps, adminToken);
      if (!roles.caller_is_bootstrap_root || !admin.permissions.platform_roles?.includes("platform_admin"))
        throw new Error("The platform admin check requires the bootstrap root administrator");
      if (roles.holders.some((h) => h.user.id === target.current_user.id && h.is_bootstrap_root))
        throw new Error("The protected root cannot be the test account");
      const accepted = async (token: string) => {
        const response = await deps.request(`${CP}/team-admin-charter`, token);
        check(response.status, 200, "/team-admin-charter");
        return !!(response.body as { accepted_at?: string } | null)?.accepted_at;
      };
      if (admin.team_admin_charter_enabled && !(await accepted(adminToken)))
        throw new Error("Accept the team administrator charter yourself before this campaign");
      const availableAdmin: UserTeamRelation =
        !target.team_admin_charter_enabled || (await accepted(targetToken)) ? "team_admin" : "pending_team_admin";
      const journal: CampaignJournal = {
        version: 1,
        adminId: admin.current_user.id,
        targetId: target.current_user.id,
        originalRoles: direct(roles, target.current_user.id),
        scope: newRunScope().token,
        teamNames: [],
        prompts: [],
      };
      deps.saveJournal(journal);
      return {
        value: { journal, availableAdmin },
        detail: `admin ${journal.adminId}; dedicated test account ${journal.targetId}; original roles [${journal.originalRoles}]`,
      };
    },
  );
  if (!preflight) return;
  const { journal, availableAdmin } = preflight;
  const campaignDeps: CampaignDeps = {
    ...deps,
    request: async (path, token, init) => {
      if (init?.method === "POST" && /^\/control-plane\/v1\/teams\/[^/]+\/prompts$/.test(path)) {
        const prompt = init.body as { name: string; text: string; command: string };
        journal.prompts.push({ teamId: decodeURIComponent(path.split("/")[4]), ...prompt });
        deps.saveJournal(journal);
      }
      return deps.request(path, token, init);
    },
  };
  const needActive = async () => {
    if (signal?.aborted) throw new Error("Campaign interrupted; restore roles and fixtures");
    if ((await bootstrap(deps, targetToken)).current_user.id !== journal.targetId)
      throw new Error("Test identity changed; restoring original grants");
  };
  try {
    const teams: Array<{ teamId: string; visibility: "private" | "public" }> = [];
    for (const visibility of ["private", "public"] as const) {
      await needActive();
      const name = `selftest-role-${journal.scope}-${visibility}`;
      journal.teamNames.push(name);
      deps.saveJournal(journal);
      const created = await deps.request(`${CP}/teams`, adminToken, {
        method: "POST",
        body: { name, description: description(journal), initial_team_admin_ids: [journal.adminId] },
      });
      check(created.status, 201, "create campaign team");
      const team = created.body as Team;
      if (!team?.id || team.id.startsWith("personal-"))
        throw new Error(`Invalid campaign team response; recover by name ${name}`);
      const verified = (await registry(deps, adminToken)).find(
        (t) => t.id === team.id && t.name === name && t.description === description(journal),
      );
      if (!verified) throw new Error(`Campaign team ${name} cannot be verified`);
      const path = `${CP}/teams/${encodeURIComponent(team.id)}`;
      check(
        (await deps.request(path, adminToken, { method: "PATCH", body: { visibility, joining_mode: "invite_only" } }))
          .status,
        200,
        path,
      );
      check(
        (
          await deps.request(`${path}/members`, adminToken, {
            method: "POST",
            body: { user_id: journal.adminId, relation: "team_editor" },
          })
        ).status,
        204,
        path,
      );
      teams.push({ teamId: team.id, visibility });
    }
    for (const [index, roles] of CAMPAIGN_PLATFORM_CASES.entries()) {
      await needActive();
      const key = `platform-${index}`;
      const changed = await runStep(
        report,
        `${key}-roles`,
        `Platform roles: ${roles.join(", ") || "none"}`,
        async () => {
          await setPlatform(deps, adminToken, journal.targetId, roles);
          const target = await bootstrap(deps, targetToken);
          if (
            target.current_user.id !== journal.targetId ||
            !same(target.permissions.platform_roles ?? [], roles.includes("platform_admin") ? PLATFORM_ROLES : roles)
          )
            throw new Error("Effective platform roles do not match the selected profile");
          return { value: true };
        },
      );
      if (!changed) throw new Error("Platform transition failed; restoring original grants");
      const route =
        roles.includes("platform_admin") || !roles.length
          ? "/users"
          : roles.includes("team_manager")
            ? "/teams/all"
            : roles.includes("feature_manager")
              ? "/admin/capabilities"
              : roles.includes("prompt_editor")
                ? "/admin/platform/prompt"
                : "/kpi/presets/sessions_over_time";
      await runStep(report, `${key}-access`, `Platform ${roles.join(", ") || "none"}: ${route} access`, async () => {
        let path = `${CP}${route}`;
        if (route.startsWith("/kpi/")) {
          const until = new Date();
          path += `?since=${encodeURIComponent(new Date(until.getTime() - 86400000).toISOString())}&until=${encodeURIComponent(until.toISOString())}`;
        }
        const response = await deps.request(path, targetToken);
        if (
          route.startsWith("/kpi/") &&
          response.status === 503 &&
          (await deps.request(path, adminToken)).status === 503
        )
          throw new SkipStep("KPI backend unavailable for both accounts");
        assertAccess(response.status, roles.length > 0, path);
        return { value: true, detail: `HTTP ${response.status}` };
      });
      if (roles.length && !roles.includes("platform_admin"))
        await runStep(report, `${key}-no-admin`, `Role ${roles[0]} cannot administer users`, async () => {
          const response = await deps.request(`${CP}/users`, targetToken);
          assertAccess(response.status, false, "/users");
          return { value: true };
        });
      const extraRoutes = [
        "/teams/candidate-admins?query=selftest",
        "/admin/platform/model-bindings",
        "/admin/platform/instructions",
        "/users/platform-roles",
        "/admin/platform/ui-settings",
        "/admin/platform/announcements",
        "/import-export/stats",
      ];
      for (const [extraIndex, extra] of extraRoutes.entries()) {
        const delegated =
          (roles.includes("team_manager") && extraIndex === 0) ||
          (roles.includes("feature_manager") && extraIndex === 1) ||
          (roles.includes("prompt_editor") && extraIndex === 2);
        if (roles.length && !roles.includes("platform_admin") && !delegated) continue;
        await runStep(
          report,
          `${key}-extra-${extraIndex}`,
          `Platform ${roles.join(", ") || "none"}: ${extra}`,
          async () => {
            const response = await deps.request(`${CP}${extra}`, targetToken);
            assertAccess(response.status, roles.length > 0, extra);
            return { value: true };
          },
        );
      }
      if (roles.includes("platform_admin")) {
        await runStep(
          report,
          "personal-exact-prompt",
          "An exact personal prompt stays private to its owner",
          async () => {
            await promptWrite(campaignDeps, adminToken, adminToken, `personal-${journal.adminId}`, true, async (id) => {
              const path = `${CP}/teams/${encodeURIComponent(`personal-${journal.adminId}`)}/prompts/${encodeURIComponent(id)}`;
              assertAccess((await deps.request(path, targetToken)).status, false, path);
            });
            return { value: true };
          },
        );
        await runStep(
          report,
          "personal-foreign-write",
          "The test account cannot create prompts in the administrator's personal space",
          async () => {
            await promptWrite(campaignDeps, targetToken, adminToken, `personal-${journal.adminId}`, false);
            return { value: true };
          },
        );

        for (const team of teams)
          await runStep(
            report,
            `admin-no-team-${team.visibility}`,
            `Platform admin cannot read ${team.visibility} team content without membership`,
            async () => {
              const response = await deps.request(
                `${CP}/teams/${encodeURIComponent(team.teamId)}/prompts`,
                targetToken,
              );
              assertAccess(response.status, false, "team prompts");
              return { value: true };
            },
          );
        for (const suffix of [
          "",
          "/prompts",
          "/sessions",
          "/agent-instances",
          "/prompts/context",
          "/prompt-categories",
          "/prompt-commands",
          "/agent-templates",
        ])
          await runStep(
            report,
            `personal-isolation-${suffix || "team"}`,
            `Personal ${suffix || "team"}: both users stay isolated, even with platform admin`,
            async () => {
              for (const [id, owner, other] of [
                [journal.adminId, adminToken, targetToken],
                [journal.targetId, targetToken, adminToken],
              ]) {
                const path = `${CP}/teams/${encodeURIComponent(`personal-${id}`)}${suffix}`;
                check((await deps.request(path, owner)).status, 200, path);
                assertAccess((await deps.request(path, other)).status, false, path);
              }
              return { value: true };
            },
          );
      }
    }
    await runStep(report, "personal-discovery", "Both accounts discover only their own personal team", async () => {
      for (const [id, token, otherId] of [
        [journal.adminId, adminToken, journal.targetId],
        [journal.targetId, targetToken, journal.adminId],
      ]) {
        const response = await deps.request(`${CP}/teams`, token);
        check(response.status, 200, "/teams");
        if (
          !Array.isArray(response.body) ||
          !response.body.some((team) => team.id === `personal-${id}` && team.is_member === true) ||
          response.body.some((team) => team.id === `personal-${otherId}`)
        )
          throw new Error("Personal team discovery leaks or omits a personal space");
      }
      return { value: true };
    });
    await setPlatform(deps, adminToken, journal.targetId, []);
    for (const [index, roles] of campaignTeamCases(availableAdmin).entries()) {
      for (const selected of teams) {
        await needActive();
        const other = teams.find((team) => team !== selected)!;
        const key = `team-${index}-${selected.visibility}`;
        await setTeam(deps, adminToken, other.teamId, journal.targetId, []);
        const changed = await runStep(
          report,
          `${key}-roles`,
          `${selected.visibility} team: ${roles.join(", ") || "non-member"}`,
          async () => {
            await setTeam(deps, adminToken, selected.teamId, journal.targetId, roles);
            const response = await deps.request(`${CP}/teams/${encodeURIComponent(selected.teamId)}`, targetToken);
            if (!roles.length && selected.visibility === "private") {
              assertAccess(response.status, false, "private team");
              return {
                value: true,
                detail: "independent admin roster confirms no membership; private metadata refused",
              };
            }
            check(response.status, 200, "team projection");
            const team = response.body as TeamWithPermissions;
            if (
              team?.id !== selected.teamId ||
              !Array.isArray(team.my_relations) ||
              !same(team.my_relations, roles) ||
              team.is_member !== roles.length > 0 ||
              !Array.isArray(team.permissions) ||
              !same(team.permissions, expectedTeamPermissions(roles, selected.visibility))
            )
              throw new Error("Team roles, membership or permissions differ from the selected profile");
            return { value: true };
          },
        );
        if (!changed) throw new Error("Team role transition failed; restoring original state");
        for (const [kind, teamId, allowed] of [
          ["own", selected.teamId, roles.length > 0],
          ["other", other.teamId, false],
        ] as const)
          await runStep(
            report,
            `${key}-${kind}-content`,
            `${selected.visibility} team ${roles.join(", ") || "non-member"}: ${kind} team content`,
            async () => {
              const path = `${CP}/teams/${encodeURIComponent(teamId)}/prompts`;
              const response = await deps.request(path, targetToken);
              assertAccess(response.status, allowed, path);
              return { value: true };
            },
          );
        if (index <= 1)
          for (const suffix of ["members", "sessions", "agent-instances"]) {
            for (const [kind, teamId, allowed] of [
              ["own", selected.teamId, roles.length > 0],
              ["other", other.teamId, false],
            ] as const) {
              await runStep(
                report,
                `${key}-${kind}-${suffix}`,
                `${selected.visibility} ${roles.join(", ") || "non-member"}: ${kind} team ${suffix}`,
                async () => {
                  const path = `${CP}/teams/${encodeURIComponent(teamId)}/${suffix}`;
                  assertAccess((await deps.request(path, targetToken)).status, allowed, path);
                  return { value: true };
                },
              );
            }
          }
        await runStep(
          report,
          `${key}-write`,
          `${selected.visibility} team ${roles.join(", ") || "non-member"}: prompt write follows editor role`,
          async () => {
            await promptWrite(campaignDeps, targetToken, adminToken, selected.teamId, roles.includes("team_editor"));
            return { value: true };
          },
        );
      }
    }
    for (const team of teams) {
      await setTeam(deps, adminToken, team.teamId, journal.targetId, []);
      await runStep(
        report,
        `revoked-${team.visibility}-read`,
        `Revocation closes ${team.visibility} team reads`,
        async () => {
          const path = `${CP}/teams/${encodeURIComponent(team.teamId)}/prompts`;
          assertAccess((await deps.request(path, targetToken)).status, false, path);
          return { value: true };
        },
      );
      await runStep(
        report,
        `revoked-${team.visibility}-write`,
        `Revocation closes ${team.visibility} team writes`,
        async () => {
          await promptWrite(campaignDeps, targetToken, adminToken, team.teamId, false);
          return { value: true };
        },
      );
    }
  } catch (error) {
    await runStep(report, "campaign-interrupted", "Complete automatic role matrix", async () => {
      throw error;
    });
  } finally {
    await recoverRoleCampaign(adminToken, deps, report);
  }
}
