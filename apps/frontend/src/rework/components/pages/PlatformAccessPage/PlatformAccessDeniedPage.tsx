// SPDX-License-Identifier: Apache-2.0
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import UserAvatar from "@shared/atoms/UserAvatar/UserAvatar";
import { platformPath } from "../../../../common/platformAccess";
import { useFrontendProperties } from "../../../../hooks/useFrontendProperties";
import { KeyCloakService } from "../../../../security/KeycloakService";
import PlatformAccessCard, { SignOutLink } from "./PlatformAccessCard";
import styles from "./PlatformAccessCard.module.css";

export default function PlatformAccessDeniedPage() {
  const { t } = useTranslation();
  const { contactSupportLink } = useFrontendProperties();
  // The person is signed in but not admitted: only the session token describes them.
  const firstName = KeyCloakService.GetUserGivenName()?.trim();
  const fullName = KeyCloakService.GetUserFullName()?.trim();
  const email = KeyCloakService.GetUserMail()?.trim();
  const accountName = fullName || email;
  return (
    <PlatformAccessCard
      lead={
        firstName
          ? t("rework.platformAccess.denied.greetingNamed", { firstName })
          : t("rework.platformAccess.denied.greeting")
      }
      title={t("rework.platformAccess.denied.title")}
      footerStart={<SignOutLink />}
      actions={
        <>
          <Button
            color="primary"
            variant="outlined"
            size="medium"
            onClick={() => window.location.replace(platformPath("/"))}
          >
            {t("rework.platformAccess.denied.check")}
          </Button>
          {contactSupportLink && (
            <Button
              color="primary"
              variant="filled"
              size="medium"
              onClick={() => window.open(contactSupportLink, "_blank", "noopener,noreferrer")}
            >
              {t("rework.platformAccess.denied.request")}
            </Button>
          )}
        </>
      }
    >
      {accountName && (
        <div className={`${styles.inner} ${styles.account}`}>
          <span aria-hidden="true">
            <UserAvatar name={accountName} size="medium" />
          </span>
          <div className={styles.innerDetails}>
            <p className={styles.innerName}>{accountName}</p>
            {fullName && email && <p className={styles.retreat}>{email}</p>}
          </div>
        </div>
      )}
      <ol className={styles.steps}>
        <li>
          {t(email ? "rework.platformAccess.denied.stepRequestWithEmail" : "rework.platformAccess.denied.stepRequest")}
        </li>
        <li>{t("rework.platformAccess.denied.stepReturn")}</li>
      </ol>
    </PlatformAccessCard>
  );
}
