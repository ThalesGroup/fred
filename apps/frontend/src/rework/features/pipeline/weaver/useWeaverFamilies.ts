// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { selfTestFamilies, type FamilyId, type SelfTestFamily } from "../familyCatalog";
import { useScenarioRun } from "../useScenarioRun";
import { runStep, SkipStep } from "../step";
import type { Scenario } from "../types";
import { sharedAuthorization, spaceAuthorization } from "./authorization";
import type { WeaverChecks } from "./checks";
import {
  sharedPlatform,
  organizationCatalogs,
  identity,
  sharedSecurity,
  documentSecurity,
  sharedObservability,
  spaceObservability,
} from "./platformChecks";
import { knowledge, agents, prompts, conversations, teams } from "./resourceScenarios";
import { web } from "./runtime";

export type WeaverLevel = "shared" | "organization" | "team" | "project" | "personal";
const shared: Partial<Record<FamilyId, Scenario<WeaverChecks>>> = {
  platform: sharedPlatform,
  identity,
  security: sharedSecurity,
  observability: sharedObservability,
  authorization: sharedAuthorization,
};
const local: Partial<Record<FamilyId, Scenario<WeaverChecks>>> = {
  knowledge,
  agents,
  prompts,
  conversations,
  web,
  security: documentSecurity,
  observability: spaceObservability,
  authorization: spaceAuthorization,
};
function skipped(id: FamilyId, reason: string): Scenario<WeaverChecks> {
  return async (_checks, report) => {
    await runStep(report, `${id}.scope`, "Check operations supported at this level", async () => {
      throw new SkipStep(reason);
    });
  };
}
/** Partition before execution so unsupported levels cannot dispatch resource mutations. */
export function weaverScenarios(level: WeaverLevel): Partial<Record<FamilyId, Scenario<WeaverChecks>>> {
  if (level === "shared") return shared;
  const scenarios = { ...local };
  if (level === "organization") {
    scenarios.platform = organizationCatalogs;
    scenarios.teams = teams;
    for (const id of ["agents", "conversations", "web"] as const)
      scenarios[id] = skipped(
        id,
        "Agent provisioning supports team, project and personal spaces; this is the organization level.",
      );
  }
  return scenarios;
}
const unused: Scenario<WeaverChecks> = async () => {};
export function useWeaverFamilies(context: WeaverChecks, level: WeaverLevel): SelfTestFamily[] {
  const scenarios = weaverScenarios(level);
  // Keep every hook in a fixed order when the selected level changes.
  return selfTestFamilies({
    platform: useScenarioRun(scenarios.platform ?? unused, context),
    identity: useScenarioRun(scenarios.identity ?? unused, context),
    knowledge: useScenarioRun(scenarios.knowledge ?? unused, context),
    agents: useScenarioRun(scenarios.agents ?? unused, context),
    prompts: useScenarioRun(scenarios.prompts ?? unused, context),
    conversations: useScenarioRun(scenarios.conversations ?? unused, context),
    teams: useScenarioRun(scenarios.teams ?? unused, context),
    web: useScenarioRun(scenarios.web ?? unused, context),
    security: useScenarioRun(scenarios.security ?? unused, context),
    observability: useScenarioRun(scenarios.observability ?? unused, context),
    authorization: useScenarioRun(scenarios.authorization ?? unused, context),
  }).filter(({ id }) => scenarios[id]);
}
