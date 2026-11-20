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
  const sheet = await workbook.file("xl/worksheets/sheet1.xml")?.async("string");
  expect(sheet).toContain('<c r="A1" t="inlineStr"><is><t xml:space="preserve">quarter</t></is></c>');
  expect(sheet).toContain('<c r="C2" t="inlineStr"><is><t xml:space="preserve">He said "go"\nnow</t></is></c>');
  expect(sheet).toContain('<c r="D3" t="inlineStr"><is><t xml:space="preserve">=1+1</t></is></c>');
  expect(sheet).toContain('<c r="E3" t="n"><v>-4</v></c>');
  expect(sheet).toContain('<c r="F3" t="b"><v>1</v></c>');
  expect(sheet).not.toContain("<f>");
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
