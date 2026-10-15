// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import Button from "@shared/atoms/Button/Button";
import TeamInitials from "@shared/atoms/TeamInitials/TeamInitials";
import { GcuPageContent } from "../GcuPage/GcuPage";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import { useFrontendProperties } from "../../../../hooks/useFrontendProperties";
import { platformPath } from "../../../../common/platformAccess";
import {
  useFreeEnrollmentPreviewQuery,
  useAcceptFreeCguMutation,
  useEnrollFreeTeamMutation,
  useRecordFreeOpeningMutation,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import PlatformAccessCard from "./PlatformAccessCard";
import styles from "./PlatformAccessCard.module.css";
import PlatformAccessError from "./PlatformAccessError";

// The backend gives this one answer for an expired, revoked or suspended link.
const isInvalidLink = (error: unknown) => {
  const { status, detail } = normalizeApiError(error);
  return status === 404 && detail === "free_enrollment_link_invalid";
};

// A team join link answers this to a person without platform access: show the refusal page.
const isPlatformAccessDenied = (error: unknown) => {
  const { status, detail } = normalizeApiError(error);
  return status === 403 && detail === "team_link_requires_platform_access";
};
const showRefusal = () => window.location.replace(platformPath("platform-access-denied"));

export default function FreeEnrollmentPage() {
  const { token = "" } = useParams();
  const { t } = useTranslation();
  const { gcuVersion } = useFrontendProperties();
  const preview = useFreeEnrollmentPreviewQuery({ token });
  const [accept, acceptance] = useAcceptFreeCguMutation();
  const [enroll, enrollment] = useEnrollFreeTeamMutation();
  const [record] = useRecordFreeOpeningMutation();
  const opening = useRef<{ token: string; result: Promise<unknown> } | null>(null);
  const [openingFailed, setOpeningFailed] = useState(false);
  useEffect(() => {
    if (!preview.isSuccess) return;
    let active = true;
    setOpeningFailed(false);
    if (opening.current?.token !== token) opening.current = { token, result: record({ token }).unwrap() };
    void opening.current.result.catch(() => {
      if (active) setOpeningFailed(true);
    });
    return () => {
      active = false;
    };
  }, [token, preview.isSuccess, record]);
  const [failure, setFailure] = useState<"invalid" | "failed" | null>(null);
  const denied = preview.isError && isPlatformAccessDenied(preview.error);
  useEffect(() => {
    if (denied) showRefusal();
  }, [denied]);
  const busy = acceptance.isLoading || enrollment.isLoading || preview.isFetching;
  const acceptTerms = async () => {
    if (!gcuVersion) return;
    try {
      await accept({ token, acceptFreeEnrollmentCgu: { version: gcuVersion } }).unwrap();
      await preview.refetch().unwrap();
    } catch (error) {
      if (isPlatformAccessDenied(error)) showRefusal();
      else setFailure(isInvalidLink(error) ? "invalid" : "failed");
    }
  };
  const join = async () => {
    setFailure(null);
    try {
      const status = await enroll({ token }).unwrap();
      if (status.admitted)
        window.location.replace(
          platformPath(status.team_id ? `team/${encodeURIComponent(status.team_id)}/agents` : "/"),
        );
      else setFailure("failed");
    } catch (error) {
      if (isPlatformAccessDenied(error)) showRefusal();
      else setFailure(isInvalidLink(error) ? "invalid" : "failed");
    }
  };
  if (denied) return null;
  if (failure === "invalid" || (preview.isError && isInvalidLink(preview.error)))
    return (
      <PlatformAccessCard title={t("rework.platformAccess.join.invalidTitle")}>
        <p className={styles.retreat}>{t("rework.platformAccess.join.invalidMessage")}</p>
      </PlatformAccessCard>
    );
  // Anything else may be temporary: never call a working link invalid.
  if (preview.isError || failure)
    return (
      <PlatformAccessError
        hideFooterLinks
        title={t(
          preview.isError ? "rework.platformAccess.join.uncheckedTitle" : "rework.platformAccess.join.failedTitle",
        )}
        message={t(preview.isError ? "rework.platformAccess.join.uncheckedMessage" : "rework.platformAccess.failed")}
        retry={() => {
          setFailure(null);
          void preview.refetch();
        }}
      />
    );
  if (preview.data?.cgu_required) return <GcuPageContent isLoading={busy} onAccept={acceptTerms} />;
  if (!preview.data)
    return (
      <PlatformAccessCard title={t("rework.platformAccess.join.checking")}>
        <p role="status" className={styles.retreat}>
          {t("rework.platformAccess.loading")}
        </p>
      </PlatformAccessCard>
    );
  return (
    <PlatformAccessCard
      title={t("rework.platformAccess.join.title")}
      actions={
        <Button color="primary" variant="filled" size="medium" disabled={busy} onClick={() => void join()}>
          {t("rework.platformAccess.join.action")}
        </Button>
      }
    >
      <div className={styles.inner}>
        <TeamInitials name={preview.data.team_name} size="medium" className={styles.teamTile} />
        <h2 className={styles.teamName}>{preview.data.team_name}</h2>
      </div>
      {openingFailed && <p role="status">{t("rework.platformAccess.links.openingFailed")}</p>}
    </PlatformAccessCard>
  );
}
