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

import { useCallback, useState } from "react";
import { runStep } from "./step";
import { authzProbeScenario, type AuthzProbeDeps } from "./scenarios/authzProbeScenario";
import { loginWithPassword } from "./keycloakDirectGrant";
import type { StepReport } from "./types";
import { KeyCloakService } from "../../../security/KeycloakService";
import { isPersonalTeamId } from "../../components/shared/utils/teamId";

interface TeamsResponseItem {
  id: string;
}

interface TeamWithPermissionsResponse {
  permissions?: string[];
}

interface PromptResponse {
  id?: string;
}

interface BootstrapResponse {
  permissions?: {
    is_platform_admin?: boolean;
    is_platform_observer?: boolean;
  };
}

async function authedFetch(
  path: string,
  token: string,
  init?: { method?: string; body?: unknown },
): Promise<{ status: number; body: unknown }> {
  const response = await fetch(path, {
    method: init?.method ?? "GET",
    headers: {
      Authorization: `Bearer ${token}`,
      ...(init?.body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: init?.body !== undefined ? JSON.stringify(init.body) : undefined,
  });
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // no body, or not JSON — the callers below only care about status in that case
  }
  return { status: response.status, body };
}

/** The real `AuthzProbeDeps` — plain authenticated fetches against the same
 * relative control-plane paths the generated RTK Query client uses, bound to
 * an explicit token instead of the app's own session (see the module doc in
 * `scenarios/authzProbeScenario.ts` for why). */
const deps: AuthzProbeDeps = {
  fetchBootstrapFlags: async (token) => {
    const { status, body } = await authedFetch("/control-plane/v1/frontend/bootstrap", token);
    if (status !== 200) throw new Error(`GET /frontend/bootstrap: HTTP ${status}`);
    const permissions = (body as BootstrapResponse)?.permissions ?? {};
    return {
      isPlatformAdmin: Boolean(permissions.is_platform_admin),
      isPlatformObserver: Boolean(permissions.is_platform_observer),
    };
  },
  fetchOwnTeamIds: async (token) => {
    const { status, body } = await authedFetch("/control-plane/v1/teams", token);
    if (status !== 200) throw new Error(`GET /teams: HTTP ${status}`);
    const teams = Array.isArray(body) ? (body as TeamsResponseItem[]) : [];
    return teams.map((t) => String(t.id)).filter((id) => !isPersonalTeamId(id));
  },
  probeRegistryAccess: async (token) => {
    const { status, body } = await authedFetch("/control-plane/v1/teams/all", token);
    const teams = status === 200 && Array.isArray(body) ? (body as TeamsResponseItem[]) : [];
    return { status, teamIds: teams.map((t) => String(t.id)) };
  },
  probeUsersAccess: async (token) => {
    const { status } = await authedFetch("/control-plane/v1/users", token);
    return status;
  },
  probeTeamPromptsAccess: async (token, teamId) => {
    const { status } = await authedFetch(`/control-plane/v1/teams/${encodeURIComponent(teamId)}/prompts`, token);
    return status;
  },
  fetchTeamPermissions: async (token, teamId) => {
    const { status, body } = await authedFetch(`/control-plane/v1/teams/${encodeURIComponent(teamId)}`, token);
    if (status !== 200) return [];
    return (body as TeamWithPermissionsResponse)?.permissions ?? [];
  },
  probeTeamWriteAccess: async (token, teamId) => {
    const marker = (globalThis.crypto?.randomUUID?.() ?? `${Math.random()}`).slice(0, 8);
    const { status, body } = await authedFetch(`/control-plane/v1/teams/${encodeURIComponent(teamId)}/prompts`, token, {
      method: "POST",
      body: {
        name: `fred-authz-selftest-${marker}`,
        text: "Authorization self-test probe — safe to delete, cleaned up automatically.",
      },
    });
    const allowed = status === 200 || status === 201;
    return { status, createdId: allowed ? ((body as PromptResponse)?.id ?? null) : null };
  },
  cleanupTeamWrite: async (token, teamId, promptId) => {
    try {
      await authedFetch(
        `/control-plane/v1/teams/${encodeURIComponent(teamId)}/prompts/${encodeURIComponent(promptId)}`,
        token,
        {
          method: "DELETE",
        },
      );
    } catch {
      // Best-effort — a failed cleanup must not crash the self-test. The prompt
      // is clearly named (`fred-authz-selftest-*`) and safe to remove manually.
    }
  },
};

export interface AuthzProbeRun {
  steps: StepReport[];
  isRunning: boolean;
  /** Run the probe against the current admin's own session — always available. */
  runForMyself: () => void;
  /** Log in as `username`/`password` (short-lived, discarded after the run — see
   * `keycloakDirectGrant.ts`) and run the same probe against that account. */
  runForProfile: (username: string, password: string) => void;
}

export function useAuthzProbeRun(): AuthzProbeRun {
  const [steps, setSteps] = useState<StepReport[]>([]);
  const [isRunning, setIsRunning] = useState(false);

  const report = useCallback((step: StepReport) => {
    setSteps((prev) => {
      const i = prev.findIndex((s) => s.id === step.id);
      if (i === -1) return [...prev, step];
      const next = [...prev];
      next[i] = step;
      return next;
    });
  }, []);

  const runForMyself = useCallback(() => {
    const token = KeyCloakService.GetToken();
    if (!token) return;
    setSteps([]);
    setIsRunning(true);
    void authzProbeScenario(token, token, deps, report).finally(() => setIsRunning(false));
  }, [report]);

  const runForProfile = useCallback(
    (username: string, password: string) => {
      const adminToken = KeyCloakService.GetToken();
      const realmConfig = KeyCloakService.GetKeycloakRealmConfig();
      if (!adminToken || !realmConfig) return;
      setSteps([]);
      setIsRunning(true);
      void (async () => {
        const targetToken = await runStep(report, "login-as", `Log in as ${username}`, async () => {
          const token = await loginWithPassword(realmConfig, username, password);
          return { value: token, detail: `authenticated as ${username}` };
        });
        if (!targetToken) return;
        await authzProbeScenario(adminToken, targetToken, deps, report);
      })().finally(() => setIsRunning(false));
    },
    [report],
  );

  return { steps, isRunning, runForMyself, runForProfile };
}
