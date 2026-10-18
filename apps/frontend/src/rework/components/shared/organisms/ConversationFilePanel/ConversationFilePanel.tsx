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
import { useDispatch, useSelector } from "react-redux";
import { useTranslation } from "react-i18next";
import { InlineDrawer } from "@shared/molecules/InlineDrawer/InlineDrawer";
import { SourceEditor } from "@shared/molecules/SourceEditor/SourceEditor";
import { Spinner } from "@shared/atoms/Spinner/Spinner";
import Button from "@shared/atoms/Button/Button";
import { useReadConversationFileQuery } from "../../../../../slices/runtime/runtimeOpenApi";
import {
  openConversationFile,
  selectConversationFileSession,
  selectConversationFileRoute,
  setConversationFileRoute,
  type ConversationFileRootState,
} from "@rework/features/conversationFiles/conversationFileSlice";
import styles from "./ConversationFilePanel.module.css";

interface ConversationFilePanelProps {
  sessionId: string;
  teamId: string;
  messagesUrl: string | null | undefined;
  open: boolean;
  onClose: () => void;
}
function FileContent({ sessionId, teamId, path }: { sessionId: string; teamId: string; path: string }) {
  const { t } = useTranslation();
  const { currentData, error, isFetching, refetch } = useReadConversationFileQuery(
    { sessionId, teamId, path },
    { refetchOnMountOrArgChange: true },
  );
  if (isFetching)
    return (
      <div className={styles.status} role="status">
        <Spinner />
        {t("conversationFiles.loading")}
      </div>
    );
  if (error) {
    const status = "status" in error ? error.status : undefined;
    const key =
      status === 403 || status === 401
        ? "denied"
        : status === 404
          ? "missing"
          : status === 415 || status === 422
            ? "unsupported"
            : "unavailable";
    return (
      <div className={styles.status} role="alert">
        {t(`conversationFiles.${key}`)}
        <Button color="primary" size="small" variant="text" onClick={() => void refetch()}>
          {t("conversationFiles.retry")}
        </Button>
      </div>
    );
  }
  if (!currentData) return null;
  return (
    <>
      <div className={styles.caption}>{t("conversationFiles.readOnly")}</div>
      <SourceEditor value={currentData.content} label={t("conversationFiles.source", { path })} readOnly />
    </>
  );
}
export function ConversationFilePanel({ sessionId, teamId, messagesUrl, open, onClose }: ConversationFilePanelProps) {
  const { t } = useTranslation();
  const dispatch = useDispatch();
  const panelId = useId();
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
      layout="push"
      floating
      resizable={{ persistKey: "capability-side-panel" }}
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
                key={`${sessionId}:${selected.path}:${session?.revision}`}
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
