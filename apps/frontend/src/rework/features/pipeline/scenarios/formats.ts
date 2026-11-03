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
// One tiny document per format the default ingestion profile processes, each
// carrying its own marker. Office files are the smallest packages their
// readers accept; the PDF is written by hand with a computed cross-reference.
import JSZip from "jszip";

export type FormatId = "txt" | "md" | "jsonl" | "pdf" | "docx" | "pptx";

export interface FormatFixture {
  id: FormatId;
  marker: string;
  build: (name: string) => Promise<File>;
}

const xml = (body: string) => `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>${body}`;
const PKG_RELS = "http://schemas.openxmlformats.org/package/2006/relationships";
const OFFICE_DOC = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument";
const REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";

function sentence(marker: string): string {
  return `The self-test format marker is ${marker}.`;
}

async function zipFile(name: string, type: string, parts: Record<string, string>): Promise<File> {
  const zip = new JSZip();
  for (const [path, content] of Object.entries(parts)) zip.file(path, content);
  return new File([await zip.generateAsync({ type: "arraybuffer" })], name, { type });
}

function contentTypes(overrides: Record<string, string>): string {
  const items = Object.entries(overrides)
    .map(([part, type]) => `<Override PartName="${part}" ContentType="${type}"/>`)
    .join("");
  return xml(
    `<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">` +
      `<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>` +
      `<Default Extension="xml" ContentType="application/xml"/>${items}</Types>`,
  );
}

function rels(entries: Array<[string, string, string]>): string {
  const items = entries
    .map(([id, type, target]) => `<Relationship Id="${id}" Type="${type}" Target="${target}"/>`)
    .join("");
  return xml(`<Relationships xmlns="${PKG_RELS}">${items}</Relationships>`);
}

/** A one-page PDF whose only text is the sentence; ASCII only, so no escaping is needed. */
export function pdfBytes(text: string): Uint8Array<ArrayBuffer> {
  const stream = `BT /F1 12 Tf 72 720 Td (${text}) Tj ET`;
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
  ];
  let out = "%PDF-1.4\n";
  const offsets: number[] = [];
  objects.forEach((body, i) => {
    offsets.push(out.length);
    out += `${i + 1} 0 obj\n${body}\nendobj\n`;
  });
  const xref = out.length;
  out += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  out += offsets.map((o) => `${String(o).padStart(10, "0")} 00000 n \n`).join("");
  out += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return new TextEncoder().encode(out);
}

const WORD = "application/vnd.openxmlformats-officedocument.wordprocessingml";
const SHEET = "application/vnd.openxmlformats-officedocument.spreadsheetml";
const SLIDES = "application/vnd.openxmlformats-officedocument.presentationml";
const W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main";
const S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
const P = "http://schemas.openxmlformats.org/presentationml/2006/main";
const A = "http://schemas.openxmlformats.org/drawingml/2006/main";

function docx(name: string, text: string): Promise<File> {
  return zipFile(name, `${WORD}.document`, {
    "[Content_Types].xml": contentTypes({ "/word/document.xml": `${WORD}.document.main+xml` }),
    "_rels/.rels": rels([["rId1", OFFICE_DOC, "word/document.xml"]]),
    "word/document.xml": xml(
      `<w:document xmlns:w="${W}"><w:body><w:p><w:r><w:t>${text}</w:t></w:r></w:p></w:body></w:document>`,
    ),
  });
}

/** One sheet: a header row, then rows of a number and a text, so SQL can filter on the number. */
function xlsx(name: string, header: [string, string], rows: Array<[number, string]>): Promise<File> {
  const text = (ref: string, value: string) => `<c r="${ref}" t="inlineStr"><is><t>${value}</t></is></c>`;
  const cells = [
    `<row r="1">${text("A1", header[0])}${text("B1", header[1])}</row>`,
    ...rows.map(
      ([code, label], i) => `<row r="${i + 2}"><c r="A${i + 2}"><v>${code}</v></c>${text(`B${i + 2}`, label)}</row>`,
    ),
  ];
  return zipFile(name, `${SHEET}.sheet`, {
    "[Content_Types].xml": contentTypes({
      "/xl/workbook.xml": `${SHEET}.sheet.main+xml`,
      "/xl/worksheets/sheet1.xml": `${SHEET}.worksheet+xml`,
    }),
    "_rels/.rels": rels([["rId1", OFFICE_DOC, "xl/workbook.xml"]]),
    "xl/workbook.xml": xml(
      `<workbook xmlns="${S}" xmlns:r="${REL}"><sheets><sheet name="Marker" sheetId="1" r:id="rId1"/></sheets></workbook>`,
    ),
    "xl/_rels/workbook.xml.rels": rels([["rId1", `${REL}/worksheet`, "worksheets/sheet1.xml"]]),
    "xl/worksheets/sheet1.xml": xml(`<worksheet xmlns="${S}"><sheetData>${cells.join("")}</sheetData></worksheet>`),
  });
}

