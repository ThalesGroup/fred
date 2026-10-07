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

import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type {
  WebResearchPage,
  WebResearchToolKind,
  WebResearchTraceResult,
} from "../../../../../utils/webResearchTrace";
import { hostOf, safeHttpUrl } from "../../../../../utils/externalUrl";
import styles from "./TraceDetailDrawer.module.css";
import webStyles from "./WebResearchToolDetail.module.css";

interface WebResearchToolDetailProps {
  kind: WebResearchToolKind;
  target: string;
  /** Null while the call is still running. */
  result: WebResearchTraceResult | null;
}

function ExternalLink({ url, children }: { url: string; children: ReactNode }) {
  const href = safeHttpUrl(url);
  if (!href) return <span>{children}</span>;
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className={webStyles.link}>
      {children}
    </a>
  );
}

/** Codes are a closed backend set; an unknown one still reads as "unavailable". */
function useErrorText(): (code: string) => string {
  const { t } = useTranslation();
  return (code) =>
    t(`rework.chatTrace.webResearch.errors.${code}`, {
      defaultValue: t("rework.chatTrace.webResearch.errors.unavailable"),
    });
}

function PageItem({ page }: { page: WebResearchPage }) {
  const { t } = useTranslation();
  const errorText = useErrorText();
  const host = hostOf(page.url);
  return (
    <li className={webStyles.page}>
      <ExternalLink url={page.url}>{page.title || host}</ExternalLink>
      <span className={webStyles.host}>{host}</span>
      {page.errorCode ? (
        <span className={webStyles.pageError}>{errorText(page.errorCode)}</span>
      ) : (
        page.snippet && <p className={webStyles.snippet}>{page.snippet}</p>
      )}
      {page.content && (
        <details className={webStyles.content}>
          <summary>
            {t("rework.chatTrace.webResearch.extractedText", { count: page.content.length })}
            {page.truncated && ` · ${t("rework.chatTrace.webResearch.truncated")}`}
          </summary>
          <p className={webStyles.contentText}>{page.content}</p>
        </details>
      )}
    </li>
  );
}

/** Curated view for native web research: what was searched or read, then each page found. */
export function WebResearchToolDetail({ kind, target, result }: WebResearchToolDetailProps) {
  const { t } = useTranslation();
  const errorText = useErrorText();
  return (
    <div className={styles.detail}>
      {target && (
        <div className={styles.toolSection}>
          <p className={styles.sectionLabel}>
            {t(kind === "fetchUrl" ? "rework.chatTrace.webResearch.page" : "rework.chatTrace.webResearch.query")}
          </p>
          {kind === "fetchUrl" ? (
            <ExternalLink url={target}>{target}</ExternalLink>
          ) : (
            <p className={webStyles.query}>{target}</p>
          )}
        </div>
      )}
      {result?.kind === "error" && <div className={styles.errorBox}>{errorText(result.errorCode)}</div>}
      {result?.kind === "pages" && (
        <div className={styles.toolSection}>
          <p className={styles.sectionLabel}>{t("rework.chatTrace.sources", { count: result.pages.length })}</p>
          {result.pages.length === 0 ? (
            <p className={webStyles.empty}>{t("rework.chatTrace.webResearch.noResults")}</p>
          ) : (
            <ol className={webStyles.pages}>
              {result.pages.map((page, index) => (
                <PageItem key={`${index}-${page.url}`} page={page} />
              ))}
            </ol>
          )}
        </div>
      )}
    </div>
  );
}
