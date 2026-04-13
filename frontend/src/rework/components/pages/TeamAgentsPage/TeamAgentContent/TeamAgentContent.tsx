import Button from "@shared/atoms/Button/Button.tsx";
import { Link, useParams } from "react-router-dom";
import { useFrontendProperties } from "../../../../../hooks/useFrontendProperties.ts";
import { useTranslation } from "react-i18next";
import { AnyAgent } from "../../../../../common/agent.ts";
import AgentCard from "@shared/organisms/AgentCard/AgentCard.tsx";
import styles from "./TeamAgentContent.module.scss";

interface TeamAgentContentProps {
  agents: AnyAgent[];
  onCreateAgent: () => void;
  onEditAgent: (agent: AnyAgent) => void;
  onToggleAgent: (agent: AnyAgent) => void;
  canUpdateAgents: boolean;
}

export default function TeamAgentContent({
  agents,
  onCreateAgent,
  onEditAgent,
  onToggleAgent,
  canUpdateAgents,
}: TeamAgentContentProps) {
  const { agentsNicknameSingular, agentsNicknamePlural } = useFrontendProperties();
  const { t } = useTranslation();
  const { teamId } = useParams();

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
