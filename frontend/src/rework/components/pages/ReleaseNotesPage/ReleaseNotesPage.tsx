import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button.tsx";
import ReleaseNotes from "../../../../pages/ReleaseNotes.tsx";
import styles from "./ReleaseNotesPage.module.css";

export default function ReleaseNotesPage() {
  const { t } = useTranslation();

  return (
    <div className={styles.releaseNotesContainer}>
      <div className={styles.releaseNotesHeader}>
        <Link to={"/"}>
          <Button
            color={"primary"}
            variant={"text"}
            size={"medium"}
            icon={{ category: "outlined", type: "arrow_back", filled: true }}
          >
            {t("rework.back")}
          </Button>
        </Link>
        <span className={styles.releaseNotesTitle}>{t("rework.userSettings.accessReleaseNotes")}</span>
      </div>
      <div className={styles.releaseNotesContent}>
        <ReleaseNotes />
      </div>
    </div>
  );
}
