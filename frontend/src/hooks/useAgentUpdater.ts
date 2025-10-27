// src/components/agentHub/hooks/useAgentUpdater.ts

import { AnyAgent } from "../common/agent";
import { Agent, Leader, useUpdateAgentAgenticV1AgentsUpdatePutMutation } from "../slices/agentic/agenticOpenApi";

export function useAgentUpdater() {
  const [mutate, meta] = useUpdateAgentAgenticV1AgentsUpdatePutMutation();

  const updateEnabled = async (agent: AnyAgent, enabled: boolean) => {
    const payload =
      agent.type === "leader"
        ? ({ ...agent, enabled, type: "leader" } as { type: "leader" } & Leader)
        : ({ ...agent, enabled, type: "agent" } as { type: "agent" } & Agent);
    return mutate({ agentSettings: payload }).unwrap();
  };

  const updateTuning = async (
    agent: AnyAgent,
    newTuning: NonNullable<AnyAgent["tuning"]>,
    isGlobal: boolean = false,
  ) => {
    const payload =
      agent.type === "leader"
        ? ({ ...agent, tuning: newTuning, type: "leader" } as { type: "leader" } & Leader)
        : ({ ...agent, tuning: newTuning, type: "agent" } as { type: "agent" } & Agent);
    return mutate({ agentSettings: payload, isGlobal }).unwrap();
  };

  const updateLeaderCrew = async (leader: Leader & { type: "leader" }, crew: string[]) => {
    const payload: { type: "leader" } & Leader = { ...leader, crew, type: "leader" };
    return mutate({ agentSettings: payload }).unwrap();
  };

  return { updateEnabled, updateTuning, updateLeaderCrew, isLoading: meta.isLoading };
}
