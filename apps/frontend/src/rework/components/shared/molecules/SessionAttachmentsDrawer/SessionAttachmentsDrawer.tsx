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

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import IconButtonMenu from "@shared/molecules/IconButtonMenu/IconButtonMenu";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import type { OptionModel } from "@models/Option.model";
import { fileIconSpec } from "../../../../utils/fileIconSpec";
import Button from "@shared/atoms/Button/Button";
import ChatSidePanel from "../ChatSidePanel/ChatSidePanel.tsx";
import { formatBytes } from "@shared/utils/formatBytes";
import type { SessionAttachment } from "@rework/types/attachments";
import DocumentPreviewDrawer, { type DocumentPreviewTarget } from "../DocumentPreviewDrawer/DocumentPreviewDrawer";
import type { ConversationFile } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import type { WorkspaceFile } from "../../../../../slices/runtime/runtimeOpenApi";
import { conversationFileUrl, workspaceFileUrl } from "../../../../features/conversationFiles";
import { downloadAuthed, fetchAuthedBlob } from "../../../../../utils/downloadUtils";
import { capabilityUiPlugins } from "@rework/features/capabilities";
import type { CapabilityConversationFiles, CapabilityUiPlugin } from "@rework/features/capabilities/types";
import DataTable from "@shared/molecules/DataTable/LocalizedDataTable";
import { ConversationFilesWikiDialog } from "@rework/features/teamWiki/ConversationFilesWikiDialog";
import { sha256, type WikiShareFile } from "@rework/features/teamWiki/wikiFileShare";
import type { ProposeWikiFileRequest } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { ConfirmationDialog } from "../ConfirmationDialog/ConfirmationDialog";
import styles from "./SessionAttachmentsDrawer.module.css";

interface SessionAttachmentsDrawerProps {
  capabilityIds?: readonly string[];
  open: boolean;
  onClose: () => void;
  attachments: SessionAttachment[];
  files?: ConversationFile[];
  workspaceFiles?: WorkspaceFile[];
  workspaceFilesUrl?: string | null;
  workspaceError?: unknown;
  workspaceLoading?: boolean;
  spaceId?: string;
  sessionId?: string;
  filesError?: unknown;
  attachmentsError?: unknown;
  filesLoading?: boolean;
  isLoading?: boolean;
  readOnly?: boolean;
  onRetryFiles?: () => void;
  onRetryAttachments?: () => void;
  spaceName?: string;
  wikiUrl?: string;
  onFileCount?: (sessionId: string, count: number) => void;
  onDeleteFile?: (documentId: string) => Promise<void>;
  onDeleteWorkspaceFile?: (path: string) => Promise<void>;
  onDelete: (attachmentId: string) => Promise<boolean> | void;
}

interface DrawerFile {
  id: string;
  name: string;
  size?: number | null;
  modified?: string | null;
  mime?: string;
  status?: SessionAttachment["status"];
  remove?: () => Promise<boolean | void> | void;
  error?: SessionAttachment["error"];
  downloadUrl?: string | null;
  preview?: DocumentPreviewTarget | null;
  actions?: ReactNode;
  prepareWikiShare?: () => Promise<ProposeWikiFileRequest>;
}

interface DrawerSection {
  key: string;
  title?: string;
  error?: unknown;
  loading?: boolean;
  retry?: () => void;
  errorKey?: string;
  errorLabel?: string;
  emptyLabel?: string;
  items: DrawerFile[];
}

// An isolated hook slot, as for side-panel launchers: changing the active
// capabilities must never reorder the drawer's hooks. No content state here.
function CapabilityFiles({
  useFiles,
  sessionId,
  render,
  onCount,
  id,
}: {
  useFiles: NonNullable<CapabilityUiPlugin["useConversationFiles"]>;
  sessionId: string;
  render: (files: CapabilityConversationFiles) => ReactNode;
  onCount: (id: string, count: number) => void;
  id: string;
}) {
  const files = useFiles(sessionId);
  useEffect(() => {
    onCount(id, files.items.length);
    return () => onCount(id, 0);
  }, [id, files.items.length, onCount]);
  return render(files);
}

