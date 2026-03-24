import Button from "@components/shared/atoms/Button/Button";
import styles from "./TeamAgentsPage.module.scss";
import { useTranslation } from "react-i18next";

export default function TeamAgentsPage() {
  const { t } = useTranslation();

  return (
    <div className={styles.teamAgentContainer}>
      <div className={styles.title}>
        {t("rework.teams.agents.title")}
        <Button color={"primary"} variant={"filled"} size={"medium"} icon={{ category: "outlined", type: "add" }}>
          {t("rework.teams.agents.create")}
        </Button>
      </div>
        <div className={styles.agentList}>
        </div>
    </div>
  );
}
