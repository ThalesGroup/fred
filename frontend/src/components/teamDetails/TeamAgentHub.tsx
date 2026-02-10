import { useTranslation } from "react-i18next";
import { usePermissions } from "../../security/usePermissions";
import { useListAgentsAgenticV1AgentsGetQuery } from "../../slices/agentic/agenticOpenApi";
import { AgentGridManager } from "../agentHub/AgentGridManager";

interface TeamAgentHubProps {
  teamId: string;
}

export function TeamAgentHub({ teamId }: TeamAgentHubProps) {
  const { t } = useTranslation();

  const { data: agents, isLoading, refetch } = useListAgentsAgenticV1AgentsGetQuery({ ownerFilter: "team", teamId });

  // Permissions
  // todo: base perm on ReBAC
  const { can } = usePermissions();
  const canEditAgents = can("agents", "update");
  const canCreateAgents = can("agents", "create");

  const handleRefetch = async () => {
    await refetch();
  };

  return (
    <AgentGridManager
      agents={agents || []}
      isLoading={isLoading}
      teamId={teamId}
      canEdit={canEditAgents}
      canCreate={canCreateAgents}
      canDelete={canEditAgents}
      onRefetchAgents={handleRefetch}
      showRestoreButton={false}
      showA2ACard={false}
      emptyStateMessage={t("teamDetails.noAgents")}
    />
  );
}
