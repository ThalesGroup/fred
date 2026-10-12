// Copyright Thales 2026
// Licensed under the Apache License, Version 2.0.

import { useTranslation } from "react-i18next";
import type { SkillDetail } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import ChatSidePanel from "@shared/molecules/ChatSidePanel/ChatSidePanel";
import { MarkdownRenderer } from "@shared/molecules/MarkdownRenderer/MarkdownRenderer";
import Button from "@shared/atoms/Button/Button";
import type { skillFileReadOf } from "@rework/utils/traceUtils";
import styles from "./SkillDetailPanel.module.css";

interface SkillDetailPanelProps {
  open: boolean;
  name: string;
  onClose: () => void;
  detail?: SkillDetail;
  file?: ReturnType<typeof skillFileReadOf>;
  loading: boolean;
  error: boolean;
  onRetry: () => void;
}

export default function SkillDetailPanel({
  open,
  name,
  onClose,
  detail,
  file,
  loading,
  error,
  onRetry,
}: SkillDetailPanelProps) {
  const { t } = useTranslation();
  const available = !error && detail?.skill.name === name;
  const instructions =
    detail?.content.replace(/^---[ \t]*\r?\n[\s\S]*?\r?\n(?:---|\.\.\.)[ \t]*(?:\r?\n|$)/, "").trim() ?? "";
  return (
    <ChatSidePanel
      open={open}
      onClose={onClose}
      title={
        file !== undefined
          ? t(file?.excerpt ? "chatbot.skills.fileExcerptTitle" : "chatbot.skills.fileTitle", {
              path: file?.path ?? "",
            })
          : t("chatbot.skills.panelTitle", { name })
      }
      titleSize="large"
      persistKey="skill-detail-panel"
    >
      {open && (
        <div className={styles.preview}>
          {file !== undefined ? (
            file ? (
              <>
                <p className={styles.description}>{t("chatbot.skills.panelTitle", { name: file.name })}</p>
                {!file.excerpt && /\.(md|markdown)$/i.test(file.path) ? (
                  <MarkdownRenderer text={file.content} fullWidth localLinksAsText />
                ) : (
                  <pre className={styles.fileText}>{file.content}</pre>
                )}
              </>
            ) : (
              <p role="status">{t("chatbot.skills.unavailable")}</p>
            )
          ) : loading ? (
            <p role="status">{t("chatbot.skills.loading")}</p>
          ) : available && detail ? (
            <>
              {detail.skill.argument_hint && (
                <p className={styles.arguments}>
                  <span className={styles.metadataLabel}>{t("chatbot.skills.arguments")}</span>{" "}
                  <code>{detail.skill.argument_hint}</code>
                </p>
              )}
              <p className={styles.description}>
                <span className={styles.metadataLabel}>{t("chatbot.skills.description")}</span>{" "}
                <em>{detail.skill.description}</em>
              </p>
              <div className={styles.instructions}>
                <MarkdownRenderer text={instructions} fullWidth localLinksAsText />
              </div>
            </>
          ) : (
            <div role="status" className={styles.error}>
              <p>{t("chatbot.skills.unavailable")}</p>
              <Button type="button" variant="text" color="primary" size="small" onClick={onRetry}>
                {t("chatbot.skills.retry")}
              </Button>
            </div>
          )}
        </div>
      )}
    </ChatSidePanel>
  );
}
