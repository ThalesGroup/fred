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

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { DocumentPreviewTarget } from "../../../../../components/documents/common/useDocumentCommands";
import {
  DocumentViewer,
  DocumentViewerModeToggle,
  type ViewMode,
} from "@shared/organisms/DocumentViewer/DocumentViewer.tsx";
import { InlineDrawer } from "@shared/molecules/InlineDrawer/InlineDrawer.tsx";
import { hasNativePreview } from "../../../../utils/documentViewerUtils.ts";

export interface DocumentPreviewDrawerProps {
  /** The document to show, or null to keep the drawer closed. */
  target: DocumentPreviewTarget | null;
  onClose: () => void;
}

/** Reading a document, wherever one is listed.
 *
 * The Fichier/Raw toggle lives in the drawer's own header rather than inside
 * the viewer, so the drawer owns which mode is showing — and resets it on every
 * new target, so one document's "Raw" choice never leaks into the next.
 */
export default function DocumentPreviewDrawer({ target, onClose }: DocumentPreviewDrawerProps) {
  const { t } = useTranslation();
  const [view, setView] = useState<ViewMode>("file");

  useEffect(() => {
    setView("file");
  }, [target?.documentUid]);

  return (
    <InlineDrawer
      open={!!target}
      onClose={onClose}
      title={target?.fileName ?? t("rework.resources.preview.title")}
      width="80vw"
      background="var(--surface-container-high)"
      headerActions={
        hasNativePreview(target?.fileName) ? <DocumentViewerModeToggle view={view} onChange={setView} /> : undefined
      }
    >
      {target && <DocumentViewer documentUid={target.documentUid} fileName={target.fileName} view={view} />}
    </InlineDrawer>
  );
}
