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

import { useTranslation } from "react-i18next";
import type { LinkPart } from "../../../../../slices/agentic/agenticOpenApi";
import Icon from "@shared/atoms/Icon/Icon";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { downloadAuthed } from "../../../../../utils/downloadUtils";
import styles from "./ArtifactLinks.module.css";

interface ArtifactLinksProps {
  links: LinkPart[];
}

/**
 * Render agent-produced downloadable artifacts (LinkPart ui_parts) as download
 * chips. The `/fs/download` route is session-authenticated, so a chip click runs
 * an authenticated fetch (live Bearer token) → blob → save rather than a plain
 * anchor navigation, which would fail without a token.
 */
export function ArtifactLinks({ links }: ArtifactLinksProps) {
  const { t } = useTranslation();
  const { showError } = useToast();

  const downloadable = links.filter((link) => Boolean(link.href));
  if (downloadable.length === 0) return null;

  const onDownload = (link: LinkPart) => {
    const name = link.file_name ?? link.title ?? t("chatbot.artifactLinks.fallbackName");
    downloadAuthed(link.href as string, name).catch(() => {
      showError({ summary: t("chatbot.artifactLinks.downloadFailed", { name }) });
    });
  };

  return (
    <div className={styles.links} aria-label={t("chatbot.artifactLinks.ariaLabel")}>
      {downloadable.map((link, index) => {
        const name = link.file_name ?? link.title ?? t("chatbot.artifactLinks.fallbackName");
        return (
          <button
            key={`${link.href}-${index}`}
            type="button"
            className={styles.chip}
            onClick={() => onDownload(link)}
            aria-label={t("chatbot.artifactLinks.downloadAria", { name })}
          >
            <span className={styles.icon} aria-hidden>
              <Icon category="outlined" type="download" />
            </span>
            <span className={styles.name}>{name}</span>
          </button>
        );
      })}
    </div>
  );
}
