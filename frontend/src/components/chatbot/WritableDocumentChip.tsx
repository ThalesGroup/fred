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
 * WritableDocumentChip
 * --------------------
 * Compact, clickable reference to a collaborative document shown inside an assistant
 * message. Clicking the chip opens/focuses the document in the editor pane; the Word
 * button exports it as .docx. The full document content lives in the pane, not here.
 *
 * Built with the rework design system (CSS modules + shared atoms), not MUI.
 */

import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import type { WritableDocumentPart } from "../../slices/agentic/agenticOpenApi.ts";
import DocumentDownloadButton from "./DocumentDownloadButton.tsx";
import styles from "./WritableDocumentChip.module.css";

export default function WritableDocumentChip({
  part,
  sessionId,
  onOpen,
}: {
  part: WritableDocumentPart;
  sessionId: string;
  onOpen?: (documentId: string) => void;
}) {
  const { t } = useTranslation();

  return (
    <div className={styles.chip}>
      <button type="button" className={styles.open} onClick={() => onOpen?.(part.document_id)}>
        <span className={styles.icon}>
          <Icon category="outlined" type="description" />
        </span>
        <span className={styles.text}>
          <span className={styles.title}>{part.title || t("chat.writableDocument.untitled", "Document")}</span>
          <span className={styles.hint}>{t("chat.writableDocument.openHint", "Open in editor")}</span>
        </span>
      </button>
      <DocumentDownloadButton sessionId={sessionId} documentId={part.document_id} title={part.title} />
    </div>
  );
}
