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

// The blocks of the "Rédaction" view, in reading order (content.py):
// chapters (heading + body segments), tables (cells edited inline), block
// groups (a repeatable set of blocks), heading-less paragraphs and the fields
// of headers / footers / text boxes. Every "Dupliquer" / "Retirer" sends the
// ready-made operation the view carries - no address is ever built here.

import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import IconButton from "@shared/atoms/IconButton/IconButton";
import type {
  BlockGroup,
  ChapterBlock,
  ContentOperation,
  ContentPart,
  FieldsBlock,
  ParagraphBlock,
  TableBlock,
} from "./api/wordTemplateCapabilityOpenApi";
import { storyOf, tableLayout } from "./contentView";
import { WordTemplatePlaceField } from "./WordTemplatePlaceField";
import { WordTemplateRichText } from "./WordTemplateRichText";
import styles from "./WordTemplateBlocks.module.css";

/** Send one batch made on the shown view; resolves true when applied. */
export type ApplyOperations = (operations: ContentOperation[]) => Promise<boolean>;

/** Ask for confirmation, then send a ready-made `remove`. */
export type ConfirmRemove = (operation: ContentOperation, message: string) => void;

interface BlockContext {
  apply: ApplyOperations;
  confirmRemove: ConfirmRemove;
  /** A batch is on its way: structural actions wait (fields stay editable). */
  busy: boolean;
}

type PartBlock = NonNullable<ContentPart["blocks"]>[number];
type GroupMember = NonNullable<BlockGroup["blocks"]>[number];

// Parts the engine names itself (in English): shown in the reader's language.
const PART_TITLE_KEYS: Record<string, string> = {
  "0": "capability.word_template.editor.beforeHeadings",
  hf: "capability.word_template.editor.headersFooters",
};

export function WordTemplateParts({ parts, ...ctx }: BlockContext & { parts: ContentPart[] }) {
  const { t } = useTranslation();
  return (
    <div className={styles.parts}>
      {parts.map((part) => (
        <section key={part.id} className={styles.part}>
          <h3 className={styles.partTitle}>{PART_TITLE_KEYS[part.id] ? t(PART_TITLE_KEYS[part.id]) : part.title}</h3>
          {(part.blocks ?? []).map((block) => (
            <PartBlockView key={blockKey(block)} block={block} {...ctx} />
          ))}
        </section>
      ))}
    </div>
  );
}

function blockKey(block: PartBlock | GroupMember): string {
  if (block.kind === "chapter" || block.kind === "block_group") return `${block.kind}:${block.from}`;
  return `${block.kind}:${block.address}`;
}

function PartBlockView({ block, ...ctx }: BlockContext & { block: PartBlock }) {
  switch (block.kind) {
    case "chapter":
      return <ChapterView chapter={block} {...ctx} />;
    case "block_group":
      return <BlockGroupView group={block} {...ctx} />;
    default:
      return <MemberView block={block} {...ctx} />;
  }
}

function MemberView({ block, ...ctx }: BlockContext & { block: GroupMember }) {
  switch (block.kind) {
    case "table":
      return <TableView table={block} {...ctx} />;
    case "fields":
      return <FieldsView block={block} {...ctx} />;
    default:
      return <ParagraphView paragraph={block} {...ctx} />;
  }
}

function ActionButton({
  kind,
  label,
  disabled,
  onClick,
}: {
  kind: "duplicate" | "remove";
  label: string;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <Button
      color={kind === "remove" ? "error" : "on-surface"}
      variant="text"
      size="2xs"
      icon={{ category: "outlined", type: kind === "remove" ? "delete" : "content_copy" }}
      disabled={disabled}
      onClick={onClick}
    >
      {label}
    </Button>
  );
}

function ChapterView({ chapter, apply, confirmRemove, busy }: BlockContext & { chapter: ChapterBlock }) {
  const { t } = useTranslation();
  const ctx = { apply, confirmRemove, busy };
  const title = chapter.heading.text?.trim() || t("capability.word_template.editor.untitledChapter");
  return (
    <article className={styles.chapter} data-level={Math.min(Math.max(chapter.level, 1), 4)}>
      <div className={styles.chapterHead}>
        <div className={styles.grow}>
          <WordTemplatePlaceField place={chapter.heading} apply={apply} variant="heading" />
        </div>
        {chapter.removable !== false && chapter.remove && (
          <ActionButton
            kind="remove"
            label={t("capability.word_template.editor.remove")}
            disabled={busy}
            onClick={() =>
              confirmRemove(chapter.remove, t("capability.word_template.editor.confirmRemoveChapter", { title }))
            }
          />
        )}
      </div>
      <div className={styles.body}>
        {(chapter.body ?? []).map((segment, index) =>
          segment.kind === "text" ? (
            <WordTemplateRichText key={`text:${segment.from ?? index}`} segment={segment} apply={apply} />
          ) : (
            <MemberView key={blockKey(segment)} block={segment} {...ctx} />
          ),
        )}
      </div>
    </article>
  );
}

