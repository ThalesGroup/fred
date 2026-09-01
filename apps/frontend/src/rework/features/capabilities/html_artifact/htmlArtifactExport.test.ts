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

import { describe, expect, it } from "vitest";
import { buildImagePdf } from "./htmlArtifactExport";

// A latin1 decode keeps a 1:1 byte↔char mapping, so string indices equal the PDF's
// byte offsets — which is what the xref table records.
async function pdfText(jpeg: Uint8Array): Promise<string> {
  const blob = buildImagePdf(jpeg, 800, 600);
  const bytes = new Uint8Array(await blob.arrayBuffer());
  return new TextDecoder("latin1").decode(bytes);
}

describe("buildImagePdf", () => {
  const jpeg = new Uint8Array([0xff, 0xd8, 0xff, 0xd9, 0x00, 0x42]);

  it("wraps the JPEG in a well-formed one-page PDF", async () => {
    const text = await pdfText(jpeg);
    expect(text.startsWith("%PDF-1.3")).toBe(true);
    expect(text.trimEnd().endsWith("%%EOF")).toBe(true);
    // The image stream declares the raw JPEG byte length and DCTDecode filter.
    expect(text).toContain("/Filter/DCTDecode/Length 6");
    expect(text).toContain("/MediaBox[0 0 595.28 446.46]"); // 595.28 * 600/800
  });

  it("records byte offsets that land exactly on each object header", async () => {
    const text = await pdfText(jpeg);

    const startxref = text.match(/startxref\n(\d+)\n%%EOF$/);
    expect(startxref).toBeTruthy();
    const xrefOffset = Number(startxref![1]);
    expect(text.slice(xrefOffset, xrefOffset + 4)).toBe("xref");

    const entries: string[] = text.slice(xrefOffset).match(/\d{10} 00000 n /g) ?? [];
    expect(entries).toHaveLength(5);
    entries.forEach((entry, i) => {
      const offset = Number(entry.slice(0, 10));
      expect(text.slice(offset).startsWith(`${i + 1} 0 obj`)).toBe(true);
    });
  });
});
