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
import Button from "@shared/atoms/Button/Button.tsx";
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
import { useApiErrorToast } from "@core/hooks/useApiErrorToast.ts";
import { useMutationAction } from "@core/hooks/useMutationAction.ts";
import { useToast } from "../../../../../../components/ToastProvider.tsx";

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
  const { showSuccess } = useToast();
  const { notifyApiError } = useApiErrorToast();
  const { runMutationAction } = useMutationAction();
  const [updateTeam, { isLoading: isSaving }] = useUpdateTeamMutation();
  const [uploadBanner] = useUploadTeamBannerMutation();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const {
    register,
    watch,
    reset,
    handleSubmit,
    formState: { isDirty },
  } = useForm<TeamSettingsParametersForm>({
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
  }, [team.description, team.is_private, reset]);

  const descriptionValue = watch("description");

  const onSave = handleSubmit(async (values) => {
    await runMutationAction({
      action: () =>
        updateTeam({
          teamId: team.id,
          updateTeamRequest: {
            description: values.description,
            is_private: values.isPrivate,
          },
        }).unwrap(),
      onSuccess: () => {
        showSuccess({ summary: t("rework.teamSettings.parameters.saveSuccess", { defaultValue: "Team updated" }) });
        reset(values);
      },
      onError: (error) =>
        notifyApiError(error, {
          summary: t("rework.teamSettings.parameters.errors.saveSummary", { defaultValue: "Failed to update team" }),
          fallbackDetail: t("rework.teamSettings.parameters.errors.saveDetail", {
            defaultValue: "Could not save team changes.",
          }),
          forbiddenDetail: t("rework.teamSettings.parameters.errors.forbiddenDetail", {
            defaultValue: "You are not allowed to perform this action.",
          }),
        }),
    });
  });

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
            imageUrl={team.banner_image_url ?? `/images/${defaultTeamBannerFile}`}
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
          {...register("description")}
        />
      </div>
      <div className={`${styles["form-section"]} ${styles["private-state"]}`}>
        {t("rework.teamSettings.parameters.privateTeam")}
        <Switch {...register("isPrivate")} />
      </div>
      <div className={styles["form-actions"]}>
        <Button color="primary" variant="filled" size="medium" onClick={onSave} disabled={!isDirty || isSaving}>
          {isSaving
            ? t("rework.teamSettings.parameters.saving", { defaultValue: "Saving…" })
            : t("rework.teamSettings.parameters.save", { defaultValue: "Save" })}
        </Button>
      </div>
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
