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
// Auto-open (Kea `usePptPreview` parity): every card folds its deck into the
// slice on mount (`previewSeen`), so the pane always knows the LATEST deck —
// including after a page reload replays history. The FIRST deck of a session
// view also opens the panel automatically (live fill and history replay alike);
// the slice's once-per-view budget (`selectShouldAutoOpen`) guarantees later
// cards never fight a user who closed the panel. The chat page re-arms the
// budget per conversation via `chatSessionScopeChanged`.

import { useEffect } from "react";
import { useDispatch, useSelector, useStore } from "react-redux";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import Button from "@shared/atoms/Button/Button";
import { requestSidePanelOpen } from "../sidePanelOpenRequestSlice";
import type { UiPartRendererProps } from "../types";
import type { PptPreviewPartData } from "./types";
import { previewKeyOf, previewSeen, selectIsPreviewSeen, selectPreview, selectShouldAutoOpen } from "./pptPreviewSlice";
import PptxDownloadButton from "./PptxDownloadButton";
import styles from "./PptPreviewCardRenderer.module.css";

const OPEN_PANEL_REQUEST = { capabilityId: "ppt_filler", widget: "ppt_preview_pane" } as const;

export function PptPreviewCardRenderer({ part }: UiPartRendererProps) {
  const { t } = useTranslation();
  const dispatch = useDispatch();
  const store = useStore();
  const preview = part as unknown as PptPreviewPartData;

  const key = previewKeyOf(preview);
  // Subscribed only to keep the effect honest across store resets; the effect
  // re-reads the LIVE state below to stay correct when sibling cards mount in
  // the same commit (their dispatches are invisible to this render's props).
  const seen = useSelector(selectIsPreviewSeen(key));

  useEffect(() => {
    type SliceState = Parameters<typeof selectShouldAutoOpen>[0];
    const state = store.getState() as SliceState;
    if (selectIsPreviewSeen(key)(state)) return;
    const shouldAutoOpen = selectShouldAutoOpen(state);
    // Fold this deck in (marks it seen, makes it current, consumes the
    // session view's auto-open budget)…
    dispatch(previewSeen(preview));
    // …and pop the panel only for the view's first deck.
    if (shouldAutoOpen) dispatch(requestSidePanelOpen(OPEN_PANEL_REQUEST));
    // Keyed on the deck identity (and re-armed when a session-scope reset
    // clears `seen`); `preview` is stable per key.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, seen]);

  const openPane = () => {
    dispatch(selectPreview(preview));
    dispatch(requestSidePanelOpen(OPEN_PANEL_REQUEST));
  };

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
          onClick={openPane}
        >
          {t("capability.ppt_filler.preview.open", { defaultValue: "Open preview" })}
        </Button>
      </div>
    </div>
  );
}
