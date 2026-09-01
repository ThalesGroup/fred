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
// already sanitized (Layer A) and carries a script-blocking CSP (Layer C). No
// author script ever runs. They do drop the live preview's `sandbox=""` frame
// (Layer B) because you cannot print an opaque-origin frame nor read its pixels;
// the two remaining layers keep the export inert. The relaxations are scoped to a
// transient print window / off-screen frame, never the in-app preview.

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

/**
 * Rasterize the artifact to a PNG and download it. The composed document renders
 * in an off-screen iframe kept `sandbox="allow-same-origin"` — WITHOUT
 * allow-scripts, so no author script runs — which is the minimum that lets us read
 * the laid-out DOM to snapshot it. `html-to-image` is imported lazily so the PNG
 * codepath adds nothing to the bundle for users who never export.
 */
export async function downloadHtmlArtifactPng(html: string, css: string, title: string): Promise<void> {
  const composed = composeHtmlDocument(html, css);
  const iframe = document.createElement("iframe");
  iframe.setAttribute("sandbox", "allow-same-origin");
  iframe.setAttribute("referrerpolicy", "no-referrer");
  iframe.style.cssText = `position:fixed;left:-99999px;top:0;width:${PNG_RENDER_WIDTH}px;height:768px;border:0;background:#fff`;
  iframe.srcdoc = composed;
  document.body.appendChild(iframe);
  try {
    await new Promise<void>((resolve, reject) => {
      iframe.addEventListener("load", () => resolve(), { once: true });
      iframe.addEventListener("error", () => reject(new Error("artifact failed to render")), { once: true });
    });
    const doc = iframe.contentDocument;
    if (!doc?.body) throw new Error("artifact document unavailable");
    // Grow the frame to the full content so nothing is clipped in the snapshot.
    const width = Math.max(doc.documentElement.scrollWidth, PNG_RENDER_WIDTH);
    const height = Math.max(doc.documentElement.scrollHeight, doc.body.scrollHeight, 1);
    iframe.style.width = `${width}px`;
    iframe.style.height = `${height}px`;

    const { toPng } = await import("html-to-image");
    const dataUrl = await toPng(doc.body, { width, height, backgroundColor: "#ffffff" });

    const anchor = document.createElement("a");
    anchor.href = dataUrl;
    anchor.download = artifactFileName(title, "png");
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  } finally {
    iframe.remove();
  }
}
