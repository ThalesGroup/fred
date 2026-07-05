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
import Switch from "@shared/atoms/Switch/Switch.tsx";
import React, { useEffect, useRef } from "react";
import { useForm } from "react-hook-form";
import ImageFileInput from "@shared/atoms/ImageFileInput/ImageFileInput.tsx";
import { TeamWithPermissions } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
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
  isPrivate: boolean;
}

const MAX_BANNER_SIZE = 5 * 1024 * 1024; // 5MB
const ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp"];

export default function TeamSettingsParameters({ team }: TeamSettingsParametersProps) {
  const { defaultTeamBannerFile } = useFrontendProperties();
  const { t } = useTranslation();
  const [updateTeam] = useUpdateTeamMutation();
  const [uploadBanner] = useUploadTeamBannerMutation();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { register, getValues, watch, reset } = useForm<TeamSettingsParametersForm>({
    defaultValues: {
      description: team.description || "",
      isPrivate: team.is_private || false,
    },
  });

  useEffect(() => {
    reset({
      description: team.description || "",
      isPrivate: team.is_private || false,
    });
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

  const handleSaveIsPrivate = () => {
    const newPrivate = getValues().isPrivate;
    if (newPrivate === team.is_private) {
      return;
    }
    updateTeam({
      teamId: team.id,
      updateTeamRequest: {
        is_private: newPrivate,
      },
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
        bodyUploadTeamBannerControlPlaneV1TeamsTeamIdBannerPost: { file },
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
          <span className={styles["team-banner-title"]}>{t("rework.teamSettings.parameters.teamBannerTitle")}</span>
          <ImageFileInput
            ref={fileInputRef}
            imageUrl={bannerImageUrl}
            alt={""}
            height={"80px"}
            accept={ALLOWED_TYPES.join(",")}
            onChange={handleBannerUpload}
          />
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
      <div className={`${styles["form-section"]} ${styles["private-state"]}`}>
        {t("rework.teamSettings.parameters.privateTeam")}
        <Switch {...register("isPrivate", { onChange: handleSaveIsPrivate })} />
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
