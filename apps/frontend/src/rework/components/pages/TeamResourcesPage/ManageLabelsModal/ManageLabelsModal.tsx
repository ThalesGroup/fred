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

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import Chip from "@shared/atoms/Chip/Chip.tsx";
import Autocomplete from "@shared/molecules/Autocomplete/Autocomplete.tsx";
import { Portal } from "@shared/utils/Portal.tsx";
import type { OptionModel } from "@models/Option.model.ts";
import {
  useListDocumentLabelsQuery,
  type DocumentMetadata,
} from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import styles from "./ManageLabelsModal.module.css";

interface LabelPatch {
  add?: string[];
  remove?: string[];
}

interface ManageLabelsModalProps {
  open: boolean;
  onClose: () => void;
  doc: DocumentMetadata;
  /** Single canonical mutation, mirroring the backend's PATCH body — returns
   *  the full, canonical stored label set, or `undefined` on failure (already
   *  toasted by the caller). */
  onMutate: (patch: LabelPatch) => Promise<string[] | undefined>;
}

/**
 * Minimal descriptive-label management dialog: current labels as removable
 * chips, plus an add field with suggestions from the label vocabulary. Every
 * add/remove applies immediately (no Save/Cancel); the mutation's response is
 * always the source of truth for the chip list, never client-computed.
 *
 * The vocabulary query lives here, not in the parent, so it only runs while
 * this dialog is mounted, and is re-fetched (not patched) after every
 * mutation — a label can appear/disappear from it for reasons this dialog
 * can't compute locally (e.g. it was the last document carrying it). A
 * failed refetch only means the suggestion list may be stale; it never
 * reverts the mutation that already succeeded.
 *
 * Hand-rolls the Portal/overlay/dialog shell (same as the sibling
 * `RenameModal`) instead of the shared `Dialog` molecule: `Dialog` assumes a
 * confirm/cancel pair, but every action here already applies immediately —
 * see COMPONENT-UX.md for when reusing it would start paying off.
 */
export default function ManageLabelsModal({ open, onClose, doc, onMutate }: ManageLabelsModalProps) {
  const { t } = useTranslation();
  const [labels, setLabels] = useState<string[]>(doc.labels ?? []);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  // `busy` (state) drives the UI; it is not enough to serialize two
  // synchronous clicks in the same tick, which both read the same
  // not-yet-committed `busy`. The ref is mutated synchronously before any
  // `await`, so the second call sees it immediately.
  const busyRef = useRef(false);

  const { data: vocabulary, refetch: refetchVocabulary } = useListDocumentLabelsQuery();
  const suggestions = vocabulary ?? [];

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const trimmedQuery = query.trim();
  const applied = new Set(labels);
  const options: OptionModel<string>[] = suggestions
    .filter((label) => !applied.has(label))
    .filter((label) => !trimmedQuery || label.toLowerCase().includes(trimmedQuery.toLowerCase()))
    .map((label) => ({ value: label, key: label, label }));
  const isKnownLabel = suggestions.includes(trimmedQuery);

  const mutate = async (patch: LabelPatch) => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    try {
      const next = await onMutate(patch);
      if (next) {
        setLabels(next);
        if (patch.add) setQuery("");
        void refetchVocabulary().catch(() => {});
      }
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  const addLabel = (label: string) => {
    const trimmed = label.trim();
    if (!trimmed || applied.has(trimmed)) return;
    void mutate({ add: [trimmed] });
  };

  const removeLabel = (label: string) => void mutate({ remove: [label] });

  return (
    <Portal id="modal-portal">
      <div className={styles.overlay} onClick={onClose}>
        <div
          className={styles.dialog}
          role="dialog"
          aria-modal="true"
          aria-labelledby="manage-labels-title"
          onClick={(e) => e.stopPropagation()}
        >
          <div className={styles.body}>
            <div className={styles.header}>
              <p id="manage-labels-title" className={styles.title}>
                {t("rework.resources.labelsModal.title")}
              </p>
              <IconButton
                variant="icon"
                size="small"
                icon={{ category: "outlined", type: "close" }}
                aria-label={t("common.close")}
                onClick={onClose}
              />
            </div>

            <div className={styles.chips}>
              {labels.length === 0 ? (
                <p className={styles.empty}>{t("rework.resources.labelsModal.currentEmpty")}</p>
              ) : (
                labels.map((label) => (
                  <Chip
                    key={label}
                    label={label}
                    onRemove={busy ? undefined : () => removeLabel(label)}
                    removeAriaLabel={t("rework.resources.labelsModal.removeAriaLabel", { label })}
                  />
                ))
              )}
            </div>

            <div className={styles.addRow}>
              {/* Keyed on the label set so a successful mutation remounts the
                  field, clearing its internal text — Autocomplete owns that
                  state and exposes no external reset. Not remounted on
                  failure, so a failed attempt stays visible and retryable. */}
              <Autocomplete<string>
                key={labels.join(" ")}
                textInput={{
                  autoFocus: true,
                  "aria-label": t("rework.resources.labelsModal.addFieldLabel"),
                  placeholder: t("rework.resources.labelsModal.addPlaceholder"),
                }}
                options={options}
                onSelect={addLabel}
                onFieldValueChange={setQuery}
              />
              <Button
                color="primary"
                variant="filled"
                size="medium"
                disabled={!trimmedQuery || applied.has(trimmedQuery) || busy}
                onClick={() => addLabel(trimmedQuery)}
              >
                {t(isKnownLabel ? "rework.resources.labelsModal.add" : "rework.resources.labelsModal.createNew")}
              </Button>
            </div>
          </div>

          <div className={styles.actions}>
            <Button color="on-surface" variant="outlined" size="medium" onClick={onClose}>
              {t("rework.resources.labelsModal.close")}
            </Button>
          </div>
        </div>
      </div>
    </Portal>
  );
}
