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
 * A thin adapter over the shared ArtifactCard (icon + title + click-to-open + action).
 */

import { useTranslation } from "react-i18next";
import type { WritableDocumentPart } from "../../slices/agentic/agenticOpenApi.ts";
import ArtifactCard from "./ArtifactCard.tsx";
import DocumentDownloadButton from "./DocumentDownloadButton.tsx";

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
    <ArtifactCard
      icon="description"
      title={part.title || t("chat.writableDocument.untitled", "Document")}
      hint={t("chat.writableDocument.openHint", "Open in editor")}
      onOpen={() => onOpen?.(part.document_id)}
      action={<DocumentDownloadButton sessionId={sessionId} documentId={part.document_id} title={part.title} />}
    />
  );
}
