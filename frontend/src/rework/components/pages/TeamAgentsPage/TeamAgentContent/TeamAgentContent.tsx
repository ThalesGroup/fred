import Button from "@shared/atoms/Button/Button.tsx";
import { Link, useParams } from "react-router-dom";
import { useFrontendProperties } from "../../../../../hooks/useFrontendProperties.ts";
import { useTranslation } from "react-i18next";
import { useMemo } from "react";
import { useGetUserDetailsControlPlaneV1UserGetQuery } from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { useGetTeamQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements.ts";
import { AnyAgent } from "../../../../../common/agent.ts";
import AgentCard from "@shared/organisms/AgentCard/AgentCard.tsx";
import styles from "./TeamAgentContent.module.scss";

interface TeamAgentContentProps {
  agents: AnyAgent[];
  onCreateAgent: () => void;
  onEditAgent: (agent: AnyAgent) => void;
  onToggleAgent: (agent: AnyAgent) => void;
}

export default function TeamAgentContent({ agents, onCreateAgent, onEditAgent, onToggleAgent }: TeamAgentContentProps) {
  const { agentsNicknameSingular, agentsNicknamePlural } = useFrontendProperties();
  const { t } = useTranslation();

  const { teamId } = useParams();
  const { data: userDetails } = useGetUserDetailsControlPlaneV1UserGetQuery();
  const isPersonalTeam = teamId === userDetails?.personalTeam.id;
  const { data: noPersonalTeam } = useGetTeamQuery({ teamId: teamId || "" }, { skip: isPersonalTeam });
  const team = isPersonalTeam ? userDetails?.personalTeam : noPersonalTeam;

  const canUpdateAgents = useMemo(() => {
    return team?.permissions?.includes("can_update_agents");
  }, [team]);

  const renderAgentCard = (agent: AnyAgent, withKey: boolean = false) => {
    return (
      <AgentCard
        key={withKey ? agent.id : undefined}
        agent={agent}
        // todo: in future, rely on direct `update` and `delete` permissions from agent (when they are returned by backend)
        readOnly={canUpdateAgents}
        onToggleEnabled={onToggleAgent}
        onEditAgent={onEditAgent}
      />
    );
  };

  return (
    <>
      <div className={styles.title}>
        {t("rework.teams.agents.title", { agentsNicknamePlural })}
        {canUpdateAgents && (
          <Button
            color={"primary"}
            variant={"filled"}
            size={"medium"}
            icon={{ category: "outlined", type: "add" }}
            onClick={onCreateAgent}
          >
            {t("rework.teams.agents.create", { agentsNicknameSingular })}
          </Button>
        )}
      </div>
      <div className={styles.agentList}>
        {agents?.map((agent) => (
          <>
            {!agent.enabled ? (
              renderAgentCard(agent, true)
            ) : (
              <Link to={`/team/${teamId}/new-chat/${agent.id}`} key={agent.id}>
                {renderAgentCard(agent)}
              </Link>
            )}
          </>
        ))}
      </div>
    </>
  );
}
