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

// PNG and PDF export for an HTML artifact, alongside the plain .html download
// (htmlArtifactDocument.downloadHtmlArtifact). Both rasterize the SAME faithful
// render, so what you get is exactly the preview — background included, and none
// of the browser print chrome (headers/footers/margins).
//
// SECURITY: the render uses `composeHtmlDocument`, already sanitized (Layer A: no
// <script>/on*-handlers) and CSP-locked (Layer C). We lay it out in an off-screen
// iframe (no allow-scripts) purely to size it, then rasterize its serialized DOM
// through an `<svg><foreignObject>` loaded as an <img>. An SVG loaded via <img>
// runs in the browser's "secure static mode": no scripts, and NO external resource
// loads at all — the same "data: only" footprint as the live preview's CSP.

import { composeHtmlDocument, artifactFileName } from "./htmlArtifactDocument";

// Off-screen render width (px) — a desktop-ish canvas so responsive artifacts lay
// out sensibly; the capture then grows to the content's full height.
const PNG_RENDER_WIDTH = 1024;
// A4 portrait width in PostScript points; the image PDF is one page this wide,
// its height set from the render's aspect ratio.
const A4_WIDTH_PT = 595.28;

function triggerDownload(url: string, filename: string): void {
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

/**
 * Render the artifact to a canvas at device resolution. The styles ride along
 * inside the serialized markup, so this needs no computed-style inlining — unlike
 * DOM-snapshot libraries, which read the global window's getComputedStyle and so
 * cannot see an iframe's nodes.
 */
async function renderArtifactToCanvas(html: string, css: string): Promise<HTMLCanvasElement> {
  const composed = composeHtmlDocument(html, css);
  const iframe = document.createElement("iframe");
  iframe.setAttribute("sandbox", "allow-same-origin");
  iframe.setAttribute("referrerpolicy", "no-referrer");
  iframe.style.cssText = `position:fixed;left:-99999px;top:0;width:${PNG_RENDER_WIDTH}px;height:10px;border:0;background:#fff`;
  iframe.srcdoc = composed;
  document.body.appendChild(iframe);
  try {
    await new Promise<void>((resolve, reject) => {
      iframe.addEventListener("load", () => resolve(), { once: true });
      iframe.addEventListener("error", () => reject(new Error("artifact failed to render")), { once: true });
    });
    const doc = iframe.contentDocument;
    if (!doc?.documentElement) throw new Error("artifact document unavailable");
    // Grow the frame to the full content height so nothing is clipped, then measure.
    const width = Math.max(doc.documentElement.scrollWidth, PNG_RENDER_WIDTH);
    iframe.style.height = `${Math.max(doc.documentElement.scrollHeight, 1)}px`;
    const height = Math.max(doc.documentElement.scrollHeight, doc.body?.scrollHeight ?? 0, 1);
    const serialized = new XMLSerializer().serializeToString(doc.documentElement);

    const svg =
      `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}">` +
      `<foreignObject x="0" y="0" width="100%" height="100%">${serialized}</foreignObject>` +
      `</svg>`;
    const svgUrl = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
    try {
      const img = new Image();
      img.width = width;
      img.height = height;
      await new Promise<void>((resolve, reject) => {
        img.onload = () => resolve();
        img.onerror = () => reject(new Error("failed to rasterize the artifact"));
        img.src = svgUrl;
      });
      const scale = window.devicePixelRatio || 1;
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(width * scale);
      canvas.height = Math.round(height * scale);
      const ctx = canvas.getContext("2d");
      if (!ctx) throw new Error("canvas 2D context unavailable");
      ctx.scale(scale, scale);
      // Opaque white base so transparent regions read as a page, not black (JPEG).
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, width, height);
      ctx.drawImage(img, 0, 0);
      return canvas;
    } finally {
      URL.revokeObjectURL(svgUrl);
    }
  } finally {
    iframe.remove();
  }
}

/**
 * Measure the artifact's laid-out content width at a given container width — the
 * `scrollWidth` includes anything overflowing (a fixed-width layout wider than the
 * panel). The live preview is `sandbox=""` (unreadable), so we lay the composed
 * document out in a transient off-screen `allow-same-origin` frame just to measure.
 * The caller turns this into a "fit width" zoom (containerWidth / contentWidth).
 */
