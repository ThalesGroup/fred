// Copyright Thales 2025
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

/**
 * pdfWorker
 * ---------
 * Shared pdf.js worker plumbing for every `react-pdf` `<Document>` in the app (the
 * streaming PDF drawer AND the PPT preview pane).
 *
 * Two hard constraints shaped this:
 *
 * 1. The worker MUST be a real module `Worker` built from a `new URL(..., import.meta.url)`
 *    so Vite bundles it. Setting only `GlobalWorkerOptions.workerSrc` to a string makes
 *    pdf.js fall back to a "fake worker" that `import()`s the bare specifier
 *    `pdf.worker.mjs`, which fails ("Setting up fake worker failed").
 *
 * 2. A single shared `workerPort` cannot be REUSED across `<Document>` remounts. On unmount
 *    react-pdf calls `loadingTask.destroy()`, which marks that port `_pendingDestroy` and
 *    evicts it from pdf.js's per-port cache. A `<Document>` mounting during that window
 *    (open a second preview, or re-fill the open deck) calls `PDFWorker.fromPort` on the
 *    same port and throws `PDFWorker.fromPort - the worker is being destroyed`.
 *
 * The fix that satisfies both: hand pdf.js a FRESH module worker per `<Document>` via
 * `configurePdfWorkerPort()`, called right before each mount (keyed to the viewer's remount
 * key). Each Document gets its own port, so no destroy of one can race a mount of another.
 */

import { pdfjs } from "react-pdf";

// Resolved by Vite to the bundled pdf.js worker asset. Used to spawn a fresh module worker
// per document (below). Kept as a URL — not a `workerSrc` string — on purpose (see constraint 1).
const pdfWorkerUrl = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url);

/**
 * Point pdf.js at a brand-new module worker for the NEXT `<Document>` to mount. Call this
 * just before mounting/remounting a `<Document>` so it never shares a port with a sibling
 * or a just-unmounted instance. No-ops (falls back to `workerSrc`) if `Worker` is missing
 * (SSR/tests), matching pdf.js's own guard.
 */
export function configurePdfWorkerPort(): void {
  if (typeof Worker === "undefined") {
    pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerUrl.toString();
    return;
  }
  pdfjs.GlobalWorkerOptions.workerPort = new Worker(pdfWorkerUrl, { type: "module" });
}

// Configure one immediately so a `<Document>` that renders before any explicit call still
// has a worker. Viewers that remount call `configurePdfWorkerPort()` again per mount.
configurePdfWorkerPort();
