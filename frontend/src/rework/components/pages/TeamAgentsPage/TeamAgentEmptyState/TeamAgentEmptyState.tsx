import Icon from "@components/shared/atoms/Icon/Icon";
import styles from "./TeamAgentEmptyState.module.css";
import { useFrontendProperties } from "../../../../../hooks/useFrontendProperties.ts";
import { IconType } from "@shared/utils/Type.ts";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button.tsx";

interface TeamAgentEmptyStateProps {
  onCreateAgent: () => void;
  canUpdateAgents: boolean;
}

export default function TeamAgentEmptyState({ onCreateAgent, canUpdateAgents }: TeamAgentEmptyStateProps) {
  const { agentIconName, agentsNicknameSingular, agentDocumentationLink } = useFrontendProperties();
  const { t } = useTranslation();

  return (
    <div className={styles.teamAgentEmptyState}>
      <div className={styles.teamAgentEmptyStatePresentation}>
        <span className={styles.teamAgentEmptyStateIcon}>
          <Icon category={"outlined"} type={agentIconName as IconType} filled={true} />
        </span>
        <span>{t("rework.teams.agents.noAgent", { agentsNicknameSingular })}</span>
      </div>
      {agentDocumentationLink && (
        <a
          className={styles.teamAgentDocumentationLink}
          href={agentDocumentationLink}
          target="_blank"
          rel="noopener noreferrer"
        >
          <Icon category={"outlined"} type={"help"} />
          {t("rework.teams.agents.documentationHelp")}
        </a>
      )}
      {canUpdateAgents && (
        <Button
          color={"primary"}
          variant={"filled"}
          size={"medium"}
          icon={{ category: "outlined", type: "add" }}
          onClick={onCreateAgent}
        >
          {t("rework.teams.agents.firstCreate", { agentsNicknameSingular })}
        </Button>
      )}
    </div>
  );
}
