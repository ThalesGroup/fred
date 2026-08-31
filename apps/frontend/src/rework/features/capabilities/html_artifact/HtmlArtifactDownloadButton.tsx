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

// Download the composed self-contained .html for one artifact, shared by BOTH the
// in-chat card and the pane header so the two stay DRY.
//
// Unlike ppt_filler / writable_document (whose bytes live behind a bearer-protected
// download route), the html_artifact markup rides inline on the chat part, so this
// is a plain client-side blob save — no network, no bearer.

import { useTranslation } from "react-i18next";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import { downloadHtmlArtifact } from "./htmlArtifactDocument";

export default function HtmlArtifactDownloadButton({ html, css, title }: { html: string; css: string; title: string }) {
  const { t } = useTranslation();
  const label = t("capability.html_artifact.download", { defaultValue: "Download .html" });

  return (
    <Tooltip text={label}>
      <IconButton
        variant="icon"
        size="small"
        icon={{ category: "outlined", type: "download" }}
        onClick={() => downloadHtmlArtifact(html, css, title)}
        aria-label={label}
      />
    </Tooltip>
  );
}
