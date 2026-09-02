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

// The html_artifact capability's `html_artifact` chat-part card (#2478).
//
// A compact reference to a rendered HTML/CSS artifact shown inside a message: an
// icon, the title, an "Open preview" button (opens the viewer pane) and a download
// button. The rendered result and the source live in the pane, not here.
//
// Two effects (ported from writable_document's card):
//  - EVERY rendered part is fed into the slice (`upsertFromPart`) so the pane's
//    merge sees every live artifact, even during history replay.
//  - Auto-open heuristic: an artifact rendered LIVE during this page load pops the
//    viewer without a click, but replaying chat HISTORY must NOT. So we auto-open a
//    `(artifact_id, version)` exactly once, and only when the page has been open >5s
//    (history replay happens in the first moments after load; a live render later).

import { useEffect } from "react";
import { useDispatch } from "react-redux";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import Button from "@shared/atoms/Button/Button";
import { requestSidePanelOpen } from "../sidePanelOpenRequestSlice";
import { useMountSessionId } from "../useOpenSessionId";
import type { UiPartRendererProps } from "../types";
import { CAPABILITY_ID, type HtmlArtifactPartData } from "./types";
import { selectHtmlArtifact, upsertFromPart } from "./htmlArtifactSlice";
import HtmlArtifactDownloadButton from "./HtmlArtifactDownloadButton";
import styles from "./HtmlArtifactCardRenderer.module.css";

// Module-level so the heuristic survives card remounts within one page load.
const seenKeys = new Set<string>();
const pageLoadedAt = Date.now();
const AUTO_OPEN_MIN_AGE_MS = 5000;

export function HtmlArtifactCardRenderer({ part }: UiPartRendererProps) {
  const { t } = useTranslation();
  const dispatch = useDispatch();
  const sessionId = useMountSessionId();
  const art = part as unknown as HtmlArtifactPartData;

  const key = `${art.artifact_id}:${art.version}`;

  // Feed every rendered snapshot into the shared slice (latest rendered wins).
  useEffect(() => {
    if (sessionId) dispatch(upsertFromPart({ sessionId, art }));
    // Keyed on artifact identity + version only; `art`/`dispatch` are stable per that key.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, key]);

  // Opening = select the artifact AND signal the page to open the html_artifact pane.
  const openPane = () => {
    if (sessionId) dispatch(upsertFromPart({ sessionId, art }));
    dispatch(selectHtmlArtifact(art.artifact_id));
    dispatch(requestSidePanelOpen({ capabilityId: CAPABILITY_ID, widget: "html_artifact_pane" }));
  };

  useEffect(() => {
    if (seenKeys.has(key)) return;
    const isLiveRender = Date.now() - pageLoadedAt > AUTO_OPEN_MIN_AGE_MS;
    // Mark seen regardless, so a history-replay mount never auto-opens later and a
    // live render only pops the pane the first time its part arrives.
    seenKeys.add(key);
    if (isLiveRender) openPane();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const title = art.title || t("capability.html_artifact.untitled", { defaultValue: "HTML artifact" });

  return (
    <div
      className={styles.card}
      role="note"
      aria-label={t("capability.html_artifact.card.aria", { defaultValue: "HTML artifact" })}
    >
      <div className={styles.header}>
        <span className={styles.icon} aria-hidden>
          <Icon category="outlined" type="code" />
        </span>
        <span className={styles.title} title={title}>
          {title}
        </span>
        <HtmlArtifactDownloadButton html={art.html} css={art.css} title={title} />
      </div>
      <div className={styles.footer}>
        <Button
          color="primary"
          variant="text"
          size="small"
          icon={{ category: "outlined", type: "code" }}
          onClick={openPane}
        >
          {t("capability.html_artifact.card.open", { defaultValue: "Open preview" })}
        </Button>
      </div>
    </div>
  );
}
