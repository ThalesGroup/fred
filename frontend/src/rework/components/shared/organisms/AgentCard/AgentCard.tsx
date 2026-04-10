import styles from "./AgentCard.module.scss";
import { Agent } from "../../../../../slices/agentic/agenticOpenApi.ts";
import Icon from "@components/shared/atoms/Icon/Icon.tsx";
import IconButton from "@components/shared/atoms/IconButton/IconButton.tsx";
import { useTranslation } from "react-i18next";
import { AnyAgent } from "../../../../../common/agent.ts";
import { useFrontendProperties } from "../../../../../hooks/useFrontendProperties.ts";
import { IconType } from "@shared/utils/Type.ts";

interface AgentCardProps {
  agent: Agent;
  readOnly: boolean;
  onToggleEnabled: (agent: AnyAgent) => void;
  onEditAgent: (agent: AnyAgent) => void;
}

export default function AgentCard({ agent, readOnly, onToggleEnabled, onEditAgent }: AgentCardProps) {
  const { agentIconName } = useFrontendProperties();
  const { t } = useTranslation();

  return (
    <div className={styles.agentCard} data-enabled={agent.enabled}>
      <div className={styles.stateLayer}>
        <div className={styles.agentInfo}>
          <div className={styles.agentPresentation}>
            <div className={styles.agentIcon}>
              <Icon category={"outlined"} type={agentIconName as IconType} />
            </div>
            <div className={styles.agentIdentity}>
              <div className={styles.agentName}>{agent.name}</div>
              <div className={styles.agentRole}>{agent.tuning.role}</div>
            </div>
          </div>
          <div className={styles.agentDescription}>{agent.tuning.description}</div>
        </div>
        {readOnly && (
          <div className={styles.actions}>
            <IconButton
              color={"on-surface"}
              variant={"icon"}
              size={"medium"}
              icon={{ category: "outlined", type: agent.enabled ? "visibility" : "visibility_off" }}
              onClick={(e) => {
                e.preventDefault();
                onToggleEnabled(agent);
              }}
            />
            <IconButton
              color={"on-surface"}
              variant={"icon"}
              size={"medium"}
              icon={{ category: "outlined", type: "edit" }}
              onClick={(e) => {
                e.preventDefault();
                onEditAgent(agent);
              }}
            />
          </div>
        )}
      </div>
      <div className={styles.newChat}>
        <span className={styles.newChatIcon}>
          <Icon category={"outlined"} type={"reviews"} />
        </span>
        {t("rework.agentCard.startChat")}
      </div>
    </div>
  );
}
