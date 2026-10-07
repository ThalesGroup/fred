// SPDX-License-Identifier: Apache-2.0
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import { PageError } from "@components/pages/PageError/PageError";
import { useFrontendProperties } from "../../../../hooks/useFrontendProperties";
import { KeyCloakService } from "../../../../security/KeycloakService";
import styles from "./PlatformAccessPage.module.css";

export default function PlatformAccessError({
  title,
  message,
  retry,
}: {
  title: string;
  message: string;
  retry: () => void;
}) {
  const { t } = useTranslation();
  const { contactSupportLink } = useFrontendProperties();
  return (
    <PageError
      title={title}
      message={message}
      actions={
        <div className={styles.actions}>
          {contactSupportLink && (
            <a className={styles.support} href={contactSupportLink} rel="noopener noreferrer" target="_blank">
              {t("rework.platformAccess.support")}
            </a>
          )}
          <Button color="primary" variant="outlined" size="medium" onClick={retry}>
            {t("rework.platformAccess.retry")}
          </Button>
          <Button color="primary" variant="outlined" size="medium" onClick={() => KeyCloakService.CallLogout()}>
            {t("rework.platformAccess.signOut")}
          </Button>
        </div>
      }
    />
  );
}
