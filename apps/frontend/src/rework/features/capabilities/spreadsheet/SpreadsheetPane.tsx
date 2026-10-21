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

// Read-only preview of a spreadsheet the agent created: sheet tabs, a table with
// a sticky header row and first column, locale-formatted numbers and the totals
// row. Data comes from the JSON preview stored beside the `.xlsx`.

import { useState } from "react";
import { useTranslation } from "react-i18next";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup";
import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { Spinner } from "@shared/atoms/Spinner/Spinner";
import type { CapabilitySidePanelProps } from "../types";
import SpreadsheetDownloadButton from "./SpreadsheetDownloadButton";
import { formatCell, formatTotal, isRightAligned } from "./spreadsheetFormat";
import type { SpreadsheetPreview, SpreadsheetSheet } from "./types";
import { useSessionSpreadsheet, useSpreadsheetPreview } from "./useSpreadsheetPreview";
import styles from "./SpreadsheetPane.module.css";

function SheetTable({ sheet, locale }: { sheet: SpreadsheetSheet; locale: string }) {
  const { t } = useTranslation();
  const cellClass = (index: number) => (isRightAligned(sheet.columns[index]) ? styles.number : undefined);
  const hidden = sheet.row_count - sheet.rows.length;

  return (
    <>
      <div className={styles.tableScroll}>
        <table className={styles.table}>
          <thead>
            <tr>
              {sheet.columns.map((column, index) => (
                <th key={index} scope="col" className={cellClass(index)}>
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sheet.rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((value, index) => (
                  <td key={index} className={cellClass(index)}>
                    {formatCell(value, sheet.columns[index], locale)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
          {sheet.totals && (
            <tfoot>
              <tr className={styles.totals}>
                {sheet.totals.map((value, index) => (
                  <td key={index} className={cellClass(index)}>
                    {formatTotal(value, sheet.columns[index], locale)}
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
    </>
  );
}

function SpreadsheetView({ preview, locale }: { preview: SpreadsheetPreview; locale: string }) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState(0);
  const sheet = preview.sheets[selected] ?? preview.sheets[0];

  return (
    <>
      {preview.sheets.length > 1 && (
        <div className={styles.tabs}>
          <ButtonGroup
            variant="tabs"
            size="small"
            color="secondary"
            aria-label={t("capability.spreadsheet.sheets")}
            items={preview.sheets.map((s) => ({ label: s.name }))}
            selectedIndex={selected}
            onSelectedIndexChange={setSelected}
          />
        </div>
      )}
      {sheet && <SheetTable sheet={sheet} locale={locale} />}
    </>
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
