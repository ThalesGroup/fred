// Copyright Thales 2026
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0

import { useState } from "react";
import { KeyCloakService } from "../../../security/KeycloakService";
import { authedFetch } from "./useAuthzProbeRun";
import { loginWithPassword } from "./keycloakDirectGrant";
import { useRunner } from "./useScenarioRun";
import { runStep } from "./step";
import {
  CAMPAIGN_JOURNAL_KEY,
  CAMPAIGN_LOCK,
  recoverRoleCampaign,
  roleCampaignScenario,
  type CampaignDeps,
} from "./scenarios/roleCampaignScenario";

export function useRoleCampaignRun() {
  const runner = useRunner();
  const [hasRecovery, setHasRecovery] = useState(() => {
    try {
      return localStorage.getItem(CAMPAIGN_JOURNAL_KEY) !== null;
    } catch {
      return true;
    }
  });
  const start = (credential: () => Promise<string>, recovery = false) =>
    runner.run(async (report, signal) => {
      await runStep(
        report,
        "campaign-execution",
        recovery ? "Recover interrupted role campaign" : "Run automatic role campaign",
        async () => {
          if (!navigator.locks)
            throw new Error("This browser needs Web Locks support to run or recover a role campaign safely");
          await navigator.locks.request(CAMPAIGN_LOCK, { ifAvailable: true }, async (lock) => {
            if (!lock) throw new Error("Another role campaign or recovery is active in this browser");
            if (!(await KeyCloakService.ensureFreshToken(30))) throw new Error("Sign in again as the bootstrap root");
            const adminToken = KeyCloakService.GetToken();
            if (!adminToken) throw new Error("No administrator credential");
            const adminId = KeyCloakService.GetUserId();
            const deps: CampaignDeps = {
              // Refresh only the admin session. The independent test token stays fixed.
              request: async (path, token, init) => {
                if (token !== adminToken) return authedFetch(path, token, init);
                if (!(await KeyCloakService.ensureFreshToken(30)) || KeyCloakService.GetUserId() !== adminId)
                  throw new Error("The administrator session expired or changed; use recovery");
                const fresh = KeyCloakService.GetToken();
                if (!fresh) throw new Error("No administrator credential; use recovery");
                return authedFetch(path, fresh, init);
              },
              readJournal: () => {
                const value = localStorage.getItem(CAMPAIGN_JOURNAL_KEY);
                return value === null ? null : JSON.parse(value);
              },
              saveJournal: (journal) => {
                if (journal) localStorage.setItem(CAMPAIGN_JOURNAL_KEY, JSON.stringify(journal));
                else localStorage.removeItem(CAMPAIGN_JOURNAL_KEY);
                setHasRecovery(journal !== null);
              },
            };
            try {
              if (recovery) await recoverRoleCampaign(adminToken, deps, report);
              else {
                const targetToken = (await credential()).trim().replace(/^Bearer\s+/i, "");
                if (!targetToken) throw new Error("Supply the dedicated test account credential");
                await roleCampaignScenario(adminToken, targetToken, deps, report, signal);
              }
            } finally {
              setHasRecovery(localStorage.getItem(CAMPAIGN_JOURNAL_KEY) !== null);
            }
          });
          return { value: true };
        },
      );
    });
  return {
    steps: runner.steps,
    isRunning: runner.isRunning,
    hasRecovery,
    runForToken: (token: string) => start(async () => token),
    runForProfile: (username: string, password: string) =>
      start(async () => {
        const realm = KeyCloakService.GetKeycloakRealmConfig();
        if (!realm) throw new Error("No Keycloak direct-login configuration");
        return loginWithPassword(realm, username, password);
      }),
    recover: () => start(async () => "", true),
  };
}
