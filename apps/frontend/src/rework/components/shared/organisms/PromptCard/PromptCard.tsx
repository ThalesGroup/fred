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
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { type PromptSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { PROMPT_CATEGORY_MAP } from "../../../../config/promptCategories.ts";
import styles from "./PromptCard.module.scss";

export interface PromptCardProps {
  prompt: PromptSummary;
  /** Resolved display name for `prompt.created_by` (falls back to the raw uid upstream). */
  authorName?: string;
  canManage: boolean;
  onEdit: () => void;
}

const PALETTE_SIZE = 5;

function colorIndex(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) & 0xffff;
  return h % PALETTE_SIZE;
}

export default function PromptCard({ prompt, authorName, canManage, onEdit }: PromptCardProps) {
  const catDef = prompt.category ? PROMPT_CATEGORY_MAP[prompt.category] : null;
  const idx = colorIndex(prompt.id);
  const body = prompt.description && prompt.description !== prompt.name ? prompt.description : null;
  const preview = !body && prompt.text_preview ? prompt.text_preview : null;
  const isDefault = prompt.is_default === true;

  return (
    <div
      className={styles.card}
      data-default={isDefault || undefined}
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

      {/* ── Header: icon + name ── */}
      <div className={styles.header}>
        <div
          className={styles.icon}
          data-color={catDef || prompt.emoji ? undefined : idx}
          style={catDef ? { backgroundColor: catDef.pillBg, color: catDef.pillFg } : undefined}
        >
          {catDef ? (
            <Icon category="outlined" type={catDef.icon} />
          ) : prompt.emoji ? (
            <span className={styles.iconEmoji}>{prompt.emoji}</span>
          ) : (
            <Icon category="outlined" type="edit_note" />
          )}
        </div>
        <span className={styles.name}>{prompt.name}</span>
      </div>

      {/* ── Body ── */}
      {(body || preview) && (
        <div className={styles.body}>
          {body && <p className={styles.description}>{body}</p>}
          {preview && <p className={styles.preview}>"{preview}"</p>}
        </div>
      )}

      {/* ── Footer: uses left · author right ── */}
      <div className={styles.footer}>
        <span className={styles.uses}>▷ {prompt.session_count ?? 0}</span>
        <span className={styles.author}>{authorName ?? "—"}</span>
      </div>
    </div>
  );
}