// Only a numeric HTTP status is safe to display from an untrusted error payload.
// Never render response bodies, exception messages, paths or credentials.
function httpStatus(error: unknown): number | undefined {
  const status = error && typeof error === "object" && "status" in error ? error.status : undefined;
  if (typeof status === "number" && status >= 400 && status <= 599) return status;
  const match = error instanceof Error && /^Download failed \(([45]\d{2})\)$/.exec(error.message);
  return match ? Number(match[1]) : undefined;
}

export function SessionAttachmentsDrawer({
  capabilityIds = [],
  open,
  onClose,
  attachments,
  files = [],
  workspaceFiles = [],
  workspaceFilesUrl = "",
  workspaceError,
  workspaceLoading = false,
  spaceId = "",
  sessionId = "",
  filesError,
  attachmentsError,
  filesLoading = false,
  isLoading = false,
  readOnly = false,
  onRetryFiles,
  onRetryAttachments,
  onDelete,
  onDeleteFile,
  onDeleteWorkspaceFile,
  spaceName = "",
  wikiUrl = "",
  onFileCount,
}: SessionAttachmentsDrawerProps) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<Record<string, DrawerFile>>({});
  const [sharing, setSharing] = useState<{ sessionId: string; files: WikiShareFile[] } | null>(null);
  const [capabilityCounts, setCapabilityCounts] = useState<Record<string, number>>({});
  const reportCount = useCallback(
    (id: string, count: number) =>
      setCapabilityCounts((previous) => (previous[id] === count ? previous : { ...previous, [id]: count })),
    [],
  );
  const count =
    attachments.length +
    files.length +
    workspaceFiles.length +
    Object.values(capabilityCounts).reduce((a, b) => a + b, 0);
  useEffect(() => {
    onFileCount?.(sessionId, count);
  }, [sessionId, count, onFileCount]);
  const share = (entries: Record<string, DrawerFile>) =>
    setSharing({
      sessionId,
      files: Object.entries(entries).flatMap(([key, file]) =>
        file.prepareWikiShare ? [{ key, name: file.name, prepareWikiShare: file.prepareWikiShare }] : [],
      ),
    });
  const [deleteTarget, setDeleteTarget] = useState<{ sessionId: string; key: string; file: DrawerFile } | null>(null);
  const [deleting, setDeleting] = useState(false);
  const pendingDelete = useRef(false);
  const activeSession = useRef(sessionId);
  activeSession.current = sessionId;
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [downloading, setDownloading] = useState<Record<string, boolean>>({});
  const pendingDownloads = useRef(new Set<string>());
  const [preview, setPreview] = useState<(DocumentPreviewTarget & { key: string }) | null>(null);
  useEffect(() => {
    setSelected({});
    setDeleteTarget(null);
    setSharing(null);
    setPreview(null);
    setErrors({});
  }, [sessionId]);
  const errorMessage = (key: string, error: unknown) => {
    const status = httpStatus(error);
    return t(`chatbot.sessionAttachments.${key}`) + (status ? ` (HTTP ${status})` : "");
  };
  const download = async (key: string, url: string, name: string) => {
    if (pendingDownloads.current.has(key)) return;
    pendingDownloads.current.add(key);
    setDownloading((previous) => ({ ...previous, [key]: true }));
    try {
      await downloadAuthed(url, name);
      setErrors((previous) => ({ ...previous, [`${key}:download`]: "" }));
    } catch (error) {
      setErrors((previous) => ({ ...previous, [`${key}:download`]: errorMessage("downloadError", error) }));
    } finally {
      pendingDownloads.current.delete(key);
      setDownloading((previous) => ({ ...previous, [key]: false }));
    }
  };
  const remove = async () => {
    const target = deleteTarget;
    if (!target?.file.remove || readOnly || target.sessionId !== sessionId || pendingDelete.current) return;
    pendingDelete.current = true;
    setDeleting(true);
    try {
      if ((await target.file.remove()) === false) throw new Error("Deletion refused");
      if (activeSession.current !== target.sessionId) return;
      setSelected((previous) => Object.fromEntries(Object.entries(previous).filter(([key]) => key !== target.key)));
      setPreview((previous) => (previous?.key === target.key ? null : previous));
      setErrors((previous) => ({ ...previous, [`${target.key}:delete`]: "" }));
      setDeleteTarget(null);
    } catch (error) {
      if (activeSession.current === target.sessionId)
        setErrors((previous) => ({ ...previous, [`${target.key}:delete`]: errorMessage("deleteError", error) }));
    } finally {
      pendingDelete.current = false;
      setDeleting(false);
    }
  };
  const sections: DrawerSection[] = [
    {
      key: "workspace",
      error: workspaceError,
      loading: workspaceLoading,
      retry: onRetryFiles,
      errorKey: "workspaceError",
      items: workspaceFiles.map((file) => ({
        id: file.path,
        name: file.name,
        size: file.size,
        modified: file.modified,
        mime: "text/plain",
        status: "ready" as const,
        remove: onDeleteWorkspaceFile ? () => onDeleteWorkspaceFile(file.path) : undefined,
        error: undefined,
        prepareWikiShare: async () => ({
          workspace_file: {
            path: file.path,
            sha256: await sha256(
              new Uint8Array(
                await (await fetchAuthedBlob(workspaceFileUrl(workspaceFilesUrl ?? "", file.path))).arrayBuffer(),
              ),
            ),
          },
        }),
        downloadUrl: workspaceFileUrl(workspaceFilesUrl ?? "", file.path),
        preview: {
          documentUid: `workspace:${sessionId}:${file.path}`,
          fileName: file.name,
          sourceUrl: workspaceFileUrl(workspaceFilesUrl ?? "", file.path),
          sourceFormat: "text" as const,
        },
      })),
    },
    {
      key: "deliverables",
      error: filesError,
      loading: filesLoading,
      retry: onRetryFiles,
      errorKey: "filesError",
      items: files.map((file) => ({
        id: file.document_id,
        name: file.name,
        size: file.size,
        modified: undefined,
        mime: file.mime,
        status: "ready" as const,
        remove: onDeleteFile ? () => onDeleteFile(file.document_id) : undefined,
        error: undefined,
        prepareWikiShare: async () => ({ document_id: file.document_id, expected_content_id: file.content_id }),
        downloadUrl: conversationFileUrl(spaceId, sessionId, file.document_id),
        preview:
          file.preview_content_id || file.mime === "application/pdf"
            ? {
                documentUid: file.document_id,
                fileName: file.name,
                sourceUrl: conversationFileUrl(spaceId, sessionId, file.document_id, !!file.preview_content_id),
              }
            : null,
      })),
    },
    {
      key: "sources",
      error: attachmentsError,
      loading: isLoading,
      retry: onRetryAttachments,
      errorKey: "attachmentsError",
      items: attachments.map((attachment) => ({
        id: attachment.attachmentId,
        name: attachment.name,
        size: attachment.sizeBytes,
        modified: undefined,
        mime: attachment.mime ?? "",
        status: attachment.status,
        error: attachment.error,
        remove: attachment.status !== "ingesting" ? () => onDelete(attachment.attachmentId) : undefined,
        prepareWikiShare:
          attachment.documentUid && attachment.status === "ready"
            ? async () => ({ document_id: attachment.documentUid! })
            : undefined,
        downloadUrl: attachment.documentUid
          ? `/control-plane/v1/spaces/${encodeURIComponent(spaceId)}/sessions/${encodeURIComponent(attachment.sessionId ?? sessionId)}/attachments/${encodeURIComponent(attachment.documentUid)}/content`
          : null,
        preview:
          attachment.documentUid && attachment.status === "ready"
            ? { documentUid: attachment.documentUid, sessionId: attachment.sessionId, fileName: attachment.name }
            : null,
      })),
    },
  ];
  const visibleSections = sections.filter((section) => section.items.length || section.error || section.loading);

  const contributors = capabilityUiPlugins.filter(
    (plugin) => capabilityIds.includes(plugin.id) && plugin.useConversationFiles,
  );
  const renderSection = (section: DrawerSection) => (
    <section
      className={styles.list}
      key={section.key}
      aria-label={section.title ?? t(`chatbot.sessionAttachments.${section.key}`)}
    >
      <h3 className={styles.heading}>{section.title ?? t(`chatbot.sessionAttachments.${section.key}`)}</h3>
      {!!section.error && (
        <div className={styles.error} role="alert">
          <p>{section.errorLabel ?? errorMessage(section.errorKey!, section.error)}</p>
          {section.retry && (
            <Button
              size="small"
              variant="outlined"
              color="secondary"
              disabled={section.loading}
              onClick={section.retry}
            >
              {t("common.retry")}
            </Button>
          )}
        </div>
      )}
      {section.loading && (
        <p className={styles.empty} role="status">
          {t("chatbot.sessionAttachments.loading")}
        </p>
      )}
      {!section.loading && !section.error && section.items.length === 0 && section.emptyLabel && (
        <p className={styles.empty}>{section.emptyLabel}</p>
      )}
      <DataTable
        data={section.items}
        size="small"
        selectable
        rowKey={(file) => `${section.key}:${file.id}`}
        selectedKeys={new Set(Object.keys(selected).filter((key) => key.startsWith(`${section.key}:`)))}
        onSelectionChange={(keys) =>
          setSelected((previous) => ({
            ...Object.fromEntries(Object.entries(previous).filter(([key]) => !key.startsWith(`${section.key}:`))),
            ...Object.fromEntries(
              section.items
                .filter((file) => keys.has(`${section.key}:${file.id}`))
                .map((file) => [`${section.key}:${file.id}`, file]),
            ),
          }))
        }
        columns={[
          {
            label: t("rework.resources.columns.name"),
            size: "minmax(0, 1fr)",
            sortable: true,
            sortValue: (file) => file.name,
            cellRenderer: (file) => {
              const key = `${section.key}:${file.id}`;
              const spec = fileIconSpec(file.name, file.mime ?? "");
              const modified = file.modified ? new Date(file.modified).toLocaleString() : undefined;
              const options: OptionModel<string>[] = file.prepareWikiShare
                ? [
                    {
                      key: "publish",
                      value: "publish",
                      label: t("chatbot.sessionAttachments.share.action"),
                      icon: { category: "outlined", type: "upload" },
                    },
                  ]
                : [];
              if (file.downloadUrl)
                options.push({
                  key: "download",
                  value: "download",
                  label: t("chatbot.sessionAttachments.download"),
                  icon: { category: "outlined", type: "download" },
                  disabled: downloading[key],
                });
              if (file.remove && !readOnly)
                options.push({
                  key: "delete",
                  value: "delete",
                  label: t("rework.resources.action.delete"),
                  icon: { category: "outlined", type: "delete" },
                  destructive: true,
                });
              return (
                <div className={styles.file} key={key}>
                  <div className={styles.row}>
                    <span className={styles.fileIcon} style={{ color: spec.color }}>
                      <Icon category="outlined" type={spec.type} filled={spec.filled} />
                    </span>
                    <Tooltip content={[file.name, modified].filter(Boolean).join(" · ")} asChild>
                      <span className={styles.name} tabIndex={0}>
                        {file.name}
                        {file.modified && (
                          <time className={styles.modified} dateTime={file.modified}>
                            {modified}
                          </time>
                        )}
                      </span>
                    </Tooltip>
                    {file.size != null && <span className={styles.size}>{formatBytes(file.size)}</span>}
                    {file.actions}
                    {file.preview && (
                      <IconButton
                        size="small"
                        variant="icon"
                        color="on-surface-retreat"
                        icon={{ category: "outlined", type: "visibility" }}
                        title={t("chatbot.sessionAttachments.preview")}
                        onClick={() => setPreview({ ...file.preview!, key })}
                      />
                    )}
                    {options.length > 0 && (
                      <IconButtonMenu
                        iconButton={{
                          size: "small",
                          variant: "icon",
                          color: "on-surface-retreat",
                          icon: { category: "outlined", type: "more_vert" },
                          "aria-label": `${t("rework.resources.action.more")}: ${file.name}`,
                          loading: downloading[key],
                        }}
                        options={options}
                        onSelect={(action) => {
                          if (action === "publish") share({ [key]: file });
                          if (action === "download" && file.downloadUrl)
                            void download(key, file.downloadUrl, file.name);
                          if (action === "delete" && file.remove && !readOnly)
                            setDeleteTarget({ sessionId, key, file });
                        }}
                      />
                    )}
                  </div>
                  {(file.status === "uploading" || file.status === "ingesting") && (
                    <p className={styles.empty} role="status">
                      {t(
                        file.status === "uploading"
                          ? "chatbot.attachmentChip.uploading"
                          : "chatbot.attachmentChip.processing",
                      )}
                    </p>
                  )}
                  {file.status === "error" && (
                    <p className={styles.error} role="alert">
                      {t("chatbot.sessionAttachments.preparationError")}
                      {file.error && t(`chatbot.attachments.errors.${file.error}`, { defaultValue: "" })}
                    </p>
                  )}
                  {["preview", "download", "delete"].map(
                    (action) =>
                      errors[`${key}:${action}`] && (
                        <p key={action} className={styles.error} role="alert">
                          {errors[`${key}:${action}`]}
                        </p>
                      ),
                  )}
                </div>
              );
            },
          },
        ]}
      />
    </section>
  );

  return (
    <>
      <ChatSidePanel
        open={open}
        onClose={onClose}
        title={t("chatbot.sessionAttachments.title")}
        persistKey="session-attachments-panel"
      >
        {Object.keys(selected).length > 0 && (
          <div className={styles.toolbar}>
            <span>{t("chatbot.sessionAttachments.share.selection", { count: Object.keys(selected).length })}</span>
            <Button
              color="primary"
              variant="text"
              size="small"
              icon={{ category: "outlined", type: "upload" }}
              disabled={Object.values(selected).some((file) => !file.prepareWikiShare)}
              onClick={() => share(selected)}
            >
              {t("chatbot.sessionAttachments.share.action")}
            </Button>
            <IconButton
              variant="icon"
              size="small"
              icon={{ category: "outlined", type: "close" }}
              aria-label={t("chatbot.documentScopePanel.clearSelection")}
              onClick={() => setSelected({})}
            />
          </div>
        )}
        {Object.values(selected).some((file) => !file.prepareWikiShare) && (
          <p className={styles.empty}>{t("chatbot.sessionAttachments.share.notReady")}</p>
        )}
        {visibleSections.length === 0 && contributors.length === 0 && (
          <p className={styles.empty}>{t("chatbot.sessionAttachments.empty")}</p>
        )}
        {contributors.map((plugin) => (
          <CapabilityFiles
            key={`${plugin.id}:${sessionId}`}
            sessionId={sessionId}
            useFiles={plugin.useConversationFiles!}
            id={plugin.id}
            onCount={reportCount}
            render={(section) => renderSection({ ...section, key: plugin.id })}
          />
        ))}
        {visibleSections.map(renderSection)}
      </ChatSidePanel>
      <ConfirmationDialog
        open={deleteTarget?.sessionId === sessionId}
        title={t("chatbot.sessionAttachments.deleteTitle")}
        message={t("chatbot.sessionAttachments.deleteMessage", { name: deleteTarget?.file.name ?? "" })}
        details={
          deleteTarget && errors[`${deleteTarget.key}:delete`] ? (
            <p role="alert" className={styles.error}>
              {errors[`${deleteTarget.key}:delete`]}
            </p>
          ) : undefined
        }
        confirmLabel={t("rework.resources.action.delete")}
        cancelLabel={t("common.cancel")}
        criticalAction
        confirmDisabled={deleting || readOnly}
        dismissible={!deleting}
        onConfirm={() => void remove()}
        onCancel={() => {
          if (!deleting) setDeleteTarget(null);
        }}
      />
      {sharing?.sessionId === sessionId && (
        <ConversationFilesWikiDialog
          key={sessionId}
          sessionId={sessionId}
          spaceId={spaceId}
          spaceName={spaceName}
          wikiUrl={wikiUrl}
          files={sharing.files}
          onClose={() => setSharing(null)}
        />
      )}
      {preview && (
        <DocumentPreviewDrawer
          key={preview.key}
          target={preview}
          onClose={() => setPreview(null)}
          onError={(error) =>
            setErrors((previous) => ({ ...previous, [`${preview.key}:preview`]: errorMessage("previewError", error) }))
          }
          onLoaded={() => setErrors((previous) => ({ ...previous, [`${preview.key}:preview`]: "" }))}
        />
      )}
    </>
  );
}
