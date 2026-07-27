// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import styles from "./TeamSettingsParameters.module.scss";
import TextArea from "@shared/atoms/TextArea/TextArea.tsx";
import { useTranslation } from "react-i18next";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup.tsx";
import Button from "@shared/atoms/Button/Button.tsx";
import React, { useEffect, useRef } from "react";
import { useForm } from "react-hook-form";
import {
  JoiningMode,
  TeamVisibility,
  TeamWithPermissions,
} from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  useUpdateTeamMutation,
  useUploadTeamBannerMutation,
} from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { useFrontendProperties } from "../../../../../../hooks/useFrontendProperties.ts";
import TeamSettingsRetention from "@shared/organisms/TeamSettingsPanel/TeamSettingsRetention/TeamSettingsRetention.tsx";

interface TeamSettingsParametersProps {
  team: TeamWithPermissions;
}

interface TeamSettingsParametersForm {
  description: string;
}

const MAX_BANNER_SIZE = 5 * 1024 * 1024; // 5MB
const ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp"];

// TEAM-09: order drives the button group's left-to-right layout and index
// mapping — keep in sync with the labels below.
const JOINING_MODES: JoiningMode[] = ["open", "invite_only"];

// TEAM-10: same left-to-right/index convention as JOINING_MODES above.
const VISIBILITIES: TeamVisibility[] = ["public", "private"];

