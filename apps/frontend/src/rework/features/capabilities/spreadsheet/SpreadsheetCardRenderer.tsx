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

// The `spreadsheet_preview` chat card: file name, download, and a button that
// opens the preview pane. Every mount registers the file (that lights the
// launcher); a card created live, not replayed from history, opens the pane once.

import { useEffect } from "react";
import { useDispatch } from "react-redux";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import Button from "@shared/atoms/Button/Button";
import { requestSidePanelOpen } from "../sidePanelOpenRequestSlice";
import { useMountSessionId } from "../useOpenSessionId";
import type { UiPartRendererProps } from "../types";
import { CAPABILITY_ID, PANE_WIDGET, type SpreadsheetPreviewPartData } from "./types";
import { openSpreadsheet, registerSpreadsheet } from "./spreadsheetPreviewSlice";
import SpreadsheetDownloadButton from "./SpreadsheetDownloadButton";
import styles from "./SpreadsheetCardRenderer.module.css";

// Module-level so the live-render heuristic survives remounts (history replay
// happens in the first seconds after load), as in the ppt_filler card.
const seenIds = new Set<string>();
const pageLoadedAt = Date.now();
const AUTO_OPEN_MIN_AGE_MS = 5000;

export function SpreadsheetCardRenderer({ part }: UiPartRendererProps) {
  const { t } = useTranslation();
  const dispatch = useDispatch();
  const sessionId = useMountSessionId();
  const preview = part as unknown as SpreadsheetPreviewPartData;

  const openPane = () => {
    dispatch(openSpreadsheet({ sessionId, preview }));
    dispatch(requestSidePanelOpen({ capabilityId: CAPABILITY_ID, widget: PANE_WIDGET }));
  };

  useEffect(() => {
    if (!sessionId) return;
    const firstSighting = !seenIds.has(preview.preview_id);
    seenIds.add(preview.preview_id);
    dispatch(registerSpreadsheet({ sessionId, preview }));
    if (firstSighting && Date.now() - pageLoadedAt > AUTO_OPEN_MIN_AGE_MS) openPane();
    // Keyed on the file identity and conversation; `preview` is stable per id.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preview.preview_id, sessionId]);

  return (
    <div className={styles.card} role="note" aria-label={t("capability.spreadsheet.card.aria")}>
      <div className={styles.header}>
        <span className={styles.icon} aria-hidden>
          <Icon category="outlined" type="table_chart" />
        </span>
        <span className={styles.title} title={preview.file_name}>
          {preview.file_name}
        </span>
        <SpreadsheetDownloadButton href={preview.xlsx_download_url} fileName={preview.file_name} />
      </div>
      <div>
        <Button
          color="primary"
          variant="text"
          size="small"
          icon={{ category: "outlined", type: "table_chart" }}
          onClick={openPane}
        >
          {t("capability.spreadsheet.card.open")}
        </Button>
      </div>
    </div>
  );
}
