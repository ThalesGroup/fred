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

// Download menu for one artifact — HTML (self-contained file), PDF (via the
// browser's print dialog), PNG (rasterized). Shared by the in-chat card and the
// pane header so the two stay DRY. The markup rides inline on the chat part, so
// HTML/PNG are plain client-side saves — no network, no bearer.

import { useTranslation } from "react-i18next";
import IconButtonMenu from "@shared/molecules/IconButtonMenu/IconButtonMenu";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import type { OptionModel } from "@models/Option.model.ts";
import { downloadHtmlArtifact } from "./htmlArtifactDocument";
import { downloadHtmlArtifactPdf, downloadHtmlArtifactPng } from "./htmlArtifactExport";

type DownloadFormat = "html" | "pdf" | "png";

export default function HtmlArtifactDownloadButton({ html, css, title }: { html: string; css: string; title: string }) {
  const { t } = useTranslation();
  const { showError } = useToast();
  const label = t("capability.html_artifact.download", { defaultValue: "Download" });

  const options: OptionModel<DownloadFormat>[] = [
    {
      value: "html",
      key: "html",
      label: t("capability.html_artifact.downloadHtml", { defaultValue: "HTML" }),
      icon: { category: "outlined", type: "code" },
    },
    {
      value: "pdf",
      key: "pdf",
      label: t("capability.html_artifact.downloadPdf", { defaultValue: "PDF" }),
      icon: { category: "outlined", type: "picture_as_pdf" },
    },
    {
      value: "png",
      key: "png",
      label: t("capability.html_artifact.downloadPng", { defaultValue: "PNG" }),
      icon: { category: "outlined", type: "image" },
    },
  ];

  const onSelect = async (format: DownloadFormat) => {
    if (format === "html") {
      downloadHtmlArtifact(html, css, title);
      return;
    }
    try {
      if (format === "pdf") {
        await downloadHtmlArtifactPdf(html, css, title);
      } else {
        await downloadHtmlArtifactPng(html, css, title);
      }
    } catch {
      showError({
        summary: t("capability.html_artifact.exportFailed", {
          format: format.toUpperCase(),
          defaultValue: "Could not export the {{format}}.",
        }),
      });
    }
  };

  return (
    <IconButtonMenu
      iconButton={{
        variant: "icon",
        size: "small",
        icon: { category: "outlined", type: "download" },
        "aria-label": label,
      }}
      options={options}
      onSelect={onSelect}
    />
  );
}
