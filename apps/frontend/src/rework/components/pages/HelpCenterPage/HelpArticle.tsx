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

import { useEffect, useState, type MouseEvent } from "react";
import { useHref, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import { Breadcrumb, type BreadcrumbSegment } from "@shared/molecules/Breadcrumb/Breadcrumb.tsx";
import { MarkdownRenderer } from "@shared/molecules/MarkdownRenderer/MarkdownRenderer";
import { helpPagePath, type HelpPage, type HelpSectionTree } from "@rework/features/helpCenter/content";
import type { HelpLang } from "@rework/features/helpCenter/manifest";
import { writeRichClipboard } from "@rework/utils/clipboardUtils";
import styles from "./HelpArticle.module.scss";

interface HelpArticleProps {
  lang: HelpLang;
  section: HelpSectionTree;
  page: HelpPage;
}

/**
 * One rendered help page: breadcrumb + copy-page-link on top, then the
 * markdown body with anchored headings. Scrolls to `#fragment` on arrival so
 * shared heading links land where they point.
 */
export default function HelpArticle({ lang, section, page }: HelpArticleProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const pageHref = useHref(helpPagePath(lang, section.id, page.meta.id));

  useEffect(() => {
    if (!location.hash) return;
    document.getElementById(decodeURIComponent(location.hash.slice(1)))?.scrollIntoView({ block: "start" });
  }, [location.hash, page.meta.id]);

  const segments: BreadcrumbSegment[] = [
    { label: t("rework.helpCenter.title"), onClick: () => navigate(`/help/${lang}`) },
    page.meta.id === "index"
      ? { label: t(section.titleKey) }
      : { label: t(section.titleKey), onClick: () => navigate(`/help/${lang}/${section.id}`) },
    ...(page.meta.id === "index" ? [] : [{ label: page.meta.title }]),
  ];

  const copyPageLink = () => {
    writeRichClipboard("", `${window.location.origin}${pageHref}`).then((ok) => {
      if (ok) {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 2000);
      }
    });
  };

  // Cross-links in the markdown render as plain <a href="/help/...">, which
  // trigger a full-page reload. Delegate clicks on same-origin absolute links
  // to the router so navigation between help pages stays instant. Modified
  // clicks (new tab, middle-click) and external/hash links fall through to the
  // browser's default handling.
  const onContentClick = (e: MouseEvent<HTMLDivElement>) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const anchor = (e.target as HTMLElement).closest("a");
    const href = anchor?.getAttribute("href");
    if (!href || !href.startsWith("/") || href.startsWith("//")) return;
    e.preventDefault();
    navigate(href);
  };

  return (
    <article className={styles.article}>
      <div className={styles.articleTop}>
        <Breadcrumb segments={segments} />
        <Tooltip text={t("rework.helpCenter.copyPageLink")}>
          <IconButton
            variant="icon"
            size="small"
            icon={{ category: "outlined", type: copied ? "check" : "content_copy" }}
            aria-label={t("rework.helpCenter.copyPageLink")}
            onClick={copyPageLink}
          />
        </Tooltip>
      </div>
      <div className={styles.articleBody} onClick={onContentClick}>
        <MarkdownRenderer text={page.body} headingAnchors />
      </div>
    </article>
  );
}
