// SPDX-License-Identifier: Apache-2.0
import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import Button from "@shared/atoms/Button/Button";
import Checkbox from "@shared/atoms/Checkbox/Checkbox";
import TeamInitials from "@shared/atoms/TeamInitials/TeamInitials";
import { MarkdownRenderer } from "@shared/molecules/MarkdownRenderer/MarkdownRenderer";
import { useLegalMarkdown } from "@hooks/useLegalMarkdown";
import { useFrontendProperties } from "../../../../hooks/useFrontendProperties";
import { platformPath } from "../../../../common/platformAccess";
import {
  useFreeEnrollmentPreviewQuery,
  useAcceptFreeCguMutation,
  useEnrollFreeTeamMutation,
  useRecordFreeOpeningMutation,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./FreeEnrollmentPage.module.css";
import PlatformAccessError from "./PlatformAccessError";

export default function FreeEnrollmentPage() {
  const { token = "" } = useParams();
  const { t } = useTranslation();
  const { gcuVersion, contactSupportLink, siteDisplayName } = useFrontendProperties();
  const acceptanceId = useId();
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
  const markdown = useLegalMarkdown("gcu");
  const [accepted, setAccepted] = useState(false);
  const [failed, setFailed] = useState(false);
  const busy = acceptance.isLoading || enrollment.isLoading || preview.isFetching;
  const join = async () => {
    setFailed(false);
    try {
      if (preview.data?.cgu_required && gcuVersion)
        await accept({ token, acceptFreeEnrollmentCgu: { version: gcuVersion } }).unwrap();
      const status = await enroll({ token }).unwrap();
      if (status.admitted) window.location.replace(platformPath("/"));
      else setFailed(true);
    } catch {
      setFailed(true);
    }
  };
  if (preview.isError || failed)
    return (
      <PlatformAccessError
        hideSignOut
        title={t("rework.platformAccess.joinTitle")}
        message={t(preview.isError ? "rework.platformAccess.invalidLink" : "rework.platformAccess.failed")}
        retry={() => {
          setFailed(false);
          void preview.refetch();
        }}
      />
    );
  return (
    <main className={styles.page}>
      <section className={styles.card} aria-labelledby="invitation-title">
        <header className={styles.header}>
          {siteDisplayName && <p className={styles.brand}>{siteDisplayName}</p>}
          <h1 id="invitation-title" className={styles.title}>
            {t("rework.platformAccess.joinTitle")}
          </h1>
        </header>
        <div className={styles.content}>
          {preview.isLoading && <p role="status">{t("rework.platformAccess.loading")}</p>}
          {preview.data && (
            <>
              <div className={styles.team}>
                <TeamInitials name={preview.data.team_name} size="medium" className={styles.avatar} />
                <div className={styles.teamDetails}>
                  <h2 className={styles.teamName}>{preview.data.team_name}</h2>
                  <p className={styles.description}>
                    {t("rework.platformAccess.joinTeam", { team: preview.data.team_name })}
                  </p>
                </div>
              </div>
              {openingFailed && <p role="status">{t("rework.platformAccess.links.openingFailed")}</p>}
              {preview.data.cgu_required && (
                <>
                  <div className={styles.legal}>
                    <MarkdownRenderer text={markdown} />
                  </div>
                  <div className={styles.acceptance}>
                    <Checkbox
                      id={acceptanceId}
                      checked={accepted}
                      onChange={(event) => setAccepted(event.target.checked)}
                    />
                    <label htmlFor={acceptanceId}>{t("rework.platformAccess.acceptCgu")}</label>
                  </div>
                </>
              )}
            </>
          )}
        </div>
        <footer className={styles.footer}>
          {contactSupportLink && (
            <a className={styles.support} href={contactSupportLink} target="_blank" rel="noopener noreferrer">
              {t("rework.platformAccess.support")}
            </a>
          )}
          {preview.data && (
            <Button
              color="primary"
              variant="filled"
              size="medium"
              icon={{ category: "outlined", type: "person_add" }}
              disabled={busy || (preview.data.cgu_required && (!accepted || !gcuVersion || !markdown))}
              onClick={() => void join()}
            >
              {t("rework.platformAccess.join")}
            </Button>
          )}
        </footer>
      </section>
    </main>
  );
}
