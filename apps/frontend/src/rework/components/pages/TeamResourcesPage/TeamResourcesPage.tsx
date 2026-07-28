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

import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { InlineDrawer } from "@shared/molecules/InlineDrawer/InlineDrawer.tsx";
import { DocumentViewer, type DocumentViewerMode } from "@shared/organisms/DocumentViewer/DocumentViewer.tsx";
import type { DocumentPreviewTarget } from "../../../../components/documents/common/useDocumentCommands";
import { hasNativePreview } from "@rework/utils/documentViewerUtils.ts";
import { getQueryUiState } from "@core/utils/queryUiState.ts";
import { useFrontendBootstrap } from "../../../../hooks/useFrontendBootstrap.ts";
import { useListAllTagsKnowledgeFlowV1TagsGetQuery } from "../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useGetTeamQuery } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { useTeamCapabilities } from "@hooks/useTeamCapabilities.ts";
import { KeyCloakService } from "../../../../security/KeycloakService.ts";
import { isPersonalTeamId, personalTeamId } from "@shared/utils/teamId.ts";
import DocumentWorkspace, { type DocumentWorkspaceHandle } from "./DocumentWorkspace/DocumentWorkspace.tsx";
import TeamFilesystemBrowser from "./TeamFilesystemBrowser/TeamFilesystemBrowser.tsx";
import AgentFilesystemBrowser from "./AgentFilesystemBrowser/AgentFilesystemBrowser.tsx";
import WorkspaceRoot from "./WorkspaceRoot/WorkspaceRoot.tsx";
import FsRootMeta from "./FsRootMeta/FsRootMeta.tsx";
import FsRootAddMenu from "./FsRootAddMenu/FsRootAddMenu.tsx";
import { StorageMeter } from "./StorageMeter/StorageMeter.tsx";
import styles from "./TeamResourcesPage.module.css";

/**
 * Official rework workspace page (FILES-04). A single tree with four differentiated roots:
 * - Resources: document ingestion into the searchable corpus. Files must live in a library
 *   (folder/tag) to be indexed, so the root only creates libraries — no top-level upload.
 * - Mon espace: the user's personal-in-team files (teams/{team}/users/{uid}, via /fs)
 * - Espace d'équipe: the team-shared files (teams/{team}/shared, via /fs)
 * - Agents: per-agent generated files (teams/{team}/agents/{instance}/users/{uid}, via /fs)
 */
