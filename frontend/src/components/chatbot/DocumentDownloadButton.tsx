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
 * DocumentDownloadButton
 * ----------------------
 * A download icon button that opens a dropdown menu letting the user pick the
 * export format for a writable document. Today only Word (.docx) is offered, but
 * the menu is data-driven (see EXPORT_FORMATS) so new formats are a one-line add.
 *
 * Owns the export + browser-download + error-toast logic so callers (the editor
 * pane and the in-message chip) stay DRY.
 *
 * Built with the rework design system (CSS modules + shared atoms), not MUI.
 */

import type { ReactNode } from "react";
import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import MenuItem from "@shared/atoms/MenuItem/MenuItem.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import type { ExportWritableDocumentFormat } from "../../slices/agentic/agenticApi.blob.ts";
import { useLazyExportWritableDocumentBlobQuery } from "../../slices/agentic/agenticApi.blob.ts";
import { WordIcon } from "../../utils/icons.tsx";
import { downloadFile } from "../../utils/downloadUtils.tsx";
import { useToast } from "../ToastProvider.tsx";
import styles from "./DocumentDownloadButton.module.css";

const sanitizeFilename = (name: string) =>
  name
    .replace(/[^\w\-. ]+/g, "")
    .trim()
    .replace(/\s+/g, "_") || "document";

/** The formats offered in the dropdown. Add an entry here to expose a new format. */
const EXPORT_FORMATS: ReadonlyArray<{
  format: ExportWritableDocumentFormat;
  extension: string;
  /** Rendered brand icon for the format (e.g. the Word SVG). */
  icon: ReactNode;
  /** i18n key + English fallback for the format's label. */
  label: [key: string, fallback: string];
}> = [
  {
    format: "docx",
    extension: "docx",
    icon: <WordIcon fontSize="small" />,
    label: ["chat.writableDocument.formatWord", "Microsoft Word"],
  },
];

export default function DocumentDownloadButton({
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
  const [exportDoc, { isFetching }] = useLazyExportWritableDocumentBlobQuery();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

  // Close on outside click or Escape while the menu is open.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const handleSelect = async (format: ExportWritableDocumentFormat, extension: string) => {
    setOpen(false);
    try {
      const blob = await exportDoc({ sessionId, documentId, format }).unwrap();
      downloadFile(blob, `${sanitizeFilename(title)}.${extension}`);
    } catch (err: any) {
      showError({
        summary: t("chat.writableDocument.downloadError", "Download failed"),
        detail: err?.message || String(err),
      });
    }
  };

  const downloadLabel = t("chat.writableDocument.download", "Download");

  return (
    <div ref={containerRef} className={styles.container}>
      <Tooltip text={downloadLabel}>
        <IconButton
          color="on-surface"
          variant="icon"
          size="small"
          icon={{ category: "outlined", type: "download" }}
          onClick={() => setOpen((v) => !v)}
          disabled={isFetching}
          aria-label={downloadLabel}
          aria-haspopup="menu"
          aria-expanded={open}
          aria-controls={open ? menuId : undefined}
        />
      </Tooltip>
      {open && (
        <ul id={menuId} role="menu" className={styles.menu} aria-label={downloadLabel}>
          <li className={styles.menuHeader} aria-hidden="true">
            {downloadLabel}
          </li>
          {EXPORT_FORMATS.map(({ format, extension, icon, label }) => (
            <MenuItem key={format} role="menuitem" onClick={() => handleSelect(format, extension)}>
              <span className={styles.formatIcon} aria-hidden="true">
                {icon}
              </span>
              <span className={styles.formatName}>{t(label[0], label[1])}</span>
              <span className={styles.formatExt}>.{extension}</span>
            </MenuItem>
          ))}
        </ul>
      )}
    </div>
  );
}
