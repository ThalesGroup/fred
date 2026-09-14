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

// The pattern review: a confirmation surface, not a form. The grid shows every
// pattern the analysis found (thumbnail, label, intent, zones, include switch),
// a card opens the detail (large thumbnail with the numbered zone outlines and
// a role per zone). Every change is an override written to the config; the
// author never has to touch anything for the agent to work.
//
// One react-pdf <Document> wraps the whole dialog so every card's <Page>
// renders from the same loaded PDF (one page per pattern, inventory order).

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Document, Page, pdfjs } from "react-pdf";
import Chip from "@shared/atoms/Chip/Chip.tsx";
import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { Spinner } from "@shared/atoms/Spinner/Spinner.tsx";
import Switch from "@shared/atoms/Switch/Switch";
import TextInput from "@shared/atoms/TextInput/TextInput";
import { Dialog } from "@shared/molecules/Dialog/Dialog.tsx";
import Select from "@shared/molecules/Select/Select.tsx";
import type { OptionModel } from "@models/Option.model.ts";
import type { Pattern, TemplateInventory, Zone } from "./api/pptBuilderCapabilityOpenApi";
import { usePatternsPreview, type PreviewSource } from "./usePatternsPreview";
import { INTENTS, ZONE_ROLES, allZones, type Intent, type PatternOverride, type ZoneRole } from "./types";
import styles from "./PatternReviewDialog.module.css";

const CARD_WIDTH = 220;
const DETAIL_WIDTH = 640;

// pdf.js worker for this dialog's <Document>. The chat preview pane provisions
// its own port per mount; the two never share a page, so a plain workerSrc
// (a fresh worker per load) is enough here, and the port is released in case
// a previous pane left a terminated one behind.
const pdfWorkerUrl = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url);

interface Props {
  open: boolean;
  inventory: TemplateInventory;
  previewSource: PreviewSource;
  /** The built-in theme (and a disabled form) is shown but not editable. */
  readOnly: boolean;
  onOverride: (patternId: string, patch: Partial<Omit<PatternOverride, "pattern_id">>) => void;
  onClose: () => void;
}

