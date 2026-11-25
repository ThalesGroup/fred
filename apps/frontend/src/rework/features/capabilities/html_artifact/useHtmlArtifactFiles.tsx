// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useDispatch, useSelector } from "react-redux";
import { useTranslation } from "react-i18next";
import IconButton from "@shared/atoms/IconButton/IconButton";
import type { CapabilityConversationFiles } from "../types";
import { requestSidePanelOpen } from "../sidePanelOpenRequestSlice";
import { selectHtmlArtifact, selectHtmlArtifactSessionId, selectHtmlArtifactsById } from "./htmlArtifactSlice";
import { artifactFileName } from "./htmlArtifactDocument";
import HtmlArtifactDownloadButton from "./HtmlArtifactDownloadButton";
import { CAPABILITY_ID } from "./types";

export function useHtmlArtifactFiles(sessionId: string): CapabilityConversationFiles {
  const { t } = useTranslation();
  const dispatch = useDispatch();
  const owner = useSelector(selectHtmlArtifactSessionId);
  const artifacts = useSelector(selectHtmlArtifactsById);
  return {
    title: t("capability.html_artifact.untitled"),
    loading: false,
    error: false,
    errorLabel: "",
    emptyLabel: t("capability.html_artifact.empty"),
    items:
      owner !== sessionId
        ? []
        : Object.values(artifacts).map((art) => ({
            id: art.artifact_id,
            name: artifactFileName(art.title),
            mime: "text/html",
            actions: (
              <>
                <IconButton
                  size="small"
                  variant="icon"
                  color="on-surface-retreat"
                  icon={{ category: "outlined", type: "visibility" }}
                  title={t("capability.html_artifact.card.open")}
                  onClick={() => {
                    dispatch(selectHtmlArtifact(art.artifact_id));
                    dispatch(requestSidePanelOpen({ capabilityId: CAPABILITY_ID, widget: "html_artifact_pane" }));
                  }}
                />
                <HtmlArtifactDownloadButton html={art.html} css={art.css} title={art.title} />
              </>
            ),
          })),
  };
}
