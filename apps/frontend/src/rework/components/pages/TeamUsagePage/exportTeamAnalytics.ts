// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import JSZip from "jszip";
import type { TFunction } from "i18next";
import type { AnalyticsResponse } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { dimension } from "./personalUsage";

const xml = (value: string) =>
  value
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, "")
    .replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;" })[c]!);

/** Aggregate snapshot only. Inline strings preserve exact integers/decimals and cannot become formulas. */
export async function teamAnalyticsWorkbook(
  spaceId: string,
  datasets: AnalyticsResponse[],
  t: TFunction,
): Promise<Blob> {
  const columns = [
    "space",
    "result",
    "since",
    "until",
    "timezone",
    "bucket",
    "dimension",
    "identity",
    "label",
    "measure",
    "unit",
    "calculation",
    "value",
    "coverage",
    "fallback",
    "truncated",
    "collection",
    "exclude_weekends",
    "exclude_holidays",
    "calendar_reference",
    "definition",
  ];
  const rows: string[][] = [columns.map((key) => t(`rework.teamAnalytics.exportColumns.${key}`))];
  for (const dataset of datasets)
    for (const [name, result] of Object.entries(dataset.results)) {
      // Preserve an empty result explicitly, without inventing a zero.
      const source = result.rows.length ? result.rows : [undefined];
      for (const row of source)
        for (const measure of result.measures) {
          const d = row ? dimension(row) : undefined;
          const estimate = row?.estimates?.[measure.id];
          rows.push([
            spaceId,
            name,
            result.since,
            result.until,
            result.timezone,
            result.bucket ?? "",
            row?.dimensions.kind ?? "",
            d?.id ?? "",
            d?.label ?? "",
            measure.id,
            measure.unit,
            measure.calculation,
            estimate ? (estimate.value ?? "") : (row?.values[measure.id] ?? ""),
            estimate?.coverage ?? "",
            estimate ? String(estimate.fallback) : "",
            String(result.truncated),
            dataset.collection_completeness,
            String(result.calendar?.exclude_weekends ?? false),
            String(result.calendar?.exclude_holidays ?? false),
            "FR national / UTC / L3133-1",
            t(`rework.teamAnalytics.metricHints.${measure.id}`, { defaultValue: "" }),
          ]);
        }
    }
  const ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
  const relationships = "http://schemas.openxmlformats.org/package/2006/relationships";
  const office = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
  const zip = new JSZip();
  zip.file(
    "[Content_Types].xml",
    `<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>`,
  );
  zip.file(
    "_rels/.rels",
    `<Relationships xmlns="${relationships}"><Relationship Id="rId1" Type="${office}/officeDocument" Target="xl/workbook.xml"/></Relationships>`,
  );
  zip.file(
    "xl/workbook.xml",
    `<workbook xmlns="${ns}" xmlns:r="${office}"><sheets><sheet name="${xml(t("rework.teamAnalytics.exportSheet"))}" sheetId="1" r:id="rId1"/></sheets></workbook>`,
  );
  zip.file(
    "xl/_rels/workbook.xml.rels",
    `<Relationships xmlns="${relationships}"><Relationship Id="rId1" Type="${office}/worksheet" Target="worksheets/sheet1.xml"/></Relationships>`,
  );
  zip.file(
    "xl/worksheets/sheet1.xml",
    `<worksheet xmlns="${ns}"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><sheetData>${rows.map((row, r) => `<row r="${r + 1}">${row.map((value, c) => `<c r="${String.fromCharCode(65 + c)}${r + 1}" t="inlineStr"><is><t xml:space="preserve">${xml(value)}</t></is></c>`).join("")}</row>`).join("")}</sheetData><autoFilter ref="A1:U${rows.length}"/></worksheet>`,
  );
  return zip.generateAsync({
    type: "blob",
    mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    compression: "DEFLATE",
  });
}
