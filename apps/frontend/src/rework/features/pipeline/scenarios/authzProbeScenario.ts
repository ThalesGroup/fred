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

// Authorization self-test: proves the live UI/API honor the authorization
// model, for the running admin's own session or for any other account. Runs
// on the SAME step-report engine as `selfTestScenario.ts` (`runStep`,
// `SkipStep`, `Reporter`), but against a different, minimal deps contract —
// see `docs/swift/platform/FRONTEND-AUTHZ-PATTERN.md`.
//
// Deliberately NOT a hardcoded "sophia should be team_admin" lookup table:
// the frontend has no way to know that (it lives in a deployment-factory
// config file this app never reads). Every expectation below is derived
// from data the API already reports about the target account itself —
// including the one positive/write check (`team-write-access`): it reads the
// target's own `can_update_resources` permission on their first team from
// `GET /teams/{teamId}` and asserts a real create only succeeds when that
// permission is present, rather than assuming a role from a name.

import { runStep, SkipStep } from "../step";
import type { Reporter } from "../types";

export interface BootstrapFlags {
  isPlatformAdmin: boolean;
  isPlatformObserver: boolean;
}

export interface RegistryProbeResult {
  status: number;
  teamIds: string[];
}

export interface TeamWriteProbeResult {
  status: number;
  /** The created prompt's id, when the write succeeded — the caller must
   * delete it via `cleanupTeamWrite` regardless of what the test asserts. */
  createdId: string | null;
}

/**
 * The reusable building blocks, each a plain authenticated fetch bound to an
 * EXPLICIT token — never the app's own session (unlike `PipelineDeps`, which
 * always acts as the current user via RTK Query). `useAuthzProbeRun` provides
 * the real implementation; tests provide a fake one.
 */
export interface AuthzProbeDeps {
  fetchBootstrapFlags(token: string): Promise<BootstrapFlags>;
  /** GET /teams for the given token's owner — collaborative teams only (personal space excluded). */
  fetchOwnTeamIds(token: string): Promise<string[]>;
  /** GET /teams/all for the given token's owner. `teamIds` is [] when `status !== 200`. */
  probeRegistryAccess(token: string): Promise<RegistryProbeResult>;
  /** GET /users for the given token's owner — status code only, body unused. */
  probeUsersAccess(token: string): Promise<number>;
  /** GET /teams/{teamId}/prompts for the given token's owner — status code only. */
  probeTeamPromptsAccess(token: string, teamId: string): Promise<number>;
  /** GET /teams/{teamId} for the given token's owner — the caller's own `permissions` on that team. */
  fetchTeamPermissions(token: string, teamId: string): Promise<string[]>;
  /** POST /teams/{teamId}/prompts for the given token's owner — a run-scoped, throwaway prompt. */
  probeTeamWriteAccess(token: string, teamId: string): Promise<TeamWriteProbeResult>;
  /** DELETE /teams/{teamId}/prompts/{promptId} — best-effort cleanup of what `probeTeamWriteAccess` created. */
  cleanupTeamWrite(token: string, teamId: string, promptId: string): Promise<void>;
}

/** Pure — no fetch, nothing to mock. A capability that returns 200 must line up
 * with the same account's own `is_platform_admin` flag, in either direction:
 * a "yes" without the flag, or the flag without the "yes", are both bugs. */
export function assertAccessMatchesPlatformAdmin(label: string, status: number, isPlatformAdmin: boolean): void {
  const allowed = status === 200;
  if (allowed === isPlatformAdmin) return;
  throw new Error(
    `${label}: HTTP ${status} (${allowed ? "allowed" : "denied"}), but is_platform_admin=${isPlatformAdmin}`,
  );
}

/** Pure — same shape as `assertAccessMatchesPlatformAdmin`, for a team-scoped write
 * capability instead of the org-level `is_platform_admin` flag. A create that
 * succeeds (200/201) must line up with the account's own `can_update_resources`
 * permission on that team, as reported by the team itself (never hardcoded). */
