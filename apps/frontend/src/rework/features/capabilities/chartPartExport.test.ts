// @vitest-environment happy-dom

import { expect, it } from "vitest";
import JSZip from "jszip";
import { chartColumns, chartRowsXlsx, downloadChartPng, serializeChartSvg } from "./chartPartExport";

it("exports original rows as typed Excel cells without executing formula-like text", async () => {
  const rows = [
    { quarter: "Q1", sales: "12.5", note: 'He said "go"\nnow' },
    { quarter: "Q2", sales: null, formula: "=1+1", negative: -4, active: true },
  ];
  expect(chartColumns(rows)).toEqual(["quarter", "sales", "note", "formula", "negative", "active"]);
  const workbook = await JSZip.loadAsync(await (await chartRowsXlsx(rows)).arrayBuffer());
  const parse = (xml: string) => new DOMParser().parseFromString(xml, "application/xml");
  const sheet = parse((await workbook.file("xl/worksheets/sheet1.xml")?.async("string")) ?? "");
  const sharedStrings = parse((await workbook.file("xl/sharedStrings.xml")?.async("string")) ?? "");
  const strings = [...sharedStrings.querySelectorAll("si")].map((cell) => cell.textContent);
  const cell = (reference: string) => sheet.querySelector(`c[r="${reference}"]`);
  const value = (reference: string) => {
    const item = cell(reference);
    const raw = item?.querySelector("v")?.textContent;
    if (raw === undefined || raw === null) return null;
    if (item?.getAttribute("t") === "s") return strings[Number(raw)];
    if (item?.getAttribute("t") === "b") return raw === "1";
    return Number(raw);
  };
  expect(["A1", "B1", "C1", "D1", "E1", "F1"].map(value)).toEqual([
    "quarter",
    "sales",
    "note",
    "formula",
    "negative",
    "active",
  ]);
  expect(["A2", "B2", "C2"].map(value)).toEqual(["Q1", "12.5", 'He said "go"\nnow']);
  expect(["A3", "B3", "D3", "E3", "F3"].map(value)).toEqual(["Q2", null, "=1+1", -4, true]);
  expect(cell("D3")?.getAttribute("t")).toBe("s");
  expect(sheet.querySelector("f")).toBeNull();
});

it("serializes the visible SVG dimensions and theme-resolved styles", () => {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("width", "640");
  svg.setAttribute("height", "320");
  const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
  line.style.stroke = "rgb(12, 34, 56)";
  svg.appendChild(line);
  document.body.appendChild(svg);
  try {
    const result = serializeChartSvg(svg);
    expect(result.width).toBe(640);
    expect(result.height).toBe(320);
    expect(result.markup).toContain('width="640"');
    expect(result.markup).toContain("rgb(12, 34, 56)");
  } finally {
    svg.remove();
  }
});

it("rejects a PNG export when no graphic is present", async () => {
  await expect(downloadChartPng(document.createElement("div"), "Sales")).rejects.toThrow(
    "Chart graphic is unavailable",
  );
});
