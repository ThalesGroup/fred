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
import type { LinkPart } from "../../../../../slices/runtime/runtimeOpenApi";
import type { RawUiPart } from "@rework/types/parts";
import Icon from "@shared/atoms/Icon/Icon";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { downloadAuthed, sameOriginDownloadUrl } from "../../../../../utils/downloadUtils";
import styles from "./ArtifactLinks.module.css";

interface ArtifactLinkChipProps {
  link: LinkPart;
  /** Markdown label: use the same download and error handling inline. */
  children?: ReactNode;
  title?: string;
}

const UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
const CONVERSATION_FILE = new RegExp(
  `^/control-plane/v1/spaces/${UUID}/sessions/${UUID}/files/(${UUID})/(?:content|preview)$`,
);

/** Match the exact stored reference, never infer download authority from prose. */
export function conversationArtifactForHref(href: string, parts: readonly RawUiPart[]): LinkPart | undefined {
  const url = sameOriginDownloadUrl(href);
  if (!url || url.search || url.hash) return undefined;
  const documentId = CONVERSATION_FILE.exec(url.pathname)?.[1];
  if (!documentId) return undefined;
  const part = parts.find(
    (part) =>
      part.type === "link" &&
      part.kind === "download" &&
      part.document_uid === documentId &&
      typeof part.href === "string" &&
      sameOriginDownloadUrl(part.href)?.href === url.href,
  );
  return part as LinkPart | undefined;
}

/**
 * One downloadable artifact chip (LinkPart). Its backend-provided URL is
 * authenticated, so a click runs an authenticated fetch (live Bearer
 * token) → blob → save rather than a plain anchor navigation, which would fail
 * without a token. Extracted from ArtifactLinks so the part-renderer registry
 * (#1977) can render one part per dispatch.
 */
export function ArtifactLinkChip({ link, children, title }: ArtifactLinkChipProps) {
  const { t } = useTranslation();
  const { showError } = useToast();

  if (!link.href) return null;

  const name = link.file_name ?? link.title ?? t("chatbot.artifactLinks.fallbackName");
  const onDownload = () => {
    downloadAuthed(link.href as string, name).catch(() => {
      showError({ summary: t("chatbot.artifactLinks.downloadFailed", { name }) });
    });
  };

  if (children !== undefined) {
    return (
      <a
        href={link.href}
        title={title}
        onClick={(event) => {
          event.preventDefault();
          onDownload();
        }}
      >
        {children}
      </a>
    );
  }

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
      <span className={styles.name} title={name}>
        {name}
      </span>
    </button>
  );
}
