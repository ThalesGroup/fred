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
import PageHeader from "@shared/molecules/PageHeader/PageHeader.tsx";
import TextArea from "@shared/atoms/TextArea/TextArea.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import { useTranslation } from "react-i18next";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup.tsx";
import Button from "@shared/atoms/Button/Button.tsx";
import AvatarCropEditor from "@shared/organisms/AvatarCropEditor/AvatarCropEditor.tsx";
import React, { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import {
  JoiningMode,
  TeamVisibility,
  TeamWithPermissions,
} from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  useUpdateTeamMutation,
  useUploadTeamAvatarMutation,
} from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { useFrontendProperties } from "../../../../../../hooks/useFrontendProperties.ts";
import TeamSettingsRetention from "@shared/organisms/TeamSettingsPanel/TeamSettingsRetention/TeamSettingsRetention.tsx";

interface TeamSettingsParametersProps {
  team: TeamWithPermissions;
}

interface TeamSettingsParametersForm {
  name: string;
  description: string;
}

// Mirrors `UpdateTeamRequest.name` server-side, so the field cannot submit a
// value the backend would reject on length alone.
const MAX_TEAM_NAME_LENGTH = 180;

const MAX_AVATAR_SIZE = 5 * 1024 * 1024; // 5MB
const ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp"];

// TEAM-09: order drives the button group's left-to-right layout and index
// mapping — keep in sync with the labels below.
const JOINING_MODES: JoiningMode[] = ["open", "invite_only"];

// TEAM-10: same left-to-right/index convention as JOINING_MODES above.
const VISIBILITIES: TeamVisibility[] = ["public", "private"];

