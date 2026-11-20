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

import type { ChartPart } from "../../../slices/runtime/runtimeOpenApi";

type Row = ChartPart["rows"][number];

export function chartColumns(rows: Row[]): string[] {
  return [...new Set(rows.flatMap((row) => Object.keys(row)))];
}

function fileName(title: string, extension: "xlsx" | "png"): string {
  const stem = title
    .trim()
    .replace(/[^\p{L}\p{N}._-]+/gu, "-")
    .replace(/^\.+|\.+$/g, "")
    .slice(0, 80);
  return `${stem || "chart"}.${extension}`;
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function xmlText(value: string): string {
  return value
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function columnName(index: number): string {
  let name = "";
  for (let value = index + 1; value > 0; value = Math.floor((value - 1) / 26)) {
    name = String.fromCharCode(65 + ((value - 1) % 26)) + name;
  }
  return name;
}

function excelCell(value: Row[string], reference: string): string {
  if (value === null) return `<c r="${reference}"/>`;
  if (typeof value === "number") return `<c r="${reference}" t="n"><v>${value}</v></c>`;
  if (typeof value === "boolean") return `<c r="${reference}" t="b"><v>${value ? 1 : 0}</v></c>`;
  return `<c r="${reference}" t="inlineStr"><is><t xml:space="preserve">${xmlText(value)}</t></is></c>`;
}

export async function chartRowsXlsx(rows: Row[]): Promise<Blob> {
  const { default: JSZip } = await import("jszip");
  const columns = chartColumns(rows);
  const sheetRows = [columns, ...rows.map((row) => columns.map((column) => row[column] ?? null))];
  const sheetData = sheetRows
    .map(
      (values, rowIndex) =>
        `<row r="${rowIndex + 1}">${values.map((value, columnIndex) => excelCell(value, `${columnName(columnIndex)}${rowIndex + 1}`)).join("")}</row>`,
    )
    .join("");
  const zip = new JSZip();
  zip.file(
    "[Content_Types].xml",
    '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
  );
  zip.file(
    "_rels/.rels",
    '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
  );
  zip.file(
    "xl/workbook.xml",
    '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Chart data" sheetId="1" r:id="rId1"/></sheets></workbook>',
  );
  zip.file(
    "xl/_rels/workbook.xml.rels",
    '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
  );
  zip.file(
    "xl/worksheets/sheet1.xml",
    `<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>${sheetData}</sheetData></worksheet>`,
  );
  return zip.generateAsync({
    type: "blob",
    mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
}

export async function downloadChartExcel(rows: Row[], title: string): Promise<void> {
  downloadBlob(await chartRowsXlsx(rows), fileName(title, "xlsx"));
}

export function serializeChartSvg(svg: SVGSVGElement): { markup: string; width: number; height: number } {
  const width = svg.getBoundingClientRect().width || Number(svg.getAttribute("width"));
  const height = svg.getBoundingClientRect().height || Number(svg.getAttribute("height"));
  if (
    !Number.isFinite(width) ||
    !Number.isFinite(height) ||
    width <= 0 ||
    height <= 0 ||
    width > 4096 ||
    height > 4096
  ) {
    throw new Error("Chart dimensions are unavailable");
  }

  const clone = svg.cloneNode(true) as SVGSVGElement;
  const sourceNodes = [svg, ...svg.querySelectorAll<SVGElement>("*")];
  const cloneNodes = [clone, ...clone.querySelectorAll<SVGElement>("*")];
  sourceNodes.forEach((source, index) => {
    const target = cloneNodes[index];
    const style = getComputedStyle(source);
    for (const property of ["fill", "stroke", "color", "font-family", "font-size", "font-weight", "opacity"]) {
      target.style.setProperty(property, style.getPropertyValue(property));
    }
  });
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  clone.setAttribute("width", String(width));
  clone.setAttribute("height", String(height));
  return { markup: new XMLSerializer().serializeToString(clone), width, height };
}

export async function downloadChartPng(plot: HTMLElement, title: string): Promise<void> {
  const svg = plot.querySelector("svg");
  if (!svg) throw new Error("Chart graphic is unavailable");
  const { markup, width, height } = serializeChartSvg(svg);
  const url = URL.createObjectURL(new Blob([markup], { type: "image/svg+xml;charset=utf-8" }));
  try {
    const image = new Image();
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve();
      image.onerror = () => reject(new Error("Chart graphic could not be loaded"));
      image.src = url;
    });
    const scale = Math.min(window.devicePixelRatio || 1, 2);
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(width * scale);
    canvas.height = Math.round(height * scale);
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Canvas is unavailable");
    context.scale(scale, scale);
    context.drawImage(image, 0, 0, width, height);
    const png = await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("PNG encoding failed"))), "image/png");
    });
    downloadBlob(png, fileName(title, "png"));
  } finally {
    URL.revokeObjectURL(url);
  }
}
