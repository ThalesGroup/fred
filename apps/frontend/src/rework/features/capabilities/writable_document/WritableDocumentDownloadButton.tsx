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

// Export dropdown for a writable document, shared by BOTH the in-chat card and the
// editor pane header so the two stay DRY (Kea's DocumentDownloadButton port). The
// menu is data-driven (EXPORT_FORMATS) so a new backend format is a one-line add.
//
// The bytes live behind the capability's bearer-protected export route, so a bare
// `<a download>` would 401; `downloadWritableDocument` fetches WITH the live bearer
// against the capability base URL resolved from `capabilityRoutingSlice`.

import { useState } from "react";
import { useSelector } from "react-redux";
import { useTranslation } from "react-i18next";
import IconButtonMenu from "@shared/molecules/IconButtonMenu/IconButtonMenu";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import type { OptionModel } from "@models/Option.model";
import { selectCapabilityBaseUrl, type CapabilityRoutingState } from "../../../../common/capabilityRoutingSlice";
import { CAPABILITY_ID } from "./api/writableDocumentCapabilityApi";
import type { WritableDocumentExportFormat } from "./api/writableDocumentCapabilityOpenApi";
import { downloadWritableDocument } from "./downloadWritableDocument";

/** The formats offered in the dropdown. Add an entry to expose a new backend format. */
const EXPORT_FORMATS: ReadonlyArray<{
  format: WritableDocumentExportFormat;
  /** i18n key for the format label. */
  labelKey: string;
}> = [
  { format: "docx", labelKey: "capability.writable_document.format.word" },
  { format: "md", labelKey: "capability.writable_document.format.markdown" },
];

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

  const options: OptionModel<WritableDocumentExportFormat>[] = EXPORT_FORMATS.map(({ format, labelKey }) => ({
    value: format,
    key: format,
    label: t(labelKey),
  }));

  const handleSelect = async (format: WritableDocumentExportFormat) => {
    if (!baseUrl) {
      showError({ summary: t("capability.writable_document.downloadError") });
      return;
    }
    setIsDownloading(true);
    try {
      await downloadWritableDocument({ baseUrl, sessionId, documentId, format, title });
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
    <IconButtonMenu
      iconButton={{
        color: "on-surface",
        variant: "icon",
        size: "small",
        icon: { category: "outlined", type: "download" },
        disabled: isDownloading,
        "aria-label": downloadLabel,
      }}
      options={options}
      onSelect={(format) => void handleSelect(format)}
    />
  );
}
