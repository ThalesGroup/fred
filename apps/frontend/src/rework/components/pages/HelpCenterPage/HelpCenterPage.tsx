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

import { useEffect, useMemo } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup.tsx";
import { getHelpPage, getHelpTree, helpPagePath } from "@rework/features/helpCenter/content";
import { DEFAULT_SECTION_ID, HELP_LANGS, isHelpLang, type HelpLang } from "@rework/features/helpCenter/manifest";
import HelpSidebar from "./HelpSidebar";
import HelpArticle from "./HelpArticle";
import HelpSearch from "./HelpSearch";
import styles from "./HelpCenterPage.module.scss";

/** App-language → help-content language ("fr-FR" → "fr"; anything non-English falls back to fr). */
function appLangToHelpLang(appLanguage: string | undefined): HelpLang {
  return appLanguage?.toLowerCase().startsWith("en") ? "en" : "fr";
}

/**
 * The Help Center: a standalone wiki-style documentation page (own tab, no
 * app chrome) rendered from the markdown corpus in `features/helpCenter/`.
 * URL space `/help/:lang/:sectionId/:pageId` — every page and heading is
 * deep-linkable. See HELP-CENTER-RFC.md.
 */
export default function HelpCenterPage() {
  const params = useParams<{ lang: string; sectionId: string; pageId: string }>();
  const navigate = useNavigate();
  const { t, i18n } = useTranslation();

  const lang = isHelpLang(params.lang) ? params.lang : null;
  const tree = useMemo(() => (lang ? getHelpTree(lang) : []), [lang]);

  // The URL is the source of truth for the content language; align the app
  // chrome (sidebar labels, buttons) on it so a shared link renders whole.
  useEffect(() => {
    if (lang && appLangToHelpLang(i18n.language) !== lang) void i18n.changeLanguage(lang);
  }, [lang, i18n]);

  if (!lang) {
    return <Navigate to={`/help/${appLangToHelpLang(i18n.language)}/${DEFAULT_SECTION_ID}`} replace />;
  }
  if (!params.sectionId) {
    return <Navigate to={`/help/${lang}/${DEFAULT_SECTION_ID}`} replace />;
  }

  const section = tree.find((s) => s.id === params.sectionId);
  if (!section) {
    return <Navigate to={`/help/${lang}/${DEFAULT_SECTION_ID}`} replace />;
  }

  const pageId = params.pageId ?? "index";
  const page = getHelpPage(lang, section.id, pageId);
  if (!page && pageId !== "index") {
    return <Navigate to={`/help/${lang}/${section.id}`} replace />;
  }

  const switchLanguage = (target: HelpLang) => {
    if (target === lang) return;
    // Same page in the target language when it exists, else the section index.
    const twin = getHelpPage(target, section.id, pageId);
    navigate(twin ? helpPagePath(target, section.id, pageId) : `/help/${target}/${section.id}`);
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.headerTitle}>
          <span className={styles.headerIcon} aria-hidden="true">
            <Icon category="outlined" type="help" />
          </span>
          <span>{t("rework.helpCenter.title")}</span>
        </div>
        <div className={styles.headerActions}>
          <HelpSearch lang={lang} tree={tree} />
          <ButtonGroup
            variant="radio"
            size="2xs"
            color="secondary"
            aria-label={t("rework.helpCenter.languageAria")}
            items={HELP_LANGS.map((l) => ({ label: l.toUpperCase() }))}
            selectedIndex={HELP_LANGS.indexOf(lang)}
            onSelectedIndexChange={(index) => switchLanguage(HELP_LANGS[index])}
          />
        </div>
      </header>
      <div className={styles.body}>
        <HelpSidebar tree={tree} lang={lang} activeSectionId={section.id} activePageId={pageId} />
        <main className={styles.main}>
          {page ? (
            <HelpArticle lang={lang} section={section} page={page} />
          ) : (
            <p className={styles.missingPage}>{t("rework.helpCenter.missingPage")}</p>
          )}
        </main>
      </div>
    </div>
  );
}