export function PatternReviewDialog({ open, inventory, previewSource, readOnly, onOverride, onClose }: Props) {
  const { t } = useTranslation();
  const { objectUrl, isLoading, error } = usePatternsPreview(open ? previewSource : null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // A PDF that fetched but does not parse is as unavailable as a failed fetch.
  const [parseFailed, setParseFailed] = useState(false);

  useMemo(() => {
    pdfjs.GlobalWorkerOptions.workerPort = null;
    pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerUrl.toString();
  }, []);

  const pageOf = useMemo(() => new Map(inventory.patterns.map((p, index) => [p.id, index + 1])), [inventory]);
  const selected = selectedId ? (inventory.patterns.find((p) => p.id === selectedId) ?? null) : null;

  const intentOptions: OptionModel<Intent>[] = INTENTS.map((intent) => ({
    value: intent,
    key: intent,
    label: t(`capability.ppt_builder.intents.${intent}`),
  }));
  const roleOptions: OptionModel<ZoneRole>[] = ZONE_ROLES.map((role) => ({
    value: role,
    key: role,
    label: t(`capability.ppt_builder.roles.${role}`),
  }));

  const body = (
    <div className={styles.body}>
      {selected ? (
        <PatternDetail
          pattern={selected}
          page={pageOf.get(selected.id) ?? 1}
          hasPdf={Boolean(objectUrl) && !parseFailed}
          readOnly={readOnly}
          roleOptions={roleOptions}
          intentOptions={intentOptions}
          onOverride={onOverride}
          onBack={() => setSelectedId(null)}
        />
      ) : (
        <PatternGrid
          inventory={inventory}
          pageOf={pageOf}
          hasPdf={Boolean(objectUrl) && !parseFailed}
          readOnly={readOnly}
          intentOptions={intentOptions}
          onOverride={onOverride}
          onOpen={setSelectedId}
        />
      )}
      {isLoading && (
        <p className={styles.hint}>
          <Spinner size={16} /> {t("capability.ppt_builder.review.loadingThumbnails")}
        </p>
      )}
      {(error || parseFailed) && (
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

// --- grid ------------------------------------------------------------------------

interface GridProps {
  inventory: TemplateInventory;
  pageOf: Map<string, number>;
  hasPdf: boolean;
  readOnly: boolean;
  intentOptions: OptionModel<Intent>[];
  onOverride: Props["onOverride"];
  onOpen: (id: string) => void;
}

function PatternGrid({ inventory, pageOf, hasPdf, readOnly, intentOptions, onOverride, onOpen }: GridProps) {
  const { t } = useTranslation();
  const included = inventory.patterns.filter((p) => p.included);
  const excluded = inventory.patterns.filter((p) => !p.included);
  const card = (pattern: Pattern) => (
    <PatternCard
      key={pattern.id}
      pattern={pattern}
      page={pageOf.get(pattern.id) ?? 1}
      hasPdf={hasPdf}
      readOnly={readOnly}
      intentOptions={intentOptions}
      onOverride={onOverride}
      onOpen={() => onOpen(pattern.id)}
    />
  );
  return (
    <>
      <div className={styles.grid}>{included.map(card)}</div>
      {excluded.length > 0 && (
        <details className={styles.excluded}>
          <summary className={styles.excludedSummary}>
            {t("capability.ppt_builder.review.excluded", { count: excluded.length })}
          </summary>
          <div className={styles.grid}>{excluded.map(card)}</div>
        </details>
      )}
    </>
  );
}

interface CardProps {
  pattern: Pattern;
  page: number;
  hasPdf: boolean;
  readOnly: boolean;
  intentOptions: OptionModel<Intent>[];
  onOverride: Props["onOverride"];
  onOpen: () => void;
}

function zoneChips(pattern: Pattern): string[] {
  const counts = new Map<string, number>();
  pattern.zones.forEach((zone) => counts.set(zone.role, (counts.get(zone.role) ?? 0) + 1));
  const chips = [...counts.entries()].map(([role, n]) => (n > 1 ? `${role} ×${n}` : role));
  pattern.groups.forEach((group) => chips.push(`${group.count} × [${group.item_zones.join(", ")}]`));
  return chips;
}

export function PatternCard({ pattern, page, hasPdf, readOnly, intentOptions, onOverride, onOpen }: CardProps) {
  const { t } = useTranslation();
  const chips = zoneChips(pattern);
  return (
    <article className={styles.card} data-excluded={!pattern.included || undefined}>
      <button type="button" className={styles.thumbnailButton} onClick={onOpen} aria-label={pattern.label}>
        <PatternThumbnail pattern={pattern} page={page} hasPdf={hasPdf} width={CARD_WIDTH} outlines={false} />
      </button>
      <div className={styles.cardBody}>
        <div className={styles.cardHeader}>
          <span className={styles.cardLabel} title={pattern.label}>
            {pattern.label}
          </span>
          <Switch
            checked={pattern.included}
            disabled={readOnly}
            aria-label={t("capability.ppt_builder.review.include", { label: pattern.label })}
            onChange={(event) => onOverride(pattern.id, { included: event.target.checked })}
          />
        </div>
        <Select
          size="xs"
          compact
          options={intentOptions}
          value={pattern.intent}
          disabled={readOnly}
          ariaLabel={t("capability.ppt_builder.review.intentFor", { label: pattern.label })}
          onChange={(intent) => onOverride(pattern.id, { intent })}
        />
        <div className={styles.chips}>
          {chips.length === 0 ? (
            <span className={styles.muted}>{t("capability.ppt_builder.review.noZone")}</span>
          ) : (
            chips.map((chip) => <Chip key={chip} label={chip} />)
          )}
        </div>
        <div className={styles.cardMeta}>
          <span className={styles.muted}>
            {t(`capability.ppt_builder.review.source.${pattern.source}`, {
              index: pattern.source_index + (pattern.source === "layout" ? 1 : 0),
            })}
          </span>
          {pattern.preferred && (
            <span className={styles.preferred}>{t("capability.ppt_builder.review.preferred")}</span>
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

// --- detail ------------------------------------------------------------------------

interface DetailProps {
  pattern: Pattern;
  page: number;
  hasPdf: boolean;
  readOnly: boolean;
  roleOptions: OptionModel<ZoneRole>[];
  intentOptions: OptionModel<Intent>[];
  onOverride: Props["onOverride"];
  onBack: () => void;
}

export function PatternDetail({
  pattern,
  page,
  hasPdf,
  readOnly,
  roleOptions,
  intentOptions,
  onOverride,
  onBack,
}: DetailProps) {
  const { t } = useTranslation();
  const zones = allZones(pattern);
  return (
    <div className={styles.detail}>
      <div className={styles.detailHeader}>
        <IconButton
          variant="icon"
          size="small"
          color="on-surface-retreat"
          icon={{ category: "outlined", type: "arrow_back" }}
          aria-label={t("capability.ppt_builder.review.back")}
          onClick={onBack}
        />
        <TextInput
          size="xs"
          value={pattern.label}
          disabled={readOnly}
          aria-label={t("capability.ppt_builder.review.labelField")}
          onChange={(event) => onOverride(pattern.id, { label: event.target.value })}
        />
        <Select
          size="xs"
          compact
          options={intentOptions}
          value={pattern.intent}
          disabled={readOnly}
          ariaLabel={t("capability.ppt_builder.review.intentFor", { label: pattern.label })}
          onChange={(intent) => onOverride(pattern.id, { intent })}
        />
      </div>
      <div className={styles.detailBody}>
        <PatternThumbnail pattern={pattern} page={page} hasPdf={hasPdf} width={DETAIL_WIDTH} outlines />
        <ol className={styles.zoneList}>
          {zones.map(({ zone, item }, index) => (
            <li key={`${zone.key}-${index}`} className={styles.zoneRow}>
              <span className={styles.zoneIndex}>{index + 1}</span>
              <span className={styles.zoneSample} title={zone.sample}>
                {item !== null && (
                  <span className={styles.muted}>
                    {t("capability.ppt_builder.review.item", { index: item + 1 })} ·{" "}
                  </span>
                )}
                {zone.sample || t("capability.ppt_builder.review.emptyZone")}
              </span>
              <Select
                size="xs"
                compact
                options={roleOptions}
                value={zone.role}
                disabled={readOnly}
                ariaLabel={t("capability.ppt_builder.review.roleFor", { index: index + 1 })}
                onChange={(role) => onOverride(pattern.id, { zone_roles: { [zone.key]: role } })}
              />
            </li>
          ))}
          {zones.length === 0 && <li className={styles.muted}>{t("capability.ppt_builder.review.noZone")}</li>}
        </ol>
      </div>
    </div>
  );
}

// --- thumbnail ----------------------------------------------------------------------

interface ThumbnailProps {
  pattern: Pattern;
  page: number;
  hasPdf: boolean;
  width: number;
  outlines: boolean;
}

export function PatternThumbnail({ pattern, page, hasPdf, width, outlines }: ThumbnailProps) {
  const zones = allZones(pattern);
  return (
    <div className={styles.thumbnail} style={{ width, aspectRatio: "16 / 9" }}>
      {hasPdf ? (
        <Page pageNumber={page} width={width} renderTextLayer={false} renderAnnotationLayer={false} loading={null} />
      ) : (
        <div className={styles.thumbnailPlaceholder}>
          <Icon category="outlined" type="slideshow" />
        </div>
      )}
      {outlines &&
        zones.map(({ zone }, index) => (
          <span
            key={`${zone.key}-${index}`}
            className={styles.outline}
            data-role={zone.role}
            style={{
              left: `${zone.box.x / 10}%`,
              top: `${zone.box.y / 10}%`,
              width: `${zone.box.w / 10}%`,
              height: `${zone.box.h / 10}%`,
            }}
          >
            <span className={styles.outlineIndex}>{index + 1}</span>
          </span>
        ))}
    </div>
  );
}

export { zoneChips, type Zone };
