// SPDX-License-Identifier: Apache-2.0
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import { useFrontendProperties } from "../../../../hooks/useFrontendProperties";
import { KeyCloakService } from "../../../../security/KeycloakService";
import { platformPath } from "../../../../common/platformAccess";
import styles from "./PlatformAccessPage.module.css";

export default function PlatformAccessDeniedPage() {
  const { t } = useTranslation();
  const { contactSupportLink } = useFrontendProperties();
  return (
    <main className={styles.page}>
      <h1>{t("rework.platformAccess.deniedTitle")}</h1>
      <p>{t("rework.platformAccess.deniedMessage")}</p>
      {contactSupportLink && (
        <a href={contactSupportLink} rel="noopener noreferrer" target="_blank">
          {t("rework.platformAccess.support")}
        </a>
      )}
      <div className={styles.actions}>
        <Button
          color="primary"
          variant="filled"
          size="medium"
          onClick={() => window.location.replace(platformPath("/"))}
        >
          {t("rework.platformAccess.retry")}
        </Button>
        <Button color="primary" variant="filled" size="medium" onClick={() => KeyCloakService.CallLogout()}>
          {t("rework.platformAccess.signOut")}
        </Button>
      </div>
    </main>
  );
}
