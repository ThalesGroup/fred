// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useState } from "react";
import { useTranslation } from "react-i18next";
import AvatarUploadCard from "@shared/molecules/AvatarUploadCard/AvatarUploadCard";
import Button from "@shared/atoms/Button/Button";
import TextInput from "@shared/atoms/TextInput/TextInput";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import TextArea from "@shared/atoms/TextArea/TextArea";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import { useSpaceAccess } from "@core/hooks/useSpaceAccess";
import {
  isValidTeamDescription,
  MAX_TEAM_NAME_LENGTH,
  TEAM_DESCRIPTION_MAX_LENGTH,
  TEAM_DESCRIPTION_MIN_LENGTH,
} from "@core/utils/teamFields";
import {
  useMySpacesQuery,
  useGetTeamAvatarQuery,
  usePutTeamAvatarMutation,
  useDeleteTeamAvatarMutation,
  useUpdateTeamParametersMutation,
} from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./TeamSettingsParameters.module.scss";

export default function TeamSettingsParameters({ spaceId }: { spaceId: string }) {
  const { t } = useTranslation();
  const context = useMySpacesQuery(undefined, { refetchOnMountOrArgChange: true });
  const space = context.currentData?.find((item) => item.id === spaceId);
  const access = useSpaceAccess(spaceId, "manage");
  const avatar = useGetTeamAvatarQuery(
    { id: spaceId },
    { skip: !access.allowed || space?.kind !== "team", refetchOnMountOrArgChange: true },
  );
  const [uploadAvatar, uploading] = usePutTeamAvatarMutation();
  const [deleteAvatar, deleting] = useDeleteTeamAvatarMutation();
  const [avatarError, setAvatarError] = useState(false);
  const [save, saving] = useUpdateTeamParametersMutation();
  // Background refreshes update pristine fields, never overwrite the user's draft.
  const [nameDraft, setNameDraft] = useState<string>();
  const [nameError, setNameError] = useState<string>();
  const [draft, setDraft] = useState<string>();
  const [error, setError] = useState<string>();
  const [saved, setSaved] = useState(false);
  const description = draft ?? space?.description ?? "";
  const trimmed = description.trim();
  const valid = isValidTeamDescription(description);
  const busy = saving.isLoading || context.isFetching;
  const name = nameDraft ?? space?.name ?? "";
  const nameValid = [...name.trim()].length > 0 && [...name.trim()].length <= MAX_TEAM_NAME_LENGTH;
  const handleRename = async () => {
    if (!access.allowed || busy || !nameValid || space?.kind !== "team") return;
    setNameError(undefined);
    try {
      await save({ id: spaceId, teamParameters: { name: name.trim() } }).unwrap();
      await context.refetch().unwrap();
      setNameDraft(undefined);
    } catch (failure) {
      setNameError(
        t(
          normalizeApiError(failure).status === 409
            ? "rework.teamSettings.parameters.name.alreadyTaken"
            : "rework.teamSettings.parameters.name.saveError",
        ),
      );
    }
  };
  const handleSave = async () => {
    if (!access.allowed || busy || !valid || space?.kind !== "team") return;
    setError(undefined);
    setSaved(false);
    try {
      await save({ id: spaceId, teamParameters: { description: trimmed } }).unwrap();
      await context.refetch().unwrap();
      setDraft(undefined);
      setSaved(true);
    } catch {
      setError(t("rework.teamSettings.parameters.description.saveError"));
    }
  };

  if (context.isError || access.error) return <ServiceNotice title={t("rework.manager.unavailable")} />;
  if (!context.currentData || (!access.settled && !access.offered)) return <p role="status">{t("common.loading")}</p>;
  if (space?.kind !== "team" || !access.offered) return <ServiceNotice title={t("rework.spaceMembers.forbidden")} />;
  return (
    <div className={styles.parameters}>
      <PageHeader title={t("rework.teamSettings.parameters.title")} />
      <section className={styles.section}>
        <TextInput
          label={t("rework.teamSettings.parameters.name.label")}
          explanation={t("rework.teamSettings.parameters.name.support")}
          value={name}
          disabled={busy}
          error={nameError}
          onChange={(event) => {
            setNameDraft(event.target.value);
            setNameError(undefined);
          }}
        />
        <Button
          color="primary"
          variant="filled"
          size="small"
          disabled={busy || !access.allowed || !nameValid || name.trim() === space.name}
          onClick={() => void handleRename()}
        >
          {t("rework.teamSettings.parameters.name.save")}
        </Button>
      </section>
      <section className={styles.section}>
        <AvatarUploadCard
          title={t("rework.teamSettings.parameters.teamAvatar.title")}
          hint={t("rework.teamSettings.parameters.teamAvatar.hint")}
          importLabel={t("rework.teamSettings.parameters.teamAvatar.import")}
          emptyLabel={t("rework.teamSettings.parameters.teamAvatar.noAvatar")}
          imageUrl={!avatar.isError ? avatar.currentData || undefined : undefined}
          uploading={!access.allowed || avatar.isFetching || uploading.isLoading}
          deleting={!access.allowed || deleting.isLoading || uploading.isLoading}
          onUpload={async (file) => {
            if (!access.allowed) return;
            setAvatarError(false);
            await uploadAvatar({ id: spaceId, fileUpload: { file } }).unwrap();
          }}
          deleteLabel={t("common.delete")}
          onDelete={() => {
            if (!access.allowed) return;
            setAvatarError(false);
            void deleteAvatar({ id: spaceId })
              .unwrap()
              .catch(() => setAvatarError(true));
          }}
        />
        {(avatarError || avatar.isError) && <p role="alert">{t("rework.teamSettings.parameters.teamAvatar.failed")}</p>}
      </section>
      <section className={styles.section}>
        <TextArea
          label={t("rework.teamDescription.label")}
          placeholder={t("rework.teamSettings.parameters.description.placeholder")}
          description={t("rework.teamDescription.helper")}
          explanation={t("rework.teamDescription.length", {
            min: TEAM_DESCRIPTION_MIN_LENGTH,
            max: TEAM_DESCRIPTION_MAX_LENGTH,
          })}
          value={description}
          rows={7}
          required
          disabled={busy}
          error={
            draft !== undefined && !valid
              ? t("rework.teamDescription.length", {
                  min: TEAM_DESCRIPTION_MIN_LENGTH,
                  max: TEAM_DESCRIPTION_MAX_LENGTH,
                })
              : undefined
          }
          onChange={(event) => {
            setDraft(event.target.value);
            setSaved(false);
            setError(undefined);
          }}
        />
        {error && <p role="alert">{error}</p>}
        {saved && <p role="status">{t("rework.teamSettings.parameters.description.saved")}</p>}
        <Button
          color="primary"
          variant="filled"
          size="small"
          disabled={busy || !access.allowed || !valid || trimmed === space.description}
          onClick={() => void handleSave()}
        >
          {t("common.save")}
        </Button>
      </section>
    </div>
  );
}
