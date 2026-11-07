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

import Button from "@shared/atoms/Button/Button";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
export interface DocumentPreviewTarget {
  documentUid: string;
  sessionId?: string;
  fileName?: string;
  /** Authenticated PDF source for a conversation-created file. */
  sourceUrl?: string;
}
import {
  DocumentViewer,
  DocumentViewerModeToggle,
  type ViewMode,
} from "@shared/organisms/DocumentViewer/DocumentViewer.tsx";
import { InlineDrawer } from "@shared/molecules/InlineDrawer/InlineDrawer.tsx";
import { hasNativePreview, isEmailFile } from "../../../../utils/documentViewerUtils.ts";

export interface DocumentPreviewDrawerProps {
  /** The document to show, or null to keep the drawer closed. */
  target: DocumentPreviewTarget | null;
  onClose: () => void;
  onError?: (error: unknown) => void;
  onLoaded?: () => void;
}

/** Reading a document, wherever one is listed.
 *
 * The Fichier/Raw toggle lives in the drawer's own header rather than inside
 * the viewer, so the drawer owns which mode is showing — and resets it on every
 * new target, so one document's "Raw" choice never leaks into the next.
 */
export default function DocumentPreviewDrawer({ target, onClose, onError, onLoaded }: DocumentPreviewDrawerProps) {
  const { t } = useTranslation();
  const [view, setView] = useState<ViewMode>("file");

  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    setView("file");
    setFailed(false);
  }, [target?.documentUid]);

  return (
    <InlineDrawer
      open={!!target}
      onClose={onClose}
      title={target?.fileName ?? t("rework.resources.preview.title")}
      width="80vw"
      headerActions={
        !target?.sourceUrl && (hasNativePreview(target?.fileName) || isEmailFile(target?.fileName)) ? (
          <DocumentViewerModeToggle view={view} onChange={setView} fileName={target?.fileName} />
        ) : undefined
      }
    >
      {failed && (
        <div role="alert">
          <p>{t("chatbot.sessionAttachments.previewError")}</p>
          <Button size="small" variant="outlined" color="secondary" onClick={() => setAttempt((value) => value + 1)}>
            {t("common.retry")}
          </Button>
        </div>
      )}
      {target && (
        <DocumentViewer
          key={`${target.documentUid}:${attempt}`}
          sourceUrl={target.sourceUrl}
          onError={(error) => {
            setFailed(true);
            onError?.(error);
          }}
          onLoaded={() => {
            setFailed(false);
            onLoaded?.();
          }}
          documentUid={target.documentUid}
          sessionId={target.sessionId}
          fileName={target.fileName}
          view={view}
        />
      )}
    </InlineDrawer>
  );
}
