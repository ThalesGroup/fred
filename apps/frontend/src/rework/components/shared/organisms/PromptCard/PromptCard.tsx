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

import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { type PromptSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { useTranslation } from "react-i18next";
import styles from "./PromptCard.module.scss";

export interface PromptCardProps {
  prompt: PromptSummary;
  canManage: boolean;
  onEdit: () => void;
}

export default function PromptCard({ prompt, canManage, onEdit }: PromptCardProps) {
  const { t } = useTranslation();
  const body = prompt.description && prompt.description !== prompt.name ? prompt.description : null;
  const preview = !body && prompt.text_preview ? prompt.text_preview : null;

  return (
    <div
      className={styles.card}
      onClick={onEdit}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && onEdit()}
    >
      {/* ── Edit overlay (hover only, personal prompts only) ── */}
      {canManage && (
        <div className={styles.editOverlay}>
          <IconButton
            size="small"
            color="on-surface"
            variant="icon"
            icon={{ category: "outlined", type: "edit" }}
            onClick={(e) => {
              e.stopPropagation();
              onEdit();
            }}
          />
        </div>
      )}

      {/* ── Header: name ── */}
      <div className={styles.header}>
        <span className={styles.name}>{prompt.name}</span>
      </div>

      {/* ── Body ── */}
      {(body || preview) && (
        <div className={styles.body}>
          {body && <p className={styles.description}>{body}</p>}
          {preview && <p className={styles.preview}>"{preview}"</p>}
        </div>
      )}

      {/* ── Footer: usage count ── */}
      <div className={styles.footer}>
        <span className={styles.uses}>{t("rework.teams.prompts.card.uses", { count: prompt.session_count ?? 0 })}</span>
      </div>
    </div>
  );
}
