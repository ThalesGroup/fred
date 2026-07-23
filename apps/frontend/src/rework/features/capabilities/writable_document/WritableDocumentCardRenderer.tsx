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

// The writable_document capability's `writable_document` chat-part card (#1905).
//
// A compact reference to a collaborative document shown inside a message: an icon,
// the title, an authorship caption (agent write vs user edit), an "Open" button
// (opens the editor pane) and an export dropdown. The editable body lives in the
// pane, not here.
//
// Two effects:
//  - EVERY rendered part is fed into the slice (`upsertFromPart`) so the pane's
//    merge sees every live document, even during history replay.
//  - Auto-open heuristic (port of Kea's first-appearance auto-open): a document
//    opened LIVE during this page load should pop the editor pane without a click,
//    but replaying chat HISTORY on load must NOT. So we auto-open a
//    `(document_id, updated_at)` exactly once, and only when the page has been open
//    >5s (history replay happens in the first moments after load; a live write later).

import { useEffect } from "react";
import { useDispatch } from "react-redux";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import Button from "@shared/atoms/Button/Button";
import { requestSidePanelOpen } from "../sidePanelOpenRequestSlice";
import type { UiPartRendererProps } from "../types";
import type { WritableDocumentPartData } from "./types";
import { selectWritableDocument, upsertFromPart } from "./writableDocumentSlice";
import { CAPABILITY_ID } from "./api/writableDocumentCapabilityApi";
import WritableDocumentDownloadButton from "./WritableDocumentDownloadButton";
import styles from "./WritableDocumentCardRenderer.module.css";

// Module-level so the heuristic survives card remounts within one page load.
const seenKeys = new Set<string>();
const pageLoadedAt = Date.now();
const AUTO_OPEN_MIN_AGE_MS = 5000;

export function WritableDocumentCardRenderer({ part }: UiPartRendererProps) {
  const { t } = useTranslation();
  const dispatch = useDispatch();
  const [searchParams] = useSearchParams();
  const sessionId = searchParams.get("session") ?? "";
  const doc = part as unknown as WritableDocumentPartData;

  const key = `${doc.document_id}:${doc.updated_at}`;

  // Feed every rendered snapshot into the shared slice (newest updated_at wins).
  useEffect(() => {
    if (sessionId) dispatch(upsertFromPart({ sessionId, doc }));
    // Keyed on document identity + version only; `doc`/`dispatch` are stable per that key.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, key]);

  // Opening = select the doc AND signal the page to open the writable_document pane.
  const openPane = () => {
    if (sessionId) dispatch(upsertFromPart({ sessionId, doc }));
    dispatch(selectWritableDocument(doc.document_id));
    dispatch(requestSidePanelOpen({ capabilityId: CAPABILITY_ID, widget: "writable_document_pane" }));
  };

  useEffect(() => {
    if (seenKeys.has(key)) return;
    const isLiveWrite = Date.now() - pageLoadedAt > AUTO_OPEN_MIN_AGE_MS;
    // Mark seen regardless, so a history-replay mount never auto-opens later and a
    // live write only pops the pane the first time its part arrives.
    seenKeys.add(key);
    if (isLiveWrite) openPane();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const title = doc.title || t("capability.writable_document.untitled");
  const caption =
    doc.updated_by === "user"
      ? t("capability.writable_document.card.updatedByUser")
      : t("capability.writable_document.card.updatedByAgent");

  return (
    <div className={styles.card} role="note" aria-label={t("capability.writable_document.card.aria")}>
      <div className={styles.header}>
        <span className={styles.icon} aria-hidden>
          <Icon category="outlined" type="edit_note" />
        </span>
        <span className={styles.title} title={title}>
          {title}
        </span>
        {sessionId && (
          <WritableDocumentDownloadButton sessionId={sessionId} documentId={doc.document_id} title={title} />
        )}
      </div>
      <div className={styles.footer}>
        <span className={styles.caption}>{caption}</span>
        <Button
          color="primary"
          variant="text"
          size="small"
          icon={{ category: "outlined", type: "edit_note" }}
          onClick={openPane}
        >
          {t("capability.writable_document.card.open")}
        </Button>
      </div>
    </div>
  );
}
