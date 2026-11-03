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
import type { IconType } from "../../components/shared/utils/Type";
import { useAgentsDeps } from "./deps/agents";
import { useAuthorizationDeps } from "./deps/authorization";
import { useConversationsDeps } from "./deps/conversations";
import { useKnowledgeDeps } from "./deps/knowledge";
import { useObservabilityDeps } from "./deps/observability";
import { usePlatformDeps } from "./deps/platform";
import { usePromptsDeps } from "./deps/prompts";
import { useSecurityDeps } from "./deps/security";
import { useTeamsDeps } from "./deps/teams";
import { agentsScenario } from "./scenarios/agentsScenario";
import { authorizationScenario } from "./scenarios/authorizationScenario";
import { conversationsScenario } from "./scenarios/conversationsScenario";
import { knowledgeScenario } from "./scenarios/knowledgeScenario";
import { observabilityScenario } from "./scenarios/observabilityScenario";
import { platformScenario } from "./scenarios/platformScenario";
import { promptsScenario } from "./scenarios/promptsScenario";
import { securityScenario } from "./scenarios/securityScenario";
import { teamsScenario } from "./scenarios/teamsScenario";
import { webResearchScenario } from "./scenarios/webResearchScenario";
import { useAuthzProbeRun } from "./useAuthzProbeRun";
import { usePipelineDeps } from "./usePipelineRun";
import { useScenarioRun, type PipelineRun } from "./useScenarioRun";

export type FamilyId =
  | "platform"
  | "identity"
  | "knowledge"
  | "agents"
  | "prompts"
  | "conversations"
  | "teams"
  | "web"
  | "security"
  | "observability"
  | "authorization";

export interface SelfTestFamily {
  id: FamilyId;
  icon: IconType;
  run: PipelineRun;
}

/** Every family, in page order. The hooks run unconditionally, so the order never changes. */
export function useSelfTestFamilies(): SelfTestFamily[] {
  const deps = usePipelineDeps();
  const platform = useScenarioRun(platformScenario, usePlatformDeps());
  const identity = useAuthzProbeRun();
  const authorization = useScenarioRun(authorizationScenario, useAuthorizationDeps());
  const knowledgeDeps = useKnowledgeDeps(deps);
  const knowledge = useScenarioRun(knowledgeScenario, knowledgeDeps);
  const agents = useScenarioRun(agentsScenario, useAgentsDeps(deps));
  const prompts = useScenarioRun(promptsScenario, usePromptsDeps(deps));
  const conversations = useScenarioRun(conversationsScenario, useConversationsDeps(deps));
  const teams = useScenarioRun(teamsScenario, useTeamsDeps());
  const web = useScenarioRun(webResearchScenario, deps);
  const security = useScenarioRun(securityScenario, useSecurityDeps(knowledgeDeps));
  const observability = useScenarioRun(observabilityScenario, useObservabilityDeps());

  return [
    { id: "platform", icon: "cloud", run: platform },
    { id: "identity", icon: "person", run: { ...identity, start: identity.runIdentity } },
    { id: "knowledge", icon: "database", run: knowledge },
    { id: "agents", icon: "smart_toy", run: agents },
    { id: "prompts", icon: "notes", run: prompts },
    { id: "conversations", icon: "forum", run: conversations },
    { id: "teams", icon: "groups", run: teams },
    { id: "web", icon: "travel_explore", run: web },
    { id: "security", icon: "shield", run: security },
    { id: "observability", icon: "analytics", run: observability },
    { id: "authorization", icon: "admin_panel_settings", run: authorization },
  ];
}
