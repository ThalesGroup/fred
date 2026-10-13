// SPDX-License-Identifier: Apache-2.0
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import { useFrontendProperties } from "../../../../hooks/useFrontendProperties";
import PlatformAccessCard, { SignOutLink, SupportLink } from "./PlatformAccessCard";

// A temporary problem the person can retry, as opposed to a definitive refusal.
export default function PlatformAccessError({
  title,
  message,
  retry,
  hideSignOut = false,
}: {
  title: string;
  message: string;
  retry: () => void;
  hideSignOut?: boolean;
}) {
  const { t } = useTranslation();
  const { contactSupportLink } = useFrontendProperties();
  const showLinks = !hideSignOut || Boolean(contactSupportLink);
  return (
    <PlatformAccessCard
      title={title}
      footerStart={
        showLinks && (
          <>
            {!hideSignOut && <SignOutLink />}
            {contactSupportLink && <SupportLink href={contactSupportLink} />}
          </>
        )
      }
      actions={
        <Button color="primary" variant="outlined" size="medium" onClick={retry}>
          {t("rework.platformAccess.retry")}
        </Button>
      }
    >
      <p role="alert">{message}</p>
    </PlatformAccessCard>
  );
}
