// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import Button from "@shared/atoms/Button/Button.tsx";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { MarkdownRenderer } from "@shared/molecules/MarkdownRenderer/MarkdownRenderer";
import { getProperty } from "../../../../common/config.tsx";
import styles from "./GdprPage.module.css";

export default function GdprPage() {
  const { t, i18n } = useTranslation();
  const [gdprMarkdown, setGdprMarkdown] = useState<string>("");

  useEffect(() => {
    const base = (import.meta.env?.BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "";
    const lang = i18n.language?.split("-")[0] ?? "en";
    const brand = (getProperty("releaseBrand") || "")
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9_-]+/g, "-")
      .replace(/^-+|-+$/g, "");
    const fetchMd = (path: string) =>
      fetch(`${base}${path}`, { cache: "no-cache" })
        .then((r) => (r.ok ? r.text() : null))
        .then((text) => (text && !text.toLowerCase().includes("<!doctype") ? text : null))
        .catch(() => null);

    const candidates = brand
      ? [`/contrib/${brand}/gdpr.${lang}.md`, `/contrib/${brand}/gdpr.md`, `/gdpr.${lang}.md`, `/gdpr.md`]
      : [`/gdpr.${lang}.md`, `/gdpr.md`];

    candidates
      .reduce((acc, path) => acc.then((text) => text ?? fetchMd(path)), Promise.resolve<string | null>(null))
      .then((text) => {
        if (text) setGdprMarkdown(text);
      });
  }, [i18n.language]);

  return (
    <div className={styles.gdprContainer}>
      <div className={styles.gdprTitle}>{t("rework.gcu.title")}</div>
      <div className={styles.gdprContent}>
        <MarkdownRenderer text={gdprMarkdown} />
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
