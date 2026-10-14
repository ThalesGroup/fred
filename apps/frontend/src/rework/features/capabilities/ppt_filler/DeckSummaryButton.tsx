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

// "What was built": the tool's own per-slide record of a ppt_builder deck,
// worded for non-technical users. Only decks carrying a summary show it.

import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import type { BuildNote, BuiltSlide } from "./types";
import styles from "./DeckSummaryButton.module.css";

const NOTES = "capability.ppt_builder.summary.notes";
const PLAIN_NOTES = new Set([
  "text_shortened",
  "content_left_out",
  "items_left_out",
  "image_unusable",
  "table_left_out",
  "table_text_smaller",
  "text_overflows",
  "left_empty",
  "fixed_slide",
]);

function kindLabel(t: TFunction, kind: string): string {
  return t(`capability.ppt_builder.kinds.${kind}`, { defaultValue: kind });
}

/** A code the UI does not know yet (newer backend) is skipped, never shown raw. */
function noteText(t: TFunction, note: BuildNote, slide: BuiltSlide): string | null {
  if (note.code === "list_continued") {
    return t(`${NOTES}.${slide.part < slide.parts ? "list_continues" : "list_continuation"}`);
  }
  if (note.code === "other_kind") {
    return t(`${NOTES}.other_kind`, { built: kindLabel(t, slide.kind), asked: kindLabel(t, note.kind ?? "") });
  }
  if (note.code === "chart_type_changed") {
    return t(`${NOTES}.chart_type_changed`, { asked: note.kind ?? "" });
  }
  if (!PLAIN_NOTES.has(note.code)) return null;
  return t(`${NOTES}.${note.code}`, note.count != null ? { count: note.count } : undefined);
}

export default function DeckSummaryButton({ summary }: { summary?: BuiltSlide[] | null }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  if (!summary?.length) return null;

  const label = t("capability.ppt_builder.summary.open");
  const close = () => setOpen(false);

  return (
    <>
      <Tooltip text={label}>
        <IconButton
          variant="icon"
          size="small"
          icon={{ category: "outlined", type: "info" }}
          onClick={() => setOpen(true)}
          aria-label={label}
          aria-haspopup="dialog"
        />
      </Tooltip>
      <Dialog
        open={open}
        title={t("capability.ppt_builder.summary.title")}
        confirmLabel={t("capability.ppt_builder.summary.close")}
        onConfirm={close}
        onCancel={close}
        hideCancel
        maxWidth={480}
      >
        <div className={styles.body}>
          <p className={styles.count}>{t("capability.ppt_builder.summary.count", { count: summary.length })}</p>
          <ol className={styles.slides}>
            {summary.map((slide, index) => {
              const notes = slide.notes
                .map((note) => noteText(t, note, slide))
                .filter((text): text is string => text !== null);
              return (
                <li key={index} className={styles.slide}>
                  <span className={styles.number}>{index + 1}</span>
                  <div className={styles.details}>
                    <span className={styles.title}>
                      {slide.title || slide.template || t("capability.ppt_builder.summary.untitled")}
                    </span>
                    <span className={styles.kind}>{kindLabel(t, slide.kind)}</span>
                    {notes.length > 0 && (
                      <ul className={styles.notes}>
                        {notes.map((text) => (
                          <li key={text}>{text}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        </div>
      </Dialog>
    </>
  );
}