export default function TeamResourcesPage() {
  const { t } = useTranslation();
  const { teamId = "" } = useParams<{ teamId: string }>();
  const { activeTeam } = useFrontendBootstrap();
  const isPersonalTeam = isPersonalTeamId(teamId) || teamId === activeTeam?.id;
  const userId = KeyCloakService.GetUserId() ?? "";
  const teamName = activeTeam?.name ?? teamId;
  // The URL may carry the bare "personal" alias, but /fs ReBAC resolves against the
  // canonical personal-<uid> resource id. Canonicalize before building any /fs path.
  const fsTeamId = teamId === "personal" ? personalTeamId(userId) : teamId;
  const userRoot = `teams/${fsTeamId}/users/${userId}`;
  const sharedRoot = `teams/${fsTeamId}/shared`;
  const corpusRef = useRef<DocumentWorkspaceHandle>(null);
  const [previewTarget, setPreviewTarget] = useState<DocumentPreviewTarget | null>(null);
  // Which rendering the preview shows. Reset to "original" on every newly opened
  // document (below) so a PDF never inherits the previous file's markdown mode.
  const [previewMode, setPreviewMode] = useState<DocumentViewerMode>("original");
  // The toggle is only offered where the two renderings actually differ — i.e.
  // formats with a native renderer (PDF today). A .docx/.xlsx/.csv is ALREADY
  // displayed as its markdown extraction, so a button there would be inert.
  const canToggleMarkdown = hasNativePreview(previewTarget?.fileName);
  const { data: team } = useGetTeamQuery({ teamId });
  const { canUpdateResources: canCreateFolder } = useTeamCapabilities(team);
  const storageUsed = team?.current_resources_storage_size;
  // Seed the preview at ~70% of the viewport so it opens near-full-page; the
  // drag handle (capped at 92vw below) lets the user trade width with the list.
  const previewSeedWidth = `${typeof window !== "undefined" ? Math.round(window.innerWidth * 0.7) : 960}px`;

  // KF health gate — identical pattern to the old KnowledgeHubPage.
  const { isError, isLoading, isFetching, isUninitialized } = useListAllTagsKnowledgeFlowV1TagsGetQuery({
    type: "document",
    limit: 1,
    offset: 0,
  });
  const kfState = getQueryUiState({ isLoading, isFetching, isUninitialized, isError });

  if (kfState === "loading") {
    return <div className={styles.loadingState}>{t("rework.resources.loading")}</div>;
  }
  if (kfState === "error") {
    return (
      <ServiceNotice
        icon="cloud_off"
        title={t("rework.serviceNotice.knowledgeService.title")}
        description={t("rework.serviceNotice.knowledgeService.description")}
        centered
      />
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.main}>
        <header className={styles.header}>
          <h1 className={styles.title}>{t("rework.resources.workspaceTitle")}</h1>
          {storageUsed != null && <StorageMeter used={storageUsed} max={team?.max_resources_storage_size} />}
        </header>

        <div className={styles.tree}>
          <WorkspaceRoot
            icon={{ category: "outlined", type: "database" }}
            title={t("rework.resources.roots.resources")}
            hint={t("rework.resources.hints.resources")}
            meta={<span className={styles.badge}>{t("rework.resources.roots.indexed")}</span>}
            defaultOpen
            action={
              canCreateFolder ? (
                <IconButton
                  color="on-surface"
                  variant="outlined"
                  size="xs"
                  icon={{ category: "outlined", type: "create_new_folder" }}
                  aria-label={t("rework.resources.menu.newFolder")}
                  title={t("rework.resources.menu.newFolder")}
                  onClick={() => corpusRef.current?.openNewFolder()}
                />
              ) : undefined
            }
          >
            <DocumentWorkspace
              ref={corpusRef}
              teamId={teamId}
              isPersonalTeam={isPersonalTeam}
              // Re-selecting the document that's already open toggles the preview
              // shut (clicking its name a second time closes it); `previewUid`
              // tells the workspace which row that is, so it can drop the
              // highlight at the same time.
              previewUid={previewTarget?.documentUid ?? null}
              onPreview={(target) => {
                setPreviewMode("original");
                setPreviewTarget((prev) => (prev?.documentUid === target.documentUid ? null : target));
              }}
            />
          </WorkspaceRoot>

          <WorkspaceRoot
            icon={{ category: "outlined", type: "person" }}
            title={t("rework.resources.roots.mine")}
            hint={t("rework.resources.hints.mine")}
            meta={
              <FsRootMeta
                root={userRoot}
                nature={
                  isPersonalTeam
                    ? t("rework.resources.roots.privatePersonal")
                    : t("rework.resources.roots.private", { team: teamName })
                }
              />
            }
            action={<FsRootAddMenu root={userRoot} />}
          >
            <TeamFilesystemBrowser root={userRoot} />
          </WorkspaceRoot>

          {!isPersonalTeam && (
            <WorkspaceRoot
              icon={{ category: "outlined", type: "groups" }}
              title={t("rework.resources.roots.team")}
              hint={t("rework.resources.hints.team")}
              meta={<FsRootMeta root={sharedRoot} />}
              action={canCreateFolder ? <FsRootAddMenu root={sharedRoot} /> : undefined}
            >
              <TeamFilesystemBrowser root={sharedRoot} canWrite={canCreateFolder} />
            </WorkspaceRoot>
          )}

          <WorkspaceRoot
            icon={{ category: "outlined", type: "auto_awesome" }}
            title={t("rework.resources.roots.agents")}
            hint={t("rework.resources.hints.agents")}
          >
            <AgentFilesystemBrowser fsTeamId={fsTeamId} userId={userId} />
          </WorkspaceRoot>
        </div>
      </div>

      {/* Preview is a full-height push-drawer flush with the page's right/top/
          bottom edges (it sits outside the padded main column), so it fills
          almost the whole page while the list keeps a sliver on the left. Same
          resizable UX as the in-conversation writable-document pane. */}
      <InlineDrawer
        open={previewTarget !== null}
        onClose={() => setPreviewTarget(null)}
        title={previewTarget?.fileName ?? t("rework.resources.preview.title")}
        headerActions={
          canToggleMarkdown ? (
            <IconButton
              color="on-surface"
              variant="icon"
              size="small"
              icon={{
                category: "outlined",
                type: previewMode === "markdown" ? "picture_as_pdf" : "description",
              }}
              aria-label={t(
                previewMode === "markdown"
                  ? "rework.resources.preview.showOriginal"
                  : "rework.resources.preview.showMarkdown",
              )}
              title={t(
                previewMode === "markdown"
                  ? "rework.resources.preview.showOriginal"
                  : "rework.resources.preview.showMarkdown",
              )}
              aria-pressed={previewMode === "markdown"}
              onClick={() => setPreviewMode((prev) => (prev === "markdown" ? "original" : "markdown"))}
            />
          ) : undefined
        }
        layout="push"
        width={previewSeedWidth}
        resizable={{ persistKey: "resources-document-preview", maxWidth: 4000, maxViewportFraction: 0.92 }}
        flushBody
      >
        {previewTarget && (
          <DocumentViewer
            documentUid={previewTarget.documentUid}
            fileName={previewTarget.fileName}
            mode={previewMode}
          />
        )}
      </InlineDrawer>
    </div>
  );
}
