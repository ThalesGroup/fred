import Button from "@shared/atoms/Button/Button.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { IconType } from "@shared/utils/Type.ts";
import { useTranslation } from "react-i18next";
import { useFrontendProperties } from "../../../../../hooks/useFrontendProperties.ts";
import styles from "./TeamAgentEmptyState.module.scss";

interface TeamAgentEmptyStateProps {
  canManageAgents: boolean;
  templatesUnavailable: boolean;
  onCreateAgent: () => void;
}

export default function TeamAgentEmptyState({
  canManageAgents,
  templatesUnavailable,
  onCreateAgent,
}: TeamAgentEmptyStateProps) {
  const { agentIconName, agentsNicknameSingular } = useFrontendProperties();
  const { t } = useTranslation();

  return (
    <div className={styles.teamAgentEmptyState}>
      <div className={styles.teamAgentEmptyStatePresentation}>
        <span className={styles.teamAgentEmptyStateIcon}>
          <Icon category={"outlined"} type={agentIconName as IconType} filled={true} />
        </span>
        <span>{t("rework.teams.agents.noAgent", { agentsNicknameSingular })}</span>
      </div>
      {canManageAgents && (
        <Button
          color={"primary"}
          variant={"filled"}
          size={"medium"}
          icon={{ category: "outlined", type: "add" }}
          onClick={onCreateAgent}
          disabled={templatesUnavailable}
        >
          {t("rework.teams.agents.firstCreate", { agentsNicknameSingular })}
        </Button>
      )}
    </div>
  );
}
