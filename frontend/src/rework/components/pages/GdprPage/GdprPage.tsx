import styles from "./GdprPage.module.css";
import Button from "@shared/atoms/Button/Button.tsx";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

export default function GdprPage() {
  const { t } = useTranslation();

  return (
    <div className={styles.gdprContainer}>
      <div className={styles.gdprTitle}>{t("rework.gcu.title")}</div>
      <div className={styles.gdprContent}>
      </div>
      <div className={styles.gdprActions}>
        <Link to={"/"}>
          <Button color={"primary"} variant={"filled"} size={"medium"}>
            {t("rework.gcu.backToApp")}
          </Button>
        </Link>
      </div>
    </div>
  );
}
