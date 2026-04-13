import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { AnyAgent } from "../../../../common/agent.ts";
import { useAgentUpdater } from "../../../../hooks/useAgentUpdater.ts";
import { useListAgentsAgenticV1AgentsGetQuery } from "../../../../slices/agentic/agenticOpenApi.ts";
import { useGetTeamQuery } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { useGetUserDetailsControlPlaneV1UserGetQuery } from "../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import styles from "./TeamAgentsPage.module.css";
import TeamAgentContent from "@components/pages/TeamAgentsPage/TeamAgentContent/TeamAgentContent.tsx";
import TeamAgentEmptyState from "@components/pages/TeamAgentsPage/TeamAgentEmptyState/TeamAgentEmptyState.tsx";
import { FullPageModal } from "@shared/molecules/FullPageModal/FullPageModal.tsx";
import AgentCreateEditModal from "@components/pages/TeamAgentsPage/AgentCreateEditModal/AgentCreateEditModal.tsx";

export default function TeamAgentsPage() {
  const { teamId } = useParams();
  const { data: userDetails } = useGetUserDetailsControlPlaneV1UserGetQuery();
  const isPersonalTeam = teamId === userDetails?.personalTeam.id;

  const ownerFilter = isPersonalTeam ? "personal" : "team";
  const { data: agents, refetch } = useListAgentsAgenticV1AgentsGetQuery({ ownerFilter, teamId });
  const { data: noPersonalTeam } = useGetTeamQuery({ teamId: teamId || "" }, { skip: isPersonalTeam });
  const team = isPersonalTeam ? userDetails?.personalTeam : noPersonalTeam;

  const { updateEnabled } = useAgentUpdater();

  const [selected, setSelected] = useState<AnyAgent | null>(null);
  const [editOpen, setEditOpen] = useState(false);

  const canUpdateAgents = useMemo(() => {
    return team?.permissions?.includes("can_update_agents");
  }, [team]);

  const handleToggleEnabled = async (agent: AnyAgent) => {
    const isEnabled = agent.enabled;
    await updateEnabled(agent, !isEnabled);
    await refetch();
  };

  const handleOpenCreateAgent = () => {
    setSelected(null);
    setEditOpen(true);
  };

  const handleEdit = (agent: AnyAgent) => {
    setSelected(agent);
    setEditOpen(true);
  };

  return (
    <div className={styles.teamAgentContainer}>
      {agents?.length !== 0 ? (
        <TeamAgentContent
          agents={agents}
          onCreateAgent={handleOpenCreateAgent}
          onEditAgent={handleEdit}
          onToggleAgent={handleToggleEnabled}
          canUpdateAgents={canUpdateAgents}
        />
      ) : (
        <TeamAgentEmptyState onCreateAgent={handleOpenCreateAgent} canUpdateAgents={canUpdateAgents} />
      )}
      <FullPageModal isOpen={editOpen} onClose={() => setEditOpen(false)} id={"create-edit-agent-modal"}>
        <AgentCreateEditModal
          modalInteraction={{ close: () => setEditOpen(false) }}
          teamName={team?.name}
          agent={selected}
          canDelete={canUpdateAgents}
          teamId={teamId}
          onDeleted={refetch}
          onSaved={refetch}
        />
      </FullPageModal>
    </div>
  );
}
