import Icon from "@components/shared/atoms/Icon/Icon";
import styles from "./TeamAgentEmptyState.module.scss";
import { useFrontendProperties } from "../../../../../hooks/useFrontendProperties.ts";
import { IconType } from "@shared/utils/Type.ts";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button.tsx";

interface TeamAgentEmptyStateProps {
  onCreateAgent: () => void;
}

export default function TeamAgentEmptyState({ onCreateAgent }: TeamAgentEmptyStateProps) {
  const { agentIconName, agentsNicknameSingular } = useFrontendProperties();
  const { t } = useTranslation();

  return (
    <div className={styles.teamAgentEmptyState}>
      <div className={styles.teamAgentEmptyStatePresentation}>
        <span className={styles.teamAgentEmptyStateIcon}>
          <Icon category={"outlined"} type={agentIconName as IconType} filled={true} />
        </span>
        <span>{t("rework.teams.agents.firstTitle", { agentsNicknameSingular })}</span>
      </div>
      <Button
        color={"primary"}
        variant={"filled"}
        size={"medium"}
        icon={{ category: "outlined", type: "add" }}
        onClick={onCreateAgent}
      >
        {t("rework.teams.agents.firstCreate", { agentsNicknameSingular })}
      </Button>
    </div>
  );
}
