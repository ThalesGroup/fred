// Copyright Thales 2025
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

/**
 * PptPreviewCard
 * --------------
 * Compact, clickable reference to a filled PowerPoint deck shown inside an assistant
 * message. Clicking the card opens/focuses the deck's PDF preview pane; the trailing button
 * downloads the source .pptx. The rendered deck lives in the pane, not here.
 *
 * A thin adapter over the shared ArtifactCard, mirroring WritableDocumentChip so both
 * in-chat artifacts look and behave the same.
 */

import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import type { PptPreviewPart } from "../../slices/agentic/agenticOpenApi.ts";
import ArtifactCard from "./ArtifactCard.tsx";
import styles from "./ArtifactCard.module.css";

export default function PptPreviewCard({
  part,
  onOpen,
}: {
  part: PptPreviewPart;
  onOpen?: (previewId: string) => void;
}) {
  const { t } = useTranslation();

  const download = part.pptx_download_url ? (
    <a
      className={styles.icon}
      href={part.pptx_download_url}
      download={part.file_name ?? undefined}
      aria-label={t("chat.pptPreview.download", "Download .pptx")}
      onClick={(e) => e.stopPropagation()}
    >
      <Icon category="outlined" type="download" />
    </a>
  ) : undefined;

  return (
    <ArtifactCard
      icon="slideshow"
      title={part.title || t("chat.pptPreview.untitled", "Presentation")}
      hint={t("chat.pptPreview.openHint", "Open preview")}
      onOpen={() => onOpen?.(part.preview_id)}
      action={download}
    />
  );
}
