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

// The pattern review: a confirmation surface, not a form. One card per pattern
// (thumbnail, label, kind, include switch); every change is an override written
// to the config. One react-pdf <Document> feeds every card's <Page>.

import { useLayoutEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Document, Page, pdfjs } from "react-pdf";
import Icon from "@shared/atoms/Icon/Icon";
import { Spinner } from "@shared/atoms/Spinner/Spinner.tsx";
import Switch from "@shared/atoms/Switch/Switch";
import TextInput from "@shared/atoms/TextInput/TextInput";
import { Dialog } from "@shared/molecules/Dialog/Dialog.tsx";
import Select from "@shared/molecules/Select/Select.tsx";
import type { OptionModel } from "@models/Option.model.ts";
import type { Pattern, TemplateInventory } from "./api/pptBuilderCapabilityOpenApi";
import { usePatternsPreview, type PreviewSource } from "./usePatternsPreview";
import { SLIDE_KINDS, type OverridePatch, type SlideKind } from "./types";
import styles from "./PatternReviewDialog.module.css";

// A plain workerSrc (a fresh worker per load) is enough here: this dialog never
// shares a page with the chat preview pane, which provisions its own port.
const pdfWorkerUrl = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url);

interface Props {
  open: boolean;
  inventory: TemplateInventory;
  previewSource: PreviewSource;
  /** The built-in template (and a disabled form) is shown but not editable. */
  readOnly: boolean;
  onOverride: (patternId: string, patch: OverridePatch) => void;
  onClose: () => void;
}

export function PatternReviewDialog({ open, inventory, previewSource, readOnly, onOverride, onClose }: Props) {
  const { t } = useTranslation();
  const { objectUrl, isLoading, error } = usePatternsPreview(open ? previewSource : null);
  // A PDF that fetched but does not parse is as unavailable as a failed fetch.
  const [parseFailed, setParseFailed] = useState(false);

  useMemo(() => {
    pdfjs.GlobalWorkerOptions.workerPort = null;
    pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerUrl.toString();
  }, []);

  const patterns = inventory.patterns ?? [];
  const pageOf = useMemo(() => new Map(patterns.map((p, index) => [p.id, index + 1])), [patterns]);
  const kindOptions: OptionModel<SlideKind>[] = SLIDE_KINDS.map((kind) => ({
    value: kind,
    key: kind,
    label: t(`capability.ppt_builder.kinds.${kind}`),
  }));
  const hasPdf = Boolean(objectUrl) && !parseFailed;

  // Toggling include moves the card to another section, which remounts it: put
  // focus back on its switch there, unfolding that section if it is folded.
  const bodyRef = useRef<HTMLDivElement>(null);
  const pendingFocus = useRef<{ id: string; included: boolean } | null>(null);
  useLayoutEffect(() => {
    const target = pendingFocus.current;
    const card = target && bodyRef.current?.querySelector<HTMLElement>(`[data-pattern-id="${CSS.escape(target.id)}"]`);
    if (!target || !card || card.hasAttribute("data-excluded") === target.included) return;
    pendingFocus.current = null;
    const section = card.closest("details");
    if (section) section.open = true;
    card.querySelector<HTMLInputElement>('input[type="checkbox"]')?.focus();
  });
  const handleOverride: Props["onOverride"] = (patternId, patch) => {
    if (patch.included !== undefined) pendingFocus.current = { id: patternId, included: patch.included };
    onOverride(patternId, patch);
  };

  // Layouts come after the deck's own slides: the builder uses them only when no slide fits.
  const slides = patterns.filter((p) => p.included !== false && p.source === "slide");
  const layouts = patterns.filter((p) => p.included !== false && p.source === "layout");
  const excluded = patterns.filter((p) => p.included === false);
  const card = (pattern: Pattern) => (
    <PatternCard
      key={pattern.id}
      pattern={pattern}
      page={pageOf.get(pattern.id) ?? 1}
      hasPdf={hasPdf}
      readOnly={readOnly}
      kindOptions={kindOptions}
      onOverride={handleOverride}
    />
  );

  const body = (
    <div className={styles.body} ref={bodyRef}>
      {slides.length > 0 && (
        <section className={styles.section} data-section="slides">
          <h3 className={styles.sectionTitle}>{t("capability.ppt_builder.review.slides", { count: slides.length })}</h3>
          <div className={styles.grid}>{slides.map(card)}</div>
        </section>
      )}
      {layouts.length > 0 && (
        <details className={styles.section} data-section="layouts">
          <summary className={styles.sectionTitle}>
            {t("capability.ppt_builder.review.layouts", { count: layouts.length })}
          </summary>
          <p className={styles.sectionHint}>{t("capability.ppt_builder.review.layoutsHint")}</p>
          <div className={styles.grid}>{layouts.map(card)}</div>
        </details>
      )}
      {excluded.length > 0 && (
        <details className={styles.section} data-section="excluded">
          <summary className={styles.sectionTitle}>
            {t("capability.ppt_builder.review.excluded", { count: excluded.length })}
          </summary>
          <div className={styles.grid}>{excluded.map(card)}</div>
        </details>
      )}
      {isLoading && (
        <p className={styles.hint}>
          <Spinner size={16} /> {t("capability.ppt_builder.review.loadingThumbnails")}
        </p>
      )}
      {(error || parseFailed || !previewSource) && (
        <p className={styles.hint}>{t("capability.ppt_builder.review.thumbnailsUnavailable")}</p>
      )}
    </div>
  );

  return (
    <Dialog
      open={open}
      title={t("capability.ppt_builder.review.title")}
      confirmLabel={t("capability.ppt_builder.review.done")}
      onConfirm={onClose}
      onCancel={onClose}
      hideCancel
      maxWidth={1040}
    >
      {objectUrl ? (
        <Document file={objectUrl} loading={null} error={null} onLoadError={() => setParseFailed(true)}>
          {body}
        </Document>
      ) : (
        body
      )}
    </Dialog>
  );
}