export default function TeamSettingsParameters({ team }: TeamSettingsParametersProps) {
  const { defaultTeamAvatarFile } = useFrontendProperties();
  const { t } = useTranslation();
  const [updateTeam] = useUpdateTeamMutation();
  const [uploadAvatar, { isLoading: isUploadingAvatar }] = useUploadTeamAvatarMutation();
  const fileInputRef = useRef<HTMLInputElement>(null);
  // The image the user just picked, pending crop. Non-null opens the editor.
  const [cropFile, setCropFile] = useState<File | null>(null);

  // Set by a failed rename only; the field's own value is form state.
  const [renameError, setRenameError] = useState<string | null>(null);
  const [isRenaming, setIsRenaming] = useState(false);

  const { register, getValues, watch, setValue } = useForm<TeamSettingsParametersForm>({
    defaultValues: {
      name: team.name,
      description: team.description || "",
    },
  });

  // Each field re-syncs on its own value, never through a shared `reset`:
  // saving the description refetches the whole team, and a reset would wipe a
  // rename the user had typed but not submitted yet.
  useEffect(() => {
    setValue("description", team.description || "");
  }, [team.description, setValue]);

  useEffect(() => {
    setValue("name", team.name);
    setRenameError(null);
  }, [team.name, setValue]);

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

  // A rename is committed by an explicit button rather than on blur like the
  // description: it renames the team everywhere, and it can be refused (team
  // names are globally unique), so it needs a deliberate action and somewhere
  // to put the refusal.
  const nameValue = watch("name");
  const trimmedName = nameValue.trim();
  const canRename = trimmedName.length > 0 && trimmedName !== team.name;

  const handleSaveName = async () => {
    // The in-flight guard is not just double-click hygiene: a second PATCH
    // would let a late 409 pin "name already taken" onto a name the user has
    // since changed.
    if (!canRename || isRenaming) return;
    setRenameError(null);
    setIsRenaming(true);
    try {
      await updateTeam({
        teamId: team.id,
        updateTeamRequest: { name: trimmedName },
      }).unwrap();
    } catch (error) {
      // 409 is the one failure the user can act on: another team holds the name.
      const status = (error as { status?: number } | undefined)?.status;
      setRenameError(
        status === 409
          ? t("rework.teamSettings.parameters.name.alreadyTaken")
          : t("rework.teamSettings.parameters.name.saveError"),
      );
    } finally {
      setIsRenaming(false);
    }
  };
  const defaultAvatarUrl = defaultTeamAvatarFile ? `/images/${defaultTeamAvatarFile}` : undefined;
  const avatarImageUrl = team.avatar_image_url ?? defaultAvatarUrl;

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

  // TEAM-10 (#2398): a PRIVATE team can never be OPEN, and there is no
  // invitation flow either — a team admin adds members by hand. So while
  // private, the joining-mode toggle is not a setting at all: it is replaced
  // by a single disabled "manual only" button rather than a two-state control
  // that refuses every click — one inert, locked state reads as the fact it
  // is, where a greyed-out toggle still reads as a choice.
  // #2433: private is the platform default — mirror it when the field is absent.
  const visibility = team.visibility ?? "private";
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

  // Picking a file no longer uploads directly — it opens the square crop editor.
  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    // Reset the input immediately so re-picking the same file re-fires onChange.
    if (fileInputRef.current) fileInputRef.current.value = "";
    if (!file || !team?.id) return;
    if (!ALLOWED_TYPES.includes(file.type)) {
      console.error("Invalid file type:", file.type);
      return;
    }
    if (file.size > MAX_AVATAR_SIZE) {
      console.error("File size exceeds limit:", file.size);
      return;
    }
    setCropFile(file);
  };

  // The editor hands back the cropped square as a bounded WebP blob (#2300).
  const handleCropSave = async (blob: Blob) => {
    if (!team?.id) return;
    const croppedFile = new File([blob], "avatar.webp", { type: "image/webp" });
    try {
      await uploadAvatar({
        teamId: team.id,
        // The generated client types the multipart file field as `string`
        // (OpenAPI 3.1 contentMediaType binary → string). The enhanced endpoint
        // sends the real File via FormData at runtime; cast to fit the generated
        // arg shape, matching the `as never` idiom used for other uploads.
        bodyUploadTeamAvatarControlPlaneV1TeamsTeamIdAvatarPost: { file: croppedFile as never },
      }).unwrap();
      // RTK Query invalidates and refetches team data automatically.
    } catch (error) {
      console.error("Avatar upload error:", error);
    } finally {
      setCropFile(null);
    }
  };

  return (
    <div className={styles["team-settings-parameters-container"]}>
      <PageHeader title={t("rework.teamSettings.parameters.title")} />
      <div className={`${styles["form-section"]} ${styles["team-name-section"]}`}>
        <TextInput
          label={t("rework.teamSettings.parameters.name.label")}
          explanation={t("rework.teamSettings.parameters.name.support")}
          maxLength={MAX_TEAM_NAME_LENGTH}
          value={nameValue}
          error={renameError ?? undefined}
          {...register("name", { onChange: () => setRenameError(null) })}
        />
        <div className={styles["team-name-actions"]}>
          <Button
            color="primary"
            variant="filled"
            size="small"
            disabled={!canRename || isRenaming}
            onClick={handleSaveName}
          >
            {t("rework.teamSettings.parameters.name.save")}
          </Button>
        </div>
      </div>
      <div className={`${styles["form-section"]} ${styles["team-images-section"]}`}>
        <div className={styles["team-avatar"]}>
          <span className={styles["team-avatar-title"]}>{t("rework.teamSettings.parameters.teamAvatar.title")}</span>
          <div className={styles["team-avatar-content"]}>
            <div className={styles["team-avatar-upload"]}>
              <input
                ref={fileInputRef}
                type="file"
                className={styles["team-avatar-file-input"]}
                accept={ALLOWED_TYPES.join(",")}
                onChange={handleFileSelect}
              />
              <Button
                color="secondary"
                variant="outlined"
                size="small"
                icon={{ category: "outlined", type: "upload" }}
                onClick={() => fileInputRef.current?.click()}
              >
                {t("rework.teamSettings.parameters.teamAvatar.import")}
              </Button>
              <span className={styles["team-avatar-hint"]}>{t("rework.teamSettings.parameters.teamAvatar.hint")}</span>
            </div>
            <div className={styles["team-avatar-preview"]}>
              {avatarImageUrl ? (
                <img className={styles["team-avatar-preview-image"]} src={avatarImageUrl} alt="" />
              ) : (
                <span className={styles["team-avatar-preview-empty"]}>
                  {t("rework.teamSettings.parameters.teamAvatar.noAvatar")}
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
              {isPrivate
                ? t("rework.teamSettings.parameters.joiningMode.privateSupport")
                : t("rework.teamSettings.parameters.joiningMode.support")}
            </span>
          </div>
          {isPrivate ? (
            <Button
              className={styles["team-settings-toggle-action"]}
              color="secondary"
              variant="outlined"
              size="small"
              icon={{ category: "outlined", type: "lock" }}
              disabled
            >
              {t("rework.teamSettings.parameters.joiningMode.manual")}
            </Button>
          ) : (
            <ButtonGroup
              variant="radio"
              size="small"
              color="secondary"
              backgroundColor="var(--surface-container-lowest)"
              aria-label={t("rework.teamSettings.parameters.joiningMode.label")}
              selectedIndex={JOINING_MODES.indexOf(joiningMode)}
              onSelectedIndexChange={handleSelectJoiningMode}
              items={[
                { label: t("rework.teamSettings.parameters.joiningMode.open") },
                { label: t("rework.teamSettings.parameters.joiningMode.inviteOnly") },
              ]}
            />
          )}
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
      {cropFile && (
        <AvatarCropEditor
          file={cropFile}
          open
          onCancel={() => setCropFile(null)}
          onSave={handleCropSave}
          saving={isUploadingAvatar}
        />
      )}
    </div>
  );
}
