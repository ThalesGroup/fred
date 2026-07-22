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

// The ppt_filler capability's `ppt_preview` chat-part card (UiPartRenderer).
//
// A compact reference to a filled deck shown inside an assistant message: a
// slideshow icon, the deck title, an "Open preview" button (opens the side panel
// via the slice) and a ".pptx" download button. The rendered deck lives in the
// pane, not here.
//
// Auto-open heuristic (port of Kea's fill→pane flow): when a deck is filled LIVE
// during this page load, its card should pop the preview panel open without a
// click. But replaying chat HISTORY on initial load also mounts these cards, and
// we must NOT auto-open then. So we auto-open a `(preview_id, version)` exactly
// once, and only if the page has been open for >5s (history replay happens in the
// first moments after load; a live fill happens well after).

import { useEffect } from "react";
import { useDispatch } from "react-redux";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import Button from "@shared/atoms/Button/Button";
import { requestSidePanelOpen } from "../sidePanelOpenRequestSlice";
import type { UiPartRendererProps } from "../types";
import type { PptPreviewPartData } from "./types";
import { openPreview } from "./pptPreviewSlice";
import PptxDownloadButton from "./PptxDownloadButton";
import styles from "./PptPreviewCardRenderer.module.css";

// Module-level so the heuristic survives card remounts within one page load.
const seenKeys = new Set<string>();
const pageLoadedAt = Date.now();
const AUTO_OPEN_MIN_AGE_MS = 5000;

export function PptPreviewCardRenderer({ part }: UiPartRendererProps) {
  const { t } = useTranslation();
  const dispatch = useDispatch();
  const preview = part as unknown as PptPreviewPartData;

  const key = `${preview.preview_id}:${preview.version}`;

  // Opening = set the preview data AND signal the page to open the ppt_filler
  // side-panel column (the page owns the single-push-drawer state).
  const openPane = (data: PptPreviewPartData) => {
    dispatch(openPreview(data));
    dispatch(requestSidePanelOpen({ capabilityId: "ppt_filler", widget: "ppt_preview_pane" }));
  };

  useEffect(() => {
    if (seenKeys.has(key)) return;
    const isLiveFill = Date.now() - pageLoadedAt > AUTO_OPEN_MIN_AGE_MS;
    // Mark seen regardless, so a history-replay mount never auto-opens later and a
    // live fill only pops the panel the first time its part arrives.
    seenKeys.add(key);
    if (isLiveFill) openPane(preview);
    // Intentionally keyed on the deck identity only; `preview`/`dispatch` are stable
    // per that identity for this heuristic.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const title = preview.title || t("capability.ppt_filler.preview.untitled", { defaultValue: "Presentation" });

  return (
    <div
      className={styles.card}
      role="note"
      aria-label={t("capability.ppt_filler.preview.cardAria", { defaultValue: "Presentation preview" })}
    >
      <div className={styles.header}>
        <span className={styles.icon} aria-hidden>
          <Icon category="outlined" type="slideshow" />
        </span>
        <span className={styles.title} title={title}>
          {title}
        </span>
        {preview.pptx_download_url && (
          <PptxDownloadButton href={preview.pptx_download_url} fileName={preview.file_name} />
        )}
      </div>
      <div className={styles.actions}>
        <Button
          color="primary"
          variant="text"
          size="small"
          icon={{ category: "outlined", type: "slideshow" }}
          onClick={() => openPane(preview)}
        >
          {t("capability.ppt_filler.preview.open", { defaultValue: "Open preview" })}
        </Button>
      </div>
    </div>
  );
}