interface CardProps {
  pattern: Pattern;
  page: number;
  hasPdf: boolean;
  readOnly: boolean;
  kindOptions: OptionModel<SlideKind>[];
  onOverride: Props["onOverride"];
}

export function PatternCard({ pattern, page, hasPdf, readOnly, kindOptions, onOverride }: CardProps) {
  const { t } = useTranslation();
  const isIncluded = pattern.included !== false;
  // Committed on every change, so a close by Enter or Escape keeps it. The draft
  // is local: an emptied field falls back to the analysis label without snapping.
  const [labelDraft, setLabelDraft] = useState(pattern.label);
  // The page is rendered at the thumbnail box's own width, so it fills it at any grid size.
  const thumbnailRef = useRef<HTMLDivElement>(null);
  const [pageWidth, setPageWidth] = useState(0);
  useLayoutEffect(() => {
    const element = thumbnailRef.current;
    if (!element) return;
    const measure = () => setPageWidth(Math.floor(element.clientWidth));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return (
    <article className={styles.card} data-pattern-id={pattern.id} data-excluded={!isIncluded || undefined}>
      <div className={styles.thumbnail} ref={thumbnailRef}>
        {hasPdf && pageWidth > 0 ? (
          <Page
            pageNumber={page}
            width={pageWidth}
            renderTextLayer={false}
            renderAnnotationLayer={false}
            loading={null}
          />
        ) : (
          <div className={styles.thumbnailPlaceholder}>
            <Icon category="outlined" type="slideshow" />
          </div>
        )}
      </div>
      <div className={styles.cardBody}>
        <div className={styles.cardHeader}>
          <TextInput
            size="xs"
            compact
            value={labelDraft}
            disabled={readOnly}
            aria-label={t("capability.ppt_builder.review.labelFor", { label: pattern.label })}
            onChange={(event) => {
              setLabelDraft(event.target.value);
              const label = event.target.value.trim();
              if (label !== pattern.label) onOverride(pattern.id, { label: label || null });
            }}
          />
          <Switch
            size="small"
            checked={isIncluded}
            disabled={readOnly}
            aria-label={t("capability.ppt_builder.review.include", { label: pattern.label })}
            onChange={(event) => onOverride(pattern.id, { included: event.target.checked })}
          />
        </div>
        <Select
          size="xs"
          compact
          options={kindOptions}
          value={pattern.kind}
          disabled={readOnly}
          ariaLabel={t("capability.ppt_builder.review.kindFor", { label: pattern.label })}
          onChange={(kind) => onOverride(pattern.id, { kind })}
        />
        <div className={styles.cardMeta}>
          <span className={styles.muted}>
            {t(`capability.ppt_builder.review.source.${pattern.source}`, {
              index: pattern.source_index + (pattern.source === "layout" ? 1 : 0),
            })}
          </span>
          {pattern.labelled_by === "heuristic" && pattern.source === "slide" && (
            <span className={styles.muted}>{t("capability.ppt_builder.review.labelledByRules")}</span>
          )}
          {pattern.exclusion_reason && (
            <span className={styles.muted}>
              {t(`capability.ppt_builder.review.exclusion.${pattern.exclusion_reason}`)}
            </span>
          )}
        </div>
      </div>
    </article>
  );
}
