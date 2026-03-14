import ImageFileInput from "@shared/atoms/ImageFileInput/ImageFileInput.tsx";
import Switch from "@shared/atoms/Switch/Switch.tsx";
import TextArea from "@shared/atoms/TextArea/TextArea.tsx";
import Button from "@shared/atoms/Button/Button.tsx";
import { ChangeEvent, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  TeamWithPermissions,
  useUpdateTeamMutation,
  useUploadTeamBannerMutation,
} from "../../../../../slices/controlPlane/controlPlaneApi.ts";
import styles from "./TeamSettingsParameters.module.scss";

interface TeamSettingsParametersProps {
  team: TeamWithPermissions;
}

const ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp"];
const MAX_BANNER_FILE_SIZE_BYTES = 5 * 1024 * 1024;

export default function TeamSettingsParameters({ team }: TeamSettingsParametersProps) {
  const { t } = useTranslation();
  const [updateTeam, { isLoading, isSuccess, isError }] = useUpdateTeamMutation();
  const [uploadTeamBanner, { isLoading: isUploadingBanner }] = useUploadTeamBannerMutation();
  const [description, setDescription] = useState(team.description || "");
  const [isPrivate, setIsPrivate] = useState(team.is_private || false);
  const [bannerUploadError, setBannerUploadError] = useState<string | null>(null);
  const [bannerUploadSuccess, setBannerUploadSuccess] = useState(false);

  useEffect(() => {
    setDescription(team.description || "");
    setIsPrivate(team.is_private || false);
  }, [team.id, team.description, team.is_private]);

  const canUpdateInfo = team.permissions?.includes("can_update_info");

  const hasChanges = useMemo(() => {
    return description !== (team.description || "") || isPrivate !== (team.is_private || false);
  }, [description, isPrivate, team.description, team.is_private]);

  const handleDescriptionChange = (event: ChangeEvent<HTMLTextAreaElement>) => {
    setDescription(event.target.value);
  };

  const handleBannerFileChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    setBannerUploadError(null);
    setBannerUploadSuccess(false);

    if (!ALLOWED_TYPES.includes(file.type)) {
      setBannerUploadError(t("teamSettingsPage.teamBanner.invalidType"));
      return;
    }

    if (file.size > MAX_BANNER_FILE_SIZE_BYTES) {
      setBannerUploadError(t("teamSettingsPage.teamBanner.tooLarge"));
      return;
    }

    try {
      await uploadTeamBanner({
        teamId: team.id,
        file,
      }).unwrap();
      setBannerUploadSuccess(true);
    } catch (error) {
      const detail =
        typeof error === "object" &&
        error !== null &&
        "data" in error &&
        typeof (error as { data?: { detail?: unknown } }).data?.detail === "string"
          ? (error as { data?: { detail?: string } }).data?.detail
          : null;
      setBannerUploadError(
        detail || t("teamSettingsPage.teamBanner.uploadError"),
      );
    }
  };

  const handleSave = async () => {
    if (!hasChanges || isLoading) return;
    try {
      await updateTeam({
        teamId: team.id,
        updateTeamRequest: {
          description,
          is_private: isPrivate,
        },
      }).unwrap();
    } catch {
      // Error state is exposed via `isError`.
    }
  };

  return (
    <div className={styles["team-settings-parameters-container"]}>
      <div className={styles["form-section"]}>
        {isError && (
          <span className={styles["status-error"]}>
            {t("teamSettingsPage.saveError", { defaultValue: "Failed to save team settings." })}
          </span>
        )}
        {isSuccess && !isError && (
          <span className={styles["status-success"]}>{t("teamSettingsPage.saveSuccess", { defaultValue: "Team settings saved." })}</span>
        )}
      </div>
      <div className={`${styles["form-section"]} ${styles["team-images-section"]}`}>
        <div className={styles["team-banner"]}>
          <span className={styles["team-banner-title"]}>{t("rework.teamSettings.parameters.teamBannerTitle")}</span>
          {bannerUploadError && <span className={styles["status-error"]}>{bannerUploadError}</span>}
          {bannerUploadSuccess && !bannerUploadError && (
            <span className={styles["status-success"]}>{t("teamSettingsPage.teamBanner.uploadSuccess")}</span>
          )}
          <ImageFileInput
            imageUrl={team.banner_image_url ? team.banner_image_url : "/images/default-team-banner.png"}
            alt={t("teamSettingsPage.teamBanner.alt")}
            height={"80px"}
            accept={ALLOWED_TYPES.join(",")}
            disabled={!canUpdateInfo || isUploadingBanner}
            onChange={handleBannerFileChange}
          />
        </div>
      </div>
      <div className={styles["form-section"]}>
        <TextArea
          label={t("rework.teamSettings.parameters.description.label")}
          placeholder={t("rework.teamSettings.parameters.description.placeholder")}
          maxLength={180}
          value={description}
          onChange={handleDescriptionChange}
        />
      </div>
      <div className={`${styles["form-section"]} ${styles["private-state"]}`}>
        {t("rework.teamSettings.parameters.privateTeam")}
        <Switch checked={isPrivate} onChange={(event) => setIsPrivate(event.target.checked)} />
      </div>
      <div className={styles["form-section"]}>
        <TextArea
          label={t("rework.teamSettings.parameters.teamPrompt.label")}
          maxLength={180}
          placeholder={t("rework.teamSettings.parameters.teamPrompt.placeholder")}
          disabled={true}
        />
      </div>
      <div className={`${styles["form-section"]} ${styles["actions"]}`}>
        <Button color="primary" variant="filled" size="medium" onClick={handleSave} disabled={!hasChanges || isLoading}>
          {isLoading ? t("teamSettingsPage.saving", { defaultValue: "Saving..." }) : t("teamSettingsPage.save", { defaultValue: "Save" })}
        </Button>
      </div>
    </div>
  );
}