function TableView({ table, apply, confirmRemove, busy }: BlockContext & { table: TableBlock }) {
  const { t } = useTranslation();
  const layout = tableLayout(table);
  const rows = table.rows ?? [];
  const hasRowActions = rows.some((row) => row.duplicate || row.remove);
  const canDuplicate = table.duplicable !== false && !!table.duplicate;
  const canRemove = table.removable !== false && !!table.remove;
  const what = table.repeat_label;
  return (
    <div className={styles.table}>
      {(canDuplicate || canRemove || what) && (
        <div className={styles.blockBar}>
          {what && <span className={styles.blockLabel}>{what}</span>}
          <span className={styles.grow} />
          {canDuplicate && table.duplicate && (
            <ActionButton
              kind="duplicate"
              label={t("capability.word_template.editor.duplicateTable")}
              disabled={busy}
              onClick={() => void apply([table.duplicate as ContentOperation])}
            />
          )}
          {canRemove && table.remove && (
            <ActionButton
              kind="remove"
              label={t("capability.word_template.editor.remove")}
              disabled={busy}
              onClick={() =>
                confirmRemove(table.remove as ContentOperation, t("capability.word_template.editor.confirmRemoveTable"))
              }
            />
          )}
        </div>
      )}
      <div className={styles.tableScroll}>
        <table className={styles.grid}>
          <tbody>
            {rows.map((row, r) => (
              <tr key={row.address}>
                {(layout[r] ?? []).map((slot, s) =>
                  slot.kind === "gap" ? (
                    <td key={`gap:${s}`} colSpan={slot.span} className={styles.gap} />
                  ) : (
                    <td
                      key={slot.cell.address}
                      colSpan={slot.cell.col_span ?? 1}
                      rowSpan={slot.cell.row_span ?? 1}
                      className={styles.cell}
                    >
                      <WordTemplatePlaceField place={slot.cell} apply={apply} variant="cell" />
                    </td>
                  ),
                )}
                {hasRowActions && (
                  <td className={styles.rowActions}>
                    {row.duplicate && (
                      <IconButton
                        variant="icon"
                        size="2xs"
                        icon={{ category: "outlined", type: "content_copy" }}
                        disabled={busy}
                        aria-label={t("capability.word_template.editor.duplicateRow")}
                        title={t("capability.word_template.editor.duplicateRow")}
                        onClick={() => void apply([row.duplicate as ContentOperation])}
                      />
                    )}
                    {row.remove && (
                      <IconButton
                        variant="icon"
                        size="2xs"
                        icon={{ category: "outlined", type: "delete" }}
                        disabled={busy}
                        aria-label={t("capability.word_template.editor.removeRow")}
                        title={t("capability.word_template.editor.removeRow")}
                        onClick={() =>
                          confirmRemove(
                            row.remove as ContentOperation,
                            t("capability.word_template.editor.confirmRemoveRow"),
                          )
                        }
                      />
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {(table.row_groups ?? []).map((group) => (
        <div key={`${group.from}-${group.to}`} className={styles.blockBar}>
          <span className={styles.blockLabel}>
            {t("capability.word_template.editor.rowGroup", { label: group.label })}
          </span>
          <span className={styles.grow} />
          <ActionButton
            kind="duplicate"
            label={t("capability.word_template.editor.duplicateOne", { label: group.label })}
            disabled={busy}
            onClick={() => void apply([group.duplicate])}
          />
          <ActionButton
            kind="remove"
            label={t("capability.word_template.editor.remove")}
            disabled={busy}
            onClick={() =>
              confirmRemove(
                group.remove,
                t("capability.word_template.editor.confirmRemoveGroup", { label: group.label }),
              )
            }
          />
        </div>
      ))}
    </div>
  );
}

function BlockGroupView({ group, ...ctx }: BlockContext & { group: BlockGroup }) {
  const { t } = useTranslation();
  const { apply, confirmRemove, busy } = ctx;
  return (
    <div className={styles.group}>
      <div className={styles.blockBar}>
        <span className={styles.blockLabel}>{group.label}</span>
        <span className={styles.grow} />
        {group.duplicable !== false && (
          <ActionButton
            kind="duplicate"
            label={t("capability.word_template.editor.duplicateOne", { label: group.label })}
            disabled={busy}
            onClick={() => void apply([group.duplicate])}
          />
        )}
        {group.removable !== false && (
          <ActionButton
            kind="remove"
            label={t("capability.word_template.editor.remove")}
            disabled={busy}
            onClick={() =>
              confirmRemove(
                group.remove,
                t("capability.word_template.editor.confirmRemoveGroup", { label: group.label }),
              )
            }
          />
        )}
      </div>
      {(group.blocks ?? []).map((member) => (
        <MemberView key={blockKey(member)} block={member} {...ctx} />
      ))}
    </div>
  );
}

function ParagraphView({ paragraph, apply }: BlockContext & { paragraph: ParagraphBlock }) {
  return (
    <div className={styles.paragraph}>
      <WordTemplatePlaceField place={paragraph} apply={apply} variant="field" />
    </div>
  );
}

function FieldsView({ block, apply }: BlockContext & { block: FieldsBlock }) {
  const { t } = useTranslation();
  const story = storyOf(block.address);
  const name = t(`capability.word_template.editor.story.${story.kind}`);
  const label = story.variant ? `${name} (${t(`capability.word_template.editor.story.${story.variant}`)})` : name;
  const fields = block.fields ?? [];
  if (fields.length === 0) return null;
  return (
    <div className={styles.fields}>
      <span className={styles.blockLabel}>{label}</span>
      {fields.map((place) => (
        <WordTemplatePlaceField key={place.address} place={place} apply={apply} variant="field" />
      ))}
    </div>
  );
}
