// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import Button from "@shared/atoms/Button/Button";
import { MarkdownRenderer } from "@shared/molecules/MarkdownRenderer/MarkdownRenderer";
import { useLegalMarkdown } from "@hooks/useLegalMarkdown";
import { useFrontendProperties } from "../../../../hooks/useFrontendProperties";
import { KeyCloakService } from "../../../../security/KeycloakService";
import { platformPath } from "../../../../common/platformAccess";
import {
  useFreeEnrollmentPreviewQuery,
  useAcceptFreeCguMutation,
  useEnrollFreeTeamMutation,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./PlatformAccessPage.module.css";
import PlatformAccessError from "./PlatformAccessError";

export default function FreeEnrollmentPage() {
  const { token = "" } = useParams();
  const { t } = useTranslation();
  const { gcuVersion, contactSupportLink } = useFrontendProperties();
  const preview = useFreeEnrollmentPreviewQuery({ token });
  const [accept, acceptance] = useAcceptFreeCguMutation();
  const [enroll, enrollment] = useEnrollFreeTeamMutation();
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
      <h1>{t("rework.platformAccess.joinTitle")}</h1>
      {preview.isLoading && <p>{t("rework.platformAccess.loading")}</p>}
      {preview.data && (
        <>
          <p>{t("rework.platformAccess.joinTeam", { team: preview.data.team_name })}</p>
          {preview.data.cgu_required && (
            <>
              <div className={styles.legal}>
                <MarkdownRenderer text={markdown} />
              </div>
              <label>
                <input type="checkbox" checked={accepted} onChange={(event) => setAccepted(event.target.checked)} />{" "}
                {t("rework.platformAccess.acceptCgu")}
              </label>
            </>
          )}
          <Button
            color="primary"
            variant="filled"
            size="medium"
            disabled={busy || (preview.data.cgu_required && (!accepted || !gcuVersion || !markdown))}
            onClick={() => void join()}
          >
            {t("rework.platformAccess.join")}
          </Button>
        </>
      )}
      {contactSupportLink && (
        <a href={contactSupportLink} target="_blank" rel="noopener noreferrer">
          {t("rework.platformAccess.support")}
        </a>
      )}
      <Button color="primary" variant="filled" size="medium" onClick={() => KeyCloakService.CallLogout()}>
        {t("rework.platformAccess.signOut")}
      </Button>
    </main>
  );
}
