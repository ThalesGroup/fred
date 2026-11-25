// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import Button from "@shared/atoms/Button/Button";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import { platformPath } from "../../../../common/platformAccess";
import {
  usePreviewTeamJoinLinkQuery,
  useRedeemTeamJoinLinkMutation,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import PlatformAccessCard from "./PlatformAccessCard";

export default function FreeEnrollmentPage() {
  const { token = "" } = useParams();
  return <TeamEnrollment key={token} token={token} />;
}

function TeamEnrollment({ token }: { token: string }) {
  const { t } = useTranslation();
  const preview = usePreviewTeamJoinLinkQuery({ token }, { refetchOnMountOrArgChange: true });
  const [redeem, redemption] = useRedeemTeamJoinLinkMutation();
  const [failure, setFailure] = useState<unknown>();
  const error = failure ?? preview.error;
  const status = normalizeApiError(error).status;
  const join = async () => {
    if (!preview.currentData || preview.isFetching || redemption.isLoading) return;
    setFailure(undefined);
    try {
      const result = await redeem({ token }).unwrap();
      window.location.replace(platformPath(`team/${encodeURIComponent(result.team_id)}`));
    } catch (error) {
      setFailure(error);
    }
  };
  const key = "rework.teamSettings.members.inviteLink";
  return (
    <PlatformAccessCard title={t("rework.platformAccess.join.title")}>
      {error ? (
        <>
          <p role="alert">
            {t(
              status === 404 || status === 422
                ? "rework.platformAccess.join.invalidMessage"
                : status === 403
                  ? `${key}.forbidden`
                  : `${key}.failed`,
            )}
          </p>
          <Button
            color="primary"
            variant="outlined"
            size="small"
            disabled={preview.isFetching}
            onClick={() => {
              setFailure(undefined);
              void preview.refetch();
            }}
          >
            {t("rework.spaceMembers.refresh")}
          </Button>
        </>
      ) : !preview.currentData ? (
        <p role="status">{t("common.loading")}</p>
      ) : (
        <>
          <h2>{preview.currentData.team_name}</h2>
          <p>{t(`${key}.hint`)}</p>
          <Button
            color="primary"
            variant="filled"
            size="medium"
            disabled={redemption.isLoading || preview.isFetching}
            onClick={() => void join()}
          >
            {t("rework.platformAccess.join.action")}
          </Button>
        </>
      )}
    </PlatformAccessCard>
  );
}
