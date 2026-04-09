import styles from "./AgentV1CreateEditForm.module.css";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import { useTranslation } from "react-i18next";

export default function AgentV1CreateEditForm() {
  const { t } = useTranslation();

  return (
    <div className={styles.agentCreateEditFormContainer}>
      <TextInput
        placeholder={t("rework.teams.formAgent.fields.name.placeholder")}
        label={t("rework.teams.formAgent.fields.name.label")}
      />
    </div>
  );
}
