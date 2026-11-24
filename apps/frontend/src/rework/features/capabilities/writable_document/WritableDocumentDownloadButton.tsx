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

// Direct download shared by conversation files and the editor pane header.
//
// The bytes live behind the capability's bearer-protected export route, so a bare
// `<a download>` would 401; `downloadWritableDocument` fetches WITH the live bearer
// against the capability base URL resolved from `capabilityRoutingSlice`.

import { useState } from "react";
import { useSelector } from "react-redux";
import { useTranslation } from "react-i18next";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { selectCapabilityBaseUrl, type CapabilityRoutingState } from "../../../../common/capabilityRoutingSlice";
import { CAPABILITY_ID } from "./api/writableDocumentCapabilityApi";
import { downloadWritableDocument } from "./downloadWritableDocument";
import { writableExportFormat } from "./writableDocumentUtils";

export default function WritableDocumentDownloadButton({
  sessionId,
  documentId,
  title,
}: {
  sessionId: string;
  documentId: string;
  title: string;
}) {
  const { t } = useTranslation();
  const { showError } = useToast();
  const baseUrl = useSelector((state: { capabilityRouting: CapabilityRoutingState }) =>
    selectCapabilityBaseUrl(state, CAPABILITY_ID),
  );
  const [isDownloading, setIsDownloading] = useState(false);

  const downloadLabel = t("capability.writable_document.download");

  const handleDownload = async () => {
    if (!baseUrl) {
      showError({ summary: t("capability.writable_document.downloadError") });
      return;
    }
    setIsDownloading(true);
    try {
      await downloadWritableDocument({ baseUrl, sessionId, documentId, format: writableExportFormat(title), title });
    } catch (err) {
      showError({
        summary: t("capability.writable_document.downloadError"),
        detail: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <IconButton
      color="on-surface"
      variant="icon"
      size="small"
      icon={{ category: "outlined", type: "download" }}
      loading={isDownloading}
      title={downloadLabel}
      onClick={() => void handleDownload()}
    />
  );
}
