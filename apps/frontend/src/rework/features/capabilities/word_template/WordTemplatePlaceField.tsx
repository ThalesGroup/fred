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

// One editable place of the "Rédaction" view, saved on blur (Escape cancels):
// `set_text` is one text field, `replace_text` edits the text around a field
// (page number, date) and never the field, `write` is a Markdown text area.
// Native <textarea>s: the TextInput/TextArea atoms are too heavy for table cells.

import { useMemo, useState, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import type { Place } from "./api/wordTemplateCapabilityOpenApi";
import {
  cellWriteOperation,
  inlineEditable,
  isEditablePiece,
  replaceTextOperations,
  setTextOperation,
  type InlineEditMode,
} from "./contentView";
import type { ApplyOperations } from "./WordTemplateBlocks";
import { usePlaceDraft } from "./usePlaceDraft";
import styles from "./WordTemplatePlaceField.module.css";

export type PlaceFieldVariant = "field" | "cell" | "heading";

interface PlaceFieldProps {
  place: Place;
  apply: ApplyOperations;
  variant: PlaceFieldVariant;
  label?: string;
  disabled?: boolean;
}

export function WordTemplatePlaceField({ place, apply, variant, label, disabled }: PlaceFieldProps) {
  if (place.edit === "replace_text") {
    return <PiecesField place={place} apply={apply} variant={variant} label={label} disabled={disabled} />;
  }
  if (place.edit === "set_text" || place.edit === "write") {
    return <TextField place={place} apply={apply} variant={variant} label={label} disabled={disabled} />;
  }
  return (
    <div className={styles.field} data-variant={variant}>
      {label && <span className={styles.label}>{label}</span>}
      <span className={styles.readOnly}>{place.text || " "}</span>
    </div>
  );
}

function rowsFor(value: string, variant: PlaceFieldVariant): number {
  const lines = value.split("\n").length;
  return Math.min(variant === "cell" ? 8 : 12, Math.max(1, lines));
}

function TextField({ place, apply, variant, label, disabled }: PlaceFieldProps) {
  const { t } = useTranslation();
  const isWrite = place.edit === "write";
  const editable = useMemo(
    () => (isWrite ? { mode: "markdown" as InlineEditMode, value: place.markdown ?? "" } : inlineEditable(place)),
    [isWrite, place],
  );
  const [focused, setFocused] = useState(false);
  const draft = usePlaceDraft(editable.value, (value) =>
    apply([isWrite ? cellWriteOperation(place.address, value) : setTextOperation(place.address, value, editable.mode)]),
  );

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Escape") {
      draft.cancel();
      e.currentTarget.blur();
    }
  };

  return (
    <div className={styles.field} data-variant={variant}>
      {label && <span className={styles.label}>{label}</span>}
      <textarea
        className={styles.input}
        data-variant={variant}
        value={draft.value}
        rows={rowsFor(draft.value, variant)}
        disabled={disabled}
        aria-label={label ?? t("capability.word_template.editor.placeAria")}
        onChange={(e) => draft.onType(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => {
          setFocused(false);
          void draft.commit();
        }}
        onKeyDown={onKeyDown}
      />
      <DraftNotes dirty={draft.dirty && !focused} remoteChange={draft.remoteChange} onCancel={draft.cancel} />
    </div>
  );
}

function PiecesField({ place, apply, variant, label, disabled }: PlaceFieldProps) {
  const pieces = place.pieces ?? [];
  return (
    <div className={styles.field} data-variant={variant}>
      {label && <span className={styles.label}>{label}</span>}
      <div className={styles.pieces}>
        {pieces.map((piece, index) =>
          isEditablePiece(piece) ? (
            <PieceInput key={index} place={place} index={index} apply={apply} disabled={disabled} label={label} />
          ) : (
            <span key={index} className={piece.field ? styles.fieldPiece : styles.readOnly}>
              {piece.text}
            </span>
          ),
        )}
      </div>
    </div>
  );
}

function PieceInput({
  place,
  index,
  apply,
  disabled,
  label,
}: {
  place: Place;
  index: number;
  apply: ApplyOperations;
  disabled?: boolean;
  label?: string;
}) {
  const { t } = useTranslation();
  const serverValue = place.pieces?.[index]?.text ?? "";
  const [focused, setFocused] = useState(false);
  const draft = usePlaceDraft(serverValue, (value) => apply(replaceTextOperations(place, { [index]: value })));
  return (
    <span className={styles.piece}>
      <input
        className={styles.input}
        data-variant="field"
        value={draft.value}
        size={Math.max(4, draft.value.length)}
        disabled={disabled}
        aria-label={label ?? t("capability.word_template.editor.placeAria")}
        onChange={(e) => draft.onType(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => {
          setFocused(false);
          void draft.commit();
        }}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            draft.cancel();
            e.currentTarget.blur();
          } else if (e.key === "Enter") {
            e.currentTarget.blur();
          }
        }}
      />
      <DraftNotes dirty={draft.dirty && !focused} remoteChange={draft.remoteChange} onCancel={draft.cancel} />
    </span>
  );
}

/** The two small notices of a draft: not saved yet, and "the AI changed this place too". */
export function DraftNotes({
  dirty,
  remoteChange,
  onCancel,
}: {
  dirty: boolean;
  remoteChange: boolean;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  if (!dirty && !remoteChange) return null;
  return (
    <span className={styles.notes}>
      {remoteChange && <span className={styles.remote}>{t("capability.word_template.editor.remoteChange")}</span>}
      {dirty && <span className={styles.unsaved}>{t("capability.word_template.editor.unsaved")}</span>}
      {/* No focus change: blurring the field would save the draft before the cancel. */}
      <button type="button" className={styles.linkButton} onMouseDown={(e) => e.preventDefault()} onClick={onCancel}>
        {remoteChange
          ? t("capability.word_template.editor.takeTheirs")
          : t("capability.word_template.editor.discardDraft")}
      </button>
    </span>
  );
}
