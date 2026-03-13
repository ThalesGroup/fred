import ImageFileInput from "@shared/atoms/ImageFileInput/ImageFileInput.tsx";
import Switch from "@shared/atoms/Switch/Switch.tsx";
import TextArea from "@shared/atoms/TextArea/TextArea.tsx";
import { useTranslation } from "react-i18next";
import { TeamWithPermissions } from "../../../../../slices/controlPlane/controlPlaneApi.ts";
import styles from "./TeamSettingsParameters.module.scss";

interface TeamSettingsParametersProps {
  team: TeamWithPermissions;
}

const ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp"];

export default function TeamSettingsParameters({ team }: TeamSettingsParametersProps) {
  const { t } = useTranslation();

  return (
    <div className={styles["team-settings-parameters-container"]}>
      <div className={styles["form-section"]}>
        {t("teamSettingsPage.readOnlyNotice", {
          defaultValue: "Team settings update is temporarily disabled while migration to control-plane is completed.",
        })}
      </div>
      <div className={`${styles["form-section"]} ${styles["team-images-section"]}`}>
        <div className={styles["team-banner"]}>
          <span className={styles["team-banner-title"]}>{t("rework.teamSettings.parameters.teamBannerTitle")}</span>
          <ImageFileInput
            imageUrl={team.banner_image_url ? team.banner_image_url : "/images/default-team-banner.png"}
            alt={""}
            height={"80px"}
            accept={ALLOWED_TYPES.join(",")}
            disabled={true}
          />
        </div>
      </div>
      <div className={styles["form-section"]}>
        <TextArea
          label={t("rework.teamSettings.parameters.description.label")}
          placeholder={t("rework.teamSettings.parameters.description.placeholder")}
          maxLength={180}
          value={team.description || ""}
          readOnly={true}
          disabled={true}
        />
      </div>
      <div className={`${styles["form-section"]} ${styles["private-state"]}`}>
        {t("rework.teamSettings.parameters.privateTeam")}
        <Switch checked={team.is_private || false} disabled={true} />
      </div>
      <div className={styles["form-section"]}>
        <TextArea
          label={t("rework.teamSettings.parameters.teamPrompt.label")}
          maxLength={180}
          placeholder={t("rework.teamSettings.parameters.teamPrompt.placeholder")}
          disabled={true}
        />
      </div>
    </div>
  );
}
