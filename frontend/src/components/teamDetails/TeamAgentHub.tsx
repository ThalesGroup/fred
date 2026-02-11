import { useTranslation } from "react-i18next";
import { useListAgentsAgenticV1AgentsGetQuery } from "../../slices/agentic/agenticOpenApi";
import { AgentGridManager } from "../agentHub/AgentGridManager";

interface TeamAgentHubProps {
  teamId: string;
  canCreateAgents?: boolean;
}

export function TeamAgentHub({ teamId, canCreateAgents }: TeamAgentHubProps) {
  const { t } = useTranslation();

  const { data: agents, isLoading, refetch } = useListAgentsAgenticV1AgentsGetQuery({ ownerFilter: "team", teamId });

  const handleRefetch = async () => {
    await refetch();
  };

  return (
    <AgentGridManager
      agents={agents || []}
      isLoading={isLoading}
      teamId={teamId}
      canCreate={canCreateAgents}
      canEdit={canCreateAgents} // todo: remove this props and use permissions list returned with each agents
      canDelete={canCreateAgents} // todo: remove this props and use permissions list returned with each agents
      onRefetchAgents={handleRefetch}
      showRestoreButton={false}
      showA2ACard={false}
      emptyStateMessage={t("teamDetails.noAgents")}
    />
  );
}
