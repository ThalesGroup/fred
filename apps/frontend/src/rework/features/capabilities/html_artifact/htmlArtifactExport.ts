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

// PDF and PNG export for an HTML artifact, alongside the plain .html download
// (htmlArtifactDocument.downloadHtmlArtifact).
//
// SECURITY: both paths render the SAME `composeHtmlDocument` output, which is
// already sanitized (Layer A: no <script>/on*-handlers) and carries a
// script-blocking CSP (Layer C). No author script runs.
//  - PDF opens the composed doc in a print window: relies on Layers A + C (you
//    cannot print an opaque-origin sandboxed frame).
//  - PNG serializes an off-screen render and rasterizes it through an
//    `<svg><foreignObject>` loaded as an <img>. An SVG loaded via <img> runs in
//    the browser's "secure static mode": no scripts, and NO external resource
//    loads at all — the same "data: only" footprint as the live preview's CSP.

import { composeHtmlDocument, artifactFileName } from "./htmlArtifactDocument";

/**
 * "Save as PDF" via the browser's print dialog: open the composed document in a
 * new tab and trigger print once it has rendered. Real, selectable text (no
 * rasterization). Returns false if the popup was blocked.
 */
export function printHtmlArtifact(html: string, css: string): boolean {
  const composed = composeHtmlDocument(html, css);
  const blob = new Blob([composed], { type: "text/html" });
  const url = URL.createObjectURL(blob);
  // Not `noopener`: we need the handle to call print(). Safe because the document
  // runs no scripts (sanitized + CSP), so it can't reach back through window.opener.
  const win = window.open(url, "_blank");
  if (!win) {
    URL.revokeObjectURL(url);
    return false;
  }
  win.addEventListener("load", () => {
    win.focus();
    win.print();
  });
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
  return true;
}

// Off-screen render width (px) — a desktop-ish canvas so responsive artifacts lay
// out sensibly; the capture then grows to the content's full height.
const PNG_RENDER_WIDTH = 1024;

function triggerDownload(dataUrl: string, filename: string): void {
  const anchor = document.createElement("a");
  anchor.href = dataUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

// Render the (already-styled) serialized document through an SVG foreignObject and
// draw it to a canvas. The styles ride along inside the serialized markup, so this
// needs no computed-style inlining — unlike DOM-snapshot libraries, which read the
// global window's getComputedStyle and therefore cannot see an iframe's nodes.
async function rasterizeToPng(xhtml: string, width: number, height: number): Promise<string> {
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}">` +
    `<foreignObject x="0" y="0" width="100%" height="100%">${xhtml}</foreignObject>` +
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
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, width, height);
    ctx.drawImage(img, 0, 0);
    return canvas.toDataURL("image/png");
  } finally {
    URL.revokeObjectURL(svgUrl);
  }
}

/**
 * Rasterize the artifact to a PNG and download it. The composed document renders
 * in an off-screen iframe (`sandbox="allow-same-origin"`, no allow-scripts) purely
 * to lay it out and read its size; we then serialize that rendered DOM — styles
 * included — and paint it via `rasterizeToPng`.
 */
export async function downloadHtmlArtifactPng(html: string, css: string, title: string): Promise<void> {
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
    const dataUrl = await rasterizeToPng(serialized, width, height);
    triggerDownload(dataUrl, artifactFileName(title, "png"));
  } finally {
    iframe.remove();
  }
}