export function assertWriteAccessMatchesTeamPermission(label: string, status: number, hasPermission: boolean): void {
  const allowed = status === 200 || status === 201;
  if (allowed === hasPermission) return;
  throw new Error(
    `${label}: HTTP ${status} (${allowed ? "allowed" : "denied"}), but can_update_resources=${hasPermission}`,
  );
}

/**
 * Runs the checks below for `targetToken` (the account under test).
 * `adminToken` is only used to resolve the full team registry for the
 * foreign-team-isolation check — it must belong to a real platform_admin
 * (guaranteed by this page's own `canAdmin` route guard), never the target.
 * Pass the same token twice to test the running admin's own session.
 */
export async function authzProbeScenario(
  adminToken: string,
  targetToken: string,
  deps: AuthzProbeDeps,
  report: Reporter,
): Promise<void> {
  const flags = await runStep(report, "bootstrap-flags", "Read bootstrap permission flags", async () => {
    const f = await deps.fetchBootstrapFlags(targetToken);
    return { value: f, detail: `is_platform_admin=${f.isPlatformAdmin}, is_platform_observer=${f.isPlatformObserver}` };
  });

  const ownTeamIds = await runStep(report, "own-teams", "List the target's own collaborative teams", async () => {
    const ids = await deps.fetchOwnTeamIds(targetToken);
    return { value: ids, detail: ids.length ? ids.join(", ") : "(none)" };
  });

  await runStep(
    report,
    "team-write-access",
    "Team write access matches the target's own can_update_resources",
    async () => {
      if (ownTeamIds === null) throw new SkipStep("the target's own team list is unknown (previous step failed)");
      const teamId = ownTeamIds[0];
      if (!teamId) throw new SkipStep("the target belongs to no collaborative team");
      const permissions = await deps.fetchTeamPermissions(targetToken, teamId);
      const hasPermission = permissions.includes("can_update_resources");
      const { status, createdId } = await deps.probeTeamWriteAccess(targetToken, teamId);
      if (createdId) await deps.cleanupTeamWrite(targetToken, teamId, createdId);
      assertWriteAccessMatchesTeamPermission(`team ${teamId} write access`, status, hasPermission);
      return {
        value: undefined,
        detail: `team ${teamId}: can_update_resources=${hasPermission}, write HTTP ${status}`,
      };
    },
  );

  if (flags) {
    await runStep(report, "registry-access", "Team registry access (GET /teams/all)", async () => {
      const { status } = await deps.probeRegistryAccess(targetToken);
      assertAccessMatchesPlatformAdmin("registry access", status, flags.isPlatformAdmin);
      return { value: undefined, detail: `HTTP ${status}` };
    });

    await runStep(report, "users-access", "User administration access (GET /users)", async () => {
      const status = await deps.probeUsersAccess(targetToken);
      assertAccessMatchesPlatformAdmin("user administration access", status, flags.isPlatformAdmin);
      return { value: undefined, detail: `HTTP ${status}` };
    });
  }

  await runStep(
    report,
    "foreign-team-isolation",
    "No implicit access to a team the target does not belong to",
    async () => {
      if (ownTeamIds === null) throw new SkipStep("the target's own team list is unknown (previous step failed)");
      const registry = await deps.probeRegistryAccess(adminToken);
      if (registry.status !== 200) throw new SkipStep("could not resolve the team registry as the running admin");
      const foreignTeamId = registry.teamIds.find((id) => !ownTeamIds.includes(id));
      if (!foreignTeamId) throw new SkipStep("no team exists that the target is not already a member of");
      const status = await deps.probeTeamPromptsAccess(targetToken, foreignTeamId);
      // This must hold for EVERY account, admin or not — nobody gets implicit
      // team content access (REBAC.md: "platform_admin carries no team
      // relation of any kind, full stop").
      if (status !== 403 && status !== 404) {
        throw new Error(`expected denial reading team ${foreignTeamId}'s prompts, got HTTP ${status}`);
      }
      return { value: undefined, detail: `team ${foreignTeamId}: HTTP ${status}` };
    },
  );
}