export default function TeamSettingsParameters({ team }: TeamSettingsParametersProps) {
  const { defaultTeamBannerFile } = useFrontendProperties();
  const { t } = useTranslation();
  const [updateTeam] = useUpdateTeamMutation();
  const [uploadBanner] = useUploadTeamBannerMutation();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { register, getValues, watch, reset } = useForm<TeamSettingsParametersForm>({
    defaultValues: {
      description: team.description || "",
    },
  });

  useEffect(() => {
    reset({ description: team.description || "" });
  }, [team.description, reset]);

  const handleSaveDescription = () => {
    const newDescription = getValues().description;
    if (newDescription === team.description) {
      return;
    }
    updateTeam({
      teamId: team.id,
      updateTeamRequest: { description: newDescription },
    });
  };
  const descriptionValue = watch("description");
  const defaultBannerUrl = defaultTeamBannerFile ? `/images/${defaultTeamBannerFile}` : undefined;
  const bannerImageUrl = team.banner_image_url ?? defaultBannerUrl;

  const joiningMode = team.joining_mode ?? "invite_only";
  const handleSelectJoiningMode = (index: number) => {
    const newMode = JOINING_MODES[index];
    if (newMode === joiningMode) {
      return;
    }
    updateTeam({
      teamId: team.id,
      updateTeamRequest: { joining_mode: newMode },
    });
  };

  // TEAM-10: a PRIVATE team can never be OPEN — disabling the whole group
  // while private (rather than just the "Open" option) both prevents
  // picking it and reflects that the server silently downgraded
  // joining_mode to INVITE_ONLY the moment visibility turned private.
  const visibility = team.visibility ?? "public";
  const isPrivate = visibility === "private";
  const handleSelectVisibility = (index: number) => {
    const newVisibility = VISIBILITIES[index];
    if (newVisibility === visibility) {
      return;
    }
    updateTeam({
      teamId: team.id,
      updateTeamRequest: { visibility: newVisibility },
    });
  };

  const handleBannerUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || !team?.id) return;

    // Client-side validation
    if (!ALLOWED_TYPES.includes(file.type)) {
      console.error("Invalid file type:", file.type);
      return;
    }

    if (file.size > MAX_BANNER_SIZE) {
      console.error("File size exceeds limit:", file.size);
      return;
    }

    try {
      await uploadBanner({
        teamId: team.id,
        // The generated client types the multipart file field as `string`
        // (OpenAPI 3.1 contentMediaType binary → string). The enhanced endpoint
        // sends the real File via FormData at runtime; cast to fit the generated
        // arg shape, matching the `as never` idiom used for other uploads.
        bodyUploadTeamBannerControlPlaneV1TeamsTeamIdBannerPost: { file: file as never },
      }).unwrap();

      console.log("Banner uploaded successfully");
      // RTK Query will automatically invalidate and refetch team data
    } catch (error) {
      console.error("Banner upload error:", error);
    } finally {
      // Reset file input
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  return (
    <div className={styles["team-settings-parameters-container"]}>
      <div className={`${styles["form-section"]} ${styles["team-images-section"]}`}>
        <div className={styles["team-banner"]}>
          <span className={styles["team-banner-title"]}>{t("rework.teamSettings.parameters.teamBanner.title")}</span>
          <div className={styles["team-banner-content"]}>
            <div className={styles["team-banner-upload"]}>
              <input
                ref={fileInputRef}
                type="file"
                className={styles["team-banner-file-input"]}
                accept={ALLOWED_TYPES.join(",")}
                onChange={handleBannerUpload}
              />
              <Button
                color="secondary"
                variant="outlined"
                size="small"
                icon={{ category: "outlined", type: "upload" }}
                onClick={() => fileInputRef.current?.click()}
              >
                {t("rework.teamSettings.parameters.teamBanner.import")}
              </Button>
              <span className={styles["team-banner-hint"]}>{t("rework.teamSettings.parameters.teamBanner.hint")}</span>
            </div>
            <div className={styles["team-banner-preview"]}>
              {bannerImageUrl ? (
                <img className={styles["team-banner-preview-image"]} src={bannerImageUrl} alt="" />
              ) : (
                <span className={styles["team-banner-preview-empty"]}>
                  {t("rework.teamSettings.parameters.teamBanner.noBanner")}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>
      <div className={styles["form-section"]}>
        <TextArea
          label={t("rework.teamSettings.parameters.description.label")}
          placeholder={t("rework.teamSettings.parameters.description.placeholder")}
          maxLength={180}
          value={descriptionValue}
          {...register("description", { onBlur: handleSaveDescription })}
        />
      </div>
      <div className={`${styles["form-section"]} ${styles["team-settings-toggles"]}`}>
        <div className={styles["team-settings-toggle-row"]}>
          <div className={styles["team-settings-toggle-label"]}>
            <span>{t("rework.teamSettings.parameters.visibility.label")}</span>
            <span className={styles["team-settings-toggle-support"]}>
              {t("rework.teamSettings.parameters.visibility.support")}
            </span>
          </div>
          <ButtonGroup
            variant="radio"
            size="small"
            color="secondary"
            backgroundColor="var(--surface-container-lowest)"
            aria-label={t("rework.teamSettings.parameters.visibility.label")}
            selectedIndex={VISIBILITIES.indexOf(visibility)}
            onSelectedIndexChange={handleSelectVisibility}
            items={[
              { label: t("rework.teamSettings.parameters.visibility.public") },
              { label: t("rework.teamSettings.parameters.visibility.private") },
            ]}
          />
        </div>
        <div className={styles["team-settings-toggle-row"]}>
          <div className={styles["team-settings-toggle-label"]}>
            <span>{t("rework.teamSettings.parameters.joiningMode.label")}</span>
            <span className={styles["team-settings-toggle-support"]}>
              {t("rework.teamSettings.parameters.joiningMode.support")}
            </span>
          </div>
          <ButtonGroup
            variant="radio"
            size="small"
            color="secondary"
            backgroundColor="var(--surface-container-lowest)"
            aria-label={t("rework.teamSettings.parameters.joiningMode.label")}
            selectedIndex={JOINING_MODES.indexOf(joiningMode)}
            onSelectedIndexChange={handleSelectJoiningMode}
            items={[
              { label: t("rework.teamSettings.parameters.joiningMode.open"), disabled: isPrivate },
              { label: t("rework.teamSettings.parameters.joiningMode.inviteOnly"), disabled: isPrivate },
            ]}
          />
        </div>
      </div>
      {/* Data & Retention (CTRLP-12 B6): lives here rather than a dedicated tab. */}
      <TeamSettingsRetention team={team} />
      {/*
      <div className={styles["form-section"]}>
        <TextArea
          label={t("rework.teamSettings.parameters.teamPrompt.label")}
          maxLength={180}
          placeholder={t("rework.teamSettings.parameters.teamPrompt.placeholder", { agentsNicknamePlural })}
          disabled={true}
        />
      </div>
*/}
    </div>
  );
}
