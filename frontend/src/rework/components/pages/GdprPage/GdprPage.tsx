import styles from "./GdprPage.module.css";
import Button from "@shared/atoms/Button/Button.tsx";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import MarkdownRenderer from "../../../../components/markdown/MarkdownRenderer";
import { getProperty } from "../../../../common/config.tsx";

export default function GdprPage() {
  const { t, i18n } = useTranslation();
  const [gdprMarkdown, setGdprMarkdown] = useState<string>("");

  useEffect(() => {
    const base = (import.meta.env?.BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "";
    const lang = i18n.language?.split("-")[0] ?? "en";
    const brand = (getProperty("releaseBrand") || "").trim().toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "");
    const fetchMd = (path: string) =>
      fetch(`${base}${path}`, { cache: "no-cache" })
        .then((r) => (r.ok ? r.text() : null))
        .then((text) => (text && !text.toLowerCase().includes("<!doctype") ? text : null))
        .catch(() => null);

    const candidates = brand
      ? [`/contrib/${brand}/gdpr.${lang}.md`, `/contrib/${brand}/gdpr.md`, `/gdpr.${lang}.md`, `/gdpr.md`]
      : [`/gdpr.${lang}.md`, `/gdpr.md`];

    candidates.reduce((acc, path) => acc.then((text) => text ?? fetchMd(path)), Promise.resolve<string | null>(null))
      .then((text) => { if (text) setGdprMarkdown(text); });
  }, [i18n.language]);

  return (
    <div className={styles.gdprContainer}>
      <div className={styles.gdprTitle}>{t("rework.gcu.title")}</div>
      <div className={styles.gdprContent}>
        <MarkdownRenderer content={gdprMarkdown} />
      </div>
      <div className={styles.gdprActions}>
        <Link to={"/"}>
          <Button color={"primary"} variant={"filled"} size={"medium"}>
            {t("rework.gcu.backToApp")}
          </Button>
        </Link>
      </div>
    </div>
  );
}
