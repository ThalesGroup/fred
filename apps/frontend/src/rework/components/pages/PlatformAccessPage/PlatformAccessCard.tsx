// SPDX-License-Identifier: Apache-2.0
import { useId, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useFrontendProperties } from "../../../../hooks/useFrontendProperties";
import { KeyCloakService } from "../../../../security/KeycloakService";
import styles from "./PlatformAccessCard.module.css";

// One card for every screen a person meets before being admitted.
export default function PlatformAccessCard({
  lead,
  title,
  children,
  footerStart,
  actions,
}: {
  /** Greeting shown larger, on its own line above the title. */
  lead?: string;
  title: string;
  children?: ReactNode;
  /** Discreet links at the footer's left. */
  footerStart?: ReactNode;
  /** Buttons at the footer's right. */
  actions?: ReactNode;
}) {
  const titleId = useId();
  const { siteDisplayName } = useFrontendProperties();
  return (
    <main className={styles.page}>
      <section className={styles.card} aria-labelledby={titleId}>
        <header className={styles.header}>
          {siteDisplayName && <p className={styles.brand}>{siteDisplayName}</p>}
          <h1 id={titleId} className={styles.title}>
            {lead && <span className={styles.lead}>{lead} </span>}
            {title}
          </h1>
        </header>
        {children && <div className={styles.content}>{children}</div>}
        {(footerStart || actions) && (
          <footer className={styles.footer}>
            {footerStart && <div className={styles.footerStart}>{footerStart}</div>}
            {actions}
          </footer>
        )}
      </section>
    </main>
  );
}

export function SupportLink({ href }: { href: string }) {
  const { t } = useTranslation();
  return (
    <a className={styles.link} href={href} target="_blank" rel="noopener noreferrer">
      {t("rework.platformAccess.support")}
    </a>
  );
}

export function SignOutLink() {
  const { t } = useTranslation();
  return (
    <button type="button" className={`${styles.link} ${styles.discreet}`} onClick={() => KeyCloakService.CallLogout()}>
      {t("rework.platformAccess.signOut")}
    </button>
  );
}
