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
import { isPersonalTeamId } from "../../../components/shared/utils/teamId";
import { runStep, SkipStep } from "../step";
import type { Scenario } from "../types";
import { assertAccessMatchesPlatformAdmin, authzProbeScenario, type AuthzProbeDeps } from "./authzProbeScenario";

type Request = (path: string, token?: string) => Promise<{ status: number; body: unknown }>;

export interface AuthorizationDeps {
  probe: AuthzProbeDeps;
  request: Request;
  /** A fresh session token, or null when the session cannot be refreshed. */
  token: () => Promise<string | null>;
  personalTeamId: string;
}

const CP = "/control-plane/v1";

/** Protected routes of every backend, without required parameters, so only authentication decides. */
export function protectedRoutes(personalTeamId: string): string[] {
  const personal = `${CP}/teams/${encodeURIComponent(personalTeamId)}`;
  return [
    `${CP}/frontend/bootstrap`,
    `${CP}/teams`,
    `${CP}/teams/all`,
    `${CP}/users`,
    `${CP}/users/platform-roles`,
    `${CP}/admin/capabilities`,
    `${CP}/admin/platform/model-bindings`,
    `${CP}/admin/platform/ui-settings`,
    `${CP}/admin/platform/announcements`,
    `${CP}/import-export/stats`,
    `${CP}/me/inactive-sessions`,
    `${CP}/team-admin-charter`,
    `${CP}/marketplace/prompts`,
    `${CP}/marketplace/agents`,
    `${personal}/prompts`,
    `${personal}/sessions`,
    `${personal}/agent-instances`,
    "/knowledge-flow/v1/tags",
    "/knowledge-flow/v1/tabular/documents",
    "/fred/agents/v2/agents/sessions",
  ];
}

/** Routes reserved to platform administrators. */
export const ADMIN_ROUTES = [
  `${CP}/users`,
  `${CP}/admin/platform/ui-settings`,
  `${CP}/admin/platform/announcements`,
  `${CP}/import-export/stats`,
];

/** Team content gated on membership: refused to a non-member even when the team is public. */
export const MEMBER_ROUTES = [
  "prompts",
  "prompt-categories",
  "prompt-commands",
  "agent-instances",
  "agent-templates",
  "members",
  "routing-policy",
  "wiki/pages",
];

export const MAX_FOREIGN_TEAMS = 5;

/** A copy of the token with one signature character changed, or null if it is not a signed JWT. */
export function resign(token: string): string | null {
  const at = token.lastIndexOf(".") + 1;
  if (at <= 0 || at >= token.length || token.split(".").length !== 3) return null;
  return token.slice(0, at) + (token[at] === "A" ? "B" : "A") + token.slice(at + 1);
}

export const authorizationScenario: Scenario<AuthorizationDeps> = async (deps, report) => {
  const token = await runStep(report, "session-token", "Refresh the current session credential", async () => {
    const value = await deps.token();
    if (!value) throw new Error("sign in again before running the authorization checks");
    return { value };
  });
  if (!token) return;

  await authzProbeScenario(token, token, deps.probe, report);

  const routes = protectedRoutes(deps.personalTeamId);
  const forged = resign(token);
  for (const [mode, credential, title] of [
    ["missing", undefined, "No protected route answers without a token"],
    ["malformed", "not-a-jwt", "No protected route accepts a malformed token"],
    ["resigned", forged, "No protected route accepts a token with an altered signature"],
  ] as const) {
    await runStep(report, `sweep-${mode}`, title, async () => {
      if (credential === null) throw new SkipStep("the session credential is not a signed JWT");
      const leaks: string[] = [];
      for (const path of routes) {
        const { status } = await deps.request(path, credential);
        if (status !== 401) leaks.push(`${path}: HTTP ${status}`);
      }
      if (leaks.length) throw new Error(`expected 401 on every route; ${leaks.join("; ")}`);
      return { value: undefined, detail: `${routes.length} routes answered 401` };
    });
  }

  await runStep(report, "admin-routes", "Platform-administration routes follow the platform admin role", async () => {
    const flags = await deps.probe.fetchBootstrapFlags(token);
    const wrong: string[] = [];
    for (const path of ADMIN_ROUTES) {
      const { status } = await deps.request(path, token);
      try {
        assertAccessMatchesPlatformAdmin(path, status, flags.isPlatformAdmin);
      } catch {
        wrong.push(`${path}: HTTP ${status}`);
      }
    }
    if (wrong.length) throw new Error(`platform_admin=${flags.isPlatformAdmin}, but ${wrong.join("; ")}`);
    return { value: undefined, detail: `${ADMIN_ROUTES.length} routes, platform_admin=${flags.isPlatformAdmin}` };
  });

  await runStep(report, "foreign-team-sweep", "Team content stays closed to a team you do not belong to", async () => {
    const registry = await deps.probe.probeRegistryAccess(token);
    if (registry.status !== 200) throw new SkipStep("the team registry cannot be read by this account");
    const own = new Set(await deps.probe.fetchOwnTeamIds(token));
    const foreign = registry.teamIds.filter((id) => !own.has(id) && !isPersonalTeamId(id)).slice(0, MAX_FOREIGN_TEAMS);
    if (foreign.length === 0) throw new SkipStep("every team in the registry counts you as a member");
    const leaks: string[] = [];
    for (const teamId of foreign) {
      for (const route of MEMBER_ROUTES) {
        const { status } = await deps.request(`${CP}/teams/${encodeURIComponent(teamId)}/${route}`, token);
        if (status !== 403 && status !== 404) leaks.push(`${teamId}/${route}: HTTP ${status}`);
      }
    }
    if (leaks.length) throw new Error(`expected 403 or 404; ${leaks.join("; ")}`);
    return { value: undefined, detail: `${foreign.length} team(s) × ${MEMBER_ROUTES.length} routes refused` };
  });
};
