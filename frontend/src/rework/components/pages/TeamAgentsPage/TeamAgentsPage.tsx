import Button from "@components/shared/atoms/Button/Button";
import styles from "./TeamAgentsPage.module.scss";
import { useTranslation } from "react-i18next";
import { useListAgentsAgenticV1AgentsGetQuery } from "../../../../slices/agentic/agenticOpenApi.ts";
import { useParams } from "react-router-dom";
import AgentCard from "@shared/organisms/AgentCard/AgentCard.tsx";
import { useGetTeamQuery } from "../../../../slices/controlPlane/controlPlaneApi.ts";
import { useMemo } from "react";
import { useAgentUpdater } from "../../../../hooks/useAgentUpdater.ts";
import { AnyAgent } from "../../../../common/agent.ts";

export default function TeamAgentsPage() {
  const { t } = useTranslation();
  const { teamId } = useParams();
  const { data: agents, refetch } = useListAgentsAgenticV1AgentsGetQuery({ ownerFilter: "team", teamId });
  const { data: team } = useGetTeamQuery({ teamId: teamId !== "user" ? teamId : "" }, { skip: !teamId });
  const { updateEnabled } = useAgentUpdater();

  const canUpdateAgents = useMemo(() => {
    return team?.permissions?.includes("can_update_agents");
  }, [team]);

  const handleToggleEnabled = async (agent: AnyAgent) => {
    const isEnabled = agent.enabled !== false;
    await updateEnabled(agent, !isEnabled);
    await refetch();
  };

  return (
    <div className={styles.teamAgentContainer}>
      <div className={styles.title}>
        {t("rework.teams.agents.title")}
        <Button color={"primary"} variant={"filled"} size={"medium"} icon={{ category: "outlined", type: "add" }}>
          {t("rework.teams.agents.create")}
        </Button>
      </div>
      <div className={styles.agentList}>
        {agents?.map((agent) => (
          <>
            <AgentCard key={agent.id} agent={agent} readOnly={canUpdateAgents} onToggleEnabled={handleToggleEnabled} />
          </>
        ))}
      </div>
    </div>
  );
}
