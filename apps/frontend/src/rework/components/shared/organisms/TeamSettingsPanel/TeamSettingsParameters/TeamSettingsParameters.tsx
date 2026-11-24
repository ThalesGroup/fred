// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useState } from "react";
import { useTranslation } from "react-i18next";
import AvatarUploadCard from "@shared/molecules/AvatarUploadCard/AvatarUploadCard";
import Button from "@shared/atoms/Button/Button";
import TextInput from "@shared/atoms/TextInput/TextInput";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import Select from "@shared/molecules/Select/Select";
import type { TeamVisibility, TeamJoiningMode } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import { crossSessionRefreshOptions, useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";
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
  useTeamMetadataQuery,
  useGetTeamAvatarQuery,
  usePutTeamAvatarMutation,
  useDeleteTeamAvatarMutation,
  useUpdateTeamParametersMutation,
} from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import TeamConversationRetention from "./TeamConversationRetention";
import styles from "./TeamSettingsParameters.module.scss";

export default function TeamSettingsParameters({ spaceId }: { spaceId: string }) {
  const { t } = useTranslation();
  const context = useMySpacesQuery(undefined, { refetchOnMountOrArgChange: true });
  const space = context.currentData?.find((item) => item.id === spaceId);
  const access = useSpaceAccess(spaceId, "manage");
  // A project's direct Owner edits the same parameters; its audience is the parent team.
  const project = space?.kind === "project";
  const supported = space?.kind === "team" || project;
  const label = (teamKey: string, projectKey: string) =>
    t(project ? `rework.projectParameters.${projectKey}` : teamKey);
  const avatar = useGetTeamAvatarQuery(
    { id: spaceId },
    { skip: !access.allowed || !supported, refetchOnMountOrArgChange: true },
  );
  const discovery = useTeamMetadataQuery({ id: spaceId }, crossSessionRefreshOptions(!access.allowed || !supported));
  useRefetchOnWindowFocus(discovery.refetch, !access.allowed || !supported, true);
  const [visibilityDraft, setVisibilityDraft] = useState<TeamVisibility>();
  const [joiningDraft, setJoiningDraft] = useState<TeamJoiningMode>();
  const [discoveryError, setDiscoveryError] = useState(false);
  const visibility = visibilityDraft ?? discovery.currentData?.visibility;
  const joiningMode = joiningDraft ?? discovery.currentData?.joining_mode;
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
    if (!access.allowed || busy || !nameValid || !supported) return;
    setNameError(undefined);
    try {
      await save({ id: spaceId, teamParameters: { name: name.trim() } }).unwrap();
      await context.refetch().unwrap();
      setNameDraft(undefined);
    } catch (failure) {
      setNameError(
        normalizeApiError(failure).status === 409
          ? label("rework.teamSettings.parameters.name.alreadyTaken", "name.alreadyTaken")
          : label("rework.teamSettings.parameters.name.saveError", "name.saveError"),
      );
    }
  };
  const handleSave = async () => {
    if (!access.allowed || busy || !valid || !supported) return;
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
  if (!supported || !access.offered) return <ServiceNotice title={t("rework.spaceMembers.forbidden")} />;
  return (
    <div className={styles.parameters}>
      <PageHeader title={t("rework.teamSettings.parameters.title")} />
      <div className={styles.body}>
        <section className={styles.section}>
          <h2>{t("rework.teamDiscovery.settingsTitle")}</h2>
          <span>{label("rework.teamDiscovery.settingsHint", "settingsHint")}</span>
          {discovery.isError ? (
            <p role="alert">{t("rework.manager.unavailable")}</p>
          ) : !discovery.currentData ? (
            <p role="status">{t("common.loading")}</p>
          ) : (
            <>
              <Select<TeamVisibility>
                size="medium"
                label={label("rework.teamDiscovery.visibility", "visibility")}
                value={visibility}
                disabled={!access.allowed || busy || discovery.isFetching}
                options={["hidden", "visible"].map((value) => ({
                  key: value,
                  value: value as TeamVisibility,
                  label: label(`rework.teamDiscovery.${value}`, value),
                }))}
                onChange={setVisibilityDraft}
              />
              <Select<TeamJoiningMode>
                size="medium"
                label={t("rework.teamDiscovery.joiningMode")}
                value={joiningMode}
                disabled={!access.allowed || busy || discovery.isFetching}
                options={["invite_only", "open"].map((value) => ({
                  key: value,
                  value: value as TeamJoiningMode,
                  label:
                    value === "open" ? label("rework.teamDiscovery.open", "open") : t(`rework.teamDiscovery.${value}`),
                }))}
                onChange={setJoiningDraft}
              />
              {visibility === "hidden" && joiningMode === "open" && (
                <span>{label("rework.teamDiscovery.hiddenOpenHint", "hiddenOpenHint")}</span>
              )}
              <Button
                color="primary"
                variant="filled"
                size="small"
                disabled={
                  !access.allowed ||
                  busy ||
                  discovery.isFetching ||
                  (visibilityDraft === undefined && joiningDraft === undefined)
                }
                onClick={async () => {
                  if (!access.allowed) return;
                  setDiscoveryError(false);
                  try {
                    await save({
                      id: spaceId,
                      teamParameters: { visibility: visibilityDraft, joining_mode: joiningDraft },
                    }).unwrap();
                    await discovery.refetch().unwrap();
                    setVisibilityDraft(undefined);
                    setJoiningDraft(undefined);
                  } catch {
                    setDiscoveryError(true);
                  }
                }}
              >
                {t("common.save")}
              </Button>
            </>
          )}
          {discoveryError && <p role="alert">{t("rework.teamDiscovery.saveFailed")}</p>}
        </section>
        <section className={styles.section}>
          <TextInput
            label={label("rework.teamSettings.parameters.name.label", "name.label")}
            explanation={label("rework.teamSettings.parameters.name.support", "name.support")}
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
            {label("rework.teamSettings.parameters.name.save", "name.save")}
          </Button>
        </section>
        <section className={styles.section}>
          <AvatarUploadCard
            title={label("rework.teamSettings.parameters.teamAvatar.title", "avatar")}
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
          {(avatarError || avatar.isError) && (
            <p role="alert">{t("rework.teamSettings.parameters.teamAvatar.failed")}</p>
          )}
        </section>
        <section className={styles.section}>
          <TextArea
            label={label("rework.teamDescription.label", "description.label")}
            placeholder={label("rework.teamSettings.parameters.description.placeholder", "description.placeholder")}
            description={label("rework.teamDescription.helper", "description.helper")}
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
          {saved && (
            <p role="status">{label("rework.teamSettings.parameters.description.saved", "description.saved")}</p>
          )}
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
        <TeamConversationRetention key={spaceId} spaceId={spaceId} allowed={access.allowed} />
      </div>
    </div>
  );
}
