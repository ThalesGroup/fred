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
import type { LinkPart } from "../../../../../slices/runtime/runtimeOpenApi";
import Icon from "@shared/atoms/Icon/Icon";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { downloadAuthed } from "../../../../../utils/downloadUtils";
import styles from "./ArtifactLinks.module.css";

interface ArtifactLinkChipProps {
  link: LinkPart;
}

/**
 * One downloadable artifact chip (LinkPart). The `/fs/download` route is
 * session-authenticated, so a click runs an authenticated fetch (live Bearer
 * token) → blob → save rather than a plain anchor navigation, which would fail
 * without a token. Extracted from ArtifactLinks so the part-renderer registry
 * (#1977) can render one part per dispatch.
 */
export function ArtifactLinkChip({ link }: ArtifactLinkChipProps) {
  const { t } = useTranslation();
  const { showError } = useToast();

  if (!link.href) return null;

  const name = link.file_name ?? link.title ?? t("chatbot.artifactLinks.fallbackName");
  const onDownload = () => {
    downloadAuthed(link.href as string, name).catch(() => {
      showError({ summary: t("chatbot.artifactLinks.downloadFailed", { name }) });
    });
  };

  return (
    <button
      type="button"
      className={styles.chip}
      onClick={onDownload}
      aria-label={t("chatbot.artifactLinks.downloadAria", { name })}
    >
      <span className={styles.icon} aria-hidden>
        <Icon category="outlined" type="download" />
      </span>
      <span className={styles.name}>{name}</span>
    </button>
  );
}
