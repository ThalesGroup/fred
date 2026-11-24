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

export async function chartRowsXlsx(rows: Row[]): Promise<Blob> {
  const { default: writeExcelFile } = await import("write-excel-file/universal");
  const columns = chartColumns(rows);
  const sheetRows = [columns, ...rows.map((row) => columns.map((column) => row[column] ?? null))];
  return writeExcelFile(sheetRows, { sheet: "Chart data" }).toBlob();
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