export async function measureArtifactWidth(html: string, css: string, containerWidth: number): Promise<number> {
  const composed = composeHtmlDocument(html, css);
  const iframe = document.createElement("iframe");
  iframe.setAttribute("sandbox", "allow-same-origin");
  iframe.setAttribute("referrerpolicy", "no-referrer");
  iframe.style.cssText = `position:fixed;left:-99999px;top:0;width:${containerWidth}px;height:10px;border:0`;
  iframe.srcdoc = composed;
  document.body.appendChild(iframe);
  try {
    await new Promise<void>((resolve, reject) => {
      iframe.addEventListener("load", () => resolve(), { once: true });
      iframe.addEventListener("error", () => reject(new Error("artifact failed to render")), { once: true });
    });
    return iframe.contentDocument?.documentElement.scrollWidth ?? containerWidth;
  } finally {
    iframe.remove();
  }
}

/** Rasterize the artifact and download it as a PNG. */
export async function downloadHtmlArtifactPng(html: string, css: string, title: string): Promise<void> {
  const canvas = await renderArtifactToCanvas(html, css);
  triggerDownload(canvas.toDataURL("image/png"), artifactFileName(title, "png"));
}

function base64ToBytes(base64: string): Uint8Array {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

/**
 * Build a minimal single-page PDF whose only content is `jpeg` scaled to fill an
 * A4-width page (height from the image aspect). Hand-assembled — one image XObject
 * (DCTDecode = raw JPEG bytes, no re-encode) — so no PDF library is needed. Byte
 * offsets are tracked exactly for the xref table.
 */
export function buildImagePdf(jpeg: Uint8Array, imgWidth: number, imgHeight: number): Blob {
  const pageWidth = A4_WIDTH_PT;
  const pageHeight = (A4_WIDTH_PT * imgHeight) / imgWidth;
  const encoder = new TextEncoder();
  const chunks: Uint8Array[] = [];
  let offset = 0;
  const offsets: number[] = [];
  const push = (chunk: Uint8Array | string) => {
    const bytes = typeof chunk === "string" ? encoder.encode(chunk) : chunk;
    chunks.push(bytes);
    offset += bytes.length;
  };
  const startObject = (n: number) => {
    offsets[n] = offset;
    push(`${n} 0 obj\n`);
  };

  push("%PDF-1.3\n");
  startObject(1);
  push("<</Type/Catalog/Pages 2 0 R>>\nendobj\n");
  startObject(2);
  push("<</Type/Pages/Kids[3 0 R]/Count 1>>\nendobj\n");
  startObject(3);
  push(
    `<</Type/Page/Parent 2 0 R/MediaBox[0 0 ${pageWidth.toFixed(2)} ${pageHeight.toFixed(2)}]` +
      `/Resources<</XObject<</Im0 4 0 R>>>>/Contents 5 0 R>>\nendobj\n`,
  );
  startObject(4);
  push(
    `<</Type/XObject/Subtype/Image/Width ${imgWidth}/Height ${imgHeight}` +
      `/ColorSpace/DeviceRGB/BitsPerComponent 8/Filter/DCTDecode/Length ${jpeg.length}>>\nstream\n`,
  );
  push(jpeg);
  push("\nendstream\nendobj\n");
  const content = `q ${pageWidth.toFixed(2)} 0 0 ${pageHeight.toFixed(2)} 0 0 cm /Im0 Do Q`;
  startObject(5);
  push(`<</Length ${content.length}>>\nstream\n${content}\nendstream\nendobj\n`);

  const xrefOffset = offset;
  let xref = `xref\n0 6\n0000000000 65535 f \n`;
  for (let n = 1; n <= 5; n += 1) xref += `${String(offsets[n]).padStart(10, "0")} 00000 n \n`;
  push(xref);
  push(`trailer\n<</Size 6/Root 1 0 R>>\nstartxref\n${xrefOffset}\n%%EOF`);

  return new Blob(chunks as BlobPart[], { type: "application/pdf" });
}

/** Rasterize the artifact and download it as a single-page image PDF. */
export async function downloadHtmlArtifactPdf(html: string, css: string, title: string): Promise<void> {
  const canvas = await renderArtifactToCanvas(html, css);
  const jpeg = base64ToBytes(canvas.toDataURL("image/jpeg", 0.92).split(",")[1]);
  const url = URL.createObjectURL(buildImagePdf(jpeg, canvas.width, canvas.height));
  triggerDownload(url, artifactFileName(title, "pdf"));
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
