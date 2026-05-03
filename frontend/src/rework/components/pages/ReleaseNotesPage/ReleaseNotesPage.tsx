import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button.tsx";
import ReleaseNotes from "../../../../pages/ReleaseNotes.tsx";
import styles from "./ReleaseNotesPage.module.css";

export default function ReleaseNotesPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <div className={styles.releaseNotesContainer}>
      <div className={styles.releaseNotesHeader}>
        <Button
          color={"primary"}
          variant={"text"}
          size={"medium"}
          icon={{ category: "outlined", type: "arrow_back", filled: true }}
          onClick={() => navigate(-1)}
        >
          {t("rework.back")}
        </Button>
        <span className={styles.releaseNotesTitle}>{t("rework.userSettings.accessReleaseNotes")}</span>
      </div>
      <div className={styles.releaseNotesContent}>
        <ReleaseNotes />
      </div>
    </div>
  );
}
