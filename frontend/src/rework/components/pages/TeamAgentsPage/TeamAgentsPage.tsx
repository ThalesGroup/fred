import Button from "@components/shared/atoms/Button/Button";
import styles from "./TeamAgentsPage.module.scss";
import { useTranslation } from "react-i18next";
import { useListAgentsAgenticV1AgentsGetQuery } from "../../../../slices/agentic/agenticOpenApi.ts";
import { useParams } from "react-router-dom";
import AgentCard from "@shared/organisms/AgentCard/AgentCard.tsx";
import { useGetTeamQuery } from "../../../../slices/controlPlane/controlPlaneApi.ts";
import { useMemo, useState } from "react";
import { useAgentUpdater } from "../../../../hooks/useAgentUpdater.ts";
import { AnyAgent } from "../../../../common/agent.ts";
import { AgentCreateEditDrawer } from "../../../../components/agentHub/AgentCreateEditDrawer.tsx";

export default function TeamAgentsPage() {
  const { t } = useTranslation();
  const { teamId } = useParams();
  const { data: agents, refetch } = useListAgentsAgenticV1AgentsGetQuery({ ownerFilter: "team", teamId });
  const { data: team } = useGetTeamQuery({ teamId: teamId !== "user" ? teamId : "" }, { skip: !teamId });
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
      <div className={styles.title}>
        {t("rework.teams.agents.title")}
        {canUpdateAgents && (
          <Button
            color={"primary"}
            variant={"filled"}
            size={"medium"}
            icon={{ category: "outlined", type: "add" }}
            onClick={handleOpenCreateAgent}
          >
            {t("rework.teams.agents.create")}
          </Button>
        )}
      </div>
      <div className={styles.agentList}>
        {/*
            todo: in future, rely on direct `update` and `delete` permissions from agent (when they are returned by backend)
         */}
        {agents?.map((agent) => (
          <>
            <AgentCard
              key={agent.id}
              agent={agent}
              readOnly={canUpdateAgents}
              onToggleEnabled={handleToggleEnabled}
              onEditAgent={handleEdit}
            />
          </>
        ))}
      </div>
      <AgentCreateEditDrawer
        canDelete={canUpdateAgents}
        open={editOpen}
        agent={selected}
        teamId={teamId}
        onClose={() => setEditOpen(false)}
        onSaved={refetch}
        onDeleted={refetch}
      />
    </div>
  );
}