function pptx(name: string, text: string): Promise<File> {
  const tree = (shapes: string) =>
    `<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>${shapes}</p:spTree></p:cSld>`;
  const ns = `xmlns:a="${A}" xmlns:r="${REL}" xmlns:p="${P}"`;
  const textBox =
    `<p:sp><p:nvSpPr><p:cNvPr id="2" name="Text"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>` +
    `<p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="6000000" cy="1000000"/></a:xfrm></p:spPr>` +
    `<p:txBody><a:bodyPr/><a:p><a:r><a:t>${text}</a:t></a:r></a:p></p:txBody></p:sp>`;
  return zipFile(name, `${SLIDES}.presentation`, {
    "[Content_Types].xml": contentTypes({
      "/ppt/presentation.xml": `${SLIDES}.presentation.main+xml`,
      "/ppt/slideMasters/slideMaster1.xml": `${SLIDES}.slideMaster+xml`,
      "/ppt/slideLayouts/slideLayout1.xml": `${SLIDES}.slideLayout+xml`,
      "/ppt/slides/slide1.xml": `${SLIDES}.slide+xml`,
      "/ppt/theme/theme1.xml": "application/vnd.openxmlformats-officedocument.theme+xml",
    }),
    "_rels/.rels": rels([["rId1", OFFICE_DOC, "ppt/presentation.xml"]]),
    "ppt/presentation.xml": xml(
      `<p:presentation ${ns}><p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>` +
        `<p:sldIdLst><p:sldId id="256" r:id="rId2"/></p:sldIdLst><p:sldSz cx="9144000" cy="6858000"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>`,
    ),
    "ppt/_rels/presentation.xml.rels": rels([
      ["rId1", `${REL}/slideMaster`, "slideMasters/slideMaster1.xml"],
      ["rId2", `${REL}/slide`, "slides/slide1.xml"],
      ["rId3", `${REL}/theme`, "theme/theme1.xml"],
    ]),
    "ppt/slideMasters/slideMaster1.xml": xml(
      `<p:sldMaster ${ns}>${tree("")}<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>` +
        `<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst></p:sldMaster>`,
    ),
    "ppt/slideMasters/_rels/slideMaster1.xml.rels": rels([
      ["rId1", `${REL}/slideLayout`, "../slideLayouts/slideLayout1.xml"],
      ["rId2", `${REL}/theme`, "../theme/theme1.xml"],
    ]),
    "ppt/slideLayouts/slideLayout1.xml": xml(`<p:sldLayout ${ns}>${tree("")}</p:sldLayout>`),
    "ppt/slideLayouts/_rels/slideLayout1.xml.rels": rels([
      ["rId1", `${REL}/slideMaster`, "../slideMasters/slideMaster1.xml"],
    ]),
    "ppt/slides/slide1.xml": xml(`<p:sld ${ns}>${tree(textBox)}</p:sld>`),
    "ppt/slides/_rels/slide1.xml.rels": rels([["rId1", `${REL}/slideLayout`, "../slideLayouts/slideLayout1.xml"]]),
    "ppt/theme/theme1.xml": xml(
      `<a:theme xmlns:a="${A}" name="Self-test"><a:themeElements>` +
        `<a:clrScheme name="Self-test">${[
          "dk1",
          "lt1",
          "dk2",
          "lt2",
          "accent1",
          "accent2",
          "accent3",
          "accent4",
          "accent5",
          "accent6",
          "hlink",
          "folHlink",
        ]
          .map((c) => `<a:${c}><a:srgbClr val="000000"/></a:${c}>`)
          .join("")}</a:clrScheme>` +
        `<a:fontScheme name="Self-test"><a:majorFont><a:latin typeface="Arial"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>` +
        `<a:minorFont><a:latin typeface="Arial"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont></a:fontScheme>` +
        `<a:fmtScheme name="Self-test"><a:fillStyleLst/><a:lnStyleLst/><a:effectStyleLst/><a:bgFillStyleLst/></a:fmtScheme>` +
        `</a:themeElements></a:theme>`,
    ),
  });
}

/** The fixtures of one run: each marker is suffixed with the run token. */
export function formatFixtures(token: string): FormatFixture[] {
  const marker = (id: FormatId) => `Selftestformat${id}${token}`;
  const plain = (id: FormatId, type: string, body: (text: string) => string): FormatFixture => ({
    id,
    marker: marker(id),
    build: async (name) => new File([body(sentence(marker(id)))], name, { type }),
  });
  return [
    plain("txt", "text/plain", (t) => `${t}\n`),
    plain("md", "text/markdown", (t) => `# Self-test format fixture\n\n${t}\n`),
    plain(
      "jsonl",
      "application/jsonl",
      (t) => `${JSON.stringify({ title: "Self-test format fixture", content: t })}\n`,
    ),
    {
      id: "pdf",
      marker: marker("pdf"),
      build: async (name) => new File([pdfBytes(sentence(marker("pdf")))], name, { type: "application/pdf" }),
    },
    { id: "docx", marker: marker("docx"), build: (name) => docx(name, sentence(marker("docx"))) },
    { id: "pptx", marker: marker("pptx"), build: (name) => pptx(name, sentence(marker("pptx"))) },
  ];
}

export interface TabularFixture {
  id: "csv" | "xlsx";
  marker: string;
  build: () => Promise<File>;
}

/** Spreadsheets and CSVs go to SQL storage, never to the search index: each has a row carrying its marker. */
export function tabularFixtures(token: string): TabularFixture[] {
  const marker = (id: TabularFixture["id"]) => `Selftest${id}${token}`;
  return [
    {
      id: "csv",
      marker: marker("csv"),
      build: async () =>
        new File([`code,label\n1,${marker("csv")}\n2,plain\n`], `fred-selftest-${token}.csv`, { type: "text/csv" }),
    },
    {
      id: "xlsx",
      marker: marker("xlsx"),
      build: () =>
        xlsx(
          `fred-selftest-${token}.xlsx`,
          ["code", "label"],
          [
            [1, marker("xlsx")],
            [2, "plain"],
          ],
        ),
    },
  ];
}
