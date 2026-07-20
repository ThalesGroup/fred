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

// pdfWorker
// ---------
// Shared pdf.js worker plumbing for every `react-pdf` `<Document>` in the app
// (currently the ppt_filler preview pane). Two hard constraints shaped this
// (fought before on Kea — port of `common/pdfWorker.ts`):
//
// 1. The worker MUST be a real module `Worker` built from a
//    `new URL(..., import.meta.url)` so Vite bundles it. Setting only
//    `GlobalWorkerOptions.workerSrc` to a string makes pdf.js fall back to a
//    "fake worker" that `import()`s the bare specifier `pdf.worker.mjs`, which
//    fails ("Setting up fake worker failed").
//
// 2. A worker port must NEVER be reused across `<Document>` remounts, and must
//    NOT be terminated by our own cleanup. On unmount react-pdf calls
//    `loadingTask.destroy()`, which marks the port `_pendingDestroy`; a
//    `<Document>` mounting during that window on the same port throws
//    "PDFWorker.fromPort - the worker is being destroyed". Terminating the
//    worker ourselves is worse: React StrictMode's mount→cleanup→remount cycle
//    then leaves `workerPort` pointing at a DEAD worker, and the next Document
//    hangs on its loading state forever.
//
// The fix that satisfies both: hand pdf.js a FRESH module worker per
// `<Document>` via `configurePdfWorkerPort()`, called during render (useMemo)
// keyed to the viewer's remount key, and let react-pdf's own destroy path tear
// each worker down with its Document.

import { pdfjs } from "react-pdf";

// Resolved by Vite to the bundled pdf.js worker asset. Kept as a URL — not a
// `workerSrc` string — on purpose (see constraint 1).
const pdfWorkerUrl = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url);

/**
 * Point pdf.js at a brand-new module worker for the NEXT `<Document>` to mount.
 * Call it just before mounting/remounting a `<Document>` (e.g. in a `useMemo`
 * keyed on the viewer's remount key) so it never shares a port with a sibling
 * or a just-unmounted instance. Falls back to `workerSrc` if `Worker` is
 * missing (SSR/tests), matching pdf.js's own guard.
 */
export function configurePdfWorkerPort(): void {
  if (typeof Worker === "undefined") {
    pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerUrl.toString();
    return;
  }
  pdfjs.GlobalWorkerOptions.workerPort = new Worker(pdfWorkerUrl, { type: "module" });
}
