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

// Read-only, Excel-like preview of a spreadsheet the agent created: column
// letters and row numbers frozen around one scrolling grid, the workbook's own
// header as row 1, and sheet tabs at the bottom. Data is the JSON preview.

import { type KeyboardEvent, type MouseEvent, useEffect, useId, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { Spinner } from "@shared/atoms/Spinner/Spinner";
import type { CapabilitySidePanelProps } from "../types";
import SpreadsheetDownloadButton from "./SpreadsheetDownloadButton";
import { columnLayouts, columnLetter, formatCell, formatTotal, isRightAligned } from "./spreadsheetFormat";
import type { SpreadsheetPreview, SpreadsheetSheet } from "./types";
import { useSessionSpreadsheet, useSpreadsheetPreview } from "./useSpreadsheetPreview";
import styles from "./SpreadsheetPane.module.css";

interface CellAddress {
  /** Excel row number (1 is the header row). */
  row: number;
  column: number;
}

const cx = (...names: (string | false | undefined)[]) => names.filter(Boolean).join(" ") || undefined;

function SheetGrid({
  sheet,
  locale,
  panelId,
  tabId,
}: {
  sheet: SpreadsheetSheet;
  locale: string;
  panelId: string;
  tabId: string;
}) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<CellAddress>({ row: 1, column: 0 });
  const layouts = useMemo(() => columnLayouts(sheet, locale), [sheet, locale]);
  const totalsRow = sheet.row_count + 2;
  const lastRow = sheet.totals ? totalsRow : sheet.row_count + 1;
  const rowHeadWidth = Math.max(String(lastRow).length + 2, 4);
  const tableWidth = rowHeadWidth + layouts.reduce((sum, layout) => sum + layout.width, 0);

  const cellClass = (row: number, column: number) =>
    cx(
      isRightAligned(sheet.columns[column]) && styles.number,
      layouts[column]?.wrap && styles.wrap,
      selected.row === row && selected.column === column && styles.selected,
    );
  const rowHead = (row: number) => (
    <th scope="row" className={cx(styles.rowHead, selected.row === row && styles.headActive)}>
      {row}
    </th>
  );
  // One delegated handler: each cell carries its "row:column" address.
  const select = (event: MouseEvent<HTMLTableElement>) => {
    const cell = (event.target as HTMLElement).closest<HTMLElement>("[data-cell]");
    if (!cell?.dataset.cell) return;
    const [row, column] = cell.dataset.cell.split(":").map(Number);
    setSelected({ row, column });
  };
  const value =
    selected.row === 1
      ? sheet.columns[selected.column]?.header
      : selected.row === totalsRow && sheet.totals
        ? formatTotal(sheet.totals[selected.column], sheet.columns[selected.column], locale)
        : formatCell(sheet.rows[selected.row - 2]?.[selected.column] ?? null, sheet.columns[selected.column], locale);
  const hidden = sheet.row_count - sheet.rows.length;

  return (
    <div className={styles.sheet} id={panelId} role="tabpanel" aria-labelledby={tabId}>
      <div className={styles.formulaBar}>
        <output className={styles.nameBox} aria-label={t("capability.spreadsheet.selectedCell")}>
          {`${columnLetter(selected.column)}${selected.row}`}
        </output>
        <span className={styles.cellValue} title={value}>
          {value}
        </span>
      </div>
      <div className={styles.gridScroll}>
        <table className={styles.grid} style={{ width: `${tableWidth}ch` }} aria-label={sheet.name} onClick={select}>
          <colgroup>
            <col style={{ width: `${rowHeadWidth}ch` }} />
            {layouts.map((layout, index) => (
              <col key={index} style={{ width: `${layout.width}ch` }} />
            ))}
          </colgroup>
          <thead>
            <tr className={styles.letters} aria-hidden="true">
              <td className={styles.corner} />
              {sheet.columns.map((_, index) => (
                <td key={index} className={cx(styles.colHead, selected.column === index && styles.headActive)}>
                  {columnLetter(index)}
                </td>
              ))}
            </tr>
            <tr className={styles.headerRow}>
              {rowHead(1)}
              {sheet.columns.map((column, index) => (
                <th key={index} scope="col" data-cell={`1:${index}`} className={cellClass(1, index)}>
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sheet.rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {rowHead(rowIndex + 2)}
                {row.map((cell, index) => (
                  <td key={index} data-cell={`${rowIndex + 2}:${index}`} className={cellClass(rowIndex + 2, index)}>
                    {formatCell(cell, sheet.columns[index], locale)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
          {sheet.totals && (
            <tfoot>
              <tr className={styles.totals}>
                {rowHead(totalsRow)}
                {sheet.totals.map((cell, index) => (
                  <td key={index} data-cell={`${totalsRow}:${index}`} className={cellClass(totalsRow, index)}>
                    {formatTotal(cell, sheet.columns[index], locale)}
                  </td>
                ))}
              </tr>
            </tfoot>
          )}
        </table>
      </div>
      {hidden > 0 && (
        <p className={styles.note}>
          {t("capability.spreadsheet.moreRows", {
            count: hidden,
            formatted: new Intl.NumberFormat(locale).format(hidden),
          })}
        </p>
      )}
    </div>
  );
}

interface SheetTabsProps {
  names: string[];
  selected: number;
  onSelect: (index: number) => void;
  tabId: (index: number) => string;
  panelId: string;
}

/** Excel-style tab strip: never wraps; arrows scroll it when the tabs overflow. */
function SheetTabs({ names, selected, onSelect, tabId, panelId }: SheetTabsProps) {
  const { t } = useTranslation();
  const listRef = useRef<HTMLDivElement>(null);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const [edges, setEdges] = useState({ atStart: true, atEnd: true });

  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const update = () =>
      setEdges({
        atStart: list.scrollLeft <= 0,
        atEnd: list.scrollLeft + list.clientWidth >= list.scrollWidth - 1,
      });
    update();
    list.addEventListener("scroll", update, { passive: true });
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update);
    observer?.observe(list);
    return () => {
      list.removeEventListener("scroll", update);
      observer?.disconnect();
    };
  }, [names.length]);

  // Scroll the strip only (not its ancestors, as scrollIntoView would) to reveal the active tab.
  useEffect(() => {
    const list = listRef.current;
    const tab = tabRefs.current[selected];
    if (!list || !tab) return;
    if (tab.offsetLeft < list.scrollLeft) list.scrollLeft = tab.offsetLeft;
    else if (tab.offsetLeft + tab.offsetWidth > list.scrollLeft + list.clientWidth) {
      list.scrollLeft = tab.offsetLeft + tab.offsetWidth - list.clientWidth;
    }
  }, [selected]);

  const scroll = (direction: -1 | 1) => {
    const list = listRef.current;
    list?.scrollBy({ left: direction * Math.max(list.clientWidth / 2, 60), behavior: "smooth" });
  };
  const focusTab = (index: number) => {
    onSelect(index);
    tabRefs.current[index]?.focus();
  };
  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const last = names.length - 1;
    const next = {
      ArrowRight: index === last ? 0 : index + 1,
      ArrowLeft: index === 0 ? last : index - 1,
      Home: 0,
      End: last,
    }[event.key];
    if (next === undefined) return;
    event.preventDefault();
    focusTab(next);
  };
  const overflowing = !(edges.atStart && edges.atEnd);

  return (
    <div className={styles.tabStrip}>
      {overflowing && (
        <div className={styles.tabArrows}>
          <IconButton
            variant="icon"
            size="2xs"
            icon={{ category: "outlined", type: "chevron_left" }}
            aria-label={t("capability.spreadsheet.previousSheets")}
            disabled={edges.atStart}
            onClick={() => scroll(-1)}
          />
          <IconButton
            variant="icon"
            size="2xs"
            icon={{ category: "outlined", type: "chevron_right" }}
            aria-label={t("capability.spreadsheet.nextSheets")}
            disabled={edges.atEnd}
            onClick={() => scroll(1)}
          />
        </div>
      )}
      <div ref={listRef} className={styles.tabList} role="tablist" aria-label={t("capability.spreadsheet.sheets")}>
        {names.map((name, index) => (
          <button
            key={index}
            ref={(el) => {
              tabRefs.current[index] = el;
            }}
            type="button"
            role="tab"
            id={tabId(index)}
            aria-selected={index === selected}
            aria-controls={panelId}
            tabIndex={index === selected ? 0 : -1}
            className={cx(styles.tab, index === selected && styles.tabActive)}
            onClick={() => onSelect(index)}
            onKeyDown={(event) => onKeyDown(event, index)}
          >
            {name}
          </button>
        ))}
      </div>
    </div>
  );
}

function SpreadsheetView({ preview, locale }: { preview: SpreadsheetPreview; locale: string }) {
  const [selected, setSelected] = useState(0);
  const baseId = useId();
  const index = preview.sheets[selected] ? selected : 0;
  const sheet = preview.sheets[index];
  const tabId = (i: number) => `${baseId}-tab-${i}`;
  const panelId = `${baseId}-panel`;

  return (
    <div className={styles.view}>
      {sheet && <SheetGrid key={index} sheet={sheet} locale={locale} panelId={panelId} tabId={tabId(index)} />}
      <SheetTabs
        names={preview.sheets.map((s) => s.name)}
        selected={index}
        onSelect={setSelected}
        tabId={tabId}
        panelId={panelId}
      />
    </div>
  );
}

export function SpreadsheetPane({ onClose }: CapabilitySidePanelProps) {
  const { t, i18n } = useTranslation();
  const current = useSessionSpreadsheet();
  const load = useSpreadsheetPreview(current?.preview_url);
  const locale = i18n.language || "en";

  return (
    <div className={styles.pane}>
      <div className={styles.header}>
        <span className={styles.icon} aria-hidden>
          <Icon category="outlined" type="table_chart" />
        </span>
        <span className={styles.title} title={current?.title}>
          {current?.title ?? t("capability.spreadsheet.untitled")}
        </span>
        {current && (
          <SpreadsheetDownloadButton href={current.xlsx_download_url} fileName={current.file_name} labelled />
        )}
        <IconButton
          variant="icon"
          size="medium"
          icon={{ category: "outlined", type: "close" }}
          aria-label={t("capability.spreadsheet.close")}
          // Blur first: closing hides the drawer, which the browser blocks while
          // a descendant still holds focus.
          onClick={(e) => {
            e.currentTarget.blur();
            onClose();
          }}
        />
      </div>
      <div className={styles.body}>
        {!current && <p className={styles.state}>{t("capability.spreadsheet.empty")}</p>}
        {current && load.status === "loading" && (
          <div className={styles.state}>
            <Spinner />
          </div>
        )}
        {current && load.status === "error" && (
          <p className={styles.state} role="alert">
            {t("capability.spreadsheet.unavailable")}
          </p>
        )}
        {current && load.status === "ready" && (
          <SpreadsheetView key={current.preview_url} preview={load.preview} locale={locale} />
        )}
      </div>
    </div>
  );
}
