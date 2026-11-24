// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import Icon from "@shared/atoms/Icon/Icon";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import Select from "@shared/molecules/Select/Select";
import { useFrontendBootstrap } from "src/hooks/useFrontendBootstrap";
import { useFrontendProperties } from "src/hooks/useFrontendProperties";
import type { ConversationTraceDetail } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { TRACE_TRANSLATION_PREFIX, useTraceChatHref, useTraceCopy } from "./traceControls";
import styles from "./ConversationTraces.module.css";

type MessageLanguage = "en" | "fr";
const languages: { key: MessageLanguage; value: MessageLanguage; label: string }[] = [
  { key: "fr", value: "fr", label: "Français" },
  { key: "en", value: "en", label: "English" },
];

export function ContactTraceOwner({ conversation }: { conversation: ConversationTraceDetail }) {
  const { t, i18n } = useTranslation(undefined, { keyPrefix: TRACE_TRANSLATION_PREFIX });
  const { bootstrap } = useFrontendBootstrap();
  const { siteDisplayName } = useFrontendProperties();
  const href = useTraceChatHref(conversation);
  const [open, setOpen] = useState(false);
  const [language, setLanguage] = useState<MessageLanguage>("en");
  const [copiedLanguage, setCopiedLanguage] = useState<MessageLanguage>();
  const [copying, setCopying] = useState(false);
  const { copied, copyFailed, copy } = useTraceCopy();
  const admin = bootstrap?.current_user;
  const signature =
    [admin?.first_name?.trim(), admin?.last_name?.trim()].filter(Boolean).join(" ") || admin?.username?.trim();
  const userFirstName = conversation.user_first_name?.trim();

  const visible = open && Boolean(signature);
  const chatUrl = visible ? new URL(href, window.location.origin).href : "";
  const subject = t("contact.subject", { lng: language, siteName: siteDisplayName });
  const greeting = userFirstName
    ? t("contact.greeting", { lng: language, userFirstName })
    : t("contact.greetingGeneric", { lng: language });
  const message = `${greeting}\n\n${t("contact.body", {
    lng: language,
    siteName: siteDisplayName,
    chatUrl,
  })}\n${signature ?? ""}`;
  const email = conversation.user_email?.trim();
  const mailHref =
    email && /^[^\s@,;]+@[^\s@,;]+$/.test(email)
      ? `mailto:${encodeURIComponent(email).replace("%40", "@")}?subject=${encodeURIComponent(subject.replace(/[\r\n]/g, " "))}&body=${encodeURIComponent(message.replace(/\r?\n/g, "\r\n"))}`
      : undefined;

  const copiedCurrentDraft = copied && !copyFailed && copiedLanguage === language;

  async function copyMessage() {
    setCopiedLanguage(undefined);
    setCopying(true);
    try {
      await copy(message);
      setCopiedLanguage(language);
    } finally {
      setCopying(false);
    }
  }

  return (
    <>
      <Button
        type="button"
        aria-haspopup="dialog"
        color="primary"
        variant="outlined"
        size="small"
        icon={{ type: "mail" }}
        title={signature ? undefined : t("contact.adminUnavailable")}
        disabled={!signature}
        onClick={() => {
          setLanguage(i18n.language.toLowerCase().startsWith("fr") ? "fr" : "en");
          setCopiedLanguage(undefined);
          setOpen(true);
        }}
      >
        {t("contact.action")}
      </Button>
      {visible && (
        <Dialog
          open
          maxWidth={560}
          title={t("contact.action")}
          cancelLabel={t("contact.close")}
          confirmLabel={t("contact.copy")}
          confirmIcon={{ type: "content_copy" }}
          onCancel={() => setOpen(false)}
          confirmDisabled={copying}
          onConfirm={() => void copyMessage()}
          footerStart={
            mailHref && (
              <a className={styles.contactMailLink} href={mailHref}>
                <Icon type="mail" /> {t("contact.mail")}
              </a>
            )
          }
        >
          <div className={styles.contactFields}>
            <Select
              label={t("contact.language")}
              value={language}
              size="small"
              onChange={(value) => {
                if (value === "en" || value === "fr") setLanguage(value);
              }}
              options={languages}
            />
            <div className={styles.contactPreview} lang={language}>
              <strong>{subject}</strong>
              <p>{message}</p>
            </div>
            {!mailHref && <p>{t("contact.noEmail")}</p>}
            <span role="status" className={styles.overviewCopyStatus}>
              {copiedCurrentDraft ? t("copied") : ""}
            </span>
            {copiedCurrentDraft && <p aria-hidden="true">{t("copied")}</p>}
            {copyFailed && copiedLanguage === language && <p role="alert">{t("copyFailed")}</p>}
          </div>
        </Dialog>
      )}
    </>
  );
}
