// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import TextArea from "@shared/atoms/TextArea/TextArea";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import { useSpaceAccess } from "@core/hooks/useSpaceAccess";
import {
  isValidTeamDescription,
  TEAM_DESCRIPTION_MAX_LENGTH,
  TEAM_DESCRIPTION_MIN_LENGTH,
} from "@core/utils/teamFields";
import {
  useMySpacesQuery,
  useUpdateTeamDescriptionMutation,
} from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./TeamSettingsParameters.module.scss";

export default function TeamSettingsParameters({ spaceId }: { spaceId: string }) {
  const { t } = useTranslation();
  const context = useMySpacesQuery(undefined, { refetchOnMountOrArgChange: true });
  const space = context.currentData?.find((item) => item.id === spaceId);
  const access = useSpaceAccess(spaceId, "manage");
  const [save, saving] = useUpdateTeamDescriptionMutation();
  // Background refreshes update pristine fields, never overwrite the user's draft.
  const [draft, setDraft] = useState<string>();
  const [error, setError] = useState<string>();
  const [saved, setSaved] = useState(false);
  const description = draft ?? space?.description ?? "";
  const trimmed = description.trim();
  const valid = isValidTeamDescription(description);
  const busy = saving.isLoading || context.isFetching;
  const handleSave = async () => {
    if (!access.allowed || busy || !valid || space?.kind !== "team") return;
    setError(undefined);
    setSaved(false);
    try {
      await save({ id: spaceId, teamDescription: { description: trimmed } }).unwrap();
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
            ? t("rework.teamDescription.length", { min: TEAM_DESCRIPTION_MIN_LENGTH, max: TEAM_DESCRIPTION_MAX_LENGTH })
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
    </div>
  );
}
