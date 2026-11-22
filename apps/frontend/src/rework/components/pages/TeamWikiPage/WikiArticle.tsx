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

import { Fragment, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import { DocumentViewer } from "@shared/organisms/DocumentViewer/DocumentViewer";
import DataTable from "@shared/molecules/DataTable/LocalizedDataTable";
import IconButtonMenu from "@shared/molecules/IconButtonMenu/IconButtonMenu";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { MarkdownRenderer } from "@shared/molecules/MarkdownRenderer/MarkdownRenderer";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { downloadAuthed } from "../../../../utils/downloadUtils";
import type { WikiPageDetail, WikiPageSummary } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  useLazyWikiPageQuery,
  useListAgentInstancesQuery,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { fileIconSpec } from "@rework/utils/fileIconSpec";
import { ancestorsOf } from "@rework/features/teamWiki/wikiTree";
import { formatDateTime } from "@rework/utils/formatDateTime";
import { formatBytes } from "@shared/utils/formatBytes";
import { EntityIdentity } from "@shared/molecules/EntityIdentity/EntityIdentity";
import UserAvatar from "@shared/atoms/UserAvatar/UserAvatar";
import { resolveAgentIcon } from "@shared/utils/agentIcon";
import { useFrontendProperties } from "../../../../hooks/useFrontendProperties";
import styles from "./WikiArticle.module.css";

interface WikiArticleProps {
  spaceId: string;
  detail: WikiPageDetail;
  pages: readonly WikiPageSummary[];
  canEdit: boolean;
  isRules: boolean;
  onEdit: () => void;
  onDelete: (file: WikiPageSummary) => void;
  onOpenHistory: () => void;
  onNavigate: (slug: string) => void;
  /** The wiki's own root — the breadcrumb's first crumb. */
  onNavigateRoot: () => void;
}

/**
 * One wiki page, rendered.
 *
 * Reading and downloading remain available to members; mutation controls are
 * editor-only. The server remains the authority for every action.
 */
export function WikiArticle({
  spaceId,
  detail,
  pages,
  canEdit,
  isRules,
  onEdit,
  onDelete,
  onOpenHistory,
  onNavigate,
  onNavigateRoot,
}: WikiArticleProps) {
  const { t } = useTranslation();
  const { showError } = useToast();
  const { page } = detail;
  const isFile = page.kind === "file";
  const { agentIconName } = useFrontendProperties();
  const { currentData: agents } = useListAgentInstancesQuery(
    { spaceId },
    {
      skip: !spaceId || ![page, ...pages].some((entry) => entry.agent_instance_id),
    },
  );
  const authorIdentity = (entry: WikiPageSummary) => {
    const isAgent = !!entry.agent_instance_id;
    const name = (isAgent ? entry.agent_name : entry.author_name) || t("rework.wiki.files.unknownAuthor");
    const agent = isAgent
      ? agents?.items.find((candidate) => candidate.agent_instance_id === entry.agent_instance_id)
      : undefined;
    const hint = [
      name,
      isAgent ? t("rework.wiki.article.writtenByAgent") : null,
      entry.updated_by_name ? t("rework.wiki.article.lastEditedBy", { user: entry.updated_by_name }) : null,
    ]
      .filter(Boolean)
      .join(" · ");
    return (
      <EntityIdentity
        name={name}
        hint={hint}
        icon={isAgent ? resolveAgentIcon(agent ?? { display_name: "", role: "" }, agentIconName) : undefined}
        visual={
          !isAgent ? (
            <UserAvatar
              name={name}
              size="x-small"
              subject={entry.author_user_id ? { spaceId, userId: entry.author_user_id } : undefined}
            />
          ) : undefined
        }
      />
    );
  };
  const [readFile] = useLazyWikiPageQuery();
  const [downloading, setDownloading] = useState<Record<string, boolean>>({});
  const [previewFailed, setPreviewFailed] = useState(false);
  const [previewAttempt, setPreviewAttempt] = useState(0);
  const fileUrl = (revision: string) =>
    `/control-plane/v1/spaces/${encodeURIComponent(spaceId)}/wiki/revisions/${encodeURIComponent(revision)}/content`;
  const files = pages.filter((child) => child.kind === "file" && child.parent_page_id === page.page_id);
  const previewable = detail.has_preview || page.mime === "application/pdf" || page.mime?.startsWith("text/");
  const download = async (file: WikiPageSummary) => {
    setDownloading((previous) => ({ ...previous, [file.page_id]: true }));
    try {
      const current = file.page_id === page.page_id ? detail : await readFile({ spaceId, pageId: file.slug }).unwrap();
      if (!current.revision_id) throw new Error("No published file");
      await downloadAuthed(fileUrl(current.revision_id), current.page.title);
    } catch {
      showError({ summary: t("chatbot.artifactLinks.downloadFailed", { name: file.title }) });
    } finally {
      setDownloading((previous) => ({ ...previous, [file.page_id]: false }));
    }
  };
  const fileActions = (file: WikiPageSummary) => (
    <div className={styles.tools}>
      {!isFile && (
        <IconButton
          variant="icon"
          size="small"
          icon={{ category: "outlined", type: "visibility" }}
          title={t("chatbot.sessionAttachments.preview")}
          aria-label={`${t("chatbot.sessionAttachments.preview")}: ${file.title}`}
          onClick={() => onNavigate(file.slug)}
        />
      )}
      <IconButton
        variant="icon"
        size="small"
        icon={{ category: "outlined", type: "download" }}
        title={t("documentLibrary.download")}
        aria-label={`${t("documentLibrary.download")}: ${file.title}`}
        loading={downloading[file.page_id]}
        disabled={file.page_id === page.page_id && !detail.revision_id}
        onClick={() => void download(file)}
      />
      {canEdit && (
        <IconButtonMenu
          iconButton={{
            variant: "icon",
            size: "small",
            icon: { category: "outlined", type: "more_vert" },
            title: t("rework.resources.action.more"),
            "aria-label": `${t("rework.resources.action.more")}: ${file.title}`,
          }}
          options={[
            {
              key: "delete",
              value: "delete",
              label: t("rework.resources.action.delete"),
              icon: { category: "outlined", type: "delete" },
              destructive: true,
            },
          ]}
          onSelect={() => onDelete(file)}
        />
      )}
    </div>
  );
  const pageTitle = isRules ? t("rework.wiki.rules.title") : page.title;

  // Led by the wiki itself and closed by the page being read, so a root page
  // still says where it sits and the way back up is in the same place on every
  // page. The last crumb carries no link — it is where you already are.
  const trail: { key: string; label: string; go?: () => void }[] = [
    { key: "__root__", label: t("rework.wiki.title"), go: onNavigateRoot },
    ...(isRules ? [] : ancestorsOf(pages, page.slug)).map((ancestor) => ({
      key: ancestor.page_id,
      label: ancestor.title,
      go: () => onNavigate(ancestor.slug),
    })),
    { key: page.page_id || "__current__", label: pageTitle },
  ];
  const isEmpty = detail.content_md.trim().length === 0;

  return (
    <article className={styles.article}>
      {/* Everything that names the page stays put; only its body scrolls. */}
      <header className={styles.header}>
        <div className={styles.topBar}>
          <nav className={styles.trail} aria-label={t("rework.wiki.article.breadcrumb")}>
            {trail.map((crumb, index) => (
              <Fragment key={crumb.key}>
                {index > 0 && (
                  <span className={styles.trailSeparator} aria-hidden="true">
                    /
                  </span>
                )}
                {crumb.go ? (
                  <button type="button" className={styles.trailLink} onClick={crumb.go}>
                    {crumb.label}
                  </button>
                ) : (
                  <span className={styles.trailCurrent} aria-current="page">
                    {crumb.label}
                  </span>
                )}
              </Fragment>
            ))}
          </nav>

          <div className={styles.actions}>
            {isFile && fileActions(page)}
            <div className={styles.tools}>
              {/* History is a read, and the endpoint is member-readable. Who wrote
                  what, and when, is exactly what a reader needs to judge a page
                  an agent may have touched — restore stays editor-only inside. */}
              {!isFile && (
                <IconButton
                  icon={{ category: "outlined", type: "history" }}
                  variant="icon"
                  size="small"
                  onClick={onOpenHistory}
                  disabled={!detail.revision_id}
                  aria-label={t("rework.wiki.article.history")}
                />
              )}
            </div>
            {canEdit && !isFile && (
              <Button color="primary" variant="filled" size="small" onClick={onEdit}>
                {t("rework.wiki.article.edit")}
              </Button>
            )}
          </div>
        </div>

        <div className={styles.titleBlock}>
          <h1 className={styles.title}>{pageTitle}</h1>

          {isRules && <p className={styles.rulesNotice}>{t("rework.wiki.rules.notice")}</p>}

          <div className={styles.meta}>
            {page.author_user_id && authorIdentity(page)}
            {page.updated_at && (
              <time dateTime={page.updated_at}>
                {t("rework.wiki.article.lastEditedAt", { when: formatDateTime(page.updated_at) })}
              </time>
            )}
          </div>
        </div>
      </header>

      <div className={styles.scroll}>
        {isFile ? (
          <>
            {previewFailed && (
              <div role="alert">
                <p>{t("chatbot.sessionAttachments.previewError")}</p>
                <Button
                  color="secondary"
                  variant="outlined"
                  size="small"
                  onClick={() => {
                    setPreviewFailed(false);
                    setPreviewAttempt((attempt) => attempt + 1);
                  }}
                >
                  {t("common.retry")}
                </Button>
              </div>
            )}
            {previewable && detail.revision_id ? (
              <div className={styles.preview}>
                <DocumentViewer
                  key={`${detail.revision_id}:${previewAttempt}`}
                  documentUid={detail.revision_id}
                  fileName={page.title}
                  sourceUrl={
                    detail.has_preview
                      ? fileUrl(detail.revision_id).replace(/\/content$/, "/preview")
                      : fileUrl(detail.revision_id)
                  }
                  sourceFormat={!detail.has_preview && page.mime?.startsWith("text/") ? "text" : undefined}
                  onError={() => setPreviewFailed(true)}
                />
              </div>
            ) : (
              <p className={styles.emptyBody}>{t("rework.wiki.files.noPreview")}</p>
            )}
          </>
        ) : isEmpty ? (
          <p className={styles.emptyBody}>{t(isRules ? "rework.wiki.rules.empty" : "rework.wiki.article.empty")}</p>
        ) : (
          <div className={styles.body}>
            <MarkdownRenderer text={detail.content_md} />
          </div>
        )}
        {!isFile && files.length > 0 && (
          <section className={styles.files} aria-labelledby="wiki-attached-files">
            <h2 id="wiki-attached-files" className={styles.filesHeading}>
              {t("rework.wiki.files.title", { count: files.length })}
            </h2>
            <DataTable
              data={files}
              size="small"
              rowKey={(file) => file.page_id}
              columns={[
                {
                  label: t("rework.resources.columns.name"),
                  size: "minmax(12rem, 2fr)",
                  sortable: true,
                  sortValue: (file) => file.title,
                  cellRenderer: (file) => {
                    const spec = fileIconSpec(file.title, file.mime ?? "");
                    return (
                      <Tooltip content={file.title} asChild>
                        <Button
                          color="on-surface"
                          variant="text"
                          size="small"
                          icon={{ category: "outlined", type: spec.type, filled: spec.filled }}
                          className={styles.fileLink}
                          onClick={() => onNavigate(file.slug)}
                        >
                          <span className={styles.fileName}>{file.title}</span>
                        </Button>
                      </Tooltip>
                    );
                  },
                },
                {
                  label: t("rework.wiki.files.author"),
                  size: "minmax(8rem, 1fr)",
                  sortable: true,
                  sortValue: (file) => file.agent_name ?? file.author_name ?? "",
                  cellRenderer: authorIdentity,
                },
                {
                  label: t("rework.wiki.files.modified"),
                  size: "10rem",
                  sortable: true,
                  sortValue: (file) => file.updated_at ?? "",
                  cellRenderer: (file) => <span className={styles.cellText}>{formatDateTime(file.updated_at)}</span>,
                },
                {
                  label: t("rework.resources.columns.size"),
                  size: "5rem",
                  sortable: true,
                  sortValue: (file) => file.size,
                  cellRenderer: (file) => (
                    <span className={styles.cellText}>{file.size == null ? "—" : formatBytes(file.size)}</span>
                  ),
                },
                {
                  label: "",
                  size: canEdit ? "8rem" : "6rem",
                  cellRenderer: fileActions,
                },
              ]}
            />
          </section>
        )}
      </div>
    </article>
  );
}
