// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import type { IconType } from "../../components/shared/utils/Type";
import type { PipelineRun } from "./useScenarioRun";

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

export function selfTestFamilies(runs: Record<FamilyId, PipelineRun>): SelfTestFamily[] {
  const {
    platform,
    identity,
    knowledge,
    agents,
    prompts,
    conversations,
    teams,
    web,
    security,
    observability,
    authorization,
  } = runs;
  return [
    { id: "platform", icon: "cloud", run: platform },
    { id: "identity", icon: "person", run: identity },
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
