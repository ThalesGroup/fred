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

import { useEffect, useId } from "react";
import { useDispatch, useSelector, useStore } from "react-redux";
import { useTranslation } from "react-i18next";
import { InlineDrawer } from "@shared/molecules/InlineDrawer/InlineDrawer";
import { SourceEditor } from "@shared/molecules/SourceEditor/SourceEditor";
import { Spinner } from "@shared/atoms/Spinner/Spinner";
import Button from "@shared/atoms/Button/Button";
import {
  openConversationFile,
  selectConversationFileSession,
  selectConversationFileRoute,
  setConversationFileRoute,
  type ConversationFileRootState,
} from "@rework/features/conversationFiles/conversationFileSlice";
import {
  conversationEditorsFor,
  registerConversationEditors,
  type ConversationEditors,
} from "@rework/features/conversationFiles/conversationEditors";
import { useConversationFileEditor } from "@rework/features/conversationFiles/useConversationFileEditor";
import styles from "./ConversationFilePanel.module.css";

interface ConversationFilePanelProps {
  sessionId: string;
  teamId: string;
  messagesUrl: string | null | undefined;
  open: boolean;
  onClose: () => void;
}
function FileContent({
  sessionId,
  teamId,
  path,
  coordinator,
  refreshRevision,
}: {
  sessionId: string;
  teamId: string;
  path: string;
  coordinator: ConversationEditors;
  refreshRevision: number;
}) {
  const { t } = useTranslation();
  const { draft, error, loading, refresh, change, flush } = useConversationFileEditor(
    coordinator,
    sessionId,
    teamId,
    path,
    refreshRevision,
  );
  if (loading && !draft)
    return (
      <div className={styles.status} role="status">
        <Spinner />
        {t("conversationFiles.loading")}
      </div>
    );
  let readError;
  if (error) {
    const status = typeof error === "object" && "status" in error ? error.status : undefined;
    const key =
      status === 403 || status === 401
        ? "denied"
        : status === 404
          ? "missing"
          : status === 415 || status === 422
            ? "unsupported"
            : "unavailable";
    readError = (
      <div className={styles.status} role="alert">
        {t(`conversationFiles.${key}`)}
        <Button type="button" color="primary" size="small" variant="text" onClick={refresh}>
          {t("conversationFiles.retry")}
        </Button>
      </div>
    );
  }
  if (!draft) return readError ?? null;
  return (
    <>
      {readError}
      <div className={styles.caption} role={draft.failed ? "alert" : "status"}>
        {t(
          `conversationFiles.${!draft.editable ? "readOnly" : draft.failed ? "saveFailed" : draft.saving ? "saving" : draft.content !== draft.savedContent ? "unsaved" : "saved"}`,
        )}
        {draft.failed && (
          <Button
            type="button"
            color="primary"
            size="small"
            variant="text"
            onClick={() => void flush().catch(() => undefined)}
          >
            {t("conversationFiles.retry")}
          </Button>
        )}
      </div>
      <SourceEditor
        value={draft.content}
        label={t("conversationFiles.source", { path })}
        readOnly={!draft.editable}
        onChange={change}
      />
    </>
  );
}
export function ConversationFilePanel({ sessionId, teamId, messagesUrl, open, onClose }: ConversationFilePanelProps) {
  const { t } = useTranslation();
  const dispatch = useDispatch();
  const panelId = useId();
  const store = useStore<ConversationFileRootState>();
  const coordinator = conversationEditorsFor(store);
  useEffect(() => registerConversationEditors(coordinator), [coordinator]);
  const session = useSelector((state: ConversationFileRootState) => selectConversationFileSession(state, sessionId));
  const routed = useSelector((state: ConversationFileRootState) => selectConversationFileRoute(state, sessionId));
  const suffix = `/agents/sessions/${encodeURIComponent(sessionId)}/messages`;
  const baseUrl = messagesUrl?.endsWith(suffix) ? messagesUrl.slice(0, -suffix.length) : null;
  useEffect(() => {
    dispatch(setConversationFileRoute({ sessionId, baseUrl }));
  }, [dispatch, sessionId, baseUrl]);
  const files = Object.values(session?.files ?? {});
  const selected = files.find((file) => file.path === session?.selectedPath) ?? files[files.length - 1];
  return (
    <InlineDrawer
      open={open}
      onClose={onClose}
      title={t("conversationFiles.title")}
      closeLabel={t("conversationFiles.close")}
      layout="push"
      floating
      resizable={{ persistKey: "capability-side-panel", resizeLabel: t("conversationFiles.resize") }}
    >
      {open && (
        <div className={styles.panel}>
          <div className={styles.tabs} role="tablist" aria-label={t("conversationFiles.files")}>
            {files.map((file, index) => (
              <button
                type="button"
                key={file.path}
                role="tab"
                id={`${panelId}-tab-${index}`}
                aria-controls={panelId}
                tabIndex={selected?.path === file.path ? 0 : -1}
                aria-selected={selected?.path === file.path}
                onKeyDown={(event) => {
                  const nextIndex =
                    event.key === "ArrowRight"
                      ? (index + 1) % files.length
                      : event.key === "ArrowLeft"
                        ? (index + files.length - 1) % files.length
                        : event.key === "Home"
                          ? 0
                          : event.key === "End"
                            ? files.length - 1
                            : null;
                  if (nextIndex === null) return;
                  event.preventDefault();
                  dispatch(openConversationFile(files[nextIndex]));
                  document.getElementById(`${panelId}-tab-${nextIndex}`)?.focus();
                }}
                className={styles.tab}
                onClick={() => dispatch(openConversationFile(file))}
              >
                {file.path}
              </button>
            ))}
          </div>
          <div
            className={styles.content}
            id={panelId}
            role="tabpanel"
            aria-labelledby={
              selected ? `${panelId}-tab-${files.findIndex((file) => file.path === selected.path)}` : undefined
            }
            aria-label={selected ? undefined : t("conversationFiles.title")}
          >
            {messagesUrl === undefined ? (
              <div role="status">{t("conversationFiles.loading")}</div>
            ) : !baseUrl ? (
              <div className={styles.status} role="alert">
                {t("conversationFiles.unavailable")}
              </div>
            ) : selected && routed === baseUrl ? (
              <FileContent
                key={JSON.stringify([sessionId, teamId, selected.path, session?.revision])}
                coordinator={coordinator}
                refreshRevision={session?.refreshRevision ?? 0}
                sessionId={sessionId}
                teamId={teamId}
                path={selected.path}
              />
            ) : (
              <div role="status">{t("conversationFiles.loading")}</div>
            )}
          </div>
        </div>
      )}
    </InlineDrawer>
  );
}
